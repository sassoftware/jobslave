#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import simplejson

import jobslave_helper
from jobslave import buildtypes
from jobslave import slave

from jobslave import jobhandler

class DummyHandler(object):
    def start(*args, **kwargs):
        pass

    def isAlive(*args, **kwargs):
        return False

    def kill(*args, **kwargs):
        pass

class DummyQueue(object):
    def disconnect(self):
        pass

class SlaveTest(jobslave_helper.JobSlaveHelper):
    def testEmptyControlTopic(self):
        self.jobSlave.controlTopic.connection.insertMessage('')
        self.jobSlave.checkControlTopic()
        self.failIf(self.jobSlave.controlTopic.inbound != [],
                    "Control topic was not read")

    def testEmptyJobQueue(self):
        self.jobSlave.checkJobQueue()

    def testJCSubscribe(self):
        assert self.jobSlave.jobControlQueue is None

        getHandler = jobhandler.getHandler
        try:
            jobhandler.getHandler = lambda *args, **kwargs: DummyHandler()
            self.jobSlave.jobQueue.inbound = \
                [simplejson.dumps({'UUID' : 'test.rpath.local-build-96'})]
            self.jobSlave.checkJobQueue()
            self.failIf(not self.jobSlave.jobControlQueue,
                        "Job control queue was not created")
            self.failIf(self.jobSlave.jobControlQueue.connectionName != \
                            '/queue/test/test.rpath.local-build-96',
                        "Unexpected connection name for job control queue")
        finally:
            jobhandler.getHandler = getHandler

    def testJCUnsubscribe(self):
        self.jobSlave.jobHandler = DummyHandler()
        self.jobSlave.jobControlQueue = DummyQueue()
        self.jobSlave.checkJobQueue()
        self.failIf(self.jobSlave.jobControlQueue,
                    "Job control queue was not unsubscribed on job completion")

    def testJCStopJob(self):
        jobId = 'test.rpath.local-build-29'
        self.jobSlave.jobHandler = DummyHandler()
        self.jobSlave.jobHandler.jobId = jobId
        self.jobSlave.jobControlQueue = DummyQueue()
        self.jobSlave.handleStopJob(jobId)
        self.failIf(self.jobSlave.jobControlQueue,
                    "Job control queue was not unsubscribed on job stop")

if __name__ == "__main__":
    testsuite.main()
