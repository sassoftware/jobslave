#
# Copyright (c) 2004-2007 rPath, Inc.
#
# All Rights Reserved
#

import os
import tempfile

from jobslave.bootloader import grub_installer
from jobslave.generators import bootable_image, constants
from jobslave.filesystems import sortMountPoints
from jobslave.imagegen import logCall

from conary.lib import util, log

class RawFsImage(bootable_image.BootableImage):
    def makeBlankFS(self, image, fsType, size, fsLabel = None):
        if os.path.exists(image):
            util.rmtree(image)
        util.mkdirChain(os.path.split(image)[0])
        logCall('dd if=/dev/zero of=%s count=1 seek=%d bs=4096' % \
                      (image, (size / 4096) - 1))

        fs = bootable_image.Filesystem(image, fsType, size, fsLabel = fsLabel)
        fs.format()
        return fs

    def mntPointFileName(self, mountPoint):
        fsType = self.mountDict[mountPoint][-1]
        tag = mountPoint[mountPoint.startswith('/') and 1 or 0:]
        tag = tag.replace("/", "_")
        tag = tag and tag or "root"
        return os.path.join(self.workDir, self.basefilename, "%s-%s.%s" % (self.basefilename, tag, fsType))

    def makeFSImage(self, sizes):
        root = self.workDir + "/root"
        try:
            # create an image file per mount point
            imgFiles = {}
            for mountPoint, (_, _, fsType) in self.mountDict.items():
                size = sizes[mountPoint]

                tag = mountPoint.replace("/", "")
                tag = tag and tag or "root"
                imgFiles[mountPoint] = path = self.mntPointFileName(mountPoint)
                log.info("Creating mount point %s at %s with size %d bytes",
                        mountPoint, path, size)
                fs = self.makeBlankFS(path, fsType, size, fsLabel=mountPoint)

                self.addFilesystem(mountPoint, fs)

            self.mountAll()

            # Install image contents.
            self.installFileTree(root)
        finally:
            try:
                self.umountAll()
                util.rmtree(root, ignore_errors = True)
            except:
                log.logger.exception("Error unmounting partitions:")

        return imgFiles

    def write(self):
        totalSize, sizes = self.getImageSize(realign = 0, partitionOffset = 0)
        finalImage = os.path.join(self.outputDir, self.basefilename + '.fs.tar.gz')

        images = self.makeFSImage(sizes)
        self.status('Compressing filesystem images')
        self.gzip(os.path.join(self.workDir, self.basefilename), finalImage)

        if self.buildOVF10:
            mountPoint = '/'
            tag = 'root'
            fsType = self.mountDict[mountPoint][-1]
            self.diskFilePath = os.path.join(self.workDir, 
                self.basefilename, 
                "%s-%s.%s" % (self.basefilename, tag, fsType))
            self.diskFileName = os.path.split(self.diskFilePath)[1]

            self.status('Building OVF 1.0 package')
            diskFileGzipPath = self.gzip(self.diskFilePath, 
                os.path.join(self.outputDir, self.diskFileName + '.gz'))
            self.ovaPath = self.createOvf(self.basefilename,
                self.jobData['description'], constants.RAWFS, diskFileGzipPath, 
                sizes['/'], totalSize, True, self.workingDir, self.outputDir)
            self.outputFileList.append((self.ovaPath, 
                'Raw Filesystem %s' % constants.OVFIMAGETAG))

        self.outputFileList.append((finalImage, 'Raw Filesystem Image'))
        self.postOutput(self.outputFileList)
