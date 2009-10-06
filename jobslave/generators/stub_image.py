#
# Copyright (c) 2005-2006 rPath, Inc.
#
# All Rights Reserved
#
import os.path

from jobslave import constants
from jobslave.imagegen import ImageGenerator

class StubImage(ImageGenerator):
    def write(self):
        f = os.path.join(constants.tmpDir, "stub.iso")

        stubContent = self.getBuildData('stringArg')

        stub = file(f, "w")
        print >> stub, stubContent

        return [(f, "Disk 1")]
