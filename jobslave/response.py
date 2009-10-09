#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

"""
Communicate status and artifacts back to the parent rBuilder.
"""

import logging
import os
import Queue
import restlib.client
import threading
import time
from conary.lib import digestlib
from conary.lib import util
try:
    from xml.etree import ElementTree as ET
except ImportError:
    from elementtree import ElementTree as ET

log = logging.getLogger(__name__)


class ResponseProxy(object):
    def __init__(self, masterUrl, jobData):
        self.imageBase = '%sapi/products/%s/images/%d/' % (masterUrl,
                jobData['project']['hostname'], jobData['buildId'])
        self.uploadBase = '%suploadBuild/%d/' % (masterUrl, jobData['buildId'])
        self.outputToken = jobData['outputToken']

        # Create a logger for things that are inside the log sending path, so
        # we can log to console without causing an infinite loop.
        self.log = logging.getLogger(__name__ + '.proxy')
        self.log.__class__ = NonSendingLogger

    def _post(self, method, path, contentType='application/xml', body=None):
        headers = {
                'Content-Type': contentType,
                'X-rBuilder-OutputToken': self.outputToken,
                }
        url = self.imageBase + path

        client = restlib.client.Client(url, headers)
        client.connect()
        return client.request(method, body)

    def _postFile(self, method, targetName, filePath, digest):
        headers = {
                'Content-Type': 'application/octet-stream',
                'X-rBuilder-OutputToken': self.outputToken,
                }
        url = self.uploadBase + targetName

        client = FilePutter(url, headers)
        client.connect()
        return client.putFile(method, filePath, digest)

    def sendStatus(self, code, message):
        root = ET.Element('imageStatus')
        ET.SubElement(root, "code").text = str(code)
        ET.SubElement(root, "message").text = message
        try:
            self._post('PUT', 'status', body=ET.tostring(root))
        except:
            log.exception("Failed to send status upstream")

    def sendLog(self, data):
        try:
            try:
                self._post('POST', 'buildLog', contentType='text/plain', body=data)
            except restlib.client.ResponseError, err:
                if err.status != 204: # No Content
                    raise
        except:
            self.log.exception("Error sending build log:")

    def postOutput(self, fileList):
        filenames = []
        for n, (filePath, description) in enumerate(fileList):
            fileName = os.path.basename(filePath)
            fileSize = os.stat(filePath).st_size
            log.info("Uploading %d of %d: %s (%d bytes)",
                    n + 1, len(fileList), fileName, fileSize)

            digest = digestlib.sha1()
            self._postFile('PUT', fileName, filePath, digest)
            digest = digest.hexdigest()

            log.info(" %s uploaded, SHA-1 digest is %s", fileName, digest)
            filenames.append((fileName, description, fileSize, digest))

        # TODO: rpc bits


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


class FilePutter(restlib.client.Client):
    def putFile(self, method, filePath, digest=None):
        fObj = open(filePath, 'rb')
        fileSize = os.fstat(fObj.fileno()).st_size

        headers = self.headers.copy()
        headers['Content-Length'] = str(fileSize)

        conn = self._connection
        conn.request(method, self.path, headers=headers)
        util.copyfileobj(fObj, conn, sizeLimit=fileSize, digest=digest)

        resp = conn.getresponse()
        if resp.status != 200:
            raise restlib.client.ResponseError(resp.status, resp.reason,
                    resp.msg, resp)
        return resp
