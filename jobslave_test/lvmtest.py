#!/usr/bin/python
#
# Copyright (c) SAS Institute Inc.
#

import testsuite
testsuite.setup()

from jobslave import lvm
from jobslave_helper import ExecuteLoggerTest


class LVMTest(ExecuteLoggerTest):
    def testLVMContainer(self):
        self.injectPopen("/dev/loop0")
        container = lvm.LVMContainer(20 * 1024*1024, "testimg", 1)

        self.failUnlessEqual(self.callLog, [
            ['losetup', '-o', '1', '--sizelimit', '20971520', '/dev/loop0', 'testimg'],
            'pvcreate /dev/loop0',
            'vgcreate vg00 /dev/loop0',
            ])

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

        self.failUnlessEqual(self.callLog, [
            'mount -n -t ext3 /dev/vg00/root / -o data=writeback,barrier=0',
            'umount -n /',
            ])

        self.reset()
        container.unmount()
        self.failUnlessEqual(self.callLog, [
            'lvchange -a n /dev/vg00/root',
            'lvchange -a n /dev/vg00/swap1',
            'vgchange -a n vg00',
            'pvchange -x n /dev/loop0',
            ['losetup', '-d', '/dev/loop0'],
            ])

if __name__ == "__main__":
    testsuite.main()
