#
# Copyright (c) SAS Institute Inc.
#

import logging

from jobslave import loophelpers
from jobslave.util import logCall
from jobslave.generators import bootable_image

log = logging.getLogger(__name__)


class LVMContainer(object):
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

        fs = bootable_image.Filesystem(fsDev, fsType, size, fsLabel=mountPoint)
        self.filesystems.append(fs)
        return fs

    def unmount(self):
        for fs in self.filesystems:
            fs.umount()
            logCall("lvchange -a n %s" % fs.fsDev)
        logCall("vgchange -a n %s" % self.volGroupName)
        logCall("pvchange -x n %s" % self.loopDev)
        loophelpers.loopDetach(self.loopDev)
