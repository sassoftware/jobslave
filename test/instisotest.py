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

from conary.lib import util, sha1helper
from conary.deps import deps

from mint import buildtypes

import jobslave_helper
from jobslave.generators import installable_iso
from jobslave import flavors
from jobslave import splitdistro
from jobslave.generators import anaconda_images

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


if __name__ == "__main__":
    testsuite.main()
