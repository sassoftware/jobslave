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
    def makeBlankFS(self, image, fsType, size, fsLabel = None):
        if os.path.exists(image):
            util.rmtree(image)
        util.mkdirChain(os.path.split(image)[0])
        util.execute('dd if=/dev/zero of=%s count=1 seek=%d bs=4096' % \
                      (image, (size / 4096) - 1))

        fs = bootable_image.Filesystem(image, fsType, size, fsLabel = fsLabel)
        fs.format()
        return fs

    def makeFSImage(self, sizes):
        root = self.workDir + "/root"
        try:
            # create an image file per mount point
            imgFiles = {}
            for mountPoint in self.mountDict.keys():
                requestedSize, minFreeSpace, fsType = self.mountDict[mountPoint]

                if requestedSize - sizes[mountPoint] < minFreeSpace:
                    requestedSize += sizes[mountPoint] + minFreeSpace

                tag = mountPoint.replace("/", "")
                tag = tag and tag or "root"
                imgFiles[mountPoint] = os.path.join(self.workDir, "%s-%s.%s" % (self.basefilename, tag, fsType))
                log.info("creating mount point %s as %s size of %d" % (mountPoint, imgFiles[mountPoint], requestedSize))
                fs = self.makeBlankFS(imgFiles[mountPoint], fsType, requestedSize, fsLabel = mountPoint)

                self.addFilesystem(mountPoint, fs)

            self.mountAll()
            self.installFileTree(root)
        finally:
            self.umountAll()
            util.rmtree(root, ignore_errors = True)

        return imgFiles

    def write(self):
        totalSize, sizes = self.getImageSize(realign = 0, partitionOffset = 0)

        images = self.makeFSImage(sizes)
        finalImages = []
        for mountPoint, image in images.items():
            self.gzip(self.outputDir, image)
            finalImages.append((image, "Raw Filesystem Image (%s)" % mountPoint))
        self.postOutput(finalImages)
