#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

"""
Communicate status and artifacts back to the parent rBuilder.
"""

import logging
import Queue
import restlib.client
import threading
import time
try:
    from xml.etree import ElementTree as ET
except ImportError:
    from elementtree import ElementTree as ET

# NB: Don't use a normal logger anywhere inside the log sending process,
# otherwise you'll end up recursing endlessly. ResponseProxy.log is configured
# specifically not to send data upstream.


class ResponseProxy(object):
    def __init__(self, jobData):
        self.rbuilderUrl = jobData['rbuilderUrl']
        self.imageBase = '%s/api/products/%s/images/%s' % (self.rbuilderUrl,
                jobData['project']['hostname'], str(jobData['buildId']))
        self.outputToken = jobData['outputToken']
        self.log = logging.getLogger(__name__ + '.proxy')
        self.log.__class__ = NonSendingLogger

    def _post(self, method, path, contentType='application/xml', body=None):
        headers = {
                'Content-Type': contentType,
                'X-rBuilder-OutputToken': self.outputToken,
                }
        url = self.imageBase + '/' + path

        client = restlib.client.Client(url, headers)
        client.connect()
        return client.request(method, body)

    def sendStatus(self, code, message):
        root = ET.Element('imageStatus')
        ET.SubElement(root, "code").text = str(code)
        ET.SubElement(root, "message").text = message
        try:
            self._post('PUT', 'status', body=ET.tostring(root))
        except:
            self.log.exception("Failed to send status upstream")

    def sendLog(self, data):
        try:
            self._post('POST', 'buildLog', contentType='text/plain', body=data)
        except restlib.client.ResponseError, err:
            if err.status != 204: # No Content
                raise

    def postOutput(self, fileList):
        print 'would send %d files' % len(fileList)


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
            try:
                self.response.sendLog(''.join(items))
            except:
                self.response.log.exception("Error sending build log:")

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
