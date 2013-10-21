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

        self.loopDev = loophelpers.loopAttach(image, offset=offset, size=totalSize)
        logCall(['lvm', 'pvcreate', self.loopDev])
        logCall(['lvm', 'vgcreate', self.volGroupName, self.loopDev])

    def addFilesystem(self, mountPoint, fsType, size):
        name = mountPoint.replace('/', '')
        if not name:
            name = 'root'

        fsDev = '/dev/vg00/%s' % name
        logCall(['lvm', 'lvcreate',
            '-n', name,
            '-L', '%sK' % (size / 1024),
            self.volGroupName])

        fs = bootable_image.Filesystem(fsDev, fsType, size, fsLabel=mountPoint,
                useLoop=False)
        self.filesystems.append(fs)
        return fs

    def unmount(self):
        for fs in self.filesystems:
            fs.umount()
        logCall(['lvm', 'vgchange', '-a', 'n', self.volGroupName])
        loophelpers.loopDetach(self.loopDev)
