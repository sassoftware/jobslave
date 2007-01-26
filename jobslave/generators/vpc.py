#
# Copyright (c) 2006-2007 rPath, Inc.
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
        if diskType == 'fixed':
            vhd.makeFlat(hdImage)
            os.rename(hdImage, filebase + '.vhd')
        elif diskType == 'difference':
            vhd.makeDynamic(hdImage, filebase + '-base.vhd')
            os.chmod(filebase + '-base.vhd', 0400)
            vhd.makeDifference(filebase + '-base.vhd', filebase + '.vhd',
                               self.basefilename + '-base.vhd')
        else:
            vhd.makeDynamic(hdImage, filebase + '.vhd')

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
        topDir = os.path.join(os.path.sep, 'tmp', self.jobId)
        image = os.path.join(topDir, self.basefilename + '.hdd')
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        outputFile = os.path.join(outputDir, self.basefilename + self.suffix)
        try:
            self.makeHDImage(image)

            self.status('Creating %s Image' % self.productName)
            workingDir = os.path.join(topDir, self.basefilename)
            if os.path.exists(workingDir):
                util.rmtree(workingDir)
            util.mkdirChain(workingDir)

            # pass just the basename, these functions handle the proper suffix
            self.createVHD(image, os.path.join(workingDir, self.basefilename))
            self.createVMC(os.path.join(workingDir, self.basefilename))

            self.status('Compressing Microsoft Virtual PC Image')
            self.gzip(workingDir, outputFile)
            self.postOutput(((outputFile, 'Virtual Server'),))
        finally:
            util.rmtree(topDir, ignore_errors = True)

    def __init__(self, *args, **kwargs):
        raw_hd_image.RawHdImage.__init__(self, *args, **kwargs)
        self.templateName = 'vpc.vmc'
        self.suffix = '.vpc.zip'
        self.productName = 'Microsoft Virtual Server'
