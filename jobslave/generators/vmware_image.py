#
# Copyright (c) 2004-2007 rPath, Inc.
#
# All Rights Reserved
#

import os
import stat

from jobslave.generators import bootable_image, raw_hd_image, constants
from jobslave.imagegen import logCall
from conary.lib import util

def vmEscape(data, eatNewlines = True):
    data = data.replace('|', '|7C')
    escapeDict = {
            '#': '|23',
            '"': '|22',
            '<': '|3C',
            '>': '|3E'}
    for key, val in escapeDict.iteritems():
        data = data.replace(key, val)
    if eatNewlines:
        delim = ''
    else:
        delim = '|0A'
    data = delim.join(data.splitlines())
    return ''.join([c for c in data if ord(c) >= 32])

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
        logCall(cmd)

    @bootable_image.timeMe
    def createVMX(self, outfile):
        #Read in the stub file
        infile = open(os.path.join(constants.templateDir, self.templateName),
                      'rb')
        #Replace the @DELIMITED@ text with the appropriate values
        filecontents = infile.read()
        infile.close()
        #@NAME@ @MEM@ @FILENAME@

        # Escape ", #, |, <, and >, strip out control characters
        displayName = vmEscape(self.jobData.get('project', {}).get('name', ''))

        filecontents = filecontents.replace('@NAME@', displayName)
        filecontents = filecontents.replace('@DESCRIPTION@',
                vmEscape(self.jobData.get('description', ''),
                    eatNewlines = False))
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
        image = os.path.join(self.workDir, self.basefilename + '.hdd')
        workingDir = os.path.join(self.workDir, self.basefilename)
        outputFile = os.path.join(self.outputDir, self.basefilename + self.suffix)

        self.makeHDImage(image)
        self.status('Creating %s Image' % self.productName)
        util.mkdirChain(workingDir)
        vmdkPath = os.path.join(workingDir, self.basefilename + '.vmdk')
        vmxPath = os.path.join(workingDir, self.basefilename + '.vmx')

        size = os.stat(image)[stat.ST_SIZE]
        self.createVMDK(image, vmdkPath, size)

        self.createVMX(vmxPath)
        self.setModes(workingDir)
        self.gzip(workingDir, outputFile)
        self.postOutput(((outputFile, self.productName + 'image'),))

    def __init__(self, *args, **kwargs):
        raw_hd_image.RawHdImage.__init__(self, *args, **kwargs)
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
