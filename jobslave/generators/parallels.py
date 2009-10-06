#
# Copyright (c) 2007 rPath, Inc.
#
# All Rights Reserved
#

import os

from jobslave.generators import constants
from jobslave.generators import bootable_image, raw_hd_image
from jobslave.generators import vhd

from conary.lib import util

class ParallelsImage(raw_hd_image.RawHdImage):
    @bootable_image.timeMe
    def createPVS(self, fileBase):
        pass

    def write(self):
        topDir = os.path.join(constants.tmpDir, self.UUID)
        outputDir = os.path.join(topDir, self.basefilename)
        outputFile = outputDir + self.suffix
        image = outputDir + '.hdd'
        try:
            if os.path.exists(outputDir):
                util.rmtree(outputDir)
            util.mkdirChain(outputDir)
            self.makeHDImage(image)

            self.status('Creating Parallels Image')

            # pass just the basename, these functions handle the proper suffix
            self.createPVS(os.path.join(outputDir, self.basefilename))

            self.status('Compressing Parallels Image')
            self.zip(outputDir, outputFile)
            import epdb
            epdb.st()
            # FIXME: deliver output file
        finally:
            util.rmtree(topDir, ignore_errors = True)

    def __init__(self, *args, **kwargs):
        raw_hd_image.RawHdImage.__init__(self, *args, **kwargs)
        # FIXME: put the proper template in here
        self.templateName = 'vpc.vmc'
        self.suffix = '.pvs.zip'
