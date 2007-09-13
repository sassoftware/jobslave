#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import os
import tempfile

import jobslave_helper
import image_stubs

from jobslave.generators import constants
from jobslave.generators import live_iso

from conary.lib import util

class LiveIsoTest(jobslave_helper.ExecuteLoggerTest):
    bases = {}
    def setUp(self):
        self.savedTmpDir = constants.tmpDir
        constants.tmpDir = tempfile.mkdtemp()
        jobslave_helper.ExecuteLoggerTest.setUp(self)

        self.bases['LiveISO'] = live_iso.LiveIso.__bases__
        live_iso.LiveIso.__bases__ = (image_stubs.BootableImageStub,)

        constants.templateDir = os.path.join(os.path.dirname( \
                os.path.dirname(os.path.abspath(__file__))), 'templates')

        constants.templateDir = os.path.join(os.path.dirname( \
                os.path.dirname(os.path.abspath(__file__))), 'templates')


    def tearDown(self):
        live_iso.LiveIso.__bases__ = self.bases['LiveISO']
        util.rmtree(constants.tmpDir, ignore_errors = True)
        constants.tmpDir = self.savedTmpDir
        jobslave_helper.ExecuteLoggerTest.tearDown(self)

    def touch(self, fn):
        if not os.path.exists(fn):
            util.mkdirChain(os.path.split(fn)[0])
            f = open(fn, 'w')
            f.write('')
            f.close()

    def testIterFiles(self):
        tmpDir = tempfile.mkdtemp()
        try:
            g = live_iso.LiveIso({}, [])
            for fn in ('foobar', 'foobaz', 'test'):
                self.touch(os.path.join(tmpDir, fn))
            res = sorted([x for x in g.iterFiles(tmpDir, 'foo')])
            ref = [os.path.join(tmpDir, 'foobar'),
                    os.path.join(tmpDir, 'foobaz')]
            self.failIf(ref != res, "expected %s but got %s" % \
                    (str(ref), str(res)))
        finally:
            util.rmtree(tmpDir)

    def testCopyFallback(self):
        fallbackDir = tempfile.mkdtemp()
        srcDir = tempfile.mkdtemp()
        destDir = tempfile.mkdtemp()
        try:
            g = live_iso.LiveIso({}, [])
            g.fallback = fallbackDir
            src = os.path.join(srcDir, 'grub')
            self.touch(src)
            fallback = os.path.join(fallbackDir, 'grub')
            self.touch(fallback)
            dest = os.path.join(destDir, 'grub')
            g.copyFallback(src, dest)
            self.failIf(not os.path.exists(dest), "file was not copied")
        finally:
            util.rmtree(fallbackDir)
            srcDir = tempfile.mkdtemp()
            destDir = tempfile.mkdtemp()

    def testCopyNoFallback(self):
        class FakePipe(object):
            def read(self):
                return 'statically'
            close = lambda *args, **kwargs: None

        fallbackDir = tempfile.mkdtemp()
        srcDir = tempfile.mkdtemp()
        destDir = tempfile.mkdtemp()
        popen = os.popen
        try:
            os.popen = lambda *args, **kwargs: FakePipe()
            g = live_iso.LiveIso({}, [])
            g.fallback = fallbackDir
            src = os.path.join(srcDir, 'grub')
            self.touch(src)
            dest = os.path.join(destDir, 'grub')
            g.copyFallback(src, dest)
            self.failIf(not os.path.exists(dest), "file was not copied")
        finally:
            util.rmtree(fallbackDir)
            srcDir = tempfile.mkdtemp()
            destDir = tempfile.mkdtemp()
            os.popen = popen

    def testGetVolName(self):
        g = live_iso.LiveIso({}, [])
        g.jobData['project'] = {}
        g.jobData['project']['name'] = 'test name 123'
        ref = 'test_name_123'
        res = g.getVolName()
        self.failIf(ref != res, "expected %s, but got %s" % (ref, res))

    def testIsoNameCD(self):
        class FakePipe(object):
            def read(self):
                return '5000'
            close = lambda *args, **kwargs: None

        g = live_iso.LiveIso({}, [])
        fd, tmpFile = tempfile.mkstemp()
        os.close(fd)
        popen = os.popen
        try:
            os.popen = lambda *args, **kwargs: FakePipe()
            res = g.isoName(tmpFile)
            ref = 'Demo CD (Live CD)'
            self.failIf(ref != res, "expected %s, but got %s" % (ref, res))
        finally:
            os.unlink(tmpFile)
            os.popen = popen

    def testIsoNameDVD(self):
        class FakePipe(object):
            def read(self):
                return '734003201'
            close = lambda *args, **kwargs: None

        g = live_iso.LiveIso({}, [])
        fd, tmpFile = tempfile.mkstemp()
        os.close(fd)
        popen = os.popen
        try:
            os.popen = lambda *args, **kwargs: FakePipe()
            res = g.isoName(tmpFile)
            ref = 'Demo DVD (Live DVD)'
            self.failIf(ref != res, "expected %s, but got %s" % (ref, res))
        finally:
            os.unlink(tmpFile)
            os.popen = popen

    def testWriteZisofs(self):
        self.injectPopen("")
        g = live_iso.LiveIso({}, [])
        g.jobData['project'] = {}
        g.jobData['project']['name'] = 'test name 123'
        g.zisofs = True
        g.makeLiveCdTree = lambda *args, **kwargs: None
        g.isoName = lambda *args, **kwargs: 'DUmmy Name'
        chmod = os.chmod
        try:
            os.chmod = lambda *args, **kwargs: None
            g.write()
            self.failIf(len(self.callLog) != 4,
                    "wrong number of calls made")
            self.failIf(len([x for x in self.callLog if 'mkzftree' in x]) != 1,
                    "mkzftree was not called")
        finally:
            os.chmod = chmod
        self.resetPopen()

    def testWrite(self):
        self.injectPopen("")
        g = live_iso.LiveIso({}, [])
        g.jobData['project'] = {}
        g.jobData['project']['name'] = 'test name 123'
        g.zisofs = False
        g.makeLiveCdTree = lambda *args, **kwargs: None
        g.isoName = lambda *args, **kwargs: 'DUmmy Name'
        chmod = os.chmod
        try:
            os.chmod = lambda *args, **kwargs: None
            g.write()
            self.failIf(len(self.callLog) != 4,
                    "wrong number of calls made")
            self.failIf(len([x for x in self.callLog if 'mkzftree' in x]),
                    "mkzftree was not called")
        finally:
            os.chmod = chmod
        self.resetPopen()

    def testMkinitrdUnionfs(self):
        g = live_iso.LiveIso({}, [])
        liveDir = tempfile.mkdtemp()
        fakeroot = tempfile.mkdtemp()
        g.findFile = lambda x, y: os.path.join(x, y)
        unlink = os.unlink
        try:
            os.unlink = lambda x: None
            self.touch(os.path.join(fakeroot, 'etc', 'udev', 'udev.conf'))
            self.touch(os.path.join(fakeroot, 'lib', 'modules', 'loop.ko'))
            self.touch(os.path.join(fakeroot, 'lib', 'modules', 'unionfs.ko'))
            g.getBuildData = lambda x: True
            g.mkinitrd(liveDir, fakeroot)
            self.failIf(len(self.callLog) != 2, "Unexpected number of calls")
            self.failIf(not self.callLog[0].startswith('e2fsimage'),
                    "expected e2fsimage to be used")
            self.failIf(not self.callLog[1].startswith('gzip'),
                    "expected gzip to be used")
        finally:
            util.rmtree(liveDir)
            util.rmtree(fakeroot)
            os.unlink = unlink

    def testMkinitrd(self):
        g = live_iso.LiveIso({}, [])
        liveDir = tempfile.mkdtemp()
        fakeroot = tempfile.mkdtemp()
        g.findFile = lambda x, y: os.path.join(x, y)
        unlink = os.unlink
        try:
            os.unlink = lambda x: None
            self.touch(os.path.join(fakeroot, 'etc', 'udev', 'udev.conf'))
            self.touch(os.path.join(fakeroot, 'lib', 'modules', 'loop.ko'))
            self.touch(os.path.join(fakeroot, 'lib', 'modules', 'unionfs.ko'))
            g.mkinitrd(liveDir, fakeroot)
            self.failIf(len(self.callLog) != 2, "Unexpected number of calls")
            self.failIf(not self.callLog[0].startswith('e2fsimage'),
                    "expected e2fsimage to be used")
            self.failIf(not self.callLog[1].startswith('gzip'),
                    "expected gzip to be used")
        finally:
            util.rmtree(liveDir)
            util.rmtree(fakeroot)
            os.unlink = unlink

    def testMkinitrdMissingMod(self):
        g = live_iso.LiveIso({}, [])
        liveDir = tempfile.mkdtemp()
        fakeroot = tempfile.mkdtemp()
        try:
            self.touch(os.path.join(fakeroot, 'etc', 'udev', 'udev.conf'))
            self.assertRaises(AssertionError, g.mkinitrd, liveDir, fakeroot)
        finally:
            util.rmtree(liveDir)
            util.rmtree(fakeroot)

    def testMakeLiveCdTree(self):
        g = live_iso.LiveIso({}, [])
        liveDir = tempfile.mkdtemp()
        fakeroot = tempfile.mkdtemp()
        try:
            g.mkinitrd = lambda *args, **kwargs: None
            self.touch(os.path.join(fakeroot, 'boot', 'vmlinuz.bogus'))
            g.jobData['name'] = 'test build'
            g.jobData['project'] = {}
            g.jobData['project']['name'] = 'test project'
            g.makeLiveCdTree(liveDir, fakeroot)
            ref = '\n'.join(('say Welcome to test build.',
                'default linux',
                'timeout 100',
                'prompt 1',
                'label linux',
                'kernel vmlinuz',
                'append initrd=initrd.img root=LABEL=test_project'))
            data = open(os.path.join(liveDir, 'isolinux.cfg')).read()
            self.failIf(data != ref, "expected:\n%s\nbut got:\n%s" % \
                    (ref, data))
        finally:
            util.rmtree(liveDir)
            util.rmtree(fakeroot)

    def testMakeLiveCdKernels(self):
        g = live_iso.LiveIso({}, [])
        liveDir = tempfile.mkdtemp()
        fakeroot = tempfile.mkdtemp()
        try:
            g.mkinitrd = lambda *args, **kwargs: None
            self.touch(os.path.join(fakeroot, 'boot', 'vmlinuz.bogus'))
            self.touch(os.path.join(fakeroot, 'boot', 'vmlinuz.bogus1'))
            self.assertRaises(AssertionError,
                    g.makeLiveCdTree, liveDir, fakeroot)
        finally:
            util.rmtree(liveDir)
            util.rmtree(fakeroot)

    def testMakeLiveCdUnionfsKernels(self):
        g = live_iso.LiveIso({}, [])
        liveDir = tempfile.mkdtemp()
        fakeroot = tempfile.mkdtemp()
        try:
            g.mkinitrd = lambda *args, **kwargs: None
            self.touch(os.path.join(fakeroot, 'boot', 'vmlinuz.bogus'))
            self.touch(os.path.join(fakeroot, 'boot', 'vmlinuz.bogus1'))
            g.getBuildData = lambda x: True
            self.assertRaises(AssertionError,
                    g.makeLiveCdTree, liveDir, fakeroot)
        finally:
            util.rmtree(liveDir)
            util.rmtree(fakeroot)


if __name__ == "__main__":
    testsuite.main()
