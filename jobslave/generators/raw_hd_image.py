#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import os, sys
import stat
import tempfile

from jobslave.filesystems import sortMountPoints
from jobslave import lvm
from jobslave.imagegen import logCall, log
from jobslave.generators import bootable_image, constants
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
        logCall('dd if=/dev/zero of=%s count=1 seek=%d bs=4096' % \
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
        lvmContainer = None

        if os.path.exists(image):
            util.rmtree(image)
        util.mkdirChain(os.path.split(image)[0])
        if '/boot' in realSizes:
            rootPart = '/boot'
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

        # root partition
        partitions = [(rootStart, rootSize / constants.sectorSize, FSTYPE_LINUX, True)]

        if len(realSizes) > 1:
            partitions.append((rootStart + (rootSize / constants.sectorSize), lvmSize / constants.sectorSize, FSTYPE_LINUX_LVM, False))

            lvmContainer = lvm.LVMContainer(lvmSize, image, (rootStart * constants.sectorSize) + rootSize)

        container.partition(partitions)


        rootFs = bootable_image.Filesystem(image, self.mountDict[rootPart][2],
            rootSize, offset = constants.partitionOffset, fsLabel = rootPart)
        rootFs.format()
        self.addFilesystem(rootPart, rootFs)

        for mountPoint, (reqSize, freeSpace, fsType) in self.mountDict.items():
            if mountPoint == rootPart:
                continue

            if lvmContainer:
                fs = lvmContainer.addFilesystem(mountPoint, fsType, realSizes[mountPoint])
            fs.format()

            self.addFilesystem(mountPoint, fs)

        self.mountAll()
        self.makeImage()
        self.installGrub(os.path.join(self.workDir, "root"), image, totalSize)

        try:
            self.umountAll()
            lvmContainer.destroy()
        except Exception, e:
            log.warning("Error tearing down LVM setup: %s" % str(e))

    def write(self):
        image = os.path.join(self.workDir, self.basefilename + '.hdd')
        self.makeHDImage(image)

        finalImage = os.path.join(self.outputDir, self.basefilename + '.hdd.gz')
        outFile = self.gzip(image, finalImage)
        self.postOutput(((finalImage, 'Raw Hard Disk Image'),))
