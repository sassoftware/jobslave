#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import os
import re
import tempfile

from conary.lib import util

import jobslave.generators
from jobslave import buildtypes
from jobslave.bootloader import grub_installer
from jobslave.bootloader import extlinux_installer

import jobslave_helper


class BootloaderTest(jobslave_helper.JobSlaveHelper):
    def _getInstaller(self, tmpdir, handler=None, kind='extlinux', name='Foo Project', **kw):
        if not handler:
            handler = self.getHandler(buildtypes.RAW_HD_IMAGE)
        if kind == 'grub':
            return grub_installer.GrubInstaller(handler, tmpdir,
                    handler.geometry, **kw)
        elif kind == 'extlinux':
            return extlinux_installer.ExtLinuxInstaller(handler, tmpdir,
                    handler.geometry, **kw)
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

    def test_install_mbr(self):
        #Also tests alternate paths for grub e.g. for ubuntu
        tmpDir = tempfile.mkdtemp()
        try:
            self.touch(os.path.join(tmpDir, 'sbin', 'grub'))
            self.touch(os.path.join(tmpDir, 'etc', 'debian_version'))
            handler = self.getHandler(buildtypes.RAW_HD_IMAGE)
            installer = jobslave.generators.get_bootloader(handler, tmpDir,
                    handler.geometry)

            self.calls = []
            self.mock(grub_installer, 'logCall', lambda x: self.calls.append(x))

            self.assertRaises(AssertionError, installer.install_mbr, tmpDir, 'asdfasdf', 516097)
            installer.install_mbr(tmpDir, os.path.join(tmpDir, 'mbr_device'),
                    2 * handler.geometry.bytesPerCylinder)
            self.failUnless('geometry (hd0) 2 64 32' in self.calls[0], 'geometry miscalculation')
        finally:
            util.rmtree(tmpDir)

    def testSLES(self):
        tmpDir = tempfile.mkdtemp()
        try:
            self.touch(os.path.join(tmpDir, 'sbin', 'grub'))
            self.touch(os.path.join(tmpDir, 'etc', 'SuSE-release'))

            installer = self._getInstaller(tmpDir, kind='grub')
            self.failUnlessEqual(installer._get_grub_conf(), 'menu.lst')

            installer.setup()

            fn = os.path.join(tmpDir, 'boot', 'grub', 'menu.lst')
            f = file(fn, 'w')
            f.write("""
# Modified by YaST2. Last modification on Wed Jun  4 03:04:00 UTC 2008
# GRUB configuration generated by rBuilder
#
# Note that you do not have to rerun grub after making changes to this file
#boot=hda
default 0
timeout =5
hiddenmenu

###Don't change this comment - YaST2 identifier: Original name: linux###
title SUSE Linux Enterprise Server 10 - 2.6.16.46-0.12
    root (hd0)
    kernel /boot/vmlinuz-2.6.16.46-0.12-default root=/dev/xvda1 ro clock=pit
    initrd /boot/initrd-2.6.16.46-0.12-default

###Don't change this comment - YaST2 identifier: Original name: failsafe###
title Failsafe -- SUSE Linux Enterprise Server 10 - 2.6.16.46-0.12
    root (/dev/xvda1)
    kernel /boot/boot/vmlinuz-2.6.16.46-0.12-default root=/dev/sda1 showopts ide=nodma apm=off acpi=off noresume edd=off 3
    initrd /boot/initrd-2.6.16.46-0.12-default

title SLES delivered by rPath (template)
    root (hd0)
    kernel /boot/vmlinuz-template ro root=LABEL=root clock=pit
""")
            f.close()
            installer.install()
            f = file(fn)
            lines = f.read()
            f.close()
            # make sure that the various fixups are performed correctly
            self.failIf('root (hd0)' in lines)
            self.failIf('root (/dev' in lines)
            self.failIf('root=/dev' in lines)
            self.failIf('/boot/boot' in lines)

            # make sure that /etc/sysconfig/bootloader is created as
            # expected
            fn = os.path.join(tmpDir, 'etc', 'sysconfig', 'bootloader')
            self.failUnless(os.path.exists(fn),
                            'SLES grub config did not create '+fn)
            lines = file(fn).read()
            self.failUnlessEqual(lines,
"""CYCLE_DETECTION="no"
CYCLE_NEXT_ENTRY="1"
LOADER_LOCATION=""
LOADER_TYPE="grub"
""")
            # make sure that /etc/grub.conf is created as expected
            fn = os.path.join(tmpDir, 'etc', 'grub.conf')
            self.failUnless(os.path.exists(fn),
                            'SLES grub config did not create '+fn)
            lines = file(fn).read()
            self.failUnlessEqual(lines,
"""setup (hd0)
quit
""")
            # make sure that /boot/grub/menu.lst is not a symlink
            # and /boot/grub/grub.conf does not exist
            self.failIf(os.path.islink(
                os.path.join(tmpDir, 'boot', 'grub', 'menu.lst')),
                        '/boot/grub/menu.lst is a symlink. it should not be')
            self.failIf(os.path.islink(
                os.path.join(tmpDir, 'etc', 'grub.conf')),
                        '/etc/grub.conf is a symlink. it should not be')

        finally:
            util.rmtree(tmpDir)
