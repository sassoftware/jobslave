#
# Copyright (c) 2005-2008 rPath, Inc.
#
# All rights reserved
#

import os

from conary.lib import log

from jobslave.bootloader import DummyInstaller
from jobslave.bootloader.extlinux_installer import ExtLinuxInstaller
from jobslave.bootloader.grub_installer import GrubInstaller


def get_bootloader(parent, image_root, override=None):
    '''
    Choose an appropriate bootloader for the given image and return a
    Bootloader instance used to prepare and install the bootloader.
    '''

    if override == 'extlinux' or (not override and \
      os.path.exists(os.path.join(image_root, 'sbin/bootman')) and \
      os.path.exists(os.path.join(image_root, 'sbin/extlinux'))):
        return ExtLinuxInstaller(parent, image_root)
    elif override == 'grub' or (not override and \
      os.path.exists(os.path.join(image_root, 'sbin/grub'))):
        return GrubInstaller(parent, image_root)
    else:
        log.warning('Could not find extlinux (with bootman) or grub')
        log.warning('No bootloader will be installed!')
        return DummyInstaller(parent, image_root)
