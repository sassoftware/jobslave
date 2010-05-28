#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved
#

import os

from conary.lib import log
from conary.lib import util

from jobslave.bootloader import DummyInstaller
from jobslave.bootloader.extlinux_installer import ExtLinuxInstaller
from jobslave.bootloader.grub_installer import GrubInstaller


def get_bootloader(parent, image_root, geometry, override=None):
    '''
    Choose an appropriate bootloader for the given image and return a
    Bootloader instance used to prepare and install the bootloader.
    '''

    grubpath = util.searchFile('grub', util.braceExpand('%s/{sbin,usr/sbin}' % image_root))
    if override == 'extlinux' or (not override and \
      os.path.exists(util.joinPaths(image_root, 'sbin/bootman')) and \
      os.path.exists(util.joinPaths(image_root, 'sbin/extlinux'))):
        return ExtLinuxInstaller(parent, image_root, geometry)
    elif override == 'grub' or (not override and grubpath):
        return GrubInstaller(parent, image_root, geometry,
                grubpath.replace(image_root, ''))
    log.warning('Could not find extlinux (with bootman) or grub')
    log.warning('No bootloader will be installed!')
    return DummyInstaller(parent, image_root, geometry)
