#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import jobslave_helper
from jobslave import buildtypes
from jobslave import slave

class SlaveTest(jobslave_helper.JobSlaveHelper):
    def setUp(self):
        jobslave_helper.JobSlaveHelper.setUp(self)
        self.slaveCfg = slave.SlaveConfig()
        self.slaveCfg.configLine('TTL 0')
        self.slaveCfg.configLine('imageTimeout 0')
        self.slaveCfg.configLine('namespace test')
        self.slaveCfg.configLine('nodeName TestSlave')
        self.slaveCfg.configLine('jobQueueName job3.0.0:x86')
        self.jobSlave = slave.JobSlave(self.slaveCfg)

    def tearDown(self):
        self.jobSlave.imageServer.stop()
        jobslave_helper.JobSlaveHelper.tearDown(self)

    def testEmptyControlTopic(self):
        self.jobSlave.controlTopic.connection.insertMessage('')
        self.jobSlave.checkControlTopic()
        self.failIf(self.jobSlave.controlTopic.inbound != [],
                    "Control topic was no read")

    def testEmptyJobQueue(self):
        self.jobSlave.checkJobQueue()


if __name__ == "__main__":
    testsuite.main()
