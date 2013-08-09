#!/usr/bin/python
#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved
#
import os
import unittest
import testsuite
from testrunner import pathManager

testsuite.setup()

from conary.local.database import UpdateJob
from jobslave import filesystems

class FilesystemsTest(unittest.TestCase):
    def testCalculatePartitionSizes(self):
        cspath = os.path.join(pathManager.getPath('JOB_SLAVE_ARCHIVE_PATH'),"tmpwatch.ccs")
        ujob = UpdateJob(None)
        ujob.setJobsChangesetList([cspath])
        mounts = ['/usr/', '/bin/', '/usr/share/', '/']
        sizes = {'/usr/share': 1707L, '/': 193L, '/bin': 0, '/usr': 12592L}
        sizes = {'/usr/share': 8192L, '/': 4096L, '/bin': 0, '/usr': 16384L}
        r = filesystems.calculatePartitionSizes(ujob, mounts)
        self.failUnlessEqual(r, (sizes, 28672L))


if __name__ == "__main__":
    testsuite.main()
