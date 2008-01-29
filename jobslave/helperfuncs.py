#
# Copyright (c) 2007 rPath, Inc.
#
# All rights reserved
#

import os
import time


def getIP():
    p = os.popen("""/sbin/ifconfig `/sbin/route | grep "^default" | sed "s/.* //"` | grep "inet addr" | awk -F: '{print $2}' | sed 's/ .*//'""")
    data = p.read().strip()
    p.close()
    return data

def getSlaveRuntimeConfig(cfgPath = os.path.join(os.path.sep, \
        'etc', 'sysconfig', 'slave_runtime')):
    d = {}
    runtimeCfg = None
    try:
        try:
            runtimeCfg = open(cfgPath)
            for l in runtimeCfg:
                if l.startswith('#'):
                    continue
                k, v = [x.strip() for x in l.split('=')[0:2]]
                d[k] = v
        except Exception:
            pass
    finally:
        if runtimeCfg:
            runtimeCfg.close()

    return d

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
