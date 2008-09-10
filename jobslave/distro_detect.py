#
# Copyright (c) 2008 rPath, Inc.
#
# All Rights Reserved
#

from conary.lib import util
import os.path

def is_SUSE(image_root):
    return os.path.exists(util.joinPaths(image_root, 'etc', 'SuSE-release'))

def is_UBUNTU(image_root):
    return os.path.exists(util.joinPaths(image_root, 'etc', 'debian_version'))

__ALL__ = ['is_SUSE', 'is_UBUNTU']
