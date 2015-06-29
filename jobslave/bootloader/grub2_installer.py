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
import os
from conary.lib import util
from contextlib import contextmanager
from jobslave import bootloader
from jobslave.mkinitrd import dracut
from jobslave.util import logCall

log = logging.getLogger(__name__)


class Grub2Installer(bootloader.BootloaderInstaller):

    def setup(self):
        defaults = util.joinPaths(self.image_root, 'etc', 'default', 'grub')
        util.mkdirChain(os.path.dirname(defaults))
        if not os.path.exists(defaults) or not os.lstat(defaults).st_size:
            with open(defaults, 'w') as f_defaults:
                print >> f_defaults, '# Defaults set by rBuilder'
                print >> f_defaults, 'GRUB_DISABLE_RECOVERY=true'

    @contextmanager
    def _mount_dev(self):
        # Temporarily bind-mount the jobslave /dev into the chroot so
        # grub2-install can see the loop device it's targeting.
        logCall("mount -o bind /dev %s/dev" %  self.image_root)
        # /etc/grub.d/10_linux tries to find the backing device for loop
        # devices, on the assumption that it's a block device with cryptoloop
        # on top. Replace losetup with a stub while running mkconfig so it
        # keeps the loop device name and all the right UUIDs get emitted.
        losetup = util.joinPaths(self.image_root, '/sbin/losetup')
        os.rename(losetup, losetup + '.bak')
        with open(losetup, 'w') as f_losetup:
            print >> f_losetup, '#!/bin/sh'
            print >> f_losetup, 'echo "$1"'
        os.chmod(losetup, 0755)
        # In order for the root device to be detected as a FS UUID and not
        # /dev/loop0 there needs to be a link in /dev/disk/by-uuid, which
        # doesn't happen with the jobmaster's containerized environment.
        link_path = None
        if self.root_device.uuid:
            link_path = util.joinPaths(self.image_root, '/dev/disk/by-uuid',
                    self.root_device.uuid)
            util.mkdirChain(os.path.dirname(link_path))
            util.removeIfExists(link_path)
            os.symlink(self.root_device.devPath, link_path)
        try:
            yield
        finally:
            try:
                if link_path:
                    os.unlink(link_path)
                os.rename(losetup + '.bak', losetup)
                logCall("umount %s/dev" %  self.image_root)
            except:
                pass

    def install(self):
        """Generate grub2 configs"""
        cfgname = '/boot/grub2/grub.cfg'
        util.mkdirChain(os.path.dirname(util.joinPaths(self.image_root, cfgname)))
        with self._mount_dev():
            logCall('chroot %s grub2-mkconfig -o %s' % (self.image_root, cfgname))
        rdgen = dracut.DracutGenerator(self.image_root)
        rdgen.generateFromGrub2()

    def install_mbr(self, root_dir, mbr_device, size):
        """Install grub2 into the MBR."""
        # Neither grub2-mkconfig nor grub2-install correctly detect the
        # partitioning type because everything is on loop mounts. Hence we
        # force it to load the right one(s).
        with self._mount_dev():
            logCall("chroot %s /usr/sbin/grub2-install /disk.img "
                    "--modules=part_msdos" % self.image_root)
