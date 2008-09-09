#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import os
import tempfile

from jobslave import lvm
from jobslave.imagegen import logCall, log
from jobslave.generators import bootable_image, constants

from conary.lib import util

FSTYPE_LINUX = "L"
FSTYPE_LINUX_LVM = "8e"


def divCeil(num, div):
    """
    Divide C{num} by C{div} and round up.
    """
    div = long(div)
    return (long(num) + (div - 1)) / div


class HDDContainer:
    def __init__(self, image, totalSize):
        self.totalSize = totalSize
        self.image = image

        self.mountPoint = tempfile.mkdtemp(dir=constants.tmpDir)

        # create the raw file
        # NB: blocksize is unrelated to the one in constants.py, and is
        # completely arbitrary.
        blocksize = 512
        seek = (totalSize - 1) / blocksize
        logCall('dd if=/dev/zero of=%s count=1 seek=%d bs=%d' % (
            image, max(seek, 0), blocksize))

    def partition(self, partitions):
        cylinders = divCeil(self.totalSize, constants.bytesPerCylinder)
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
        _, realSizes = self.getImageSize()
        lvmContainer = None

        def align(size):
            alignTo = constants.bytesPerCylinder
            return divCeil(size, alignTo) * alignTo

        if os.path.exists(image):
            util.rmtree(image)
        util.mkdirChain(os.path.split(image)[0])
        if '/boot' in realSizes:
            rootPart = '/boot'
        else:
            rootPart = '/'

        # Align root partition to nearest cylinder, but add in the
        # partition offset so that the *end* of the root will be on a
        # cylinder boundary.
        rootEnd = align(constants.partitionOffset + realSizes[rootPart])
        rootSize = rootEnd - constants.partitionOffset

        # Collect sizes of all non-boot partitions, pad 10% for LVM
        # overhead, and realign to the nearest cylinder.
        lvmSize = sum(x[1] for x in realSizes.items() if x[0] != rootPart)
        lvmSize += int(lvmSize * 0.10)
        lvmSize = align(lvmSize)

        totalSize = rootEnd + lvmSize
        container = HDDContainer(image, totalSize)

        # Calculate the offsets and sizes of the root and LVM partitions.
        # Note that the Start/Blocks variables are measured in blocks
        # of 512 bytes (constants.sectorSize)
        # NB: both of these sizes are already block-aligned.
        rootStart = constants.partitionOffset / constants.sectorSize
        rootBlocks = rootSize / constants.sectorSize
        partitions = [(rootStart, rootBlocks, FSTYPE_LINUX, True)]

        if len(realSizes) > 1:
            lvmStart = rootStart + rootBlocks
            lvmBlocks = divCeil(lvmSize, constants.sectorSize)
            partitions.append((lvmStart, lvmBlocks, FSTYPE_LINUX_LVM, False))

            lvmContainer = lvm.LVMContainer(lvmSize, image,
                lvmStart * constants.sectorSize)

        container.partition(partitions)

        rootFs = bootable_image.Filesystem(image, self.mountDict[rootPart][2],
            rootSize, offset = constants.partitionOffset, fsLabel = rootPart)
        rootFs.format()
        self.addFilesystem(rootPart, rootFs)

        for mountPoint, (reqSize, freeSpace, fsType) in self.mountDict.items():
            if mountPoint == rootPart:
                continue

            # FIXME: this code is broken - fs is only set in a branch
            # it only happens to work now because we only support one
            # partition and the continue above gets hit
            if lvmContainer:
                fs = lvmContainer.addFilesystem(mountPoint, fsType, realSizes[mountPoint])
            fs.format()

            self.addFilesystem(mountPoint, fs)

        self.mountAll()

        # Install contents into image
        root_dir = os.path.join(self.workDir, "root")
        bootloader_installer = self.installFileTree(root_dir)

        # Install bootloader's MBR onto the disk
        #  first bind mount the disk image into the root dir.
        #  this lets some bootloaders (like grub) write to the disk
        diskpath = os.path.join(root_dir, 'disk.img')
        f = open(diskpath, 'w')
        f.close()
        logCall('mount -obind %s %s' %(image, diskpath))
        try:
            bootloader_installer.install_mbr(root_dir, image, totalSize)
        finally:
            logCall('umount %s' % diskpath)
            os.unlink(diskpath)

        # Unmount and destroy LVM
        try:
            self.umountAll()
            if lvmContainer:
                lvmContainer.destroy()
        except Exception, e:
            log.warning("Error tearing down LVM setup: %s" % str(e))

        return totalSize

    def write(self):
        image = os.path.join(self.workDir, self.basefilename + '.hdd')
        self.makeHDImage(image)

        finalImage = os.path.join(self.outputDir, self.basefilename + '.hdd.gz')

        self.status('Compressing hard disk image')
        outFile = self.gzip(image, finalImage)
        self.postOutput(((finalImage, 'Raw Hard Disk Image'),))
