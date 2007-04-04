from conary.lib import util
from jobslave.generators import loophelpers
from jobslave.generators import bootable_image

class LVMFilesystem(bootable_image.Filesystem):
    def mount(self, mountPoint):
        # no loopback needed here
        util.execute("mount %s %s" % (self.fsDev, mountPoint))
        self.mounted = True

    def umount(self):
        if not self.mounted:
            return
        util.execute("umount %s" % (self.fsDev))
        self.mounted = False

class LVMContainer:
    volGroupName = "vg00"
    loopDev = None
    filesystems = []

    def __init__(self, totalSize, image = None, offset = 0):
        assert image and offset # for now

        self.loopDev = loophelpers.loopAttach(image, offset)
        util.execute("pvcreate %s" % self.loopDev)
        util.execute("vgcreate %s %s" % (self.volGroupName, self.loopDev))

    def addFilesystem(self, mountPoint, size):
        name = mountPoint.replace('/', '')
        fsDev = '/dev/vg00/%s' % name
        util.execute('lvcreate -n %s -L%dK vg00' % (name, size / 1024))

        fs = LVMFilesystem(fsDev, size)
        self.filesystems.append(fs)
        return fs

    def destroy(self):
        for fs in self.filesystems:
            fs.umount()
            util.execute("lvchange -a n %s" % fs.fsDev)
        util.execute("vgchange -a n %s" % self.volGroupName)
        util.execute("pvchange -x n %s" % self.loopDev)
        loophelpers.loopDetach(self.loopDev)