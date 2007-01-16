#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import jobslave_helper
from jobslave import buildtypes
from jobslave import jobhandler

class DummyResponse(object):
    pass

class HandlerTest(jobslave_helper.JobSlaveHelper):
    def getHandler(self, buildType):
        return jobhandler.getHandler( \
            {'serialVersion': 1,
             'type' : 'build',
             'project' : 'foo.rpath.local',
             'name' : 'Foo',
             'UUID' : 'fake_uuid',
             'troveName' : 'group-core',
             'troveVersion' : '/conary.rpath.com@rpl:1/0:1.0.1-1-1',
             'troveFlavor': '1#x86',
             'data' : {'jsversion': '1.2.3'},
             'buildType' : buildType},
            DummyResponse())

    def testGetInstallableISO(self):
        handler = self.getHandler(buildtypes.INSTALLABLE_ISO)
        assert handler, "Failed to get Installable ISO"

    def testGetRawFSImage(self):
        handler = self.getHandler(buildtypes.RAW_FS_IMAGE)
        assert handler, "Failed to get Raw Filesystem Image"

    def testGetTarball(self):
        handler = self.getHandler(buildtypes.TARBALL)
        assert handler, "Failed to get Tarball"

    def testGetLiveISO(self):
        handler = self.getHandler(buildtypes.LIVE_ISO)
        assert handler, "Failed to get Live ISO"

    def testGetRawHdImage(self):
        handler = self.getHandler(buildtypes.RAW_HD_IMAGE)
        assert handler, "Failed to get Raw Hard Disk Image"

    def testGetVMwareImage(self):
        handler = self.getHandler(buildtypes.VMWARE_IMAGE)
        assert handler, "Failed to get VMware Player Image"

    def testGetESX(self):
        handler = self.getHandler(buildtypes.VMWARE_ESX_IMAGE)
        assert handler, "Failed to get VMware ESX Image"

    def testGetVirtualServer(self):
        handler = self.getHandler(buildtypes.VIRTUAL_PC_IMAGE)
        assert handler, "Failed to get Virtual Server Image"

    def testGetXenOVA(self):
        handler = self.getHandler(buildtypes.XEN_OVA)
        assert handler, "Failed to get Xen Enterprise Image"


if __name__ == "__main__":
    testsuite.main()
