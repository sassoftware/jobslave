#
# Copyright (c) 2008 rPath, Inc.
#
# All Rights Reserved
#

from conary.lib import util
import os.path

def is_SUSE(image_root, version=None):
    versionFile = util.joinPaths(image_root, 'etc', 'SuSE-release')
    if not os.path.exists(versionFile):
        return False

    if not version:
        return True

    for line in open(versionFile):
        if line.startswith('VERSION'):
            ver = int(line.split('=')[1])
            if ver == version:
                return True

    return False

def is_UBUNTU(image_root):
    return os.path.exists(util.joinPaths(image_root, 'etc', 'debian_version'))

__ALL__ = ['is_SUSE', 'is_UBUNTU']
