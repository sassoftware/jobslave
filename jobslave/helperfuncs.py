#
# Copyright (c) 2007 rPath, Inc.
#
# All rights reserved
#

import os

def getIP():
    p = os.popen("""/sbin/ifconfig `/sbin/route | grep "^default" | sed "s/.* //"` | grep "inet addr" | awk -F: '{print $2}' | sed 's/ .*//'""")
    data = p.read().strip()
    p.close()
    return data

def getSlaveRuntimeConfig():
    d = {}
    try:
        try:
            runtimeCfg = open('/etc/sysconfig/slave_runtime')
            for l in runtimeCfg:
                if l.startswith('#'):
                    continue
                k, v = l.split('=')[0:2]
                d[k] = v
        except Exception:
            pass
    finally:
        if runtimeCfg:
            runtimeCfg.close()

    return d

