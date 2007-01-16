#
# Copyright (c) 2006 rPath, Inc.
#
# All Rights Reserved
#

import os

from jobslave.generators import constants
from jobslave.generators import bootable_image, raw_hd_image
from jobslave.generators import vhd

from conary.lib import util

class VirtualPCImage(raw_hd_image.RawHdImage):
    @bootable_image.timeMe
    def createVHD(self, hdImage, filebase):
        diskType = self.getBuildData('vhdDiskType')
        if diskType == 'dynamic':
            vhd.makeDynamic(hdImage, filebase + '.vhd')
        elif diskType == 'fixed':
            vhd.makeFlat(hdImage)
            os.rename(hdImage, filebase + '.vhd')
        elif diskType == 'difference':
            vhd.makeDynamic(hdImage, filebase + '-base.vhd')
            os.chmod(filebase + '-base.vhd', 0400)
            vhd.makeDifference(filebase + '-base.vhd', filebase + '.vhd',
                               self.basefilename + '-base.vhd')

    @bootable_image.timeMe
    def createVMC(self, fileBase):
        outfile = fileBase + '.vmc'
        diskFileName = fileBase + '.vhd'
        # Read in the stub file
        infile = open(os.path.join(constants.templateDir, self.templateName),
                      'rb')
        # Replace the @DELIMITED@ text with the appropriate values
        filecontents = infile.read()
        infile.close()
        filecontents = filecontents.replace('@DISK_FILENAME@',
                                            os.path.basename(diskFileName))
        filecontents = filecontents.replace('@MINT_VERSION@',
                                            'UNKNOWN')

        # write the file to the proper location
        ofile = open(outfile, 'wb')
        # NOTE: Virtual PC only handles UTF-16.
        ofile.write(filecontents.encode('utf-16'))
        ofile.close()

    def write(self):
        image = os.path.join(os.path.sep, 'tmp', self.basefilename + '.hdd')
        try:
            self.makeHDImage(image)

            self.status('Creating Microsoft Virtual PC Image')
            outputDir = os.path.join(os.path.sep, 'tmp', self.basefilename)
            outputFile = outputDir + self.suffix
            if os.path.exists(outputDir):
                util.rmtree(outputDir)
            os.mkdir(outputDir)

            # pass just the basename, these functions handle the proper suffix
            self.createVHD(image, os.path.join(outputDir, self.basefilename))
            self.createVMC(os.path.join(outputDir, self.basefilename))

            self.status('Compressing Microsoft Virtual PC Image')
            self.zip(outputDir, outputFile)
            import epdb
            epdb.st()
            # FIXME: deliver output file
        finally:
            util.rmtree(image, ignore_errors = True)
            util.rmtree(outputDir, ignore_errors = True)
            util.rmtree(outputFile, ignore_errors = True)

    def __init__(self, *args, **kwargs):
        raw_hd_image.RawHdImage.__init__(self, *args, **kwargs)
        self.templateName = 'vpc.vmc'
        self.suffix = '.vpc.zip'
