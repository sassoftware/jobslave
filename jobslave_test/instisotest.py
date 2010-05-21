#!/usr/bin/python
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import httplib
import os
import tempfile
import time
import StringIO

from conary.lib import util, sha1helper
from conary.deps import deps
from conary import versions


import jobslave_helper
from jobslave.generators import anaconda_images
from jobslave.generators import constants
from jobslave.generators import installable_iso
from jobslave import buildtypes
from jobslave import flavors
from jobslave import splitdistro
from jobslave import gencslist

from testrunner import pathManager

class InstallableIsoTest(jobslave_helper.JobSlaveHelper):
    def testGetArchFlavor(self):
        f = deps.parseFlavor("use: blah is: x86")
        self.failUnlessEqual(installable_iso.getArchFlavor(f).freeze(), flavors.pathSearchOrder[1])

        f = deps.parseFlavor("use: blah is: x86 x86_64")
        self.failUnlessEqual(installable_iso.getArchFlavor(f).freeze(), flavors.pathSearchOrder[0])

        f = deps.parseFlavor("use: foo")
        self.failUnlessEqual(installable_iso.getArchFlavor(f), None)

    def testCloneTree(self):
        def mkfile(path, fileName, contents = ""):
            tmpFile = open(os.path.join(path, fileName), 'w')
            tmpFile.write(contents)
            tmpFile.close()

        def getContents(*args):
            tmpFile = open(os.path.join(*args))
            res = tmpFile.read()
            tmpFile.close()
            return res

        # prepare source dir
        srcDir = tempfile.mkdtemp()
        subDir = os.path.join(srcDir, 'subdir')
        os.mkdir(subDir)
        destDir = tempfile.mkdtemp()

        # stock some initial files in the source tree
        mkfile(srcDir, 'EULA', "Nobody expects the Spanish Inquisition!")
        mkfile(srcDir, 'LICENSE', "Tell him we've already got one.")
        mkfile(subDir, 'README', "None shall pass.")

        # now make a colliding dir
        os.mkdir(os.path.join(srcDir, 'collide'))
        os.mkdir(os.path.join(destDir, 'collide'))

        # and collide a file
        mkfile(destDir, 'LICENSE', "Spam, Spam, Spam, Spam...")

        try:
            splitdistro.lndir(srcDir, destDir)
            # ensure basic files were cloned
            assert(getContents(destDir, 'EULA') == getContents(srcDir, 'EULA'))

            # ensure initial contents were overwritten
            self.failUnless(getContents(destDir, 'LICENSE') == \
                            getContents(srcDir, 'LICENSE'),
                            "File contents were not replaced.")

            # ensure sub directories were properly traversed
            assert(getContents(destDir, 'subdir', 'README') == \
                   "None shall pass.")
        finally:
            # clean up dirs
            util.rmtree(srcDir)
            util.rmtree(destDir)

    def testAnacondaImages(self):
        fontPath = '/usr/share/fonts/bitstream-vera/Vera.ttf'
        if not os.path.exists(fontPath):
            raise testsuite.SkipTestException("Vera.ttf is missing")
        tmpDir = tempfile.mkdtemp()
        ai = anaconda_images.AnacondaImages("Mint Test Suite",
            os.path.join(pathManager.getPath("JOB_SLAVE_PATH"),"pixmaps"),
            tmpDir, fontPath)
        ai.processImages()

        files = set(['first-lowres.png', 'anaconda_header.png',
            'progress_first.png', 'syslinux-splash.png',
            'first.png', 'splash.png', 'progress_first-375.png'])
        self.failUnlessEqual(files, set(os.listdir(tmpDir)))

    def testLinkRecurse(self):
        d1 = tempfile.mkdtemp()
        d2 = tempfile.mkdtemp()

        util.mkdirChain(d1 + "/bar")
        file(d1 + "/foo", "w").write("hello world")
        file(d1 + "/bar/baz", "w").write("goodbye world")

        installable_iso._linkRecurse(d1, d2)

        # make sure that linkRecurse recursively links files and dirs
        assert(os.path.exists(d2 + "/foo"))
        assert(os.path.exists(d2 + "/bar/baz"))

    def testBuildStamp(self):
        ii = self.getHandler(buildtypes.INSTALLABLE_ISO)

        d = tempfile.mkdtemp()

        ii.writeBuildStamp(d)
        lines = open(d + "/.buildstamp").readlines()
        self.failUnlessEqual(lines[1], 'Test Project\n')
        self.failUnlessEqual(lines[5],
                'group-core /conary.rpath.com@rpl:1/0.000:1.0.1-1-1 1#x86\n')

    def testConaryClient(self):
        ii = self.getHandler(buildtypes.INSTALLABLE_ISO)

        # check the returned conary client cfg for sanity
        cc = ii.getConaryClient('/', '1#x86')
        self.failUnlessEqual(str(cc.cfg.installLabelPath), "[Label('conary.rpath.com@rpl:1')]")

    def checkSha1(self, fileName, sum):
        assert(sha1helper.sha1ToString(sha1helper.sha1FileBin(fileName)) == sum)

    def testConvertSplash(self):
        if not os.path.exists('/usr/bin/pngtopnm'):
            raise testsuite.SkipTestException("pngtopnm is not installed")
        ii = self.getHandler(buildtypes.INSTALLABLE_ISO)

        d1 = tempfile.mkdtemp()
        d2 = tempfile.mkdtemp()

        util.mkdirChain(os.path.join(d1, 'isolinux'))
        util.mkdirChain(os.path.join(d2, 'pixmaps'))
        util.copyfile(os.path.join(pathManager.getPath('JOB_SLAVE_ARCHIVE_PATH'), 'syslinux-splash.png'),
                      os.path.join(d2, 'pixmaps', 'syslinux-splash.png'))
        self.suppressOutput(ii.convertSplash, d1, d2)

        result = os.path.join(d1, 'isolinux', 'splash.lss')
        self.checkSha1(result, 'b36af127d5336db0a39a9955cd44b3a8466aa048')

    def testMissedFlavor(self):
        flv = deps.parseFlavor('is: trash')
        res = installable_iso.getArchFlavor(flv)
        ref = deps.Flavor()
        self.failIf(res != ref, "expected '%s' but got '%s'" % (ref, res))


class InstallIso2Test(jobslave_helper.ExecuteLoggerTest):
    bases = {}

    def status(self, msg):
        self.messages.append(msg)

    def setUp(self):
        self.messages = []
        self.savedTmpDir = constants.tmpDir
        constants.tmpDir = tempfile.mkdtemp()
        jobslave_helper.ExecuteLoggerTest.setUp(self)

    def testGetUpdateJob(self):
        troveName = 'test'
        troveFlavor = deps.parseFlavor('is: x86')

        class DummyClient(object):
            def updateChangeSet(xself, job, **kwargs):
                self.failUnlessEqual(job, [(troveName, (None, None),
                    (troveVersion, troveFlavor), True)])
                return ('uJob', 'suggMap')
        def getBuildData(field):
            self.failUnlessEqual(field, 'anaconda-custom')
            return '%s=%s[%s]' % (troveName, troveVersionString, troveFlavor)
        cclient = DummyClient()
        g = self.getHandler(buildtypes.INSTALLABLE_ISO)
        g.callback = installable_iso.Callback(self.status)
        g.getBuildData = getBuildData

        # Normal version (e.g. from user entry)
        troveVersion = versions.VersionFromString(
                '/test.rpath.local@rpl:1/1.2-3-4')
        troveVersionString = troveVersion.asString()
        self.failUnlessEqual(g._getUpdateJob(cclient, 'anaconda-custom'),
                'uJob')

        # Frozen version (e.g. from trove picker)
        troveVersion = versions.ThawVersion(
                '/test.rpath.local@rpl:1/1234567890.0:1.2-3-4')
        troveVersionString = troveVersion.freeze()
        self.failUnlessEqual(g._getUpdateJob(cclient, 'anaconda-custom'),
                'uJob')

    def testGetNVF(self):
        class DummyUJob(object):
            getPrimaryJobs = lambda *args, **kwargs: [('1', '2', '34')]
        g = self.getHandler(buildtypes.INSTALLABLE_ISO)
        res = g._getNVF(DummyUJob())
        ref = ('1', '3', '4')
        self.failIf(ref != res, "_getNVF returned incorrect results")

    def testWriteProductImage(self):
        class FakeClient(object):
            def __init__(x):
                x.cfg = x
                x.installLabelPath = [versions.Label('test.rpath.local@rpl:1')]
            setUpdateCallback = lambda *args, **kwargs: None
            applyUpdate = lambda *args, **kwargs: None

        class DummyImages(object):
            processImages = lambda *args, **kwargs: None
            __init__ = lambda *args, **kwargs: None

        topdir = tempfile.mkdtemp()
        AnacondaImages = installable_iso.AnacondaImages
        unlink = os.unlink
        try:
            self.touch(os.path.join(topdir, 'isolinux', 'test.msg'))
            os.unlink = lambda *args, **kwargs: None
            installable_iso.AnacondaImages = DummyImages
            g = self.getHandler(buildtypes.INSTALLABLE_ISO)
            g.callback = installable_iso.Callback(self.status)
            g.jobData['name'] = 'test build'
            g.baseTrove = 'baseTrove'
            g.baseFlavor = deps.Flavor()
            g.getConaryClient = lambda *args, **kwargs: FakeClient()
            g._getUpdateJob = lambda *args, **kwargs: True
            g._getLabelPath = lambda *args, **kwargs: ""
            g.writeProductImage(topdir, 'x86')
            self.failUnlessEqual([x[0] for x in self.callLog],
                    ['sed', 'tar', 'tar', 'tar', 'tar', '/usr/bin/mkcramfs'])
        finally:
            os.unlink = unlink
            installable_iso.AnacondaImages = AnacondaImages
            util.rmtree(topdir)

    def testBuildIsos(self):
        basedir = tempfile.mkdtemp()
        popen = os.popen
        rename = os.rename
        # tested function changes dirs.
        cwd = os.getcwd()
        try:
            os.popen = lambda *args, **kwargs: StringIO.StringIO('734003201')
            os.rename = lambda a, b: self.touch(b)
            topdir = os.path.join(basedir, 'topdir')
            self.touch(os.path.join(topdir, 'images', 'boot.iso'))
            disc1 = os.path.join(basedir, 'disc1')
            util.mkdirChain(disc1)
            disc2 = os.path.join(basedir, 'disc2')
            self.touch(os.path.join(disc2, 'isolinux', 'isolinux.bin'))
            util.mkdirChain(os.path.join(basedir, 'junk'))
            g = self.getHandler(buildtypes.INSTALLABLE_ISO)
            g.basefilename = 'testcase'
            g.jobData['name'] = 'test build'
            g.jobData['project'] = {}
            g.jobData['project']['name'] = 'test project'
            g.buildIsos(topdir)
            self.failIf(len(self.callLog) != 4, "incorrect number of calls")
        finally:
            os.chdir(cwd)
            os.popen = popen
            os.rename = rename
            util.rmtree(basedir)

    def testBuildIsosFailure(self):
        basedir = tempfile.mkdtemp()
        popen = os.popen
        rename = os.rename
        # tested function changes dirs.
        cwd = os.getcwd()
        try:
            os.popen = lambda *args, **kwargs: StringIO.StringIO('734003201')
            os.rename = lambda a, b: None
            topdir = os.path.join(basedir, 'topdir')
            self.touch(os.path.join(topdir, 'images', 'boot.iso'))
            disc1 = os.path.join(basedir, 'disc1')
            util.mkdirChain(disc1)
            g = self.getHandler(buildtypes.INSTALLABLE_ISO)
            g.basefilename = ''
            g.jobData['name'] = 'test build'
            g.jobData['project'] = {}
            g.jobData['project']['name'] = 'test project'
            g.jobData['project']['hostname'] = 'test'
            self.assertRaises(RuntimeError, g.buildIsos, topdir)
        finally:
            os.chdir(cwd)
            os.popen = popen
            os.rename = rename
            util.rmtree(basedir)

    def testSetupKickstart(self):
        g = self.getHandler(buildtypes.INSTALLABLE_ISO)
        ilcContents = """default linux
prompt 1
timeout 600
display boot.msg
F1 boot.msg
F2 options.msg
F3 general.msg
F4 param.msg
F5 rescue.msg
F7 snake.msg
label linux
  kernel vmlinuz
  append initrd=initrd.img ramdisk_size=8192
label text
  kernel vmlinuz
  append initrd=initrd.img text ramdisk_size=8192
label expert
  kernel vmlinuz
  append expert initrd=initrd.img ramdisk_size=8192
label ks
  kernel vmlinuz
  append ks initrd=initrd.img ramdisk_size=8192
label lowres
  kernel vmlinuz
  append initrd=initrd.img lowres ramdisk_size=8192
label local
  localboot 1
"""

        ilcValidContents = """default kscdrom
prompt 1
timeout 600
display boot.msg
F1 boot.msg
F2 options.msg
F3 general.msg
F4 param.msg
F5 rescue.msg
F7 snake.msg
label linux
  kernel vmlinuz
  append initrd=initrd.img ramdisk_size=8192
label text
  kernel vmlinuz
  append initrd=initrd.img text ramdisk_size=8192
label expert
  kernel vmlinuz
  append expert initrd=initrd.img ramdisk_size=8192
label ks
  kernel vmlinuz
  append ks initrd=initrd.img ramdisk_size=8192
label lowres
  kernel vmlinuz
  append initrd=initrd.img lowres ramdisk_size=8192
label local
  localboot 1
label kscdrom
  kernel vmlinuz
  append initrd=initrd.img ramdisk_size=8192 ks=cdrom
"""
            
        ilcNewContents = g.addKsBootLabel( [ x + "\n" for x in ilcContents.splitlines() ] )
        self.failIf("".join(ilcNewContents) != ilcValidContents, "kscdrom boot entry addition failed")

    def testPrepareTemplates(self):
        topdir = tempfile.mkdtemp()
        templateDir = tempfile.mkdtemp()
        try:
            self.touch(os.path.join(templateDir, 'isolinux', 'test.msg'))
            g = self.getHandler(buildtypes.INSTALLABLE_ISO)
            res = g.prepareTemplates(topdir, templateDir)
            ref = os.path.join(topdir, 'rPath', 'changesets')
            self.failIf(ref != res, "expected %s but got %s" % (ref, res))
        finally:
            util.rmtree(topdir)
            util.rmtree(templateDir)

    def testExtractMediaTemplate(self):
        class FakeClient(object):
            def __init__(x, root):
                x.root = root
                x.cfg = x
                x.installLabelPath = [versions.Label('test.rpath.local@rpl:1')]
            def applyUpdate(x, *args, **kwargs):
                self.touch(os.path.join(x.root,
                    'usr', 'lib', 'media-template', 'all', 'stuff'))
                self.touch(os.path.join(x.root, 'all', 'stuff'))

        topdir = tempfile.mkdtemp()
        try:
            g = self.getHandler(buildtypes.INSTALLABLE_ISO)
            g.baseFlavor = deps.parseFlavor('is: x86')
            g.getConaryClient = lambda root, *args, **kwargs: FakeClient(root)
            g.callback = installable_iso.Callback(self.status)
            g._getUpdateJob = lambda *args, **kwargs: 'bogus'

            g.extractMediaTemplate(topdir)
            self.failIf(len(self.callLog) != 2, "unexpected number of calls")
        finally:
            util.rmtree(topdir)

    def testMissingMediaTemplate(self):
        class FakeClient(object):
            def __init__(x, root):
                x.root = root
                x.cfg = x
                x.installLabelPath = [versions.Label('test.rpath.local@rpl:1')]

        topdir = tempfile.mkdtemp()
        try:
            g = self.getHandler(buildtypes.INSTALLABLE_ISO)
            g.baseFlavor = deps.parseFlavor('is: x86')
            g.getConaryClient = lambda root, *args, **kwargs: FakeClient(root)
            g.callback = installable_iso.Callback(self.status)
            g._getUpdateJob = lambda *args, **kwargs: None

            g.extractMediaTemplate(topdir)
            self.failIf(len(self.callLog) != 0, "unexpected number of calls")
        finally:
            util.rmtree(topdir)

    def testExtractChangeSets(self):
        class FakeTreeGenerator(object):
            parsePackageData = lambda *args, **kwargs: None
            extractChangeSets = lambda *args, **kwargs: None

        class FakeClient(object):
            def __init__(x, root):
                x.root = root
                x.cfg = x
                x.installLabelPath = [versions.Label('test.rpath.local@rpl:1')]
            createChangeSet = lambda *args, **kwargs: None

        csdir = tempfile.mkdtemp()
        clientVersion = 38
        getArchFlavor = installable_iso.getArchFlavor
        TreeGenerator = gencslist.TreeGenerator
        try:
            gencslist.TreeGenerator = lambda *args, **kwargs: \
                    FakeTreeGenerator()

            installable_iso.getArchFlavor = lambda x: deps.Flavor()
            g = self.getHandler(buildtypes.INSTALLABLE_ISO)
            g.baseFlavor = deps.Flavor()
            g.troveFlavor = deps.Flavor()
            g.getConaryClient = lambda root, *args, **kwargs: FakeClient(root)
            g.troveName = 'test'
            g.callback = installable_iso.Callback(self.status)
            g.extractChangeSets(csdir, clientVersion)
        finally:
            gencslist.TreeGenerator = TreeGenerator
            installable_iso.getArchFlavor = getArchFlavor
            util.rmtree(csdir)

    def testWrite(self):
        class FakeTreeGenerator(object):
            parsePackageData = lambda *args, **kwargs: None
            extractChangeSets = lambda *args, **kwargs: None
            writeCsList = lambda *args, **kwargs: None
            writeGroupCs = lambda *args, **kwargs: None

        tmpDir = tempfile.mkdtemp()
        getArchFlavor = installable_iso.getArchFlavor
        splitDistro = splitdistro.splitDistro
        try:
            splitdistro.splitDistro = lambda *args, **kwargs: None
            installable_iso.getArchFlavor = lambda *args, **kwargs: \
                    deps.Flavor()
            g = self.getHandler(buildtypes.INSTALLABLE_ISO)
            g._setupTrove = lambda *args, **kwargs: None
            g.extractChangeSets = lambda *args, **kwargs: FakeTreeGenerator()
            g.retrieveTemplates = lambda *args, **kwargs: (tmpDir, 38)
            g.prepareTemplates = lambda *args, **kwargs: (tmpDir, 38)
            g.extractMediaTemplate = lambda *args, **kwargs: None
            g.extractPublicKeys = lambda *args, **kwargs: None
            g.setupKickstart = lambda *args, **kwargs: None
            g.writeProductImage = lambda *args, **kwargs: None
            g.buildIsos = lambda *args, **kwargs: None
            g.baseFlavor = deps.Flavor()
            g.status = self.status
            g.jobData['name'] = 'test build'
            g.troveName = 'test'
            g.maxIsoSize = 650 * 1024 * 1024
            g.buildOVF10 = False
            g.write()
        finally:
            splitdistro.splitDistro = splitDistro
            installable_iso.getArchFlavor = getArchFlavor
            util.rmtree(tmpDir)


class CallbackTest(jobslave_helper.JobSlaveHelper):
    def status(self, msg):
        self.messages.append(msg)

    def setUp(self):
        self.messages = []
        self.__class__.__base__.setUp(self)

    def testRequestingChangeSet(self):
        cb = installable_iso.Callback(self.status)
        cb.setChangeSet('foo')
        cb.requestingChangeSet()
        self.failIf(self.messages != ['Requesting foo from repository'])

    def testDownloadingChangeSet(self):
        cb = installable_iso.Callback(self.status)
        cb.setChangeSet('foo')
        cb.downloadingChangeSet(0, 1024)
        self.failIf(self.messages != \
                ['Downloading foo from repository (0% of 1k)'])

    def testDownloadingFileContents(self):
        cb = installable_iso.Callback(self.status)
        cb.setChangeSet('foo')
        cb.downloadingFileContents(0, 1024)
        self.failIf(self.messages != \
                ['Downloading files for foo from repository (0% of 1k)'])

    def testPrefix(self):
        cb = installable_iso.Callback(self.status)
        cb.setChangeSet('foo')
        cb.setPrefix('test: ')
        cb.downloadingFileContents(0, 1024)
        self.failIf(self.messages != \
                ['test: Downloading files for foo from repository (0% of 1k)'])


if __name__ == "__main__":
    testsuite.main()
