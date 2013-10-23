#
# Copyright (c) SAS Institute Inc.
#

import os

from jobslave import splitdistro
import jobslave_helper
import tempfile
from conary.lib import util

ISOBLOCK_SIZE = 2048

class SplitDistroTest(jobslave_helper.JobSlaveHelper):
    def testSpaceUsed(self):
        tmpdir = tempfile.mkdtemp()
        assert splitdistro.spaceused(tmpdir, ISOBLOCK_SIZE) == 0
        for blocks, fn in [(x + 1, os.path.join(tmpdir, str(x))) \
                           for x in range(10)]:
            f = open(fn, 'w')
            f.write('a')
            f.close()
            assert splitdistro.spaceused(tmpdir, ISOBLOCK_SIZE) == \
                   ISOBLOCK_SIZE * blocks
            assert splitdistro.spaceused(fn, ISOBLOCK_SIZE) == 2048

    def testPrepareDir(self):
        unified = tempfile.mkdtemp()
        f = open(os.path.join(unified, 'README'), 'w')
        f.close()
        util.mkdirChain(os.path.join(unified, 'media-template', 'all'))
        path = tempfile.mkdtemp()
        f = open(os.path.join(path, 'junk'), 'w')
        f.close()
        csdir = 'foo/changesets'

        self.suppressOutput(splitdistro.preparedir, unified, path, csdir)
        dirList = os.listdir(path)
        assert 'junk' not in dirList, \
               "Cruft from last run present"
        assert 'README' in dirList, 'common files not imported'
        assert 'foo' in dirList, 'missing changeset directory'
        assert os.listdir(os.path.join(path, 'foo')) == ['changesets']

    def testWriteDiscInfo(self):
        tmpdir = tempfile.mkdtemp()

        splitdistro.writediscinfo(tmpdir, 1, 6 * ['a'])
        f = open(os.path.join(tmpdir, '.discinfo'))
        assert f.read() == 'a\na\na\n1\na\na\n'

    def testLnDir(self):
        tmpdir = tempfile.mkdtemp()
        tmpdir2 = tempfile.mkdtemp()

        for sub in ('a', 'b', 'c'):
            subdir = os.path.join(tmpdir, sub)
            os.mkdir(subdir)
        for dir in (tmpdir, subdir):
            for fn in [os.path.join(dir, str(x)) for x in range(10)]:
                f = open(fn, 'w')
                f.close()
        os.mkdir(os.path.join(tmpdir2, 'c'))

        splitdistro.lndir( \
            tmpdir, tmpdir2, excludes = ['b', os.path.join('c', '9')])

        dirList = sorted(os.listdir(tmpdir2))
        self.failIf('9' not in dirList,
                    'File of same basename and different path as an '
                    'exclusion was not copied')
        self.failIf('b' in dirList, "named excslusion subdir was copied")
        assert dirList == \
               ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'c']

        dirList = sorted(os.listdir(os.path.join(tmpdir2, 'c')))
        self.failIf('9' in dirList, "explicitly excluded file was copied")
        assert dirList == \
               ['0', '1', '2', '3', '4', '5', '6', '7', '8']

    def testLnDirErr(self):
        tmpdir = tempfile.mkdtemp()
        tmpdir2 = tempfile.mkdtemp()

        os.mkdir(os.path.join(tmpdir, 'b'))
        f = open(os.path.join(tmpdir, 'b', 'a'), 'w')
        f.close()
        os.chmod(tmpdir2, 0)
        self.assertRaises(OSError, splitdistro.lndir, tmpdir, tmpdir2)

    def testLnDirDirs(self):
        tmpdir = tempfile.mkdtemp()
        tmpdir2 = tempfile.mkdtemp()

        os.mkdir(os.path.join(tmpdir, 'a'))
        for dirName in ('b', 'c'):
            util.mkdirChain(os.path.join(tmpdir, 'a', dirName))
            util.mkdirChain(os.path.join(tmpdir, dirName))
        splitdistro.lndir(tmpdir, tmpdir2, excludes = \
                          ['b', os.path.join('a', 'c')])
        dirList = os.listdir(os.path.join(tmpdir2, 'a'))
        self.failIf('b' not in dirList,
                    "Directory a/b should not have been excluded")
        self.failIf('c' in dirList,
                    "Directory a/c should have been excluded")
        dirList = os.listdir(tmpdir2)
        self.failIf('c' not in dirList,
                    "Directory c should not have been excluded")
        self.failIf('b' in dirList,
                    "Directory b should have been excluded")

    def testLnDirFiles(self):
        tmpdir = tempfile.mkdtemp()
        tmpdir2 = tempfile.mkdtemp()

        os.mkdir(os.path.join(tmpdir, 'a'))
        for fn in ('b', 'c'):
            f = open(os.path.join(tmpdir, 'a', fn), 'w')
            f.close()
            f = open(os.path.join(tmpdir, fn), 'w')
            f.close()
        splitdistro.lndir(tmpdir, tmpdir2, excludes = \
                          ['b', os.path.join('a', 'c')])
        dirList = os.listdir(os.path.join(tmpdir2, 'a'))
        self.failIf('b' not in dirList,
                    "File a/b should not have been excluded")
        self.failIf('c' in dirList,
                    "File a/c should have been excluded")
        dirList = os.listdir(tmpdir2)
        self.failIf('c' not in dirList,
                    "File c should not have been excluded")
        self.failIf('b' in dirList,
                    "File b should have been excluded")

    def testLnDirSubdirs(self):
        tmpdir = tempfile.mkdtemp()
        tmpdir2 = tempfile.mkdtemp()

        util.mkdirChain(os.path.join(tmpdir, 'a', 'b', 'c', 'd'))
        splitdistro.lndir(tmpdir, tmpdir2, excludes =
                          [os.path.join('a', 'b')])
        self.failIf(os.path.exists( \
            os.path.join(tmpdir2, 'a', 'b', 'c', 'd')),
                    "Dir a/b/c/d should not have been copied")
        self.failIf(os.path.exists(os.path.join(tmpdir2, 'a', 'b', 'c')),
                    "Dir a/b/c should not have been copied")
        self.failIf(os.path.exists(os.path.join(tmpdir2, 'a', 'b')),
                    "Dir a/b should not have been copied")
        self.failIf(not os.path.exists(os.path.join(tmpdir2, 'a')),
                    "Dir a should have been copied")

    def testLnDirExistDirs(self):
        tmpdir = tempfile.mkdtemp()
        tmpdir2 = tempfile.mkdtemp()

        util.mkdirChain(os.path.join(tmpdir, 'a', 'b'))
        util.mkdirChain(os.path.join(tmpdir2, 'a', 'b'))
        splitdistro.lndir(tmpdir, tmpdir2)
        self.failIf(not os.path.exists(os.path.join(tmpdir2, 'a', 'b')),
                    "Dir a/b should exist")
