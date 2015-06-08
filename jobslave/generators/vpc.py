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


import os

from jobslave import buildtypes
from jobslave import imagegen
from jobslave.generators import constants
from jobslave.generators import bootable_image, raw_hd_image, ovf_image
from jobslave.generators import vhd
from jobslave.geometry import GEOMETRY_VHD

from conary.lib import util

class VirtualPCImage(raw_hd_image.RawHdImage):
    geometry = GEOMETRY_VHD

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
        image = os.path.join(self.workDir, self.basefilename + '.hdd')
        outputFile = os.path.join(self.outputDir, self.basefilename + self.suffix)

        self.makeHDImage(image)
        self.status('Creating %s Image' % self.productName)

        workingDir = os.path.join(self.workDir, self.basefilename)
        if os.path.exists(workingDir):
            util.rmtree(workingDir)
        util.mkdirChain(workingDir)

        # pass just the basename, these functions handle the proper suffix
        self.createVHD(image, os.path.join(workingDir, self.basefilename))
        self.createVMC(os.path.join(workingDir, self.basefilename))

        self.status('Compressing Microsoft Virtual PC Image')
        self.gzip(workingDir, outputFile)
        self.outputFileList.append((outputFile, 'Virtual Server'))

        if self.buildOVF10:
            self.capacity = 10000
            diskFileSize = imagegen.getFileSize(outputFile)
            self.ovfImage = ovf_image.XenOvfImage(self.basefilename,
                self.jobData['description'], constants.VHD, outputFile,
                diskFileSize, self.capacity, True, 
                self.getBuildData('vmMemory'), workingDir,
                self.outputDir)

            self.ovfObj = self.ovfImage.createOvf()
            self.ovfXml = self.ovfImage.writeOvf()
            self.ovfImage.createManifest()
            self.ovaPath = self.ovfImage.createOva()
            self.outputFileList.append((self.ovaPath,
                '%s %s' % (self.productName, constants.OVFIMAGETAG)))

        self.postOutput(self.outputFileList)

    def __init__(self, *args, **kwargs):
        raw_hd_image.RawHdImage.__init__(self, *args, **kwargs)
        self.templateName = 'vpc.vmc'
        self.suffix = '.vpc.tar.gz'
        self.productName = buildtypes.typeNamesShort[buildtypes.VIRTUAL_PC_IMAGE]
