#
# Copyright (c) 2007 rPath, Inc.
#
# All Rights Reserved
#

import os
from conary.lib import util
from jobslave.imagegen import logCall

def loopAttach(image, offset = 0):
    p = os.popen('losetup -f')
    dev = p.read().strip()
    p.close()
    logCall('losetup %s %s %s' % \
                     (offset and ('-o%d' % offset) or '', dev, image))
    logCall('sync')
    return dev

def loopDetach(dev):
    logCall('losetup -d %s' % dev, ignoreErrors = True)
