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


from jobslave import buildtypes
from jobslave.generators import bootable_image, vpc


class VirtualIronVHD(vpc.VirtualPCImage):
    @bootable_image.timeMe
    def createVMC(self, fileBase):
        # a vritual iron image is a microsoft virtual pc image without the
        # vmc file. so stub it out.
        pass

    def __init__(self, *args, **kwargs):
        vpc.VirtualPCImage.__init__(self, *args, **kwargs)
        self.suffix = '.vhd.tar.gz'
        self.productName = buildtypes.typeNamesShort[buildtypes.VIRTUAL_IRON]
