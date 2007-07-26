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

from conary.lib import util
import jobslave_helper
import bootable_stubs

# Replace generator's old superclass, BootableImage, with our
# stub, BootableImageStub
from jobslave.generators import constants
constants.tmpDir = "/tmp"

from jobslave.generators import raw_fs_image
from jobslave.generators import raw_hd_image
from jobslave.generators import xen_ova
from jobslave.generators import tarball


class GeneratorsTest(jobslave_helper.ExecuteLoggerTest):
    bases = {}
    def setUp(self):
        jobslave_helper.ExecuteLoggerTest.setUp(self)
        self.bases['RawFsImage'] = raw_fs_image.RawFsImage.__bases__
        raw_fs_image.RawFsImage.__bases__ = (bootable_stubs.BootableImageStub,)

        self.bases['RawHdImage'] = raw_hd_image.RawHdImage.__bases__
        raw_hd_image.RawHdImage.__bases__ = (bootable_stubs.BootableImageStub,)

        self.bases['XenOVA'] = xen_ova.XenOVA.__bases__
        xen_ova.XenOVA.__bases__ = (bootable_stubs.BootableImageStub,)

        self.bases['Tarball'] = tarball.Tarball.__bases__
        tarball.Tarball.__bases__ = (bootable_stubs.BootableImageStub,)


    def tearDown(self):
        raw_fs_image.RawFsImage.__bases__ = self.bases['RawFsImage']
        raw_hd_image.RawHdImage.__bases__ = self.bases['RawHdImage']
        xen_ova.XenOVA.__bases__ = self.bases['XenOVA']
        tarball.Tarball.__bases__ = self.bases['Tarball']

        jobslave_helper.ExecuteLoggerTest.tearDown(self)

    def testRawFsImage(self):
        o1 = os.path.exists
        o2 = util.rmtree

        try:
            os.path.exists = lambda x: True
            util.rmtree = lambda x, **kwargs: True

            g = raw_fs_image.RawFsImage([], {})
            g.write()
        finally:
            os.path.exists = o1
            util.rmtree = o2

        self.failUnlessEqual(
            self.callLog,
             ['dd if=/dev/zero of=/tmp/workdir/image/image-swap.swap count=1 seek=-1 bs=4096',
              'mkswap -L swap /tmp/workdir/image/image-swap.swap',
              'dd if=/dev/zero of=/tmp/workdir/image/image-root.ext3 count=1 seek=-1 bs=4096',
              'mke2fs -L / -F -b 4096 /tmp/workdir/image/image-root.ext3 0',
              'tune2fs -i 0 -c 0 -j -L "/" /tmp/workdir/image/image-root.ext3']
        )

        self.failUnlessEqual(g.filesystems.keys(), ['swap', '/'])

    def testRawHdImage(self):
        self.injectPopen("")
        g = raw_hd_image.RawHdImage([], {})
        g.write()

        self.failUnlessEqual(
            self.callLog,
            ['dd if=/dev/zero of=/tmp/workdir/image.hdd count=1 seek=125 bs=4096',
             'losetup -o65636  /tmp/workdir/image.hdd',
             'sync',
             'pvcreate ',
             'vgcreate vg00 ',
             'losetup -o65536  /tmp/workdir/image.hdd',
             'sync',
             'mke2fs -L / -F -b 4096  0',
             'tune2fs -i 0 -c 0 -j -L "/" ',
             'losetup -d ',
             'lvcreate -n swap -L0K vg00',
             'mkswap -L swap /dev/vg00/swap',
             'lvchange -a n /dev/vg00/swap',
             'vgchange -a n vg00',
             'pvchange -x n ',
             'losetup -d ']
        )
        self.resetPopen()

    def testXenOVA(self):
        raise testsuite.SkipTestException, "Not mocked out enough yet"
        g = xen_ova.XenOVA([], {})
        g.write()

    def testTarball(self):
        oldChdir = os.chdir
        try:
            os.chdir = lambda x: x
            g = tarball.Tarball([], {})
            g.write()
        finally:
            os.chdir = oldChdir


if __name__ == "__main__":
    testsuite.main()
