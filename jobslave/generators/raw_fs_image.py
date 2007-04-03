#
# Copyright (c) 2004-2007 rPath, Inc.
#
# All Rights Reserved
#

import os
import tempfile

from jobslave.generators import bootable_image, constants
from jobslave.filesystems import sortMountPoints

from conary.lib import util, log

class RawFsImage(bootable_image.BootableImage):
    def makeBlankFS(self, image, size):
        if os.path.exists(image):
            util.rmtree(image)
        util.mkdirChain(os.path.split(image)[0])
        util.execute('dd if=/dev/zero of=%s count=1 seek=%d bs=4096' % \
                      (image, (size / 4096) - 1))
        self.formatFS(image, size)

    def makeFSImage(self, sizes):
        # make a dictionary out of the filesystems, excluding swap

        workDir = tempfile.mkdtemp(dir=constants.tmpDir)
        root = None
        try:
            # create an image file per mount point
            imgFiles = {}
            for x in self.mountDict.keys():
                requestedSize, minFreeSpace, fsType = self.mountDict[x]

                if requestedSize - sizes[x] < minFreeSpace:
                    requestedSize += sizes[x] + minFreeSpace

                tag = x.replace("/", "")
                tag = tag and tag or "root"
                imgFiles[x] = os.path.join(workDir, "%s-%s.ext3" % (self.basefilename, tag))
                log.info("creating mount point %s as %s size of %d" % (x, imgFiles[x], requestedSize))
                self.makeBlankFS(imgFiles[x], requestedSize)

            # mount all newly-created image files
            root = os.path.join(workDir, 'root')
            for x in reversed(sortMountPoints(self.mountDict.keys())):
                log.info("working on " + x)
                util.mkdirChain(root + x)
                util.execute('mount -o loop %s %s' % (imgFiles[x], root + x))

            # install file tree into unified set of mounts
            self.installFileTree(root, self.jobData['data'].get("swapSize", 128) * 1048576)

        finally:
            if root:
                for x in sortMountPoints(self.mountDict.keys()):
                    util.execute('umount %s' % (root + x))
                util.rmtree(root, ignore_errors = True)

        return imgFiles.values()

    def write(self):
        mounts = [x[0] for x in self.jobData['filesystems'] if x[0]]

        sizes, totalSize = self.getImageSize(mounts)
        topDir = os.path.join(constants.tmpDir, self.jobId)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        finalImage = os.path.join(outputDir, self.basefilename + '.ext3.gz')
        try:
            images = self.makeFSImage(sizes)
            for image in images:
                self.gzip(image, os.path.join(outputDir, os.path.basename(image)) + '.gz')
            self.postOutput(((finalImage, 'Raw Filesystem Image'),))
        finally:
            util.rmtree(topDir, ignore_errors = True)
