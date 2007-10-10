#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import boto
import os
import stat
import sys
import tempfile

from conary.lib import util
import jobslave_helper
import image_stubs

from jobslave import buildtypes
from jobslave import imagegen
# Replace generator's old superclass, BootableImage, with our
# stub, BootableImageStub
from jobslave.generators import constants

from jobslave.generators import raw_fs_image
from jobslave.generators import raw_hd_image
from jobslave.generators import xen_ova
from jobslave.generators import tarball
from jobslave.generators import ami
from jobslave.generators import virtual_iron
from jobslave.generators import vpc
from jobslave.generators import vmware_image
from jobslave.generators import installable_iso
from jobslave.generators import update_iso


class GeneratorsTest(jobslave_helper.ExecuteLoggerTest):
    bases = {}
    def setUp(self):
        self.savedTmpDir = constants.tmpDir
        constants.tmpDir = tempfile.mkdtemp()
        jobslave_helper.ExecuteLoggerTest.setUp(self)
        self.bases['RawFsImage'] = raw_fs_image.RawFsImage.__bases__
        raw_fs_image.RawFsImage.__bases__ = (image_stubs.BootableImageStub,)

        self.bases['RawHdImage'] = raw_hd_image.RawHdImage.__bases__
        raw_hd_image.RawHdImage.__bases__ = (image_stubs.BootableImageStub,)

        self.bases['Tarball'] = tarball.Tarball.__bases__
        tarball.Tarball.__bases__ = (image_stubs.BootableImageStub,)

        self.bases['UpdateISO'] = update_iso.UpdateIso.__bases__
        update_iso.UpdateIso.__bases__ = (image_stubs.InstallableIsoStub,)

        constants.templateDir = os.path.join(os.path.dirname( \
                os.path.dirname(os.path.abspath(__file__))), 'templates')


    def tearDown(self):
        raw_fs_image.RawFsImage.__bases__ = self.bases['RawFsImage']
        raw_hd_image.RawHdImage.__bases__ = self.bases['RawHdImage']
        tarball.Tarball.__bases__ = self.bases['Tarball']
        update_iso.UpdateIso.__bases__ = self.bases['UpdateISO']

        util.rmtree(constants.tmpDir, ignore_errors = True)
        constants.tmpDir = self.savedTmpDir
        jobslave_helper.ExecuteLoggerTest.tearDown(self)

    def testRawFsImage(self):
        o1 = os.path.exists
        o2 = util.rmtree

        try:
            os.path.exists = lambda x: True
            util.rmtree = lambda x, **kwargs: True

            g = raw_fs_image.RawFsImage({}, [])
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

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'Raw Filesystem Image')

    def testRawFsImageNames(self):
        g = raw_fs_image.RawFsImage({}, [])
        mountPoint = '/'
        g.mountDict = {mountPoint: (0, 100, 'ext3')}
        ref = '/tmp/workdir/image/image-root.ext3'
        res = g.mntPointFileName(mountPoint)
        self.failIf(ref != res, "expected %s for '%s' but got %s" % \
                (ref, mountPoint, res))

    def testRawFsImageNames2(self):
        g = raw_fs_image.RawFsImage({}, [])
        mountPoint = 'swap'
        g.mountDict = {mountPoint: (0, 100, 'swap')}
        ref = '/tmp/workdir/image/image-swap.swap'
        res = g.mntPointFileName(mountPoint)
        self.failIf(ref != res, "expected %s for '%s' but got %s" % \
                (ref, mountPoint, res))

    def testRawFsImageNames3(self):
        g = raw_fs_image.RawFsImage({}, [])
        mountPoint = '/mnt/test'
        g.mountDict = {mountPoint: (0, 100, 'ext3')}
        ref = '/tmp/workdir/image/image-mnt_test.ext3'
        res = g.mntPointFileName(mountPoint)
        self.failIf(ref != res, "expected %s for '%s' but got %s" % \
                (ref, mountPoint, res))

    def testRawFsImageNames4(self):
        g = raw_fs_image.RawFsImage({}, [])
        mountPoint = 'swap2'
        g.mountDict = {mountPoint: (0, 100, 'swap')}
        ref = '/tmp/workdir/image/image-swap2.swap'
        res = g.mntPointFileName(mountPoint)
        self.failIf(ref != res, "expected %s for '%s' but got %s" % \
                (ref, mountPoint, res))

    def testRawHdImage(self):
        self.injectPopen("")
        g = raw_hd_image.RawHdImage({}, [])
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

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'Raw Hard Disk Image')

    def testVirtualIronImage(self):
        self.injectPopen("")
        g = virtual_iron.VirtualIronVHD({}, [])
        g.createVHD = lambda *args, **kwargs: None
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

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'Virtual Server')

    def testCreateFixedVHD(self):
        self.injectPopen("")
        tmpDir = tempfile.mkdtemp()
        try:
            baseFileName = os.path.join(tmpDir, 'base.hdd')
            f = open(baseFileName, 'w')
            f.write('')
            f.close()
            fileBase = os.path.join(tmpDir, 'output')
            g = virtual_iron.VirtualIronVHD({}, [])
            g.getBuildData = lambda *args, **kwargs: 'fixed'
            g.createVHD(baseFileName, fileBase)
            self.failIf(not os.path.exists(fileBase + '.vhd'),
                    "expected output not created")
        finally:
            util.rmtree(tmpDir)

    def testCreateDifferenceVHD(self):
        self.injectPopen("")
        tmpDir = tempfile.mkdtemp()
        try:
            baseFileName = os.path.join(tmpDir, 'base.hdd')
            f = open(baseFileName, 'w')
            f.write('')
            f.close()
            fileBase = os.path.join(tmpDir, 'output')
            g = virtual_iron.VirtualIronVHD({}, [])
            g.getBuildData = lambda *args, **kwargs: 'difference'
            g.createVHD(baseFileName, fileBase)
            os.listdir(tmpDir)
            self.failIf(sorted(os.listdir(tmpDir)) != \
                    ['base.hdd', 'output-base.vhd', 'output.vhd'],
                    "unexepcted output")
        finally:
            util.rmtree(tmpDir)

    def testCreateDynamicVHD(self):
        self.injectPopen("")
        tmpDir = tempfile.mkdtemp()
        try:
            baseFileName = os.path.join(tmpDir, 'base.hdd')
            f = open(baseFileName, 'w')
            f.write('')
            f.close()
            fileBase = os.path.join(tmpDir, 'output')
            g = virtual_iron.VirtualIronVHD({}, [])
            g.getBuildData = lambda *args, **kwargs: 'dynamic'
            g.createVHD(baseFileName, fileBase)
            self.failIf(not os.path.exists(fileBase + '.vhd'),
                    "expected output not created")
        finally:
            util.rmtree(tmpDir)

    def testCreateVMC(self):
        tmpDir = tempfile.mkdtemp()
        try:
            fileBase = os.path.join(tmpDir, 'filebase')
            g = vpc.VirtualPCImage({}, [])
            g.createVMC(fileBase)
            self.failIf(not os.path.exists(os.path.join( \
                    tmpDir, fileBase + '.vmc')), "output file not created")
        finally:
            util.rmtree(tmpDir)

    def testXenOVA(self):
        g = xen_ova.XenOVA({'buildType': buildtypes.XEN_OVA,
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
            'description': 'this is a test'}, [])
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
        g.getImageSize = lambda *args, **kwargs: (100, {'/': 100, '/mnt': 100})
        g.write()
        self.failIf([x.split()[0] for x in self.callLog] != \
                ['split', 'for', 'split', 'for', 'tar'],
                "unexpected command sequnce")

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'Xen OVA Image')

    def testXenCreateXVA(self):
        g = xen_ova.XenOVA({'buildType': buildtypes.XEN_OVA,
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
            'description': 'this is a test'}, [])
        g.mountDict = {'/mnt': (0, 100, 'ext3'), '/': (0, 100, 'ext3')}
        g.mountLabels = xen_ova.sortMountPoints(g.mountDict)
        fd, tmpFile = tempfile.mkstemp()
        try:
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

    def testTarball(self):
        oldChdir = os.chdir
        try:
            os.chdir = lambda x: x
            g = tarball.Tarball({}, [])
            g.write()
        finally:
            os.chdir = oldChdir

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'Tar File')

    def testTarballChdir(self):
        def BadChdir(chd):
            raise RuntimeError
        oldChdir = os.chdir
        try:
            os.chdir = BadChdir
            g = tarball.Tarball({}, [])
            self.assertRaises(RuntimeError, g.write)
        finally:
            os.chdir = oldChdir

    def testAMI(self):
        g = self.getHandler(buildtypes.AMI)
        g.createAMIBundle = lambda *args, **kwargs: '/fake/path'
        g.uploadAMIBundle = lambda *args, **kwargs: True
        g.registerAMI = lambda *args, **kwargs: ('testId', 'testManifest')
        g.postAMI = lambda amiID, amiManifestName: None
        g.write()

    def testCreateAMIBundle(self):
        bundlePath = tempfile.mkdtemp()
        try:
            inputFSImage = os.path.join(bundlePath, 'trash')
            fakeBundle = os.path.join(bundlePath, 'bundle.xml')
            f = open(fakeBundle, 'w')
            f.write('')
            f.close()
            g = self.getHandler(buildtypes.AMI)
            ref = os.path.basename(fakeBundle)
            res = g.createAMIBundle(inputFSImage, bundlePath)
            self.failIf(ref != res, "expected %s but got %s" % (ref, res))
            self.failIf(not self.callLog[0].startswith('ec2-bundle-image'),
                    "Expected ec2 bundle call")
        finally:
            util.rmtree(bundlePath)

    def testUploadAMIBundle(self):
        g = self.getHandler(buildtypes.AMI)
        pathToManifest = '/tmp/fake/path'

        self.failIf(not g.uploadAMIBundle(pathToManifest),
                "Unexpected error during upload")
        self.failIf(self.callLog != \
                ['ec2-upload-bundle -m /tmp/fake/path -b fake_s3_bucket ' \
                '-a fake_public_key -s fake_private_key'],
                "upload call not formed as expected")

    def testRegisterAMI(self):
        g = self.getHandler(buildtypes.AMI)
        class FakeBoto(object):
            register_image = lambda *args, **kwargs: 'fakeAMIId'
            modify_image_attribute = lambda *args, **kwargs: None
        connect_ec2 = boto.connect_ec2
        try:
            boto.connect_ec2 = lambda *args, **kwargs: FakeBoto()
            res = g.registerAMI('/tmp/fake_path')
            ref = ('fakeAMIId', 'fake_s3_bucket/fake_path')
            self.failIf(ref != res, "expected %s but got %s" % \
                    (str(ref), str(res)))
        finally:
            boto.connect_ec2 = connect_ec2

    def testAMIOddsNEnds(self):
        g = self.getHandler(buildtypes.AMI)
        tmpDir = tempfile.mkdtemp()
        g.writeConaryRc = lambda *args, **kwargs: None
        g.hugeDiskMountpoint = '/mnt/huge'
        try:
            g.fileSystemOddsNEnds(tmpDir)
            f = open(os.path.join(tmpDir, 'etc', 'fstab'))
            data = f.read()
            self.failIf(data != \
                    '/dev/sda2\t/mnt/huge\t\text3\tdefaults 1 2\n' \
                    '/dev/sda3\tswap\t\tswap\tdefaults 0 0\n',
                    "Unexpected mount structure")
        finally:
            util.rmtree(tmpDir)

    def testAMIBundleError(self):
        g = self.getHandler(buildtypes.AMI)
        def badCall(cmd):
            raise RuntimeError
        logCall = ami.logCall
        try:
            ami.logCall = badCall
            # these calls aren't technically needed but protect the test suite
            # from actually calling Amazon with busted data
            g.uploadAMIBundle = lambda *args, **kwargs: True
            g.registerAMI = lambda *args, **kwargs: ('testId', 'testManifest')
            g.postAMIOutput = lambda amiID, amiManifestName: None
            self.assertRaises(ami.AMIBundleError, g.write)
        finally:
            ami.logCall = logCall

    def testAMIUploadError(self):
        g = self.getHandler(buildtypes.AMI)
        def badCall(cmd):
            raise RuntimeError
        logCall = ami.logCall
        try:
            ami.logCall = badCall
            # these calls aren't technically needed but protect the test suite
            # from actually calling Amazon with busted data
            g.createAMIBundle = lambda *args, **kwargs: '/fake/path'
            g.registerAMI = lambda *args, **kwargs: ('testId', 'testManifest')
            g.postAMIOutput = lambda amiID, amiManifestName: None
            self.assertRaises(ami.AMIUploadError, g.write)
        finally:
            ami.logCall = logCall

    def testAMIRegisterError(self):
        g = self.getHandler(buildtypes.AMI)
        def badCall(cmd):
            raise RuntimeError
        connect_ec2 = boto.connect_ec2
        try:
            boto.connect_ec2 = badCall
            # these calls aren't technically needed but protect the test suite
            # from actually calling Amazon with busted data
            g.createAMIBundle = lambda *args, **kwargs: '/fake/path'
            g.uploadAMIBundle = lambda *args, **kwargs: True
            g.postAMIOutput = lambda amiID, amiManifestName: None
            self.assertRaises(ami.AMIRegistrationError, g.write)
        finally:
            boto.connect_ec2 = connect_ec2

    def testVMwareImage(self):
        self.injectPopen("")
        g = vmware_image.VMwareImage({}, [])

        g.makeHDImage = lambda x: open(x, 'w').write('')
        g.adapter = 'ide'
        tmpDir = tempfile.mkdtemp()
        g.workDir = tmpDir
        g.outputDir = tmpDir
        try:
            g.write()
            ref = ['image.vmx']
            res = os.listdir(os.path.join(tmpDir, 'image'))
            self.failIf(ref != res, "expected %s, but got %s" % \
                    (str(ref), str(res)))
            self.failIf(not self.callLog[0].startswith( \
                    'raw2vmdk -C 0 -H 16 -S 63 -A ide'),
                    "expected call to make vmdk")
        finally:
            util.rmtree(tmpDir)
        self.resetPopen()

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'VMware Player Image')

    def testSCSIVMwareImage(self):
        self.injectPopen("")
        g = vmware_image.VMwareImage({}, [])

        g.makeHDImage = lambda x: open(x, 'w').write('')
        g.adapter = 'lsilogic'
        tmpDir = tempfile.mkdtemp()
        g.workDir = tmpDir
        g.outputDir = tmpDir
        try:
            g.write()
            ref = ['image.vmx']
            res = os.listdir(os.path.join(tmpDir, 'image'))
            self.failIf(ref != res, "expected %s, but got %s" % \
                    (str(ref), str(res)))
            self.failIf(not self.callLog[0].startswith( \
                    'raw2vmdk -C 0 -H 128 -S 32 -A lsilogic'),
                    "expected call to make vmdk")
        finally:
            util.rmtree(tmpDir)
        self.resetPopen()

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'VMware Player Image')

    def testVMwareSetModes(self):
        g = vmware_image.VMwareImage({}, [])
        tmpDir = tempfile.mkdtemp()
        try:
            file1 = os.path.join(tmpDir, 'file1')
            file2 = os.path.join(tmpDir, 'file2')
            vmxFile = os.path.join(tmpDir, 'file.vmx')
            for fn in (file1, file2, vmxFile):
                open(fn, 'w').write('')
            g.setModes(tmpDir)
            self.failIf(os.stat(file1)[stat.ST_MODE] != 0100600,
                    "Incorrect file mode")
            self.failIf(os.stat(file2)[stat.ST_MODE] != 0100600,
                    "Incorrect file mode")
            self.failIf(os.stat(vmxFile)[stat.ST_MODE] != 0100755,
                    "Incorrect file mode")
        finally:
            util.rmtree(tmpDir)

    def testESXVMDK(self):
        g = vmware_image.VMwareESXImage({}, [])
        tmpDir = tempfile.mkdtemp()
        try:
            hdImage = os.path.join(tmpDir, 'hdimage.hdd')
            open(hdImage, 'w').write('')
            outFile = os.path.join(tmpDir, 'outfile.vmdk')
            size = 1024 * 1024
            g.createVMDK(hdImage, outFile, size)
            self.failIf(sorted(os.listdir(tmpDir)) != \
                    ['outfile-flat.vmdk', 'outfile.vmdk'],
                    "expected vmdk to be produced")
        finally:
            util.rmtree(tmpDir)

    def testUpdateISOTemplates(self):
        tmpDir = tempfile.mkdtemp()
        try:
            g = update_iso.UpdateIso({}, [])
            ref = os.path.join(tmpDir, g.productDir, 'changesets')
            res = g.prepareTemplates(tmpDir)
            self.failIf(os.listdir(tmpDir) != ['rPath'],
                    "productDir not created")
            self.failIf(sorted(os.listdir(os.path.join(tmpDir, g.productDir))) \
                    != ['base', 'changesets'], "subdirs not created")
            self.failIf(ref != res, "expected %s but got %s" % (ref, res))
            self.failIf(g.setupKickStart() != None, "expected stubbed function")
            self.failIf(g.writeProductImage() != None,
                    "expected stubbed function")
        finally:
            util.rmtree(tmpDir)


if __name__ == "__main__":
    testsuite.main()
