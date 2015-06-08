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


import logging
from jobslave import mkinitrd
from jobslave.util import logCall
from jobslave.distro_detect import is_RH

log = logging.getLogger(__name__)


class RedhatGenerator(mkinitrd.InitrdGenerator):

    MODULES = [
            'ata_piix',
            'megaraid',
            'mptscsih',
            'mptspi',
            'scsi_transport_spi',
            'virtio_blk',
            'virtio_net',
            'virtio_pci',
            'xenblk',
            ]

    def generateOne(self, kver, rdPath):
        log.info("Rebuilding initrd for kernel %s", kver)
        args = ['/usr/sbin/chroot', self.image_root, '/sbin/mkinitrd',
                '-f', '--allow-missing']
        for driver in self.MODULES:
            args.append('--with=' + driver)
        if is_RH(self.image_root):
            args.append('--preload=xenblk')
        args.extend([rdPath, kver])
        logCall(args)
