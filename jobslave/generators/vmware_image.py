#
# Copyright (c) 2011 rPath, Inc.
#

import os
import stat

from jobslave import buildtypes
from jobslave.generators import bootable_image, raw_hd_image, constants, \
    ovf_image
from jobslave.util import logCall
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
        if isinstance(value, unicode):
            value = value.encode('utf8')
        template = template.replace('@%s@' % name, str(value))
    return template


class VMwareImage(raw_hd_image.RawHdImage):

    ovfClass = ovf_image.VMwareOVFImage

    templateName = 'vmwareplayer.vmx'
    productName = buildtypes.typeNamesShort[buildtypes.VMWARE_IMAGE]
    raw2vmdk = '/usr/bin/raw2vmdk'

    platforms = {'' : 'other26xlinux',
                 'Red Hat Enterprise Linux AS 4' : 'rhel4',
                 'Red Hat Enterprise Linux Server 5' : 'rhel5',
                 'Red Hat Enterprise Linux Desktop Workstation 5' : 'rhel5',
                 'SLES 11 Delivered by rPath' : 'sles11',
                 'SLES 10 Delivered by rPath' : 'sles10',
                }

    def _createVMDK(self, hdImage, outfile, size, streaming=False):
        args = [
                self.raw2vmdk,
                '-C', str(self.geometry.cylindersRequired(size)),
                '-H', str(self.geometry.heads),
                '-S', str(self.geometry.sectors),
                '-A', self.adapter,
                ]
        if streaming:
            args += ['-s']
        args += [hdImage, outfile]

        logCall(args)

    @bootable_image.timeMe
    def createVMDK(self, hdImage, outfile, size):
        self._createVMDK(hdImage, outfile, size, False)

    @bootable_image.timeMe
    def createVMX(self, outfile, type='vmx'):
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
            'CAPACITY': str(self.capacity),
            }

        #write the file to the proper location
        #Read in the stub file
        if type == 'ovf':
            template = 'vmware.ovf.in'
            variables['GUESTOS'] = self.getGuestOSOvf()
        else:
            template = self.templateName
        infile = open(os.path.join(constants.templateDir, template),
                  'rb')
        filecontents = infile.read()
        infile.close()
        # Substitute values into the placeholders in the templtae.
        filecontents = substitute(filecontents, variables)
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

        disk = self.makeHDImage(image)
        self.status('Creating %s Image' % self.productName)

        util.mkdirChain(self.workingDir)
        vmdkPath = self.writeMachine(disk)
        if self.buildOVF10:
            self.writeVmwareOvf(disk.totalSize, vmdkPath)

        self.postOutput(self.outputFileList)

    def writeMachine(self, disk, callback=None):
        """Create VMX tarball for VMware Workstation deployments.

        A standard format VMDK will be created. The path to it will be returned
        for use in the OVF 1.0 generator.
        """
        if not callback:
            callback = VMwareCallback()
        vmxPath = os.path.join(self.workingDir, self.basefilename + '.vmx')
        vmdkPath = os.path.join(self.workingDir, self.basefilename + '.vmdk')
        outputPath = os.path.join(self.outputDir, self.basefilename +
                '.vmware.tar.gz')
        self.capacity = disk.totalSize
        # TODO: Add progress to raw2vmdk and pass it to creatingDisk()
        callback.creatingDisk(None, None)
        self.createVMDK(disk.image, vmdkPath, self.capacity)
        self.vmdkSize = os.stat(vmdkPath)[stat.ST_SIZE]
        disk.destroy()

        # TODO: Add progress to self.gzip() and pass it to creatingArchive()
        callback.creatingArchive(None, None)
        self.createVMX(vmxPath)
        self.setModes(self.workingDir)
        self.gzip(self.workingDir, outputPath)
        self.outputFileList.append(
            (outputPath, self.productName + ' Image'))
        return vmdkPath

    def writeVmwareOvf(self, capacity, vmdkPath):
        """Create OVF 1.0 output for general purpose usage."""
        vmdkGzOutputFile = os.path.join(self.outputDir, self.basefilename +
                '.vmdk.gz')
        self.gzip(vmdkPath, vmdkGzOutputFile)
        util.remove(vmdkPath)

        self.ovaPath = self.createOvf(self.basefilename,
                self.jobData['description'], constants.VMDK, vmdkGzOutputFile,
                capacity, True, self.workingDir, self.outputDir)
        self.outputFileList.append((self.ovaPath,
            self.productName + ' %s' % constants.OVFIMAGETAG))

    def __init__(self, *args, **kwargs):
        raw_hd_image.RawHdImage.__init__(self, *args, **kwargs)
        self.configure()

    def configure(self):
        self.adapter = self.getBuildData('diskAdapter')
        self.vmSnapshots = self.getBuildData('vmSnapshots')
        self.vmMemory = self.getBuildData('vmMemory')
        self.vmdkSize = None
        self.capacity = None

    def getGuestOS(self):
        platformName = self.getBuildData('platformName')
        platform = self.platforms.get(platformName, 'other26xlinux')
        suffix = self.baseFlavor.satisfies(deps.parseFlavor('is: x86_64')) \
                and "-64" or ""
        return platform + suffix

    def getGuestOSOvf(self):
        platform = 'other26xlinux'
        suffix = self.baseFlavor.satisfies(deps.parseFlavor('is: x86_64')) \
                and "-64" or ""
        return platform + suffix


class VMwareESXImage(VMwareImage):

    createType = 'vmfs'
    productName = buildtypes.typeNamesShort[buildtypes.VMWARE_ESX_IMAGE]

    def configure(self):
        VMwareImage.configure(self)
        self.adapter = 'lsilogic'
        self.vmSnapshots = False

    @bootable_image.timeMe
    def createOvfVMDK(self, hdImage, outfile, size):
        self._createVMDK(hdImage, outfile, size, True)

    def writeMachine(self, disk, callback=None):
        """Create OVF 0.9 tarball for ESX deployments.

        A streaming format VMDK will be created. The path to it will be
        returned for use in the OVF 1.0 generator.
        """
        if not callback:
            callback = VMwareCallback()
        ovfPath = os.path.join(self.workingDir, self.basefilename + '.ovf')
        vmdkPath = os.path.join(self.workingDir, self.basefilename + '.vmdk')
        ovfOutputFile = os.path.join(self.outputDir, self.basefilename +
                '-ovf.tar.gz')
        self.capacity = disk.totalSize
        # TODO: Add progress to raw2vmdk and pass it to creatingDisk()
        callback.creatingDisk(None, None)
        self.createOvfVMDK(disk.image, vmdkPath, disk.totalSize)
        self.vmdkSize = os.stat(vmdkPath)[stat.ST_SIZE]
        disk.destroy()

        # TODO: Add progress to self.gzip() and pass it to creatingArchive()
        callback.creatingArchive(None, None)
        self.createVMX(ovfPath, type='ovf')
        self.setModes(self.workingDir)
        self.gzip(self.workingDir, ovfOutputFile)
        self.outputFileList.append(
            (ovfOutputFile, self.productName + ' OVF 0.9 Image'))
        return vmdkPath


class VMwareCallback(object):

    def creatingDisk(self, completed, total):
        pass

    def creatingArchive(self, completed, total):
        pass
