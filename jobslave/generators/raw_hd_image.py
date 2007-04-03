#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import os
import tempfile

from jobslave.filesystems import sortMountPoints
from jobslave.generators import bootable_image, constants
from math import ceil

from conary.lib import util

class RawHdImage(bootable_image.BootableImage):
    def __init__(self, *args, **kwargs):
        bootable_image.BootableImage.__init__(self, *args, **kwargs)
        self.freespace = self.jobData['data'].get("freespace", 250) * 1048576
        self.swapSize = self.jobData['data'].get("swapSize", 128) * 1048576

    def getImageSize(self):
        mounts = [x[0] for x in self.jobData['filesystems'] if x[0]]
        sizes, totalSize = self.getTroveSize(mounts)

        totalSize = 0
        realSizes = {}
        for x in self.mountDict.keys():
            requestedSize, minFreeSpace, type = self.mountDict[x]

            if requestedSize - sizes[x] < minFreeSpace:
                requestedSize += sizes[x] + minFreeSpace

            # pad size and align to sector
            requestedSize = int(ceil((requestedSize + 20 * 1024 * 1024) / 0.87))
            adjust = (constants.cylindersize- \
                             (requestedSize % constants.cylindersize)) % \
                             constants.sectorSize
            requestedSize += adjust

            totalSize += requestedSize

            realSizes[x] = requestedSize

        totalSize += constants.partitionOffset

        return totalSize, realSizes

    def makeBlankDisk(self, image):
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

        # create the root (/ or /boot) partition, non LVM
        start = constants.partitionOffset / constants.sectorSize
        partSize = rootSize / constants.sectorSize #  (rootSize / constants.sectorSize)
        fdiskCommands = "%d %d L *\n" % (start, partSize)

        # create the raw file
        util.execute('dd if=/dev/zero of=%s count=1 seek=%d bs=4096' % \
                      (image, (totalSize/ 4096) - 1))

        # partition it
        cylinders = totalSize / constants.cylindersize
        cmd = '/sbin/sfdisk -C %d -S %d -H %d %s -uS --force' % \
            (cylinders, constants.sectors, constants.heads, image)

        start += partSize
        size = lvmSize / constants.sectorSize
        fdiskCommands += "%d %d 8e\n" % (start, partSize)

        sfdisk = util.popen(cmd, 'w')
        sfdisk.write(fdiskCommands)
        sfdisk.close()

        # format / (or /boot)
        dev = None
        try:
            dev = self.loop(image, offset = constants.partitionOffset)
            self.formatFS(dev, rootSize)
        finally:
            if dev:
                util.execute('losetup -d %s' % dev)
                util.execute('sync')
        mounts = {}
        mounts[None] = image

        # pvcreate the rest
        dev = None
        try:
            dev = self.loop(image, offset = constants.partitionOffset + rootSize)
            util.execute("pvcreate %s" % dev)
            util.execute("vgcreate vg00 %s" % dev)
            for x in self.mountDict:
                if x == rootPart:
                    continue

                name = x.replace('/', '')
                fsDev = '/dev/vg00/%s' % name
                util.execute('lvcreate -n %s -L%dK vg00' % (name, realSizes[x] / 1024))
                self.formatFS(fsDev)
                mounts[x] = fsDev

        finally:
            if dev:
#                util.execute('losetup -d %s' % dev)
                util.execute('sync')

        return mounts

    def makeHDImage(self, image, size = None):
        mountPoint = tempfile.mkdtemp(dir=constants.tmpDir)
        try:
            mounts = self.makeBlankDisk(image)

            util.execute('mount -o loop,offset=%d %s %s' % \
                (constants.partitionOffset, mounts[None], mountPoint))

            del mounts[None]
            for x in reversed(sortMountPoints(mounts.keys())):
                if not x:
                    continue

                util.mkdirChain(mountPoint + x)
                util.execute('mount %s %s' % (mounts[x], mountPoint + x))

            self.installFileTree(mountPoint, 0)
            self.installGrub(mountPoint, image, size)
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
