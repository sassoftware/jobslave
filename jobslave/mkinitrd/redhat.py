#
# Copyright (c) 2011 rPath, Inc.
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
