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


from conary.lib import util
import os.path


def is_RH(image_root):
    return os.path.exists(util.joinPaths(image_root, 'etc/redhat-release'))


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
