#
# Copyright (c) 2005-2008 rPath, Inc.
#
# All rights reserved
#

import os

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
    else:
        return GrubInstaller(parent, image_root)

