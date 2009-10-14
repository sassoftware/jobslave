#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import logging
import os
import tempfile

from jobslave import buildtypes
from jobslave import lvm
from jobslave.util import logCall
from jobslave.generators import bootable_image, constants

from conary.lib import util

log = logging.getLogger(__name__)

FSTYPE_LINUX = "L"
FSTYPE_LINUX_LVM = "8e"


def divCeil(num, div):
    """
    Divide C{num} by C{div} and round up.
    """
    div = long(div)
    return (long(num) + (div - 1)) / div


class HDDContainer:
    def __init__(self, image, totalSize, 
                 heads=constants.heads, 
                 sectors=constants.sectors
                ):
        self.totalSize = totalSize
        self.image = image
        self.heads = heads
        self.sectors = sectors
        # a derived value for convenience
        self.bytesPerCylinder = heads * sectors * constants.sectorSize

        # create the raw file
        # NB: blocksize is unrelated to the one in constants.py, and is
        # completely arbitrary.
        blocksize = 512
        seek = (totalSize - 1) / blocksize
        logCall('dd if=/dev/zero of=%s count=1 seek=%d bs=%d' % (
            image, max(seek, 0), blocksize))

    def partition(self, partitions):
        stdin = ''
        for start, size, fsType, bootable in partitions:
            stdin += "%d %d %s%s\n" % (start, size, fsType,
                    (bootable and " *" or ""))

        cylinders = divCeil(self.totalSize, self.bytesPerCylinder)
        logCall('/sbin/sfdisk -C %d -S %d -H %d %s -uS --force'
                % (cylinders, self.sectors, self.heads, self.image),
                stdin=stdin)


class RawHdImage(bootable_image.BootableImage):

    def makeHDImage(self, image):
        _, realSizes = self.getImageSize()
        lvmContainer = None

        def align(size):
            alignTo = self.heads * self.sectors * constants.sectorSize
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
        container = HDDContainer(image, totalSize, self.heads, self.sectors)

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
        logCall('mount -n -obind %s %s' %(image, diskpath))
        try:
            bootloader_installer.install_mbr(root_dir, image, totalSize)
        finally:
            blkidtab = os.path.join(root_dir, "etc", "blkid.tab")
            if os.path.exists(blkidtab):
                os.unlink(blkidtab)
            logCall('umount -n %s' % diskpath)
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
        self.productName = 'Raw Hard Disk'
        image = os.path.join(self.workDir, self.basefilename + '.hdd')
        self.capacity = self.makeHDImage(image)

        finalImage = os.path.join(self.outputDir, self.basefilename + '.hdd.gz')

        self.status('Compressing hard disk image')
        outFile = self.gzip(image, finalImage)

        if self.buildOVF10:
            self.ovaPath = self.createOvf(self.basefilename,
                self.jobData['description'], constants.RAWHD, finalImage,
                self.capacity, True, self.workingDir, 
                self.outputDir)
            self.outputFileList.append((self.ovaPath,
                'Raw Hard Disk %s' % constants.OVFIMAGETAG))


        self.outputFileList.append((finalImage, 'Raw Hard Disk Image'),)
        self.postOutput(self.outputFileList)
