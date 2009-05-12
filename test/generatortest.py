#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import boto
import inspect
import os
import stat
import sys
import tempfile

from conary import trove
from conary.lib import util
from conary.deps import deps
from conary import conaryclient

import jobslave_helper
import image_stubs
import bootableimgtest
import logging

from jobslave import buildtypes
from jobslave import imagegen
# Replace generator's old superclass, BootableImage, with our
# stub, BootableImageStub
from testutils import mock
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

import simplejson

class GeneratorThreadTest(jobslave_helper.ExecuteLoggerTest):
    def setUp(self):
        f = open ('archive/jobdata.txt')
        try:
            self.jobData = simplejson.loads(f.read())
        finally:
            f.close()
        super(GeneratorThreadTest, self).setUp()
        self.mock(os, 'fork', lambda: 0)
        self.mock(os, 'waitpid', lambda x, y: None)
        self.mock(os, 'setpgid', lambda x, y: None)
        self.mock(os, '_exit', lambda x: None)

        class LogHandler(object):
            def __init__(x, jobId, response):
                x.jobId = jobId
                x.response = response
            acquire = release = lambda x: None
        self.mock(imagegen, 'LogHandler', LogHandler)

    def testRun(self):
        parent = bootableimgtest.MockJobSlave()
        gen = imagegen.Generator(self.jobData, parent)
        self.mock(gen, 'write', lambda : None)
        self.mock(imagegen.response, 'MCPResponse', jobslave_helper.DummyResponse)
        gen.run()

        self.failIf(gen.response is None)
        self.failIf(gen.response is parent.response)
        self.failIf(gen.logger.response is parent.response)

        rootLogger = logging.getLogger('')
        rootLogger.removeHandler(gen.logger)
        del gen.logger

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
              'mke2fs -F -b 4096 -I 128 /tmp/workdir/image/image-root.ext3 0',
              'tune2fs -i 0 -c 0 -j -L "root" /tmp/workdir/image/image-root.ext3']
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
            ['dd if=/dev/zero of=/tmp/workdir/image.hdd count=1 seek=4095 bs=512',
             'losetup -o1048576  /tmp/workdir/image.hdd',
             'sync',
             'pvcreate ',
             'vgcreate vg00 ',
             'losetup -o65536  /tmp/workdir/image.hdd',
             'sync',
             'mke2fs -F -b 4096 -I 128  240',
             'tune2fs -i 0 -c 0 -j -L "root" ',
             'losetup -d ',
             'lvcreate -n swap -L0K vg00',
             'mkswap -L swap /dev/vg00/swap',
             'mount -obind /tmp/workdir/image.hdd /tmp/workdir/root/disk.img',
             'umount /tmp/workdir/root/disk.img',
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
            ['dd if=/dev/zero of=/tmp/workdir/image.hdd count=1 seek=4095 bs=512',
             'losetup -o1048576  /tmp/workdir/image.hdd',
             'sync',
             'pvcreate ',
             'vgcreate vg00 ',
             'losetup -o65536  /tmp/workdir/image.hdd',
             'sync',
             'mke2fs -F -b 4096 -I 128  240',
             'tune2fs -i 0 -c 0 -j -L "root" ',
             'losetup -d ',
             'lvcreate -n swap -L0K vg00',
             'mkswap -L swap /dev/vg00/swap',
             'mount -obind /tmp/workdir/image.hdd /tmp/workdir/root/disk.img',
             'umount /tmp/workdir/root/disk.img',
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

    def testCitrixXVA(self):
        _listDir = os.listdir
        _unlink = os.unlink

        def listdir(path):
            if path.endswith('xvda'):
                return ['chunk-000000000', 'chunk-000000001']
            else:
                return _listdir(path)
        def unlink(path):
            if not path.endswith('hdimage'):
                return _unlink(path)

        try:
            os.listdir = listdir
            os.unlink = unlink

            g = xen_ova.XenOVA({
                'project': {'name': 'Foo Bar'},
              }, [])
            g.makeHDImage = lambda image_path: 1500000000
            g.write()
        finally:
            os.listdir = _listDir
            os.unlink = _unlink

        self.failUnlessEqual(self.callLog, [
                'split -b 1000000000 -a 9 -d %s/hdimage '
                    '"%s/ova_base/xvda/chunk-"' % (g.workDir, g.workDir),
                'gzip "%s/ova_base/xvda/chunk-000000000"' % g.workDir,
                'gzip "%s/ova_base/xvda/chunk-000000001"' % g.workDir,
                'tar -cv -f "%s/%s/%s.xva" -C "/tmp/workdir/ova_base" -T '
                    '"%s/files"' % (constants.finishedDir, g.UUID,
                    g.basefilename, g.workDir)
            ])

        file_list = open(g.workDir + '/files').read()
        self.failUnlessEqual(file_list,
            'ova.xml\nxvda/chunk-000000000.gz\nxvda/chunk-000000001.gz\n')

        ova_maybe = open(g.workDir + '/ova_base/ova.xml').read()
        ova_good = '''<?xml version="1.0" ?>
    <appliance version="0.1">
        <vm name="vm">
            <label>Foo Bar</label>
            <shortdesc>Created by rPath rBuilder</shortdesc>
            <config mem_set="0" vcpus="1"/>
            <hacks is_hvm="false" kernel_boot_cmdline="root=/dev/xvda1 ro ">
            </hacks>
<vbd device="xvda" function="root" mode="w" vdi="vdi_xvda" />
        </vm>
<vdi name="vdi_xvda" size="1500000000" source="file://xvda" type="dir-gzipped-chunks" variety="system" />
</appliance>
'''
        self.failUnlessEqual(ova_maybe, ova_good)

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'Citrix XenServer (TM) Image')

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
            g._kernelMetadata['ec2-aki'] = 'aki-zzzzzz'
            g._kernelMetadata['ec2-ari'] = 'ari-zzzzzz'
            mock.mockMethod(g.getBuildData)
            g.amiData = {'ec2ProductCode': 'asdfg,hjkl'}

            ref = os.path.basename(fakeBundle)
            res = g.createAMIBundle(inputFSImage, bundlePath)
            self.failUnlessEqual(ref, res)

            self.failUnlessEqual(len(self.callLog), 1)
            called = self.callLog[0]
            self.failUnlessEqual(called.split()[0], 'ec2-bundle-image')
            for x in 'cdiku':
                self.failUnless(' -%s ' % x in called)
            self.failUnless(' -p "image_None.img"' in called)
            self.failUnless(' -r "i386"' in called)
            self.failUnless(' --kernel "aki-zzzzzz"' in called)
            self.failUnless(' --ramdisk "ari-zzzzzz"' in called)
            self.failUnless(' --productcodes "asdfg,hjkl"' in called)
        finally:
            util.rmtree(bundlePath)

    def testUploadAMIBundle(self):
        g = self.getHandler(buildtypes.AMI)
        pathToManifest = '/tmp/fake/path'

        self.failIf(not g.uploadAMIBundle(pathToManifest),
                "Unexpected error during upload")
        self.failUnless(isinstance(self.callLog[0], tuple))
        self.failIf(self.callLog[0][0] != \
                'ec2-upload-bundle -m /tmp/fake/path -b fake_s3_bucket ' \
                '-a fake_public_key -s fake_private_key',
                "upload call not formed as expected")
        # Check that the proxy was sent to the command
        self.assertEquals(self.callLog[0][1], {'https_proxy': 'https://jim:bar@proxy.example.com:888/', 'http_proxy': 'http://jim:bar@proxy.example.com:888/'})

    def testUploadAMIBundleNoProxy(self):
        g = self.getHandler(buildtypes.AMI)
        g.jobData['proxy'] = {}
        pathToManifest = '/tmp/fake/path'

        self.failIf(not g.uploadAMIBundle(pathToManifest),
                "Unexpected error during upload")
        self.failUnless(isinstance(self.callLog[0], tuple))
        self.failIf(self.callLog[0][0] != \
                'ec2-upload-bundle -m /tmp/fake/path -b fake_s3_bucket ' \
                '-a fake_public_key -s fake_private_key',
                "upload call not formed as expected")
        # Check that the proxy was sent to the command
        self.assertEquals(self.callLog[0][1], None)

    def testRegisterAMI(self):
        g = self.getHandler(buildtypes.AMI)
        self.initargs = None
        class FakeBoto(object):
            def __init__(s, *a, **k):
                self.initargs = (a, k)
            register_image = lambda *args, **kwargs: 'fakeAMIId'
            modify_image_attribute = lambda *args, **kwargs: None
        connect_ec2 = boto.connect_ec2
        try:
            boto.connect_ec2 = lambda *args, **kwargs: FakeBoto(*args, **kwargs)
            res = g.registerAMI('/tmp/fake_path')
            ref = ('fakeAMIId', 'fake_s3_bucket/fake_path')
            self.failIf(ref != res, "expected %s but got %s" % \
                    (str(ref), str(res)))
            self.assertEquals(self.initargs[1], {
                'proxy': 'proxy.example.com',
                'proxy_user': 'jim',
                'proxy_port': 888,
                'proxy_pass': 'bar',
                })
        finally:
            boto.connect_ec2 = connect_ec2

    def testAMIKernelMetadata(self):
        """
        Setup a chroot with a changeset that owns a files /boot/vmlinuz.* that
        has ec2-ari and ec2-aki metadata set.
        """

        # create a component
        repos = self.openRepository()
        t = self.addComponent('foo:runtime', '1.0-1-1', repos=repos,
                              fileContents=[('/boot/vmlinuz', 'foo')])

        # create some metadata
        ti = trove.TroveInfo()
        mi = trove.MetadataItem()
        mi.keyValue['ec2-ari'] = 'foo'
        mi.keyValue['ec2-aki'] = 'bar'
        ti.metadata.addItem(mi)

        tl = [(t.getName(), t.getVersion(), t.getFlavor())]

        # set the metadata on the component
        repos.setTroveInfo(zip(tl, [ti] * len(tl)))

        # install the component into a root
        self.updatePkg(self.cfg.root, t.getName(), t.getVersion())

        # close the repository
        self.stopRepository()

        # run method that we want to test
        g = self.getHandler(buildtypes.AMI)
        g.conarycfg = self.cfg
        g.cc = conaryclient.ConaryClient(self.cfg)
        g._findKernelMetadata()

        # cleanup chroot
        util.rmtree(self.cfg.root)

        # make sure the metadata was dicovered correctly
        self.failUnless(g._kernelMetadata == {
            'ec2-ari': 'foo',
            'ec2-aki': 'bar',
        })


    def testAMIOddsNEnds(self):
        g = self.getHandler(buildtypes.AMI)
        g._findKernelMetadata = lambda *args, **kwargs: None
        tmpDir = tempfile.mkdtemp()
        g.writeConaryRc = lambda *args, **kwargs: None
        g.hugeDiskMountpoint = '/mnt/huge'
        try:
            g.fileSystemOddsNEnds(tmpDir)
            f = open(os.path.join(tmpDir, 'etc', 'fstab'))
            data = f.read()
            self.failIf(data != \
                    '\n/dev/sda2\t/mnt/huge\t\text3\tdefaults 1 2' \
                    '\n/dev/sda3\tswap\t\tswap\tdefaults 0 0',
                    "Unexpected mount structure")
        finally:
            util.rmtree(tmpDir)

    def testAMIBundleError(self):
        g = self.getHandler(buildtypes.AMI)
        def badCall(cmd, *args, **kw):
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
        def badCall(cmd, *args, **kwargs):
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
        def badCall(cmd, *args, **kwargs):
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
        g.baseFlavor = deps.parseFlavor("xen,domU is: x86")
        tmpDir = tempfile.mkdtemp()
        g.workDir = tmpDir
        g.outputDir = tmpDir
        try:
            g.write()
            ref = sorted(['image.vmx'])
            res = sorted(os.listdir(os.path.join(tmpDir, 'image')))
            self.failIf(ref != res, "expected %s, but got %s" % \
                    (str(ref), str(res)))
            self.failIf(not self.callLog[0].startswith( \
                    'raw2vmdk -C 0 -H 64 -S 32 -A ide'),
                    "expected call to make vmdk")
            vmxData = open(os.path.join(tmpDir, 'image', 'image.vmx')).read()
            self.failIf("other26xlinux-64" in vmxData,
                    "expected 32 bit image")
        finally:
            util.rmtree(tmpDir)
        self.resetPopen()

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'VMware (R) Image')

    def testSCSIVMwareImage(self):
        self.injectPopen("")
        g = vmware_image.VMwareImage({}, [])

        g.makeHDImage = lambda x: open(x, 'w').write(' ')
        g.baseFlavor = deps.parseFlavor("some,random,junk is: x86_64")
        g.adapter = 'lsilogic'
        tmpDir = tempfile.mkdtemp()
        g.workDir = tmpDir
        g.outputDir = tmpDir
        try:
            g.write()
            ref = sorted(['image.vmx'])
            res = sorted(os.listdir(os.path.join(tmpDir, 'image')))
            self.failIf(ref != res, "expected %s, but got %s" % \
                    (str(ref), str(res)))
            self.failIf(not self.callLog[0].startswith( \
                    'raw2vmdk -C 1 -H 64 -S 32 -A lsilogic'),
                    "expected call to make vmdk")
            vmxData = open(os.path.join(tmpDir, 'image', 'image.vmx')).read()
            self.failIf("other26xlinux-64" not in vmxData,
                    "expected 64 bit image")
        finally:
            util.rmtree(tmpDir)
        self.resetPopen()

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'VMware (R) Image')

    def testVMwareOVFImage(self):
        self.injectPopen("")
        g = vmware_image.VMwareOVFImage({}, [])

        g.makeHDImage = lambda x: open(x, 'w').write(' ')
        g.baseFlavor = deps.parseFlavor("some,random,junk is: x86_64")
        g.adapter = 'lsilogic'
        tmpDir = tempfile.mkdtemp()
        g.workDir = tmpDir
        g.outputDir = tmpDir

        try:
            g.write()
            ref = sorted(['image.ovf'])
            res = sorted(os.listdir(os.path.join(tmpDir, 'image')))
            self.failIf(ref != res, "expected %s, but got %s" % \
                    (str(ref), str(res)))
            self.failIf(not self.callLog[0].startswith( \
                    'raw2vmdk -C 1 -H 64 -S 32 -s'),
                    "expected call to make vmdk")
            ovfData = open(os.path.join(tmpDir, 'image', 'image.ovf')).read()
            self.failIf('ovf:id="107"' not in ovfData)
            self.failIf('ovf:id="36"' in ovfData)
            self.failIf('<rasd:Caption>scsiController0</rasd:Caption>' not in ovfData)
            self.failIf('@' in ovfData)
            self.failIf('<!--' in ovfData)
            self.failIf('-->' in ovfData)
            self.failIf('<rasd:Connection>bridged</rasd:Connection>' not in ovfData)
            self.failIf('ovf:capacity="1"' not in ovfData)
            self.failIf('<File ovf:href="image.vmdk" ovf:id="file1" ovf:size="0"' not in ovfData)
        finally:
            util.rmtree(tmpDir)
        self.resetPopen()

        self.assertEquals(len(g.posted_output), 1)
        self.assertEquals(g.posted_output[0][1], 'VMware (R) OVF Image')

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
            res = g.prepareTemplates(tmpDir, None)
            self.failIf(os.listdir(tmpDir) != ['rPath'],
                    "productDir not created")
            self.failIf(sorted(os.listdir(os.path.join(tmpDir, g.productDir))) \
                    != ['base', 'changesets'], "subdirs not created")
            self.failIf(ref != res, "expected %s but got %s" % (ref, res))
            self.failIf(g.setupKickstart(tmpDir) != None,
                    "expected stubbed function")
            self.failIf(g.writeProductImage(tmpDir, 'x86') != None,
                    "expected stubbed function")
        finally:
            util.rmtree(tmpDir)

    def testUpdateISOOverride(self):
        def fail(*args, **kwargs):
            raise RuntimeError("This call should not have been made")

        g = update_iso.UpdateIso({}, [])

        retrieveTemplates = g.__class__.__base__.retrieveTemplates
        g.__class__.__base__.retrieveTemplates = fail

        prepareTemplates = g.__class__.__base__.prepareTemplates
        g.__class__.__base__.prepareTemplates = fail
        tmpDir = tempfile.mkdtemp()
        try:
            g.prepareTemplates(tmpDir, None)
            g.retrieveTemplates()
        finally:
            g.__class__.__base__.retrieveTemplates = retrieveTemplates
            g.__class__.__base__.prepareTemplates = prepareTemplates
            util.rmtree(tmpDir)

class GeneratorsMetaTest(jobslave_helper.ExecuteLoggerTest):
    def testUpdateIsoApi(self):
        # this test exists to force engineers to pay attention to how api
        # changes in installable ISO can affect update ISO
        ignoreList = []

        updateIsoFuncs = [x for x in \
                update_iso.UpdateIso.__dict__.iteritems() if callable(x[1])]
        installableIsoFuncs = dict([x for x in \
                installable_iso.InstallableIso.__dict__.iteritems() \
                if callable(x[1])])
        for funcName, ufunc in updateIsoFuncs:
            uargs, uvarargs, uvarkw, udefaults = inspect.getargspec(ufunc)
            ifunc = installableIsoFuncs.get(funcName)
            self.failIf(not ifunc and funcName not in ignoreList,
                    "%s is a member function of updateIso but not installIso" \
                            % funcName)
            iargs, ivarargs, ivarkw, idefaults = inspect.getargspec(ifunc)
            self.failIf(uargs != iargs,
                    "%s method in update ISO is probably " \
                            "missing these args: %s" % (funcName,
                                str([x for x in iargs if x not in uargs])))
            self.failIf(uvarargs != ivarargs,
                    "%s method in update ISO does not match variable args" % \
                            funcName)
            self.failIf(uvarkw != ivarkw,
                    "%s method in update ISO does not match keyword args" % \
                            funcName)


if __name__ == "__main__":
    testsuite.main()
