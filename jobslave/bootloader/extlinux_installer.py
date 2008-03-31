#
# Copyright (c) 2008 rPath, Inc.
#
# All rights reserved
#

import os

from conary.lib import log
from conary.lib import util

from jobslave import bootloader
from jobslave.generators import constants
from jobslave.imagegen import logCall


class ExtLinuxInstaller(bootloader.BootloaderInstaller):
    def install(self):
        # Tell bootman where / is
        root_conf = open(os.path.join(self.image_root, 'etc', 'bootloader.d',
            'root.conf'), 'w')
        print >>root_conf, 'timeout 50'
        print >>root_conf, 'add_options ro'
        print >>root_conf, 'root LABEL=/'
        root_conf.close()

        # Create extlinux configs
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
                constants.heads, constants.sectors))
        finally:
            logCall('umount "%s"' % image_dev)
            logCall('umount "%s"' % image_proc)

    def install_mbr(self, mbr_device, size):
        # Install MBR
        mbr_path = os.path.join(self.image_root, 'boot', 'extlinux', 'mbr.bin')
        if not os.path.exists(mbr_path):
            raise RuntimeError('syslinux MBR not found at "%s"'
                % mbr_path)
        logCall('dd if="%s" of="%s" conv=notrunc' % (mbr_path, mbr_device))
