#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import logging
log = logging.getLogger(__name__)

from jobslave import buildtypes
from jobslave.generators import bootable_image
from jobslave.generators import raw_hd_image
from jobslave.generators import tarball
from jobslave.generators import vmware_image

class AMIImage(raw_hd_image.RawHdImage):
    fileType = buildtypes.typeNames[buildtypes.AMI]

    def write(self):
        if not self.jobData['data'].get('ebsBacked'):
            obj = tarball.Tarball(self.cfg, self.jobData)
            return obj.write()

        image = os.path.join(self.workDir, self.basefilename + '.hdd')
        disk = self.makeHDImage(image)

        self.status('Compressing hard disk image')
        vmdkImage = os.path.join(self.workDir, self.basefilename + '.vmdk')
        vmware_image.createVMDK(image, vmdkImage, disk.totalSize,
                geometry=self.geometry, adapter='lsilogic', hwVersion=10,
                streaming=True)

        self.outputFileList.append((vmdkImage, 'VMDK Disk Image'),)
        self.postOutput(self.outputFileList, attributes={
            'uncompressed_size': disk.totalSize,
            'disk_format': 'vmdk',
            })

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
                    freeSpace=200*1024*1024),
                F('root', '/', 'ext4', minSize=1024*1024,
                    freeSpace=freeSpace),
                ]
        return dict((x.mount, x) for x in fsList)
