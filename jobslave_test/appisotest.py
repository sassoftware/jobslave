#
# Copyright (c) SAS Institute Inc.
#

import os
import stat
import tempfile
from math import ceil

from conary.lib import util
from conary.lib import sha1helper

from jobslave.generators import appliance_iso

import jobslave_helper

class TarSplitTest(jobslave_helper.JobSlaveHelper):
    def setUp(self):
        jobslave_helper.JobSlaveHelper.setUp(self)

        # size of sample file (in KB)
        self.sampleSize = 97

        # create a sample file to use for testing
        self.sampleFile = tempfile.mktemp()
        kb = 1024
        fh = open(self.sampleFile, 'w')
        rand = open('/dev/urandom')
        for i in range(self.sampleSize):
            fh.write(rand.read(kb))
        rand.close()
        fh.close()

    def tearDown(self):
        util.remove(self.sampleFile)

        jobslave_helper.JobSlaveHelper.tearDown(self)

    def mktree(self):
        baseDir = tempfile.mkdtemp()
        ts = appliance_iso.TarSplit(self.sampleFile)

        # Change default chunkSize to 10KB
        ts.chunkSize = 10 * 1024

        ts.splitFile(baseDir)
        return ts, baseDir

    def testSplitFile(self):
        ts, baseDir = self.mktree()

        sizeInBytes = float(self.sampleSize * 1024)

        self.failUnlessEqual(ceil(sizeInBytes / ts.chunkSize), len(ts.files))
        self.failUnlessEqual(len(ts.files) * 2, len(ts.tblist))

        for fn in ts.files:
            path = os.path.join(baseDir, fn)
            self.failUnless(os.access(path, os.R_OK))

    def testTbList(self):
        ts, baseDir = self.mktree()

        for i, fn in enumerate(ts.files):
            tbIndex = i*2
            oldEntry = ts.tblist[tbIndex].split()
            newEntry = ts.tblist[tbIndex+1].split()

            self.failUnlessEqual(len(oldEntry), 3)
            self.failUnlessEqual(len(newEntry), 4)
            self.failUnlessEqual(oldEntry[0], fn)
            self.failUnlessEqual(oldEntry[0], newEntry[0])
            self.failUnlessEqual(oldEntry[1], newEntry[1])
            self.failUnlessEqual(oldEntry[2], newEntry[2])

            binSha1 = sha1helper.sha1FileBin(os.path.join(baseDir, fn))
            sha1 = sha1helper.sha1ToString(binSha1)

            self.failUnlessEqual(newEntry[3], sha1)

    def testWriteTbList(self):
        tblistFile = tempfile.mktemp()
        ts, baseDir = self.mktree()

        ts.writeTbList(tblistFile)

        for i, line in enumerate(open(tblistFile).readlines()):
            line = line.strip()
            parts = line.split()

            self.failUnlessEqual(line, ts.tblist[i])

            # Add this assertion to make sure the testsuite gets updated if
            # more data is added to the file.
            self.failUnless(len(parts) <= 4)
            self.failUnless(len(parts) >= 3)

            if len(parts) >= 4:
                chunkfile, size, disc, sha1sum = parts[:4]
            elif len(parts) == 3:
                chunkfile, size, disc = parts
                sha1sum = None

            size = long(size)
            disc = int(disc)

            self.failUnlessEqual(disc, 1)
            self.failUnlessEqual(chunkfile, ts.files[i/2])

            path = os.path.join(baseDir, chunkfile)
            realSize = os.stat(path)[stat.ST_SIZE]

            self.failUnlessEqual(size, realSize)
