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

class SlaveTest(jobslave_helper.JobSlaveHelper):
    def testSlave(self):
        from jobslave import jobhandler
        import epdb
        epdb.st()

    def getHandler(self, buildType):
        return jobhandler.getHandler({'buildType' : buildType}, '')

    def testGetInstallableISO(self):
        handler = self.getHandler(buildtypes.INSTALLABLE_ISO)
        assert handler, "Failed to get Installable ISO"

if __name__ == "__main__":
    testsuite.main()
