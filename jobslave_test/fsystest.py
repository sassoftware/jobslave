#
# Copyright (c) SAS Institute Inc.
#

import unittest

from conary.local.database import UpdateJob
from jobslave import filesystems
from jobslave_test import resources


class FilesystemsTest(unittest.TestCase):
    def testCalculatePartitionSizes(self):
        cspath = resources.get_archive("tmpwatch.ccs")
        ujob = UpdateJob(None)
        ujob.setJobsChangesetList([cspath])
        mounts = ['/usr/', '/bin/', '/usr/share/', '/']
        sizes = {'/usr/share': 1707L, '/': 193L, '/bin': 0, '/usr': 12592L}
        sizes = {'/usr/share': 8192L, '/': 4096L, '/bin': 0, '/usr': 16384L}
        r = filesystems.calculatePartitionSizes(ujob, mounts)
        self.failUnlessEqual(r, (sizes, 28672L))
