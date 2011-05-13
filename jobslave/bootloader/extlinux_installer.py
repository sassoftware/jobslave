#
# Copyright (c) 2011 rPath, Inc.
#

import os
from conary.lib import util

from jobslave import bootloader
from jobslave.mkinitrd import redhat as rh_initrd
from jobslave.util import logCall


class ExtLinuxInstaller(bootloader.BootloaderInstaller):
    def install(self):
        # Create extlinux configs
        bootloader.writeBootmanConfigs(self)
        logCall('chroot "%s" /sbin/bootman' % self.image_root)

        self.mkinitrd()

        if not self.do_install:
            return

        # Bind-mount /dev so extlinux can write to the boot sector
        image_dev = os.path.join(self.image_root, 'dev')
        logCall('mount -n --bind /dev "%s"' % image_dev)

        # Install extlinux
        try:
            util.mkdirChain(os.path.join(self.image_root, 'boot', 'extlinux'))
            logCall('chroot "%s" /sbin/extlinux --install '
                '--heads %s --sectors %s /boot/extlinux/' % (self.image_root,
                    self.geometry.heads, self.geometry.sectors))
        finally:
            logCall('umount -n "%s"' % image_dev)

    def install_mbr(self, root_dir, mbr_device, size):
        # Install MBR
        mbr_path = os.path.join(self.image_root, 'boot', 'extlinux', 'mbr.bin')
        if not os.path.exists(mbr_path):
            raise RuntimeError('syslinux MBR not found at "%s"'
                % mbr_path)
        logCall('dd if="%s" of="%s" conv=notrunc' % (mbr_path, mbr_device))

    def mkinitrd(self):
        irg = rh_initrd.RedhatGenerator(self.image_root)
        irg.generateFromBootman()
