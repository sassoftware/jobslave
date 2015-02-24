#
# Copyright (c) SAS Institute Inc.
#

import os
from testutils import mock

from jobslave.generators import raw_hd_image, bootable_image
from jobslave_test.jobslave_helper import JobSlaveHelper
from conary.lib import util

class RawHdImage(JobSlaveHelper):
    def testSkelDir(self):
        img = raw_hd_image.RawHdImage(self.slaveCfg, self.data)
        util.rmtree(img.root)
        mock.mockMethod(img._getLabelPath, returnValue='cny.tv@ns:1')
        mock.mock(img, 'bootloader')
        img.swapSize = 1024*1024

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
        self.constants.templateDir = os.path.join(self.testDir, '..',
                'templates')
        Mocked = set(['losetup', 'mkfs.ext3', 'tune2fs', ])
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

        def mockCalculatePartitionSizes(uJob, mounts):
            sizes = dict.fromkeys(mounts, 1024*2)
            return sizes, sum(sizes.values())

        img = raw_hd_image.RawHdImage(self.slaveCfg, self.data)
        util.rmtree(img.root, ignore_errors=True)
        util.mkdirChain(os.path.join(img.root, "root"))
        file(os.path.join(img.root, "root", "conary-tag-script.in"), "w").write(
                "echo nothing here")
        util.mkdirChain(img.changesetDir)
        img.swapSize = 1024*1024

        mock.mockMethod(img._getLabelPath, returnValue='cny.tv@ns:1')
        mock.mockMethod(img.downloadChangesets)
        mock.mockMethod(img.postOutput)
        mock.mockMethod(img.loadRPM)
        self.mock(bootable_image.filesystems, 'calculatePartitionSizes',
                mockCalculatePartitionSizes)
        self.mock(img, 'updateGroupChangeSet', lambda x: None)
        img.write()
