#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import os
import testsuite
testsuite.setup()

import jobslave_helper
from jobslave import buildtypes

class HandlerTest(jobslave_helper.JobSlaveHelper):
    def testGetInstallableISO(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.INSTALLABLE_ISO)
        assert handler, "Failed to get Installable ISO"

    def testGetRawFSImage(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.RAW_FS_IMAGE)
        assert handler, "Failed to get Raw Filesystem Image"

    def testGetTarball(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.TARBALL)
        assert handler, "Failed to get Tarball"

    def testGetLiveISO(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.LIVE_ISO)
        assert handler, "Failed to get Live ISO"

    def testGetRawHdImage(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.RAW_HD_IMAGE)
        assert handler, "Failed to get Raw Hard Disk Image"

    def testGetVMwareImage(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.VMWARE_IMAGE)
        assert handler, "Failed to get VMware Player Image"

    def testGetESX(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.VMWARE_ESX_IMAGE)
        assert handler, "Failed to get VMware ESX Image"

    def testGetVirtualServer(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.VIRTUAL_PC_IMAGE)
        assert handler, "Failed to get Virtual Server Image"

    def testGetXenOVA(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.XEN_OVA)
        assert handler, "Failed to get Xen Enterprise Image"

    def testGetAMI(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.AMI)
        assert handler, "Failed to get AMI"

    def testGetUpdateIso(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.UPDATE_ISO)
        assert handler, "Failed to get Update ISO"

if __name__ == "__main__":
    testsuite.main()
