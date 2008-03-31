#!/usr/bin/python2.4
#
# Copyright (c) 2008 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import os
import re
import tempfile

from conary.lib import util

from jobslave import buildtypes
from jobslave.bootloader import grub_installer
from jobslave.bootloader import extlinux_installer

import jobslave_helper

class BootloaderTest(jobslave_helper.JobSlaveHelper):
    def _getInstaller(self, tmpdir, handler=None, kind='extlinux', name='Foo Project'):
        if not handler:
            handler = self.getHandler(buildtypes.RAW_HD_IMAGE)
        if kind == 'grub':
            return grub_installer.GrubInstaller(handler, tmpdir)
        elif kind == 'extlinux':
            return extlinux_installer.ExtLinuxInstaller(handler, tmpdir)
        else:
            self.fail()

    def testBasicGrubConf(self):
        data = grub_installer.getGrubConf('TEST_IMAGE')
        self.failIf(not re.search('title TEST_IMAGE \(template\)', data),
                "title string didn't show up in grub")
        self.failIf(not re.search('initrd /boot/initrd', data),
                "bad initrd string for non-dom0")

    def testDom0GrubConf(self):
        data = grub_installer.getGrubConf('TEST_IMAGE', dom0 = True, xen = True)
        self.failIf(not re.search('kernel /boot/xen.gz', data),
                "wrong kernel command line for dom0")
        self.failIf(not re.search('module /boot/initrd', data),
                "bad initrd string for dom0")

    def testDomUGrubConf(self):
        data = grub_installer.getGrubConf('TEST_IMAGE', dom0 = False,
                xen = True)
        self.failIf(not re.search('xvda', data),
                "wrong boot device for domU")
        self.failIf(not re.search('timeout=0', data),
                "timeout should be 0 on domU")

    def testClockGrubConf(self):
        data = grub_installer.getGrubConf('TEST_IMAGE', clock = "clock=pit")
        self.failIf(not re.search('clock=pit', data),
                "clock setting did not appear")

    def testSetupGrub(self):
        tmpDir = tempfile.mkdtemp()
        try:
            installer = self._getInstaller(tmpDir, kind='grub')
            self.touch(os.path.join(tmpDir, 'sbin', 'grub'))
            installer.setup()
            installer.install()
            self.failIf('etc' not in os.listdir(tmpDir),
                    "setupGrub did not create expected dir structure")
            self.failIf('boot' not in os.listdir(tmpDir),
                    "setupGrub did not create expected dir structure")
        finally:
            util.rmtree(tmpDir)

    def testGrubName(self):
        tmpDir = tempfile.mkdtemp()
        try:
            self.touch(os.path.join(tmpDir, 'sbin', 'grub'))
            self.touch(os.path.join(tmpDir, 'etc', 'issue'),
                    contents = 'TEST_NAME')

            installer = self._getInstaller(tmpDir, kind='grub')
            installer.setup()
            installer.install()

            f = open(os.path.join(tmpDir, 'etc', 'grub.conf'))
            data = f.read()
            f.close()
            self.failIf('TEST_NAME' not in data,
                    "grub title not taken from /etc/issue")
        finally:
            util.rmtree(tmpDir)

    def testEmptyGrubName(self):
        '''
        Make sure grub title falls back to defaults if /etc/issue exists but
        is empty.

        Tests: RBL-2333
        '''
        tmpDir = tempfile.mkdtemp()
        try:
            handler = self.getHandler(buildtypes.RAW_HD_IMAGE)

            self.touch(os.path.join(tmpDir, 'sbin', 'grub'))
            self.touch(os.path.join(tmpDir, 'etc', 'issue'))

            installer = self._getInstaller(tmpDir, handler=handler, kind='grub')
            installer.setup()
            installer.install()

            f = open(os.path.join(tmpDir, 'etc', 'grub.conf'))
            data = f.read()
            f.close()
            self.failUnless(handler.jobData['project']['name'] in data,
                'grub title not taken from job data')
        finally:
            util.rmtree(tmpDir)
