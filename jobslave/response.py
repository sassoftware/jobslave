#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved.
#

"""
Communicate status and artifacts back to the parent rBuilder.
"""

import logging
import os
import Queue
import threading
import time
from conary.lib import digestlib
from conary.lib.http import http_error
from conary.lib.http import opener
from xml.etree import ElementTree as ET
from jobslave import jobstatus

log = logging.getLogger(__name__)


class ResponseProxy(object):
    def __init__(self, masterUrl, jobData):
        self.imageBase = '%sapi/v1/images/%d' % (masterUrl, jobData['buildId'])
        self.uploadBase = '%suploadBuild/%d/' % (masterUrl, jobData['buildId'])
        self.outputToken = jobData['outputToken']
        self.opener = opener.URLOpener(connectAttempts=2)

        # Create a logger for things that are inside the log sending path, so
        # we can log to console without causing an infinite loop.
        self.log = logging.getLogger(__name__ + '.proxy')
        self.log.__class__ = NonSendingLogger

    def post(self, method, path, contentType='application/xml', body=None):
        headers = {
                'Content-Type': contentType,
                'X-rBuilder-OutputToken': self.outputToken,
                }
        if path is None:
            url = self.imageBase
        else:
            url = "%s/%s" % (self.imageBase.rstrip('/'), path)
        return self.opener.open(url, data=body, method=method, headers=headers)

    def postFileObject(self, method, targetName, fobj, size):
        headers = {
                'Content-Type': 'application/octet-stream',
                'X-rBuilder-OutputToken': self.outputToken,
                }
        url = self.uploadBase + targetName
        req = self.opener.newRequest(url, method=method, headers=headers)
        body = DigestingReader(fobj)
        req.setData(body, size=size)
        self.opener.open(req)
        return body.hexdigest()

    def postFile(self, method, targetName, filePath):
        fobj = open(filePath, 'rb')
        size = os.fstat(fobj.fileno()).st_size
        return self.postFileObject(method, targetName, fobj, size)

    def sendStatus(self, code, message):
        root = ET.Element('image')
        ET.SubElement(root, "status").text = str(code)
        ET.SubElement(root, "status_message").text = message
        try:
            self.post('PUT', path=None, body=ET.tostring(root))
        except:
            if code >= jobstatus.FINISHED:
                # Don't eat errors from sending a final status.
                raise
            log.exception("Failed to send status upstream")

    def sendLog(self, data):
        try:
            try:
                self.post('POST', 'build_log', contentType='text/plain', body=data)
            except http_error.ResponseError, err:
                if err.errcode != 204: # No Content
                    raise
        except:
            self.log.exception("Error sending build log:")

    def postOutput(self, fileList, withMetadata=True, attributes=None):
        root = ET.Element('files')
        for n, (filePath, description) in enumerate(fileList):
            # unicodify file names, dropping any invalid bytes
            fileName = os.path.basename(filePath).decode('utf8', 'ignore')

            fileSize = os.stat(filePath).st_size
            log.info("Uploading %d of %d: %s (%d bytes)",
                    n + 1, len(fileList), fileName, fileSize)

            digest = self.postFile('PUT', fileName, filePath)
            log.info(" %s uploaded, SHA-1 digest is %s", fileName, digest)

            file = ET.SubElement(root, 'file')
            ET.SubElement(file, 'title').text = description
            ET.SubElement(file, 'size').text = str(fileSize)
            ET.SubElement(file, 'sha1').text = digest
            ET.SubElement(file, 'file_name').text = fileName
        attr = ET.SubElement(root, 'attributes')
        if attributes:
            for key, value in attributes.iteritems():
                ET.SubElement(attr, key).text = str(value)

        if withMetadata:
            self.post('PUT', 'build_files', body=ET.tostring(root))


class LogHandler(threading.Thread, logging.Handler):
    """
    Log handler that periodically sends records upstream to the parent
    rBuilder. All sending is done from a separate thread to avoid blocking the
    caller.
    """
    maxSize = 4096
    maxWait = 4

    def __init__(self, response):
        threading.Thread.__init__(self)
        logging.Handler.__init__(self)
        self.response = response
        self.buffer = Queue.Queue()
        self.started = self.stopped = False
        self.daemon = True

    def close(self):
        self.acquire()
        started = self.started
        self.stopped = True
        self.release()

        if started:
            self.join()

        logging.Handler.close(self)

    def emit(self, record):
        if getattr(record, 'dontSend', False):
            return
        self.buffer.put(self.format(record) + '\n')

    def run(self):
        self.acquire()
        self.started = True
        self.release()

        while True:
            # Check if we're stopped first, but exit only after emptying the
            # queue.
            self.acquire()
            stopped = self.stopped
            self.release()

            # Collect as many items as possible in 1 second.
            start = time.time()
            items = []
            while time.time() - start < 1.0:
                try:
                    items.append(self.buffer.get(True, 0.1))
                except Queue.Empty:
                    continue

            # Send all collected items upstream
            if items:
                self.response.sendLog(''.join(items))

            if stopped:
                return


class NonSendingLogger(logging.Logger):
    """
    Logger whose emitted messages will not be relayed upstream.
    """
    def makeRecord(self, *args, **kwargs):
        record = logging.Logger.makeRecord(self, *args, **kwargs)
        record.dontSend = True
        return record


class DigestingReader(object):

    def __init__(self, fobj):
        self.fobj = fobj
        self.digest = digestlib.sha1()

    def read(self, numbytes=None):
        d = self.fobj.read(numbytes)
        self.digest.update(d)
        return d

    def seek(self, where):
        # This allows the conary http client to rewind the body file, and
        # resets the digest along with it.
        assert where == 0
        self.digest = digestlib.sha1()
        self.fobj.seek(0)

    def hexdigest(self):
        return self.digest.hexdigest()
