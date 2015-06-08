#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
