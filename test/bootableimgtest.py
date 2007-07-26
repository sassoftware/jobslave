#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import os
import re
import tempfile
import simplejson

from conary.lib import util
from conary.deps import deps

import jobslave_helper
from jobslave import slave
from jobslave.generators import bootable_image
import jobslave.loophelpers

class BootableImageHelperTest(jobslave_helper.JobSlaveHelper):
    def testBasicGrubConf(self):
        data = bootable_image.getGrubConf('TEST_IMAGE')
        self.failIf(not re.search('title TEST_IMAGE \(template\)', data),
                "title string didn't show up in grub")
        self.failIf(not re.search('initrd /boot/initrd', data),
                "bad initrd string for non-dom0")

    def testDom0GrubConf(self):
        data = bootable_image.getGrubConf('TEST_IMAGE', dom0 = True, xen = True)
        self.failIf(not re.search('kernel /boot/xen.gz', data),
                "wrong kernel command line for dom0")
        self.failIf(not re.search('module /boot/initrd', data),
                "bad initrd string for dom0")

    def testDomUGrubConf(self):
        data = bootable_image.getGrubConf('TEST_IMAGE', dom0 = False,
                xen = True)
        self.failIf(not re.search('xvda', data),
                "wrong boot device for domU")
        self.failIf(not re.search('timeout=0', data),
                "timeout should be 0 on domU")

    def testCopyFile(self):
        tmpDir = tempfile.mkdtemp()
        try:
            srcFile = os.path.join(tmpDir, 'a')
            destFile = os.path.join(tmpDir, 'b')
            self.touch(srcFile)
            bootable_image.copyfile(srcFile, destFile)
            self.failIf(not os.path.exists(destFile),
                    "copyfile didn't operate properly")
        finally:
            util.rmtree(tmpDir)

    def testCopyTree(self):
        tmpDir = tempfile.mkdtemp()
        try:
            srcDir = os.path.join(tmpDir, 'a')
            util.mkdirChain(srcDir)
            subDir = os.path.join(srcDir, 'a')
            util.mkdirChain(subDir)
            destDir = os.path.join(tmpDir, 'b')
            util.mkdirChain(destDir)
            srcFile = os.path.join(subDir, 'a')
            self.touch(srcFile, contents = 'test')
            bootable_image.copytree(srcDir, destDir)
            self.failIf(not os.path.exists(os.path.join(destDir, 'a')),
                    "copytree didn't operate properly")
            self.failIf(not os.path.exists(os.path.join(destDir, 'a', 'a')),
                    "expected file to be copied by copytree")
        finally:
            util.rmtree(tmpDir)

    def testMount(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600)
        logCall = bootable_image.logCall
        loopAttach = jobslave.loophelpers.loopAttach
        try:
            bootable_image.logCall = lambda *args, **kwargs: None
            jobslave.loophelpers.loopAttach = lambda *args, **kwargs: '/dev/loop0'
            fsm.mount('/tmp')
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopAttach = loopAttach
        self.failIf(not fsm.mounted, "Couldn't mount an ext3 partition")

    def testSwapMount(self):
        fsm = bootable_image.Filesystem('/dev/null', 'swap', 104857600)
        fsm.mount('/tmp')
        self.failIf(fsm.mounted, "Allowed to mount a swap partition")

    def testSwapUnmount(self):
        fsm = bootable_image.Filesystem('/dev/null', 'swap', 104857600)
        fsm.umount()
        self.failIf(fsm.mounted, "Allowed to unmount a swap partition")

    def testUmountNotMounted(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600)
        fsm.loopDev = '/dev/loop0'
        fsm.umount()
        self.failIf(fsm.loopDev != '/dev/loop0',
                "allowed to umount an unmounted partition")

    def testUmount(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600)
        logCall = bootable_image.logCall
        loopDetach = jobslave.loophelpers.loopDetach
        try:
            bootable_image.logCall = lambda *args, **kwargs: None
            jobslave.loophelpers.loopDetach = lambda *args, **kwargs: None
            fsm.loopDev = '/dev/loop0'
            fsm.mounted = True
            fsm.umount()
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopDetach = loopDetach
        self.failIf(fsm.mounted, "Couldn't umount an ext3 partition")

    def testFormatInvalid(self):
        fsm = bootable_image.Filesystem('/dev/null', 'notta_fs', 104857600)
        logCall = bootable_image.logCall
        loopDetach = jobslave.loophelpers.loopDetach
        loopAttach = jobslave.loophelpers.loopAttach
        try:
            bootable_image.logCall = lambda *args, **kwargs: None
            jobslave.loophelpers.loopDetach = lambda *args, **kwargs: None
            jobslave.loophelpers.loopAttach = lambda *args, **kwargs: '/dev/loop0'
            self.assertRaises(RuntimeError, fsm.format)
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopDetach = loopDetach
            jobslave.loophelpers.loopAttach = loopAttach

    def testFormatSwap(self):
        fsm = bootable_image.Filesystem('/dev/null', 'swap', 104857600)
        def DummyLogCall(cmd):
            # this is the line that actually tests the format call
            assert 'mkswap' in cmd
        logCall = bootable_image.logCall
        loopDetach = jobslave.loophelpers.loopDetach
        loopAttach = jobslave.loophelpers.loopAttach
        try:
            bootable_image.logCall = DummyLogCall
            jobslave.loophelpers.loopDetach = lambda *args, **kwargs: None
            jobslave.loophelpers.loopAttach = lambda *args, **kwargs: '/dev/loop0'
            fsm.format()
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopDetach = loopDetach
            jobslave.loophelpers.loopAttach = loopAttach

    def testFormatExt3(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600,
                offset = 512)
        def DummyLoopDetach(*args, **kwargs):
            self.detachCalled = True
        self.detachCalled = False
        logCall = bootable_image.logCall
        loopDetach = jobslave.loophelpers.loopDetach
        loopAttach = jobslave.loophelpers.loopAttach
        try:
            bootable_image.logCall = lambda *args, **kwargs: None
            jobslave.loophelpers.loopDetach = DummyLoopDetach
            jobslave.loophelpers.loopAttach = lambda *args, **kwargs: '/dev/loop0'
            fsm.format()
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopDetach = loopDetach
            jobslave.loophelpers.loopAttach = loopAttach
        self.failIf(not self.detachCalled,
                "ext3 format did not reach completion")

class MockResponse(object):
    pass

class MockJobSlave(object):
    def __init__(self):
        self.response = MockResponse()
        self.cfg = slave.SlaveConfig()

class BootableImageTest(jobslave_helper.JobSlaveHelper):
    def setUp(self):
        data = simplejson.loads(open('archive/jobdata.txt').read())
        self.mockJobSlave = MockJobSlave()
        bootable_image.BootableImage.status = lambda *args, **kwargs: None
        self.bootable = bootable_image.BootableImage(data, self.mockJobSlave)
        jobslave_helper.JobSlaveHelper.setUp(self)

    def tearDown(self):
        jobslave_helper.JobSlaveHelper.tearDown(self)

    def testBootableImageNotWritable(self):
        self.assertRaises(NotImplementedError, self.bootable.write)

    def testGzipDir(self):
        tmpDir = tempfile.mkdtemp()
        try:
            src = os.path.join(tmpDir, 'test')
            util.mkdirChain(src)
            self.touch(os.path.join(src, 'junk'), contents = '\n')
            dest = src + '.tgz'
            self.bootable.gzip(src)
            self.failIf(not os.path.exists(dest),
                    "gzip did not function for directory")
        finally:
            util.rmtree(tmpDir)

    def testGzipFile(self):
        tmpDir = tempfile.mkdtemp()
        try:
            src = os.path.join(tmpDir, 'test')
            self.touch(src, contents = '\n')
            dest = src + '.gz'
            self.bootable.gzip(src)
            self.failIf(not os.path.exists(dest),
                    "gzip did not function for file")
        finally:
            util.rmtree(tmpDir)

    def testInstallNoGrub(self):
        tmpDir = tempfile.mkdtemp()
        try:
            res = self.bootable.installGrub(tmpDir, None, None)
        finally:
            util.rmtree(tmpDir)
        self.failIf(res, "Attempted to run grub on defunct chroot")

    def testInstallGrub(self):
        tmpDir = tempfile.mkdtemp()
        os.mkdir(os.path.join(tmpDir, 'sbin'))
        os.system('touch %s' % os.path.join(tmpDir, 'sbin', 'grub'))
        logCall = bootable_image.logCall
        try:
            bootable_image.logCall = lambda *args, **kargs: None
            res = self.bootable.installGrub(tmpDir, 'trash', 10000)
        finally:
            bootable_image.logCall = logCall
            util.rmtree(tmpDir)
        self.failIf(not res, "Grub didn't run when grub was present")


    def testAddMissingScsiModules(self):
        tmpDir = tempfile.mkdtemp()
        try:
            # ensure this line doesn't backtrace if there's no /etc dir
            self.bootable.addScsiModules(tmpDir)
        finally:
            util.rmtree(tmpDir)

    def testAddScsiModules(self):
        tmpDir = tempfile.mkdtemp()
        try:
            self.touch(os.path.join(tmpDir, 'etc', 'modprobe.conf'),
                    'dummy line')
            self.bootable.addScsiModules(tmpDir)
            data = open(os.path.join(tmpDir, 'etc', 'modprobe.conf')).read()
            self.failIf('scsi_hostadapter' not in data,
                        "scsi modules not added to modprobe.conf")
        finally:
            util.rmtree(tmpDir)

    def testGetKernelFlavor(self):
        self.failIf('!kernel.smp' not in self.bootable.getKernelFlavor(),
                "non-xen kernel returned wrong flavor")
        self.bootable.baseFlavor = deps.parseFlavor('xen,domU is: x86')
        self.failIf(self.bootable.getKernelFlavor() != '',
                "getKernelFlavor favored non-xen flavor for xen group")

    def testGetImageSize(self):
        self.bootable.mountDict = {'/boot' : (0, 10240, 'ext3')}
        self.bootable.getTroveSize = \
                lambda *args, **kwargs: ({'/boot': 10240}, 0)
        totalSize, realSizes = self.bootable.getImageSize()
        self.failIf(totalSize != 24194560, \
                "Expected total size of 24194560 but got %d" % totalSize)
        self.failIf(realSizes != {'/boot': 24129024}, \
                "Expected real sizes of {'/boot': 24129024} but got %s" % \
                str(realSizes))

    def testFSOddsNEnds(self):
        # deliberately run fsoddsnends with a blank chroot to ensure it
        # won't backtrace
        tmpDir = tempfile.mkdtemp()
        self.bootable.writeConaryRc = lambda *args, **kwargs: None
        try:
            self.bootable.fileSystemOddsNEnds(tmpDir)
            self.failIf(os.listdir(tmpDir) == [],
                    "FilesystemOddsNEnds should have added content")
        finally:
            util.rmtree(tmpDir)

    def testFSOddsNEnds2(self):
        tmpDir = tempfile.mkdtemp()
        self.touch(os.path.join(tmpDir, 'etc', 'init.d', 'xdm'))
        self.touch(os.path.join(tmpDir, 'etc', 'inittab'))
        self.touch(os.path.join(tmpDir, 'usr', 'share', 'zoneinfo', 'UTC'))
        self.bootable.writeConaryRc = lambda *args, **kwargs: None
        try:
            self.bootable.fileSystemOddsNEnds(tmpDir)
            self.failIf(os.listdir(tmpDir) == [],
                    "FilesystemOddsNEnds should have added content")
        finally:
            util.rmtree(tmpDir)

    def testFSOddsNEnds3(self):
        tmpDir = tempfile.mkdtemp()
        # trigger runlevel five, but leave out /etc/inittab just to see
        # what happens.
        self.touch(os.path.join(tmpDir, 'etc', 'init.d', 'xdm'))
        self.bootable.writeConaryRc = lambda *args, **kwargs: None
        try:
            self.bootable.fileSystemOddsNEnds(tmpDir)
            self.failIf(os.listdir(tmpDir) == [],
                    "FilesystemOddsNEnds should have added content")
        finally:
            util.rmtree(tmpDir)

    def testFSOddsNEnds4(self):
        tmpDir = tempfile.mkdtemp()
        # set filesystems, but no /etc/fstab
        self.bootable.mountDict = {'/' : (0, 100, 'ext3'),
                                     '/boot': (0, 100, 'ext3'),
                                     'swap' : (0, 100, 'swap')}
        self.bootable.filesystems = self.bootable.mountDict
        self.bootable.writeConaryRc = lambda *args, **kwargs: None
        try:
            self.bootable.fileSystemOddsNEnds(tmpDir)
            self.failIf('fstab' not in os.listdir(os.path.join(tmpDir, 'etc')),
                    "FilesystemOddsNEnds should have added /etc/fstab")
        finally:
            util.rmtree(tmpDir)


if __name__ == "__main__":
    testsuite.main()
