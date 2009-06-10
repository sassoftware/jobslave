#
# Copyright (c) 2008 rPath, Inc.
#
# All rights reserved
#

import os

from conary.lib import util

from jobslave import bootloader
from jobslave.imagegen import logCall


class ExtLinuxInstaller(bootloader.BootloaderInstaller):
    def install(self):
        # Create extlinux configs
        bootloader.writeBootmanConfigs(self)
        logCall('chroot "%s" /sbin/bootman' % self.image_root)

        # Mount /proc (this is called after /proc is unmounted the first time)
        # and bind-mount /dev (so extlinux can write to the boot sector)
        image_proc = os.path.join(self.image_root, 'proc')
        logCall('mount -t proc proc "%s"' % image_proc)
        image_dev = os.path.join(self.image_root, 'dev')
        logCall('mount --bind /dev "%s"' % image_dev)

        # Install extlinux
        try:
            util.mkdirChain(os.path.join(self.image_root, 'boot', 'extlinux'))
            logCall('chroot "%s" /sbin/extlinux --install '
                '--heads %s --sectors %s /boot/extlinux/' % (self.image_root,
                self.heads, self.sectors))
        finally:
            logCall('umount "%s"' % image_dev)
            logCall('umount "%s"' % image_proc)

    def install_mbr(self, root_dir, mbr_device, size):
        # Install MBR
        mbr_path = os.path.join(self.image_root, 'boot', 'extlinux', 'mbr.bin')
        if not os.path.exists(mbr_path):
            raise RuntimeError('syslinux MBR not found at "%s"'
                % mbr_path)
        logCall('dd if="%s" of="%s" conv=notrunc' % (mbr_path, mbr_device))
