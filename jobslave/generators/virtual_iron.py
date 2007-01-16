#
# Copyright (c) 2006 rPath, Inc.
#
# All Rights Reserved
#

from jobslave.generators import bootable_image, vpc

from conary.lib import util

class VirtualIronVHD(vpc.VirtualPCImage):
    @bootable_image.timeMe
    def createVMC(self, fileBase):
        # a vritual iron image is a microsoft virtual pc image without the
        # vmc file. so stub it out.
        pass

    def __init__(self, *args, **kwargs):
        vpc.VirtualPCImage.__init__(self, *args, **kwargs)
        self.suffix = '.vhd.zip'
