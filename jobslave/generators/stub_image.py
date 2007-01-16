#
# Copyright (c) 2005-2006 rPath, Inc.
#
# All Rights Reserved
#
import os.path

from jobslave.generators.imagegen import ImageGenerator

class StubImage(ImageGenerator):
    def write(self):
        f = os.path.join(os.path.sep, 'tmp', "stub.iso")

        buildId = self.jobId
        stubContent = self.getBuildData('stringArg')

        stub = file(f, "w")
        print >> stub, stubContent

        return [(f, "Disk 1")]
