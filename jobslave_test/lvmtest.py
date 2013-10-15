#
# Copyright (c) SAS Institute Inc.
#

from jobslave import lvm
from jobslave_helper import ExecuteLoggerTest


class LVMTest(ExecuteLoggerTest):
    def testLVMContainer(self):
        self.injectPopen("/dev/loop0")
        container = lvm.LVMContainer(20 * 1024*1024, "testimg", 1)

        self.failUnlessEqual(self.callLog, [
            ['losetup', '-o', '1', '--sizelimit', '20971520', '/dev/loop0', 'testimg'],
            ['lvm', 'pvcreate', '/dev/loop0'],
            ['lvm', 'vgcreate', 'vg00', '/dev/loop0'],
            ])

        self.reset()

        root = container.addFilesystem('/', 'ext3', 1024)
        swap = container.addFilesystem('swap1', 'swap', 1024)
        self.failUnlessEqual(self.callLog, [
            ['lvm', 'lvcreate', '-n', 'root', '-L', '1K', 'vg00'],
            ['lvm', 'lvcreate', '-n', 'swap1', '-L', '1K', 'vg00'],
            ])

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
            ['lvm', 'vgchange', '-a', 'n', 'vg00'],
            ['losetup', '-d', '/dev/loop0'],
            ])
