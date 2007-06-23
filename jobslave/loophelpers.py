#
# Copyright (c) 2007 rPath, Inc.
#
# All Rights Reserved
#

import os
from conary.lib import util

def loopAttach(image, offset = 0):
    p = os.popen('losetup -f')
    dev = p.read().strip()
    p.close()
    util.execute('losetup %s %s %s' % \
                     (offset and ('-o%d' % offset) or '', dev, image))
    util.execute('sync')
    return dev

def loopDetach(dev):
    util.execute('losetup -d %s' % dev)
