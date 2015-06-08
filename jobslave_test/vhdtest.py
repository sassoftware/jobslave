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


import os
import tempfile

from jobslave.generators import vhd
from jobslave_test.jobslave_helper import JobSlaveHelper

class VHDTest(JobSlaveHelper):
    def setUp(self):
        fd, fn = tempfile.mkstemp()
        f = os.fdopen(fd, "w")
        f.seek(1024 * 1024)
        f.write("\0")
        f.close()

        self.fn = fn
        super(VHDTest, self).setUp()

    def tearDown(self):
        super(VHDTest, self).tearDown()
        os.unlink(self.fn)

    def validateVHD(self, fn, magic = "conectix"):
        # naive validation function, this could check checksums, etc
        x = file(fn).read()
        self.failUnless(magic in x)

    def testFlat(self):
        vhd.makeFlat(self.fn)
        self.validateVHD(self.fn)

    def testDynamic(self):
        fd, outFn = tempfile.mkstemp()
        os.close(fd)
        try:
            vhd.makeDynamic(self.fn, outFn)
            self.validateVHD(outFn)
        finally:
            os.unlink(outFn)

    def testDifference(self):
        fd, outFn = tempfile.mkstemp()
        os.close(fd)
        try:
            vhd.makeDifference(self.fn, outFn)
            self.validateVHD(outFn, magic = "cxsparse")
        finally:
            os.unlink(outFn)

    def testPacketHeaderAttributes(self):
        pkt = vhd.SparseDiskHeader()
        self.assertRaises(AttributeError, pkt.__getattribute__,
                "notarealattribute")

    def testBlockTable(self):
        blk = vhd.BlockAllocationTable(10)
        self.failIf(blk[1] != 4294967295L, "enexpected return")
