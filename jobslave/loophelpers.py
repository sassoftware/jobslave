#
# Copyright (c) SAS Institute Inc.
#

import os
from jobslave.util import logCall


def loopAttach(image, offset=None, size=None):
    p = os.popen('losetup -f')
    dev = p.read().strip()
    p.close()
    cmd = ['losetup']
    if offset:
        cmd += ['-o', str(offset)]
    if size:
        cmd += ['--sizelimit', str(size)]
    cmd += [dev, image]
    logCall(cmd)
    return dev


def loopDetach(dev):
    logCall(['losetup', '-d', dev], ignoreErrors=True)
