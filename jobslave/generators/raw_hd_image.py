#
# Copyright (c) SAS Institute Inc.
#

import logging
import os

from jobslave import lvm
from jobslave.generators import bootable_image, constants
from jobslave.geometry import FSTYPE_LINUX, FSTYPE_LINUX_LVM
from jobslave.util import logCall, divCeil

from conary.lib import util

log = logging.getLogger(__name__)


class HDDContainer(object):

    def __init__(self, image, geometry, totalSize=None):
        self.image = image
        self.geometry = geometry
        if totalSize is None:
            totalSize = os.stat(image).st_size
        self.totalSize = totalSize

    def create(self):
        # create the raw file
        # NB: blocksize is unrelated to the one in constants.py, and is
        # completely arbitrary.
        blocksize = 512
        seek = (self.totalSize - 1) / blocksize
        logCall('dd if=/dev/zero of=%s count=1 seek=%d bs=%d' % (
            self.image, max(seek, 0), blocksize))

    def destroy(self):
        if self.image:
            util.remove(self.image)
            self.image = None

    def partition(self, partitions):
        # Extended partitions are not supported since we're either using a
        # single partition for non-LVM or two for LVM (/boot + one PV)
        assert len(partitions) <= 4
        fObj = open(self.image, 'r+b')

        fObj.seek(440)
        fObj.write(os.urandom(4)) # disk signature
        fObj.write('\0\0')

        numParts = 0
        for start, size, fsType, bootable in partitions:
            numParts += 1
            log.info("Partition %d: start %d  size %d  flags %02x  type %02x",
                    numParts, start, size, bootable, fsType)
            fObj.write(self.geometry.makePart(start, size, bootable, fsType))

        assert numParts <= 4
        while numParts < 4:
            fObj.write('\0' * 16)
            numParts += 1

        fObj.write('\x55\xAA') # MBR signature

        assert fObj.tell() == 512
        fObj.close()


class RawHdImage(bootable_image.BootableImage):

    def makeHDImage(self, image):
        realSizes = self.getImageSize()
        lvmContainer = None

        # Align to the next cylinder
        def align(size, alignTo):
            return divCeil(size, alignTo) * alignTo
        alignPart = lambda size: align(size, self.geometry.bytesPerCylinder)
        alignLvm = lambda size: align(size, 1024*1024)

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
        rootStart = self.geometry.offsetBytes
        rootEnd = alignPart(rootStart + realSizes[rootPart])
        rootSize = rootEnd - rootStart

        # Collect sizes of all non-boot partitions
        lvmSize = sum(alignLvm(x[1]) for x in realSizes.items()
                if x[0] != rootPart)
        lvmSize += 1048576  # room for metadata
        lvmSize = alignPart(lvmSize)

        # Add one cylinder to the disk to work around grub/VMware/BIOS bugs
        # and/or a misunderstanding by this developer of how partition table
        # sizes are calculated, see RBL-8292.
        totalSize = alignPart(rootEnd + lvmSize + 1)
        container = HDDContainer(image, self.geometry, totalSize)
        container.create()

        # Calculate the offsets and sizes of the root and LVM partitions.
        # Note that the Start/Blocks variables are measured in blocks.
        # NB: both of these sizes are already block-aligned.
        rootStartBlock = rootStart / self.geometry.BLOCK
        rootSizeBlock = rootSize / self.geometry.BLOCK
        partitions = [(rootStartBlock, rootSizeBlock, FSTYPE_LINUX, True)]

        if len(realSizes) > 1:
            lvmStartBlock = rootStartBlock + rootSizeBlock
            lvmSizeBlock = lvmSize / self.geometry.BLOCK
            partitions.append((lvmStartBlock, lvmSizeBlock,
                FSTYPE_LINUX_LVM, False))

            lvmContainer = lvm.LVMContainer(lvmSize, image,
                    lvmStartBlock * self.geometry.BLOCK)
        else:
            lvmContainer = None

        container.partition(partitions)

        root = self.mountDict[rootPart]
        rootFs = bootable_image.Filesystem(image, root.fstype, rootSize,
                offset=rootStart, fsLabel=root.name)
        rootFs.format()
        self.addFilesystem(rootPart, rootFs)

        for mountPoint, req in self.mountDict.items():
            if mountPoint == rootPart or req.fstype == 'unallocated':
                continue
            fs = lvmContainer.addFilesystem(req.name, mountPoint, req.fstype,
                    realSizes[mountPoint])
            fs.format()
            self.addFilesystem(mountPoint, fs)

        try:
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

        finally:
            try:
                self.umountAll()
                if lvmContainer:
                    lvmContainer.unmount()
            except Exception, e:
                log.warning("Error tearing down filesystems:", exc_info=True)

        return container

    def write(self):
        self.productName = 'Raw Hard Disk'
        image = os.path.join(self.workDir, self.basefilename + '.hdd')
        disk = self.makeHDImage(image)
        self.capacity = disk.totalSize

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

    def preTagScripts(self):
        super(RawHdImage, self).preTagScripts()
        # APPENG-3382: disable the zeroconf route
        fpath = os.path.join(self.root, 'etc', 'sysconfig', 'network')
        contents = file(fpath).read().rstrip()
        f = file(fpath, "w")
        f.write(contents)
        f.write("\nNOZEROCONF=yes\n")
        f.close()

