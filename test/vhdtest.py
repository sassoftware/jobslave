#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
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
        _, outFn = tempfile.mkstemp()
        try:
            vhd.makeDynamic(self.fn, outFn)
            self.validateVHD(outFn)
        finally:
            os.unlink(outFn)

    def testDifference(self):
        _, outFn = tempfile.mkstemp()
        try:
            vhd.makeDifference(self.fn, outFn)
            self.validateVHD(outFn, magic = "cxsparse")
        finally:
            os.unlink(outFn)

if __name__ == "__main__":
    testsuite.main()
