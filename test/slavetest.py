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
    def testEmptyControlTopic(self):
        self.jobSlave.controlTopic.connection.insertMessage('')
        self.jobSlave.checkControlTopic()
        self.failIf(self.jobSlave.controlTopic.inbound != [],
                    "Control topic was no read")

    def testEmptyJobQueue(self):
        self.jobSlave.checkJobQueue()


if __name__ == "__main__":
    testsuite.main()
