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
import time

import jobslave_helper
from jobslave import buildtypes
from jobslave import slave

from jobslave import jobhandler
from jobslave import jobslave_error

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


if __name__ == "__main__":
    testsuite.main()
