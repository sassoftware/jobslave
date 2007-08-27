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

import tempfile

from conary.lib import util
import jobslave_helper
import bootable_stubs

from jobslave import buildtypes
# Replace generator's old superclass, BootableImage, with our
# stub, BootableImageStub
from jobslave.generators import constants

from jobslave.generators import raw_fs_image
from jobslave.generators import raw_hd_image
from jobslave.generators import xen_ova
from jobslave.generators import tarball


class GeneratorsTest(jobslave_helper.ExecuteLoggerTest):
    bases = {}
    def setUp(self):
        self.savedTmpDir = constants.tmpDir
        constants.tmpDir = tempfile.mkdtemp()
        jobslave_helper.ExecuteLoggerTest.setUp(self)
        self.bases['RawFsImage'] = raw_fs_image.RawFsImage.__bases__
        raw_fs_image.RawFsImage.__bases__ = (bootable_stubs.BootableImageStub,)

        self.bases['RawHdImage'] = raw_hd_image.RawHdImage.__bases__
        raw_hd_image.RawHdImage.__bases__ = (bootable_stubs.BootableImageStub,)

        self.bases['Tarball'] = tarball.Tarball.__bases__
        tarball.Tarball.__bases__ = (bootable_stubs.BootableImageStub,)


    def tearDown(self):
        raw_fs_image.RawFsImage.__bases__ = self.bases['RawFsImage']
        raw_hd_image.RawHdImage.__bases__ = self.bases['RawHdImage']
        tarball.Tarball.__bases__ = self.bases['Tarball']

        util.rmtree(constants.tmpDir, ignore_errors = True)
        constants.tmpDir = self.savedTmpDir
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

    def testRawFsImageNames(self):
        g = raw_fs_image.RawFsImage([], {})
        mountPoint = '/'
        g.mountDict = {mountPoint: (0, 100, 'ext3')}
        ref = '/tmp/workdir/image/image-root.ext3'
        res = g.mntPointFileName(mountPoint)
        self.failIf(ref != res, "expected %s for '%s' but got %s" % \
                (ref, mountPoint, res))

    def testRawFsImageNames2(self):
        g = raw_fs_image.RawFsImage([], {})
        mountPoint = 'swap'
        g.mountDict = {mountPoint: (0, 100, 'swap')}
        ref = '/tmp/workdir/image/image-swap.swap'
        res = g.mntPointFileName(mountPoint)
        self.failIf(ref != res, "expected %s for '%s' but got %s" % \
                (ref, mountPoint, res))

    def testRawFsImageNames3(self):
        g = raw_fs_image.RawFsImage([], {})
        mountPoint = '/mnt/test'
        g.mountDict = {mountPoint: (0, 100, 'ext3')}
        ref = '/tmp/workdir/image/image-mnt_test.ext3'
        res = g.mntPointFileName(mountPoint)
        self.failIf(ref != res, "expected %s for '%s' but got %s" % \
                (ref, mountPoint, res))

    def testRawFsImageNames4(self):
        g = raw_fs_image.RawFsImage([], {})
        mountPoint = 'swap2'
        g.mountDict = {mountPoint: (0, 100, 'swap')}
        ref = '/tmp/workdir/image/image-swap2.swap'
        res = g.mntPointFileName(mountPoint)
        self.failIf(ref != res, "expected %s for '%s' but got %s" % \
                (ref, mountPoint, res))

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
        g = xen_ova.XenOVA([], {'buildType': buildtypes.XEN_OVA,
            'outputToken': '580466f08ddfcfa130ee85f2d48c61ced992d4d4',
            'name': 'Test Linux',
            'type': 'build',
            'troveVersion': '/test.rpath.local@rpl:devel/0.0:1.3-1-6',
            'UUID': 'test.rpath.local-build-96',
            'project': {'conaryCfg': 'entitlement test.rpath.com xxxxxxxxxxxxxx\nrepositoryMap test.rpath.local http://test.rpath.local/conary/\nuser test.rpath.local anonymous anonymous\n',
                'hostname': 'test',
                'name': 'Test Linux',
                'label': 'test.rpath.local@rpl:devel'},
            'troveFlavor': '1#x86:i486:i586:i686:~!sse2|5#use:~Mesa.dri:~MySQL-python.threadsafe:X:~!alternatives:~!ati:~!bootstrap:~buildtests:desktop:~!dom0:~!domU:emacs:gcj:gnome:~!grub.static:ipv6:~!kernel.debug:~!kernel.debugdata:~!kernel.numa:~!kernel.pae:~kernel.smp:krb:ldap:nptl:~!nvidia:~!openssh.smartcard:~!openssh.static_libcrypto:pam:pcre:perl:~!pie:~!postfix.mysql:qt:readline:sasl:~!selinux:~sqlite.threadsafe:ssl:tcl:tcpwrappers:tk:~!xen:~xorg-server.dmx:~xorg-server.dri:~xorg-server.xnest',
            'troveName': 'group-dist',
            'protocolVersion': 1, 'outputUrl': 'http://nowhere:31337/',
            'data': {'jsversion': '3.1.3',
                'baseFileName': '',
                'media-template': 'media-template=/test.rpath.local@rpl:devel/1.3.0-2-1[is: x86]'},
            'description': 'this is a test'})
        g.mountDict = {'/mnt': (0, 100, 'ext3'), '/': (0, 100, 'ext3')}
        def MockMakeFSImage(*args, **kwargs):
            for mountPoint in g.mountDict.keys():
                fn = g.mntPointFileName(mountPoint)
                path = os.path.split(fn)[0]
                util.mkdirChain(path)
                f = open(fn, 'w')
                f.write('test')
                f.close()
        g.makeFSImage = MockMakeFSImage
        g.getImageSize = lambda: (100, {'/': 100, '/mnt': 100})
        g.write()
        self.failIf([x.split()[0] for x in self.callLog] != \
                ['split', 'for', 'split', 'for', 'tar'],
                "unexpected command sequnce")

    def testXenCreateXVA(self):
        g = xen_ova.XenOVA([], {'buildType': buildtypes.XEN_OVA,
            'outputToken': '580466f08ddfcfa130ee85f2d48c61ced992d4d4',
            'name': 'Test Linux',
            'type': 'build',
            'troveVersion': '/test.rpath.local@rpl:devel/0.0:1.3-1-6',
            'UUID': 'test.rpath.local-build-96',
            'project': {'conaryCfg': 'entitlement test.rpath.com xxxxxxxxxxxxxx\nrepositoryMap test.rpath.local http://test.rpath.local/conary/\nuser test.rpath.local anonymous anonymous\n',
                'hostname': 'test',
                'name': 'Test Linux',
                'label': 'test.rpath.local@rpl:devel'},
            'troveFlavor': '1#x86:i486:i586:i686:~!sse2|5#use:~Mesa.dri:~MySQL-python.threadsafe:X:~!alternatives:~!ati:~!bootstrap:~buildtests:desktop:~!dom0:~!domU:emacs:gcj:gnome:~!grub.static:ipv6:~!kernel.debug:~!kernel.debugdata:~!kernel.numa:~!kernel.pae:~kernel.smp:krb:ldap:nptl:~!nvidia:~!openssh.smartcard:~!openssh.static_libcrypto:pam:pcre:perl:~!pie:~!postfix.mysql:qt:readline:sasl:~!selinux:~sqlite.threadsafe:ssl:tcl:tcpwrappers:tk:~!xen:~xorg-server.dmx:~xorg-server.dri:~xorg-server.xnest',
            'troveName': 'group-dist',
            'protocolVersion': 1, 'outputUrl': 'http://nowhere:31337/',
            'data': {'jsversion': '3.1.3',
                'baseFileName': '',
                'media-template': 'media-template=/test.rpath.local@rpl:devel/1.3.0-2-1[is: x86]'},
            'description': 'this is a test'})
        g.mountDict = {'/mnt': (0, 100, 'ext3'), '/': (0, 100, 'ext3')}
        g.mountLabels = xen_ova.sortMountPoints(g.mountDict)
        fd, tmpFile = tempfile.mkstemp()
        templateDir = constants.templateDir
        try:
            constants.templateDir = os.path.join(os.path.dirname( \
                    os.path.dirname(os.path.abspath(__file__))), 'templates')
            g.createXVA(tmpFile, {'/mnt' : 100, '/' : 100})
            f = open(tmpFile)
            data = f.read()
            f.close()
            ref = '\n'.join(('<?xml version="1.0" ?>',
                '    <appliance version="0.1">',
                '        <vm name="vm">',
                '            <label>Test Linux</label>',
                '            <shortdesc>Created by rPath rBuilder</shortdesc>',
                '            <config mem_set="0" vcpus="1"/>',
                '            <hacks is_hvm="false" kernel_boot_cmdline="root=/dev/sda1 ro ">',
                '            </hacks>',
                '            <vbd device="sda" function="root" mode="w" vdi="vdi_sda"/>',
                '            <vbd device="sdb" function="root" mode="w" vdi="vdi_sdb"/>',
                '        </vm>',
                '    <vdi name="vdi_sda" size="100" source="file://sda" type="dir-gzipped-chunks"/>',
                '    <vdi name="vdi_sdb" size="100" source="file://sdb" type="dir-gzipped-chunks"/>',
                '</appliance>',
                ''))
            self.failIf(data != ref, "malformed XVA")
        finally:
            os.unlink(tmpFile)
            constants.templateDir = templateDir


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
