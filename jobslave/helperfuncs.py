#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved
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
