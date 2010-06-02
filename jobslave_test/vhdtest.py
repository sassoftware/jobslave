#!/usr/bin/python
#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved
#

import os
import testsuite
import tempfile
import sys
testsuite.setup()

from jobslave.generators import vhd

class VHDTest(testsuite.TestCase):
    def setUp(self):
        fd, fn = tempfile.mkstemp()
        f = os.fdopen(fd, "w")
        f.seek(1024 * 1024)
        f.write("\0")
        f.close()

        self.fn = fn
        testsuite.TestCase.setUp(self)

    def tearDown(self):
        testsuite.TestCase.tearDown(self)
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


if __name__ == "__main__":
    testsuite.main()
