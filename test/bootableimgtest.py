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

from conary.lib import util

import jobslave_helper
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
            f = open(srcFile, 'w')
            f.write('test')
            f.close()
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
            f = open(srcFile, 'w')
            f.write('test')
            f.close()
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


class BootableImageTest(jobslave_helper.JobSlaveHelper):
    def setUp(self):
        jobslave_helper.JobSlaveHelper.setUp(self)

    def tearDown(self):
        jobslave_helper.JobSlaveHelper.tearDown(self)

    # tests to follow


if __name__ == "__main__":
    testsuite.main()
