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


def getMountedFiles(mntPoint):
    mntPoint = mntPoint.rstrip(os.path.sep)
    data = os.popen('fuser -m %s 2>/dev/null' % mntPoint, 'r').read()
    paths = set()
    for pid in data.split():
        fd_dir_path = '/proc/%s/fd' % pid
        try:
            fd_list = os.listdir(fd_dir_path)
        except (IOError, OSError):
            # The process disappeared (it was probably fuser)
            continue
        for fd in fd_list:
            try:
                path = os.readlink(os.path.join(fd_dir_path, fd))
            except (IOError, OSError):
                # This process might have shown up b/c of listdir
                continue
            if path.startswith(mntPoint + os.path.sep):
                paths.add(path)
    return paths
