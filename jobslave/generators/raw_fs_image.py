#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import os
import tempfile

from jobslave.generators import raw_hd_image, constants

from conary.lib import util

class RawFsImage(raw_hd_image.RawHdImage):
    def getImageSize(self):
        return raw_hd_image.RawHdImage.getImageSize(self) - \
            constants.partitionOffset

    def makeFSImage(self, image, size = None):
        if not size:
            size = self.getImageSize()
        mountPoint = tempfile.mkdtemp(dir=constants.tmpDir)
        try:
            self.makeBlankFS(image, size)
            util.execute('mount -o loop %s %s' % (image, mountPoint))
            self.installFileTree(mountPoint)
            util.execute('umount %s' % mountPoint)
        finally:
            util.rmtree(mountPoint, ignore_errors = True)

    def write(self):
        size = self.getImageSize()
        topDir = os.path.join(os.path.sep, 'tmp', self.jobId)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        image = os.path.join(topDir, self.basefilename + '.ext3')
        finalImage = os.path.join(outputDir, self.basefilename + '.ext3.gz')
        try:
            self.makeFSImage(image, size)
            outFile = self.gzip(image, finalImage)
            self.postOutput(((finalImage, 'Raw Filesystem Image'),))
        finally:
            util.rmtree(topDir, ignore_errors = True)
