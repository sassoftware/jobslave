#
# Copyright (c) 2004-2007 rPath, Inc.
#
# All Rights Reserved
#

import os
import stat

from jobslave import buildtypes
from jobslave.generators import bootable_image, raw_hd_image, constants
from jobslave.imagegen import logCall
from conary.lib import util
from conary.deps import deps

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


def substitute(template, variables):
    l = []
    excludeLines = False
    # first go through the file looking for <!-- if @KEY@ == val
    for line in template.split('\n'):
        # check for a condition
        if line.startswith('<!-- if'):
            fields = line.split()
            if len(fields) != 5:
                raise RuntimeError('invalid template file')
            key = fields[2][1:-1]
            value = fields[4]
            # if the condition is not met, start skipping lines
            if variables[key] != value:
                excludeLines = True
            continue
        elif line.startswith('-->'):
            # end of the conditional section, start including
            # stuff again
            excludeLines = False
            continue
        if not excludeLines:
            l.append(line)
    template = '\n'.join(l)
    for name, value in variables.items():
        template = template.replace('@%s@' % name, str(value))
    return template


class VMwareImage(raw_hd_image.RawHdImage):
    useOVF = False

    @bootable_image.timeMe
    def createVMDK(self, hdImage, outfile, size):
        cylinders = raw_hd_image.divCeil(size, constants.bytesPerCylinder)
        logCall('raw2vmdk -C %d -H %d -S %d -A %s %s %s' % (
            cylinders, constants.heads, constants.sectors,
            self.adapter, hdImage, outfile))

    @bootable_image.timeMe
    def createVMX(self, outfile):
        # Escape ", #, |, <, and >, strip out control characters
        displayName = self.jobData.get('project', {}).get('name', '')
        description = self.jobData.get('description', '')

        variables = {
            'NAME': vmEscape(displayName),
            'DESCRIPTION': vmEscape(description, eatNewlines=False),
            'MEM': self.vmMemory,
            'FILENAME': self.basefilename,
            'NETWORK_CONNECTION': (self.getBuildData('natNetworking')
                and 'nat' or 'bridged'),
            'ADAPTER': self.adapter,
            'ADAPTERDEV': self.adapter == 'lsilogic' and 'scsi' or 'ide',
            'SNAPSHOT': str(not self.vmSnapshots).upper(),
            'GUESTOS': self.getGuestOS(),
            'SIZE': str(self.vmdkSize),
            'CAPACITY': str(self.vmdkCapacity),
            }

        #write the file to the proper location
        # Don't write a vmx for OVF images, since we've not tested that
        if not self.useOVF:
            #Read in the stub file
            infile = open(os.path.join(constants.templateDir, self.templateName),
                      'rb')
            filecontents = infile.read()
            infile.close()
            # Substitute values into the placeholders in the templtae.
            filecontents = substitute(filecontents, variables)
            ofile = open(outfile, 'wb')
            ofile.write(filecontents)
            ofile.close()

        # if we have a sparse disk, we can write out an .ovf too
        if self.useOVF:
            assert(self.getGuestOS() in ('other26xlinux', 'other26xlinux-64'))
            infile = open(os.path.join(constants.templateDir, 'vmware.ovf.in'),
                          'rb')
            filecontents = infile.read()
            infile.close()
            filecontents = substitute(filecontents, variables)
            ovfPath = os.path.join(os.path.dirname(outfile),
                                   self.basefilename + '.ovf')
            file(ovfPath, 'wb').write(filecontents)

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

        self.vmdkCapacity = os.stat(image)[stat.ST_SIZE]
        self.createVMDK(image, vmdkPath, self.vmdkCapacity)
        try:
            self.vmdkSize = os.stat(vmdkPath)[stat.ST_SIZE]
        except OSError:
            pass

        self.createVMX(vmxPath)
        self.setModes(workingDir)
        self.gzip(workingDir, outputFile)
        self.postOutput(((outputFile, self.productName + ' Image'),))

    def __init__(self, *args, **kwargs):
        raw_hd_image.RawHdImage.__init__(self, *args, **kwargs)
        self.adapter = self.getBuildData('diskAdapter')
        self.vmSnapshots = self.getBuildData('vmSnapshots')
        self.vmMemory = self.getBuildData('vmMemory')
        self.templateName = 'vmwareplayer.vmx'
        self.productName = buildtypes.typeNamesShort[buildtypes.VMWARE_IMAGE]
        self.suffix = '.vmware.tar.gz'
        self.vmdkSize = 0
        self.vmdkCapacity = 0

        if self.adapter == 'lsilogic':
            self.scsiModules = True

    def getGuestOS(self):
        suffix = self.baseFlavor.satisfies(deps.parseFlavor('is: x86_64')) \
                and "-64" or ""
        return "other26xlinux" + suffix

class VMwareOVFImage(VMwareImage):
    useOVF = True

    @bootable_image.timeMe
    def createVMDK(self, hdImage, outfile, size):
        cylinders = raw_hd_image.divCeil(size, constants.bytesPerCylinder)
        logCall('raw2vmdk -C %d -H %d -S %d -s %s %s' % (
            cylinders, constants.heads, constants.sectors,
            hdImage, outfile))

class VMwareESXImage(VMwareImage):
    useOVF = False
    def __init__(self, *args, **kwargs):
        VMwareImage.__init__(self, *args, **kwargs)
        self.adapter = 'lsilogic'
        self.vmSnapshots = False
        self.createType = 'vmfs'
        self.templateName = 'vmwareesx.vmx'
        self.productName = buildtypes.typeNamesShort[buildtypes.VMWARE_ESX_IMAGE]
        self.suffix = '.esx.tar.gz'
        self.scsiModules = True

    @bootable_image.timeMe
    def createVMDK(self, hdImage, outfile, size):
        cylinders = raw_hd_image.divCeil(size, constants.bytesPerCylinder)
        extents = raw_hd_image.divCeil(size, 512)

        # Generate the VMDK from template.
        infile = open(os.path.join(constants.templateDir, 'vmdisk.vmdk'), 'rb')
        filecontents = infile.read()
        infile.close()

        filecontents = substitute(filecontents, {
            'CREATE_TYPE': self.createType,
            'FILENAME': self.basefilename,
            'ADAPTER': self.adapter,
            'EXTENTS': extents,

            'CYLINDERS': cylinders,
            'HEADS': constants.heads,
            'SECTORS': constants.sectors,

            'EXT_TYPE': self.createType == 'vmfs' and 'VMFS' or 'FLAT',
          })

        ofile = open(outfile, 'wb')
        ofile.write(filecontents)
        ofile.close()

        # Move the raw HD image into place.
        os.rename(hdImage, outfile.replace('.vmdk', '-flat.vmdk'))

    def getGuestOS(self):
        arch64 = self.baseFlavor.satisfies(deps.parseFlavor('is: x86_64'))
        return arch64 and "otherlinux-64" or "linux"
