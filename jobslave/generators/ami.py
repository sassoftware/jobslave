#
# Copyright (c) 2010-2012 rPath, Inc.
#
# All Rights Reserved
#

import logging
log = logging.getLogger(__name__)

from jobslave import buildtypes
from jobslave.generators import bootable_image
from jobslave.generators import raw_hd_image
from jobslave.generators import tarball

class AMIImage(raw_hd_image.RawHdImage):
    fileType = buildtypes.typeNames[buildtypes.AMI]

    def write(self):
        # We don't need swap files, aws provides a swap partition for this
        # purpose
        self.swapSize = 0
        if not self.jobData['data'].get('ebsBacked'):
            obj = tarball.Tarball(self.cfg, self.jobData)
            return obj.write()

        return super(AMIImage, self).write()

    def getFilesystems(self):
        mountPoints = super(AMIImage, self).getFilesystems()
        if mountPoints:
            return mountPoints
        # If the product definition did not supply a partition scheme, default
        # to LVM (/boot and /)
        F = bootable_image.FsRequest
        freeSpace = (self.getBuildData("freespace") or 256) * 1024 * 1024
        fsList = [
                F('boot', '/boot', 'ext4', minSize=1024*1024,
                    freeSpace=50*1024*1024),
                F('root', '/', 'ext4', minSize=1024*1024,
                    freeSpace=freeSpace),
                ]
        return dict((x.mount, x) for x in fsList)

