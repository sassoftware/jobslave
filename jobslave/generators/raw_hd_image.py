#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import os
import stat
import tempfile

from jobslave.filesystems import sortMountPoints
from jobslave.generators import bootable_image, constants, lvm
from math import ceil

from conary.lib import util

FSTYPE_LINUX = "L"
FSTYPE_LINUX_LVM = "8e"

class HDDContainer:
    def __init__(self, image, totalSize):
        self.totalSize = totalSize
        self.image = image

        self.mountPoint = tempfile.mkdtemp(dir=constants.tmpDir)

        # create the raw file
        util.execute('dd if=/dev/zero of=%s count=1 seek=%d bs=4096' % \
            (image, (totalSize / 4096) - 1))

    def partition(self, partitions):
        cylinders = self.totalSize / constants.cylindersize
        cmd = '/sbin/sfdisk -C %d -S %d -H %d %s -uS --force' % \
            (cylinders, constants.sectors, constants.heads, self.image)
        sfdisk = util.popen(cmd, 'w')

        for start, size, fsType, bootable in partitions:
            sfdisk.write("%d %d %s" % (start, size, fsType))
            if bootable:
                sfdisk.write(" *")
            sfdisk.write("\n")

        sfdisk.close()


class RawHdImage(bootable_image.BootableImage):
    def makeHDImage(self, image):
        totalSize, realSizes = self.getImageSize()

        if os.path.exists(image):
            util.rmtree(image)
        util.mkdirChain(os.path.split(image)[0])
        if '/boot' in realSizes:
            rootPart = '/boot'
            rootSize = realSizes['/boot']
        else:
            rootPart = '/'

        rootSize = realSizes[rootPart]

        # pad 10% for LVM overhead and realign lvmSize
        lvmSize = sum(x[1] for x in realSizes.items() if x[0] != rootPart)
        lvmSize += lvmSize * 0.10
        totalSize += lvmSize * 0.10

        # align totalSize to cylinder
        totalSize += (constants.cylindersize - \
                     (totalSize % constants.cylindersize)) % \
                     constants.cylindersize

        container = HDDContainer(image, totalSize)

        rootStart = constants.partitionOffset / constants.sectorSize

        partitions = [
            (rootStart, rootSize / constants.sectorSize, FSTYPE_LINUX, True),
            (rootStart + (rootSize / constants.sectorSize), lvmSize / constants.sectorSize, FSTYPE_LINUX_LVM, False),
        ]

        container.partition(partitions)

        import epdb
        epdb.st()


        lvmContainer = lvm.LVMContainer(lvmSize, image, (rootStart * constants.sectorSize) + rootSize)
        try:
            rootFs = bootable_image.Filesystem(image, rootSize, offset = constants.partitionOffset)
            rootFs.format()
            self.addFilesystem(rootPart, rootFs)

            for mountPoint in self.mountDict:
                if mountPoint == rootPart:
                    continue
                fs = lvmContainer.addFilesystem(mountPoint, realSizes[mountPoint])
                fs.format()

                self.addFilesystem(mountPoint, fs)

            self.mountAll()
            self.makeImage()
            self.installGrub(os.path.join(self.topDir, "root"), image, totalSize)
        finally:
            self.umountAll()
            lvmContainer.destroy()

    def write(self):
        # FIXME: don't init this here
        self.topDir = os.path.join(constants.tmpDir, self.jobId)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        image = os.path.join(self.topDir, self.basefilename + '.hdd')
        finalImage = os.path.join(outputDir, self.basefilename + '.hdd.gz')
        try:
            self.makeHDImage(image)
            outFile = self.gzip(image, finalImage)
            self.postOutput(((finalImage, 'Raw Hard Disk Image'),))
        finally:
            pass
        #    util.rmtree(self.topDir, ignore_errors = True)
