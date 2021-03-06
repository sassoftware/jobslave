#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


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

    def testGetRawHdImage(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.RAW_HD_IMAGE)
        assert handler, "Failed to get Raw Hard Disk Image"

    def testGetVMwareImage(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.VMWARE_IMAGE)
        assert handler, "Failed to get VMware (R) Image"

    def testGetESX(self):
        handler = self.suppressOutput(self.getHandler,
                                     buildtypes.VMWARE_ESX_IMAGE)
        assert handler, "Failed to get VMware (R) ESX Image"

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
