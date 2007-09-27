#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import httplib
import os
import re
import tempfile
import time
import simplejson
import StringIO

import image_stubs

from conary.lib import util, sha1helper
from conary.deps import deps
from conary import versions

from mint import buildtypes

import jobslave_helper
from jobslave.generators import installable_iso
from jobslave.generators import constants
from jobslave import flavors
from jobslave import splitdistro
from jobslave.generators import anaconda_images
from jobslave import gencslist

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
            self.failIf(getContents(destDir, 'LICENSE') == \
                        getContents(srcDir, 'LICENSE'),
                        "File contents were illegally overridden.")

            # ensure sub directories were properly traversed
            assert(getContents(destDir, 'subdir', 'README') == \
                   "None shall pass.")
        finally:
            # clean up dirs
            util.rmtree(srcDir)
            util.rmtree(destDir)

    def testAnacondaImages(self):
        tmpDir = tempfile.mkdtemp()
        ai = anaconda_images.AnacondaImages("Mint Test Suite",
            "../pixmaps/", tmpDir,
            "/usr/share/fonts/bitstream-vera/Vera.ttf")
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
        x = open(d + "/.buildstamp").read()
        self.failUnless('Test Project' in x)
        self.failUnless('group-core /conary.rpath.com@rpl:1/0:1.0.1-1-1 1#x86' in x)

    def testConaryClient(self):
        ii = self.getHandler(buildtypes.INSTALLABLE_ISO)
        ii._setupTrove()

        # check the returned conary client cfg for sanity
        cc = ii.getConaryClient('/', '1#x86')
        self.failUnlessEqual(str(cc.cfg.installLabelPath), "[Label('conary.rpath.com@rpl:1')]")

    def checkSha1(self, fileName, sum):
        assert(sha1helper.sha1ToString(sha1helper.sha1FileBin(fileName)) == sum)

    def testConvertSplash(self):
        ii = self.getHandler(buildtypes.INSTALLABLE_ISO)

        d1 = tempfile.mkdtemp()
        d2 = tempfile.mkdtemp()

        util.mkdirChain(os.path.join(d1, 'isolinux'))
        util.mkdirChain(os.path.join(d2, 'pixmaps'))
        util.copyfile(os.path.join(self.testDir, 'archive', 'syslinux-splash.png'),
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

        self.bases['LiveISO'] = installable_iso.InstallableIso.__bases__
        installable_iso.InstallableIso.__bases__ = \
                (image_stubs.ImageGeneratorStub,)

    def tearDown(self):
        installable_iso.InstallableIso.__bases__ = self.bases['LiveISO']
        jobslave_helper.ExecuteLoggerTest.tearDown(self)

    def testGetMasterIPAddress(self):
        g = installable_iso.InstallableIso({}, [])
        getSlaveRuntimeConfig = installable_iso.getSlaveRuntimeConfig
        try:
            installable_iso.getSlaveRuntimeConfig = lambda: \
                    {'MASTER_IP': 'junk'}
            res = g._getMasterIPAddress()
            ref = 'junk'
            self.failIf(ref != res, "Master IP was not honored")
        finally:
            installable_iso.getSlaveRuntimeConfig = getSlaveRuntimeConfig

    def testGetUpdateJob(self):
        class DummyClient(object):
            updateChangeSet = lambda *args, **kwargs: ('uJob', 'suggMap')
        g = installable_iso.InstallableIso({}, [])
        g.callback = installable_iso.Callback(self.status)
        cclient = DummyClient()
        troveSpec = 'test=/test.rpath.local@rpl:1/1-1-1[is: x86]'
        troveName = troveSpec.split('=')[0]
        g.getBuildData = lambda key: troveSpec
        res = g._getUpdateJob(cclient, troveName)
        ref = 'uJob'
        self.failIf(res != ref, "getUpdateJob did not perform as expected")

    def testGetNVF(self):
        class DummyUJob(object):
            getPrimaryJobs = lambda *args, **kwargs: [('1', '2', '34')]
        g = installable_iso.InstallableIso({}, [])
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
            g = installable_iso.InstallableIso({}, [])
            g.callback = installable_iso.Callback(self.status)
            g.jobData['name'] = 'test build'
            g.baseTrove = 'baseTrove'
            g.baseFlavor = deps.Flavor()
            g.getConaryClient = lambda *args, **kwargs: FakeClient()
            g._getUpdateJob = lambda *args, **kwargs: True
            g.writeProductImage(topdir, 'x86')
            self.failIf(len(self.callLog) != 9, "unexpected number of calls")
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
            g = installable_iso.InstallableIso({}, [])
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
            g = installable_iso.InstallableIso({}, [])
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
        topdir = tempfile.mkdtemp()
        try:
            g = installable_iso.InstallableIso({}, [])
            self.touch(os.path.join(topdir, 'media-template',
                'disc1', 'ks.cfg'))
            g.setupKickstart(topdir)
            self.failIf(len(self.callLog) != 1, "incorrect number of calls")
            self.failIf(not self.callLog[0].startswith('sed -i'),
                    "expected sed to be called")
        finally:
            util.rmtree(topdir)

    def testRetrieveTemplates(self):
        self.count = 0
        self.returnCodes = [202, 303, 200, 200]
        class FakeResponse(object):
            fp = 0
            def __init__(x, status):
                x.status = status
            read = lambda *args: 'bogus status'
            def getheader(x, hdr):
                if hdr == 'Content-Type':
                   return (self.count == 3) \
                           and 'text/plain' or 'application/x-tar'
                elif hdr == 'Location':
                    return 'http://127.0.0.1:8003?stuff'

        class DummyConnection(object):
            close = lambda *args, **kwargs: None
            connect = lambda *args, **kwargs: None
            request = lambda *args, **kwargs: None
            def getresponse(x):
                self.count += 1
                return FakeResponse(self.returnCodes[self.count - 1])

        class FakeClient(object):
            def __init__(x):
                x.cfg = x
                x.installLabelPath = [versions.Label('test.rpath.local@rpl:1')]

        class FakeUJob(object):
            getPrimaryJobs = lambda *args, **kwargs: []

        HTTPConnection = httplib.HTTPConnection
        sleep = time.sleep
        try:
            time.sleep = lambda x: None
            httplib.HTTPConnection = lambda *args, **kwargs: DummyConnection()
            g = installable_iso.InstallableIso({}, [])
            g.baseFlavor = deps.parseFlavor('is: x86')
            g.getConaryClient = lambda *args, **kwargs: FakeClient()
            g.callback = installable_iso.Callback(self.status)
            g._getUpdateJob = lambda *args, **kwargs: FakeUJob()
            g._getNVF = lambda *args, **kwargs: ('test',
                    versions.VersionFromString( \
                            '/test.rpath.local@rpl:1/1-1-1'),
                    deps.parseFlavor('is: x86'))
            g._getMasterIPAddress = lambda *args, **kwargs: '127.0.0.1'
            res = g.retrieveTemplates()
            self.failIf(not res[0].endswith('unified'),
                    "expected unified tree")
        finally:
            time.sleep = sleep
            httplib.HTTPConnection = HTTPConnection

    def testPrepareTemplates(self):
        topdir = tempfile.mkdtemp()
        templateDir = tempfile.mkdtemp()
        try:
            self.touch(os.path.join(templateDir, 'isolinux', 'test.msg'))
            g = installable_iso.InstallableIso({}, [])
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
            g = installable_iso.InstallableIso({}, [])
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
            g = installable_iso.InstallableIso({}, [])
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
            g = installable_iso.InstallableIso({}, [])
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
            g = installable_iso.InstallableIso({}, [])
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
