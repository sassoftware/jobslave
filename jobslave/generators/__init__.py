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
