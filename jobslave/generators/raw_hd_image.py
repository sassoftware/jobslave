#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import os
import tempfile

from jobslave.generators import bootable_image, constants
from math import ceil

from conary.lib import util

class RawHdImage(bootable_image.BootableImage):
    def __init__(self, *args, **kwargs):
        bootable_image.BootableImage.__init__(self, *args, **kwargs)
        self.freespace = self.jobData['data'].get("freespace", 250) * 1048576
        self.swapSize = self.jobData['data'].get("swapSize", 128) * 1048576

    def getImageSize(self):
        size = bootable_image.BootableImage.getTroveSize(self)
        size += self.freespace + constants.partitionOffset

        size = int(ceil((size + 20 * 1024 * 1024 + self.swapSize) / 0.87))
        size += (constants.cylindersize - \
                     (size % constants.cylindersize)) % \
                     constants.cylindersize

        return size

    def makeHDImage(self, image, size = None):
        if not size:
            size = self.getImageSize()
        mountPoint = tempfile.mkdtemp(dir=constants.tmpDir)
        try:
            self.makeBlankDisk(image, size)

            util.execute('mount -o loop,offset=%d %s %s' % \
                             (constants.partitionOffset, image, mountPoint))

            self.installFileTree(mountPoint)
            self.installGrub(mountPoint, image)
            util.execute('umount %s' % mountPoint)
        finally:
            # simply a failsafe to ensure image is unmounted
            util.execute('mount | grep %s && umount %s || true' % \
                             (mountPoint, mountPoint))
            util.rmtree(mountPoint, ignore_errors = True)

    def write(self):
        topDir = os.path.join(constants.tmpDir, self.jobId)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        image = os.path.join(topDir, self.basefilename + '.hdd')
        finalImage = os.path.join(outputDir, self.basefilename + '.hdd.gz')
        try:
            self.makeHDImage(image)
            outFile = self.gzip(image, finalImage)
            self.postOutput(((finalImage, 'Raw Hard Disk Image'),))
        finally:
            util.rmtree(topDir, ignore_errors = True)
