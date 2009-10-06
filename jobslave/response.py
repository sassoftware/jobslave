#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

import logging
import sys
import threading
import time


class ResponseProxy(object):
    def __init__(self):
        pass

    def sendStatus(self, code, message):
        print 'would send status', code, message

    def sendLog(self, data):
        print 'would send log %r' % data

    def postOutput(self, fileList):
        print 'would send %d files' % len(fileList)


class LogHandler(logging.Handler):
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
                print >> sys.stderr, "Error sending build log:"
                traceback.print_exc()
                sys.stderr.flush()
