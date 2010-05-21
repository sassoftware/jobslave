#!/usr/bin/python
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import unittest
import testsuite
testsuite.setup()

import os
from cStringIO import StringIO

from conary.repository import changeset
from jobslave import filesystems
from jobslave import lvm
from jobslave_helper import ExecuteLoggerTest

class LVMTest(ExecuteLoggerTest):
    def testLVMContainer(self):
        self.injectPopen("/dev/loop0")
        container = lvm.LVMContainer(20 * 1024*1024, "testimg", 1)

        self.failUnlessEqual(self.callLog,
            ['losetup -o1 /dev/loop0 testimg',
             'sync',
             'pvcreate /dev/loop0',
             'vgcreate vg00 /dev/loop0']
        )

        self.reset()

        root = container.addFilesystem('/', 'ext3', 1024)
        swap = container.addFilesystem('swap1', 'swap', 1024)
        self.failUnlessEqual(self.callLog,
            ['lvcreate -n root -L1K vg00',
             'lvcreate -n swap1 -L1K vg00'],
        )

        self.reset()
        root.mount("/")
        root.umount()
        root.umount() # make sure we don't fail umounting a non-mounted filesystem
        swap.mount("/")
        swap.umount()

        self.failUnlessEqual(self.callLog,
            ['mount -n /dev/vg00/root /',
             'umount -n /dev/vg00/root']
        )

        self.reset()
        container.destroy()
        self.failUnlessEqual(self.callLog,
            ['lvchange -a n /dev/vg00/root',
             'lvchange -a n /dev/vg00/swap1',
             'vgchange -a n vg00',
             'pvchange -x n /dev/loop0',
             'losetup -d /dev/loop0']
        )

if __name__ == "__main__":
    testsuite.main()
