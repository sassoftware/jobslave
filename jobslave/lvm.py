#
# Copyright (c) 2007 rPath, Inc.
# All Rights Reserved
#

import logging
import sys

from conary.lib import util
from jobslave import loophelpers
from jobslave.util import logCall
from jobslave.generators import bootable_image

log = logging.getLogger(__name__)


class LVMFilesystem(bootable_image.Filesystem):
    def mount(self, mountPoint):
        if self.fsType == "swap":
            return

        # no loopback needed here
        logCall("mount -n %s %s" % (self.fsDev, mountPoint))
        self.mounted = True

    def umount(self):
        if self.fsType == "swap":
            return

        if not self.mounted:
            return

        logCall("umount -n %s" % (self.fsDev), ignoreErrors = True)
        self.mounted = False

class LVMContainer:
    volGroupName = "vg00"
    loopDev = None

    def __init__(self, totalSize, image = None, offset = 0):
        self.filesystems = []
        assert image # for now

        self.loopDev = loophelpers.loopAttach(image, offset)
        logCall("pvcreate %s" % self.loopDev)
        logCall("vgcreate %s %s" % (self.volGroupName, self.loopDev))

    def addFilesystem(self, mountPoint, fsType, size):
        name = mountPoint.replace('/', '')
        if not name:
            name = 'root'

        fsDev = '/dev/vg00/%s' % name
        logCall('lvcreate -n %s -L%dK vg00' % (name, size / 1024))

        fs = LVMFilesystem(fsDev, fsType, size, fsLabel = mountPoint)
        self.filesystems.append(fs)
        return fs

    def destroy(self):
        for fs in self.filesystems:
            fs.umount()
            logCall("lvchange -a n %s" % fs.fsDev)
        logCall("vgchange -a n %s" % self.volGroupName)
        logCall("pvchange -x n %s" % self.loopDev)
        loophelpers.loopDetach(self.loopDev)
