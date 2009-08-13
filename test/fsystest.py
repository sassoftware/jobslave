#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#
import os
import unittest
import testsuite
from testrunner import pathManager

testsuite.setup()

from conary.repository import changeset
from jobslave import filesystems

class FilesystemsTest(unittest.TestCase):
    def testCalculatePartitionSizes(self):
        # loading a changeset from disk is easier than
        # bringing up an entire Conary stack and creating one.
        cs = changeset.ChangeSetFromFile(os.path.join(pathManager.getPath('JOB_SLAVE_ARCHIVE_PATH'),"tmpwatch.ccs") )

        mounts = ['/usr/', '/bin/', '/usr/share/', '/']
        sizes = {'/usr/share': 1707L, '/': 193L, '/bin': 0, '/usr': 12592L}
        sizes = {'/usr/share': 8192L, '/': 4096L, '/bin': 0, '/usr': 16384L}
        r = filesystems.calculatePartitionSizes(cs, mounts)
        self.failUnlessEqual(r, (sizes, 28672L))


if __name__ == "__main__":
    testsuite.main()
