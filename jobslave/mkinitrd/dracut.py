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
from conary.lib import util
from jobslave import mkinitrd
from jobslave.util import logCall


class DracutGenerator(mkinitrd.InitrdGenerator):

    MODULES = [
            'ata_piix',
            'megaraid_sas',
            'mptscsih',
            'mptspi',
            'scsi_transport_spi',
            'virtio_blk',
            'virtio_net',
            'virtio_pci',
            'xenblk',

            'btrfs',
            'ext4',
            'xfs',
            ]

    DRACUT_MODULES = set([
            'btrfs',
            'lvm',
            ])

    def generateOne(self, kver, rdPath):
        if not os.path.exists(util.joinPaths(self.image_root, '/sbin/btrfs')):
            self.DRACUT_MODULES.discard('btrfs')
        args = ['/usr/sbin/chroot', self.image_root, '/sbin/dracut',
                '--force',
                '--add=' + ' '.join(self.DRACUT_MODULES),
                '--add-drivers=' + ' '.join(self.MODULES),
                ]
        args.extend([rdPath, kver])
        logCall(args)
