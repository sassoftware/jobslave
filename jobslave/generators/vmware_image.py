#
# Copyright (c) 2004-2007 rPath, Inc.
#
# All Rights Reserved
#

import os

from jobslave.generators import bootable_image, raw_hd_image, constants

from conary.lib import util

class VMwareImage(raw_hd_image.RawHdImage):
    @bootable_image.timeMe
    def createVMDK(self, hdImage, outfile, size):
        if self.adapter == 'ide':
            cylinders = size / constants.cylindersize
            cmd = 'raw2vmdk -C %d -H %d -S %d -A %s %s %s' % \
                (cylinders, constants.heads, constants.sectors,
                 self.adapter, hdImage, outfile)
        else:
            cylinders = (size / constants.cylindersize) * \
                (constants.heads * constants.sectors) / \
                (constants.scsiHeads * constants.scsiSectors)
            cmd = 'raw2vmdk -C %d -H %d -S %d -A %s %s %s' % \
                (cylinders, constants.scsiHeads, constants.scsiSectors,
                 self.adapter, hdImage, outfile)
        util.execute(cmd)

    @bootable_image.timeMe
    def createVMX(self, outfile):
        #Read in the stub file
        infile = open(os.path.join(constants.templateDir, self.templateName),
                      'rb')
        #Replace the @DELIMITED@ text with the appropriate values
        filecontents = infile.read()
        infile.close()
        #@NAME@ @MEM@ @FILENAME@
        displayName = self.jobData['project']['name'].replace('"', '')
        filecontents = filecontents.replace('@NAME@', displayName)
        filecontents = filecontents.replace('@MEM@', str(self.vmMemory))
        filecontents = filecontents.replace('@FILENAME@', self.basefilename)
        filecontents = filecontents.replace('@NETWORK_CONNECTION@', \
            self.getBuildData('natNetworking') and 'nat' or 'bridged')
        filecontents = filecontents.replace('@ADAPTER@', self.adapter)
        filecontents = filecontents.replace('@ADAPTERDEV@',
                                            (self.adapter == 'lsilogic') \
                                                and 'scsi' or 'ide')
        filecontents = filecontents.replace('@SNAPSHOT@',
                                            str(not self.vmSnapshots).upper())

        #write the file to the proper location
        ofile = open(outfile, 'wb')
        ofile.write(filecontents)
        ofile.close()

    def setModes(self, baseDir):
        files = os.listdir(baseDir)
        for f in files:
            if f.endswith('.vmx'):
                os.chmod(os.path.join(baseDir, f), 0755)
            else:
                os.chmod(os.path.join(baseDir, f), 0600)

    def write(self):
        topDir = os.path.join(os.path.sep, 'tmp', self.jobId)
        image = os.path.join(topDir, self.basefilename + '.hdd')
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        workingDir = os.path.join(topDir, self.basefilename)
        outputFile = os.path.join(outputDir, self.basefilename + self.suffix)
        try:
            size = self.getImageSize()
            self.makeHDImage(image, size)
            self.status('Creating %s Image' % self.productName)
            if os.path.exists(workingDir):
                util.rmtree(workingDir)
            util.mkdirChain(workingDir)
            vmdkPath = os.path.join(workingDir, self.basefilename + '.vmdk')
            vmxPath = os.path.join(workingDir, self.basefilename + '.vmx')

            # passing size simply to avoid recalculation, since that incurs
            # network traffic
            self.createVMDK(image, vmdkPath, size)

            self.createVMX(vmxPath)
            self.setModes(workingDir)
            self.gzip(workingDir, outputFile)
            self.postOutput(((outputFile, self.productName + 'image'),))
        finally:
            util.rmtree(topDir, ignore_errors = True)

    def __init__(self, *args, **kwargs):
        raw_hd_image.RawHdImage.__init__(self, *args, **kwargs)
        self.freespace = self.getBuildData("freespace") * 1048576
        self.swapSize = self.getBuildData("swapSize") * 1048576
        self.adapter = self.getBuildData('diskAdapter')
        self.vmSnapshots = self.getBuildData('vmSnapshots')
        self.vmMemory = self.getBuildData('vmMemory')
        self.templateName = 'vmwareplayer.vmx'
        self.productName = "VMware Player"
        self.suffix = '.vmware.tgz'

        if self.adapter == 'lsilogic':
            self.scsiModules = True

class VMwareESXImage(VMwareImage):
    def __init__(self, *args, **kwargs):
        VMwareImage.__init__(self, *args, **kwargs)
        self.adapter = 'lsilogic'
        self.vmSnapshots = False
        self.createType = 'vmfs'
        self.templateName = 'vmwareesx.vmx'
        self.productName = "VMware ESX Server"
        self.suffix = '.esx.tgz'
        self.scsiModules = True

    @bootable_image.timeMe
    def createVMDK(self, hdImage, outfile, size):
        cylinders = size / constants.cylindersize
        infile = open(os.path.join(constants.templateDir, 'vmdisk.vmdk'), 'rb')
        #Replace the @DELIMITED@ text with the appropriate values
        filecontents = infile.read()
        infile.close()

        filecontents = filecontents.replace('@CREATE_TYPE@', self.createType)
        filecontents = filecontents.replace('@FILENAME@', self.basefilename)
        filecontents = filecontents.replace('@ADAPTER@', self.adapter)
        filecontents = filecontents.replace('@EXTENTS@', str(size / 512))
        filecontents = filecontents.replace('@CYLINDERS@', str(cylinders))
        filecontents = filecontents.replace( \
            '@EXT_TYPE@', self.createType == 'vmfs' and 'VMFS' or 'FLAT')

        ofile = open(outfile, 'wb')
        ofile.write(filecontents)
        ofile.close()

        os.rename(hdImage, outfile.replace('.vmdk', '-flat.vmdk'))
