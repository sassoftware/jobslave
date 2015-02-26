#
# Copyright (c) SAS Institute Inc.
#

import os
from testutils import mock

from jobslave.generators import raw_hd_image, bootable_image
from jobslave_test.jobslave_helper import JobSlaveHelper
from conary.lib import util

class RawHdImage(JobSlaveHelper):
    def setUp(self):
        super(RawHdImage, self).setUp()
        self.mock(bootable_image.loophelpers, 'loopAttach', lambda *a, **kw:
            '/dev/not-a-chance')
        self.mock(bootable_image.loophelpers, 'loopDetach', lambda *a, **kw:
            None)

        def mockCalculatePartitionSizes(uJob, mounts):
            sizes = dict.fromkeys(mounts, 1024*2)
            return sizes, sum(sizes.values())
        self.mock(bootable_image.filesystems, 'calculatePartitionSizes',
                mockCalculatePartitionSizes)

        self.img = raw_hd_image.RawHdImage(self.slaveCfg, self.data)
        mock.mock(self.img, 'bootloader')
        self.img.swapSize = 1024*1024
        mock.mockMethod(self.img._getLabelPath, returnValue='cny.tv@ns:1')

    def testSkelDir(self):
        from conary.lib import epdb; epdb.serve()
        img = self.img

        img.preTagScripts()
        self.assertEquals(
            file(os.path.join(img.root, 'etc', 'sysconfig', 'network')).read(),
            """\
#Installed by rBuilder
NETWORKING=yes
HOSTNAME=localhost.localdomain
NOZEROCONF=yes
""")

    def testVirtualHardwareVersion(self):
        img = self.img
        Mocked = set(['mkfs.ext3', 'tune2fs', ])
        origLogCall = raw_hd_image.logCall
        logCallArgs = []
        def mockLogCall(cmd, **kw):
            logCallArgs.append((cmd, kw))
            if (isinstance(cmd, list) and cmd[0] in Mocked) or cmd.startswith('mount') or cmd.startswith('umount') or cmd.startswith('chroot'):
                return
            return origLogCall(cmd, **kw)
        self.mock(raw_hd_image, 'logCall', mockLogCall)
        self.mock(bootable_image, 'logCall', mockLogCall)
        self.mock(bootable_image.loophelpers, 'logCall', mockLogCall)
        mknodArgs = []
        def mockMknod(*args):
            mknodArgs.append(args)
        self.mock(os, 'mknod', mockMknod)

        chmodArgs = []
        def mockChmod(*args):
            chmodArgs.append(args)
        self.mock(os, 'chmod', mockMknod)

        util.mkdirChain(os.path.join(img.root, "root"))
        file(os.path.join(img.root, "root", "conary-tag-script.in"), "w").write(
                "echo nothing here")
        util.mkdirChain(img.changesetDir)

        mock.mockMethod(img.downloadChangesets)
        mock.mockMethod(img.postOutput)
        mock.mockMethod(img.loadRPM)
        self.mock(img, 'updateGroupChangeSet', lambda x: None)
        img.write()
