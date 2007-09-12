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

    def testWriteZisofsZisofs(self):
        self.injectPopen("")
        g = live_iso.LiveIso({}, [])
        g.jobData['project'] = {}
        g.jobData['project']['name'] = 'test name 123'
        g.makeLiveCdTree = lambda *args, **kwargs: None
        g.isoName = lambda *args, **kwargs: 'DUmmy Name'
        chmod = os.chmod
        try:
            os.chmod = lambda *args, **kwargs: None
            g.write()
            self.failIf(len(self.callLog) != 4,
                    "wrong number of calls made")
        finally:
            os.chmod = chmod
        self.resetPopen()

    def testWrite(self):
        self.injectPopen("")
        g = live_iso.LiveIso({}, [])
        g.jobData['project'] = {}
        g.zisofs = False
        g.jobData['project']['name'] = 'test name 123'
        g.makeLiveCdTree = lambda *args, **kwargs: None
        g.isoName = lambda *args, **kwargs: 'DUmmy Name'
        chmod = os.chmod
        try:
            os.chmod = lambda *args, **kwargs: None
            g.write()
            self.failIf(len(self.callLog) != 4,
                    "wrong number of calls made")
        finally:
            os.chmod = chmod
        self.resetPopen()


if __name__ == "__main__":
    testsuite.main()
