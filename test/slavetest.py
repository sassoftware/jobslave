#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import os
import simplejson
import sha
import StringIO
import tempfile
import time
import xmlrpclib

import jobslave_helper
from jobslave import buildtypes
from jobslave import slave

from jobslave import jobhandler
from jobslave import jobslave_error

from conary.lib import util
import conary.repository.transport

class DummyHandler(object):
    def __init__(x, *args, **kwargs):
        x.running = False

    def start(x, *args, **kwargs):
        x.running = True

    def isAlive(x, *args, **kwargs):
        return x.running

    def kill(x, *args, **kwargs):
        x.running = False

class DummyQueue(object):
    def disconnect(self):
        pass

class SlaveTest(jobslave_helper.JobSlaveHelper):
    def testEmptyControlTopic(self):
        self.jobSlave.controlTopic.connection.insertMessage('')
        self.jobSlave.checkControlTopic()
        self.failIf(self.jobSlave.controlTopic.inbound != [],
                    "Control topic was not read")

    def testStopJob(self):
        jobId = 'test.rpath.local-build-29'
        self.jobSlave.jobHandler = DummyHandler()
        self.jobSlave.jobHandler.jobId = jobId
        self.jobSlave.handleStopJob(jobId)
        self.failIf(self.jobSlave.jobHandler.running,
            "Job was not killed on command")

    def testJSRun(self):
        disconnect = self.jobSlave.disconnect
        _exit = os._exit
        def MockExit(exitCode):
            raise SystemExit(exitCode)
        try:
            os._exit = MockExit
            self.jobSlave.disconnect = lambda *args, **kwargs: None
            self.assertRaises(SystemExit, self.jobSlave.run)
        finally:
            self.jobSlave.disconnect = disconnect
            os._exit = _exit

    def testInitialStatus(self):
        savedTime = time.time
        try:
            time.time = lambda: 300
            self.jobSlave.heartbeat()
            self.failIf(self.jobSlave.lastHeartbeat != 300,
                    "heartbeat timestamp was not recorded")
        finally:
            time.time = savedTime

    def testProtocols(self):
        @slave.protocols(1)
        def testFunction(*args, **kwargs):
            return 5

        self.assertRaises(jobslave_error.ProtocolError, testFunction, self)
        self.assertRaises(jobslave_error.ProtocolError, testFunction, self,
                protocolVersion = 2)
        self.failIf(testFunction(self, protocolVersion = 1) != 5,
                "Unexpected return value")

    def testGetBestProtocol(self):
        self.failIf(self.jobSlave.getBestProtocol((1,)) != 1,
                "Expected common protocol version of 1")

    def testSendJobStatus(self):
        class DummyHandler(object):
            def __init__(x):
                x.sentStatus = False
            def status(x):
                x.sentStatus = True
        self.jobSlave.jobHandler = DummyHandler()
        self.jobSlave.sendJobStatus()
        self.failIf(not self.jobSlave.jobHandler.sentStatus,
                "Expected status to be sent")

    def testChunkedPutFileDigest(self):
        tmpDir = tempfile.mkdtemp()
        class Response(object):
            status = ''
            reason = ''

        class FakeOpener(object):
            __init__ = lambda *args, **kwargs: None
            createConnection = lambda x, *args, **kwargs: [x, '', [], []]
            connect = lambda *args, **kwargs: None
            close = lambda *args, **kwargs: None
            putrequest = lambda *args, **kwargs: None
            putheader = lambda *args, **kwargs: None
            endheaders = lambda *args, **kwargs: None
            send = lambda *args, **kwargs: None
            getresponse = lambda *args, **kwargs: Response()

        XMLOpener = slave.XMLOpener
        try:
            slave.XMLOpener = FakeOpener
            buf = 'test sha1 code in httpPutFile'
            size = len(buf)
            inFile = StringIO.StringIO(buf)
            sha1 = sha.new()
            origDigest = sha1.hexdigest()
            url = 'http://localhost'
            slave.httpPutFile(url, inFile, size, chunked = True, digest = sha1)
            postDigest = sha1.hexdigest()
            self.assertNotEquals(origDigest, postDigest)
            sha1 = sha.new()
            sha1.update(buf)
            self.assertEquals(postDigest, sha1.hexdigest())
        finally:
            slave.XMLOpener = XMLOpener
            util.rmtree(tmpDir)

    def testPutFileDigest(self):
        tmpDir = tempfile.mkdtemp()
        class Response(object):
            status = ''
            reason = ''

        class FakeOpener(object):
            __init__ = lambda *args, **kwargs: None
            createConnection = lambda x, *args, **kwargs: [x, '', [], []]
            connect = lambda *args, **kwargs: None
            close = lambda *args, **kwargs: None
            putrequest = lambda *args, **kwargs: None
            putheader = lambda *args, **kwargs: None
            endheaders = lambda *args, **kwargs: None
            send = lambda *args, **kwargs: None
            getresponse = lambda *args, **kwargs: Response()

        XMLOpener = slave.XMLOpener
        try:
            slave.XMLOpener = FakeOpener
            buf = 'test sha1 code in httpPutFile'
            size = len(buf)
            inFile = StringIO.StringIO(buf)
            sha1 = sha.new()
            origDigest = sha1.hexdigest()
            url = 'http://localhost'
            slave.httpPutFile(url, inFile, size, digest = sha1)
            postDigest = sha1.hexdigest()
            #self.assertNotEquals(origDigest, postDigest)
            sha1 = sha.new()
            sha1.update(buf)
            self.assertEquals(postDigest, sha1.hexdigest())
        finally:
            slave.XMLOpener = XMLOpener
            util.rmtree(tmpDir)

    def testPostJobOutputDigest(self):
        # Validate that postJobOutput handles sha digests properly, assuming
        # that copyfileObj does as well
        self.buildFilenames = []
        class FakeProxy(object):
            def setBuildFilenamesSafe(x, buildId, outputToken, filenames):
                self.buildFilenames.append(filenames)
                return (False, '')
        def fakePutFile(url, inFile, size, rateLimit = None, proxies = None,
                chunked=False, extraHeaders = [], digest = None):
            digest.update(inFile.read())
        jobId = 'test.rpath.local-build-1'
        buildId = 1
        destUrl = 'http://localhost/test'
        outputToken = 'token'
        testDir = tempfile.mkdtemp()
        httpPutFile = slave.httpPutFile
        buf = 'test of sha1 computation'
        ServerProxy = xmlrpclib.ServerProxy
        try:
            xmlrpclib.ServerProxy = lambda *args, **kwargs: FakeProxy()
            slave.httpPutFile = fakePutFile
            srcFile = os.path.join(testDir, 'srcFile')
            self.touch(srcFile, contents = buf)
            files = [[srcFile, 'test trash']]
            slave.JobSlave.postJobOutput(self.jobSlave, jobId, buildId,
                destUrl, outputToken, files)

            fLen, hash = self.buildFilenames[0][0][2:]
            self.assertEquals(fLen, len(buf))
            sha1 = sha.new()
            sha1.update(buf)
            self.assertEquals(hash, sha1.hexdigest())
        finally:
            xmlrpclib.ServerProxy = ServerProxy
            slave.httpPutFile = httpPutFile
            util.rmtree(testDir)


if __name__ == "__main__":
    testsuite.main()
