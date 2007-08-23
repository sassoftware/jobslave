#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import os
import testsuite
import sys
testsuite.setup()

from jobslave.generators import xen_ova

class XenEnterpriseGeneratorTest(testsuite.TestCase):
    def testSortMountPoints(self):
        data = {'swap': (0, 100, 'swap'), '/': (0, 100, 'ext3')}
        ref = {'sda' : '/', 'sdb': 'swap'}
        res = xen_ova.sortMountPoints(data)
        self.failIf(ref != res, "expected %s but got %s" % (str(ref), str(res)))

    def testSortBootOverride(self):
        data = {'swap': (0, 100, 'swap'), '/': (0, 100, 'ext3'),
                '/boot' : (0, 100, 'ext3')}
        ref = {'sda' : '/boot', 'sdb': 'swap', 'sdc': '/'}
        res = xen_ova.sortMountPoints(data)
        self.failIf(ref != res, "expected %s but got %s" % (str(ref), str(res)))

    def testSortSwapOrder(self):
        data = {'swap2': (0, 100, 'swap'), '/': (0, 100, 'ext3'),
                'swap' : (0, 100, 'swap'), '/mnt': (0, 100, 'ext3')}
        ref = {'sda' : '/', 'sdb': 'swap', 'sdc': 'swap2', 'sdd': '/mnt'}
        res = xen_ova.sortMountPoints(data)
        self.failIf(ref != res, "expected %s but got %s" % (str(ref), str(res)))

    def testOrdToAscii(self):
        index = 0
        ref = 'a'
        res = xen_ova.ordToAscii(index)
        self.failIf(ref != res, "Expected %d to be mapped to %s but got %s" % \
                (index, ref, res))

    def testOrdToAscii2(self):
        index = 1
        ref = 'b'
        res = xen_ova.ordToAscii(index)
        self.failIf(ref != res, "Expected %d to be mapped to %s but got %s" % \
                (index, ref, res))

    def testOrdToAscii3(self):
        index = 26
        ref = 'aa'
        res = xen_ova.ordToAscii(index)
        self.failIf(ref != res, "Expected %d to be mapped to %s but got %s" % \
                (index, ref, res))

    def testOrdToAscii4(self):
        index = 52
        ref = 'ba'
        res = xen_ova.ordToAscii(index)
        self.failIf(ref != res, "Expected %d to be mapped to %s but got %s" % \
                (index, ref, res))

    def testOrdToAscii5(self):
        index = 702
        ref = 'aaa'
        res = xen_ova.ordToAscii(index)
        self.failIf(ref != res, "Expected %d to be mapped to %s but got %s" % \
                (index, ref, res))


if __name__ == "__main__":
    testsuite.main()
