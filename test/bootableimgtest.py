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

class BootableImageTest(jobslave_helper.JobSlaveHelper):
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


if __name__ == "__main__":
    testsuite.main()
