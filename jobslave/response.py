#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

"""
Communicate status and artifacts back to the parent rBuilder.
"""

import logging
import restlib.client
import sys
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

    def _post(self, method, path, headers=None, body=None):
        finalHeaders = {
                'Content-Type': 'application/xml',
                'X-rBuilder-OutputToken': self.outputToken,
                }
        if headers:
            finalHeaders.update(headers)
        url = self.imageBase + '/' + path

        client = restlib.client.Client(url, finalHeaders)
        client.connect()
        response = client.request(method, body)

    def sendStatus(self, code, message):
        self.log.debug("Sending status: %d %s", code, message)
        root = ET.Element('imageStatus')
        ET.SubElement(root, "code").text = str(code)
        ET.SubElement(root, "message").text = message
        try:
            self._post('PUT', 'status', body=ET.tostring(root))
        except:
            self.log.exception("Failed to send status upstream")

    def sendLog(self, data):
        self.log.info("Would send %d bytes of log data", len(data))

    def postOutput(self, fileList):
        print 'would send %d files' % len(fileList)


class LogHandler(logging.Handler):
    """
    Log handler that periodically sends records upstream to the parent
    rBuilder.
    """
    maxSize = 4096
    maxWait = 4

    def __init__(self, response):
        logging.Handler.__init__(self)
        self.response = response
        self.buffer = ''
        self.lastSent = 0

    def close(self):
        logging.Handler.close(self)
        self.flush()

    def emit(self, record):
        if getattr(record, 'dontSend', False):
            return
        self.buffer += self.format(record) + '\n'
        if (len(self.buffer) > self.maxSize
                or time.time() - self.lastSent > self.maxWait):
            self.flush()

    def flush(self):
        self.acquire()
        buffer, self.buffer = self.buffer, ''
        self.lastSent = time.time()
        self.release()

        if buffer:
            try:
                self.response.sendLog(buffer)
            except:
                self.response.log.exception("Error sending build log:")


class NonSendingLogger(logging.Logger):
    """
    Logger whose emitted messages will not be relayed upstream.
    """
    def makeRecord(self, *args, **kwargs):
        record = logging.Logger.makeRecord(self, *args, **kwargs)
        record.dontSend = True
        return record
