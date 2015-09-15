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
import stat
from collections import namedtuple

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


class OSInfo(namedtuple('OSInfo', 'ovfId version description osType')):
    __slots__ = ()


class VMwareImage(raw_hd_image.RawHdImage):

    ovfClass = ovf_image.VMwareOVFImage

    templateName = 'vmwareplayer.vmx'
    productName = buildtypes.typeNamesShort[buildtypes.VMWARE_IMAGE]

    platforms = {'' : ('other26xlinux', ''),
                 'Red Hat Enterprise Linux AS 4': ('rhel4', '4'),
                 'Red Hat Enterprise Linux Server 5': ('rhel5', '5'),
                 'Red Hat Enterprise Linux Desktop Workstation 5':
                    ('rhel5', '5'),
                 'Red Hat Enterprise Linux Server 6': ('rhel6', '6'),
                 'SLES 11 Delivered by rPath': ('sles11', '11'),
                 'SLES 10 Delivered by rPath': ('sles10', '10'),
                 'SuSE Linux Enterprise Server 10 SP3': ('sles10', '10'),
                 'SuSE Linux Enterprise Server 11 SP1': ('sles11', '11') ,

                 # Map centos 5 -> rhel 5 for now since VCD doesn't currently
                 # support centos 5.
                 'CentOS 5': ('rhel5', '5'),
                }

    WithCompressedDisks = True

    def _getPlatformAndVersion(self):
        platformName = self.getBuildData('platformName')
        return self.platforms.get(platformName, self.platforms[''])

    def getPlatformAndVersion(self):
        if not self.productDefinition:
            return self._getPlatformAndVersion()

        info = self.productDefinition.getPlatformInformation()
        if not info or not hasattr(info, 'platformClassifier'):
            return self._getPlatformAndVersion()

        cls = info.platformClassifier

        # Map centos 5 -> rhel 5 for now since VCD doesn't currently
        # support centos 5.
        if cls.name == 'centos':
            name = 'rhel'
        else:
            name = cls.name

        name = '%s%s' % (name, cls.version)
        version = cls.version

        return (name, version)

    @bootable_image.timeMe
    def createVMDK(self, hdImage, outfile, size):
        createVMDK(hdImage, outfile, size, geometry=self.geometry,
                adapter=self.adapter, hwVersion=self.hwVersion,
                streaming=False)

    @bootable_image.timeMe
    def createVMX(self, outfile, type='vmx'):
        # Escape ", #, |, <, and >, strip out control characters
        displayName = self.original_basefilename
        description = self.jobData.get('description', '')

        variables = {
            'NAME': vmEscape(displayName),
            'DESCRIPTION': vmEscape(description, eatNewlines=False),
            'MEM': self.vmMemory,
            'CPUS': self.vmCPUs,
            'FILENAME': self.basefilename,
            'NETWORK_CONNECTION': (self.getBuildData('natNetworking')
                and 'nat' or 'bridged'),
            'ADAPTER': self.adapter,
            'ADAPTERDEV': self.adapter == 'lsilogic' and 'scsi' or 'ide',
            'SNAPSHOT': str(not self.vmSnapshots).upper(),
            'GUESTOS': self.getGuestOS(),
            'VIRTUAL_HARDWARE_VERSION' : self.hwVersion,
            }

        #write the file to the proper location
        #Read in the stub file
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
                '.vmware.zip')
        self.capacity = disk.totalSize
        # TODO: Add progress to raw2vmdk and pass it to creatingDisk()
        callback.creatingDisk(None, None)
        self.createVMDK(disk.image, vmdkPath, self.capacity)
        disk.destroy()

        # TODO: Add progress to self.gzip() and pass it to creatingArchive()
        callback.creatingArchive(None, None)
        self.createVMX(vmxPath)
        self.setModes(self.workingDir)
        self.zipArchive(self.workingDir, outputPath)
        self.outputFileList.append(
            (outputPath, self.productName + ' Image'))
        return vmdkPath

    def compressDiskImage(self, vmdkPath):
        if not self.WithCompressedDisks:
            # Need to add the file to the final directory
            destf = util.AtomicFile(os.path.join(self.outputDir, self.basefilename + '.vmdk'))
            util.copyfileobj(file(vmdkPath), destf)
            destf.commit()
            return destf.finalPath
        vmdkGzOutputFile = os.path.join(self.outputDir, self.basefilename +
                '.vmdk.gz')
        self.gzip(vmdkPath, vmdkGzOutputFile)
        util.remove(vmdkPath)
        return vmdkGzOutputFile

    def writeVmwareOvf(self, capacity, vmdkPath):
        """Create OVF 1.0 output for general purpose usage."""
        vmdkPath = self.compressDiskImage(vmdkPath)

        # Insert OS info.
        self.ovfClass.osInfo = self.getGuestOSInfo()
        # Insert hardware version
        self.ovfClass.hwVersion = self.hwVersion

        self.ovaPath = self.createOvf(
                constants.VMDK, vmdkPath,
                capacity, diskCompressed=self.WithCompressedDisks,
                workingDir=self.workingDir, outputDir=self.outputDir,
                hwVersion=self.hwVersion)
        self.outputFileList.append((self.ovaPath,
            self.productName + ' %s' % constants.OVFIMAGETAG))

    def __init__(self, *args, **kwargs):
        raw_hd_image.RawHdImage.__init__(self, *args, **kwargs)
        self.configure()

    def configure(self):
        self.adapter = self.getBuildData('diskAdapter')
        self.vmSnapshots = self.getBuildData('vmSnapshots')
        self.vmMemory = self.getBuildData('vmMemory')
        self.vmCPUs = self.getBuildData('vmCPUs')
        self.capacity = None
        # APPENG-3232
        if self.vmMemory > 32 * 1024 or self.vmCPUs > 8:
            self.hwVersion = 10
        else:
            self.hwVersion = 7

    def getGuestOS(self):
        # vmwareOs hook used for windows builds.
        if 'vmwareOS' in self.jobData:
            return self.jobData['vmwareOS']

        # for all linux builds, we send a paltform name
        else:
            platform, version = self.getPlatformAndVersion()
            if self.baseFlavor.satisfies(deps.parseFlavor('is: x86_64')):
                platform += '-64'
            return platform

    def getGuestOSInfo(self):
        platform = self.getGuestOS()
        if platform.startswith('winNet'):
            # Windows 2003
            version = '2003'
            platformName = 'Windows Server 2003'
            if platform.endswith('-64'):
                ovfId = 70
                osType = 'winNetStandard64Guest'
            else:
                ovfId = 69
                osType = 'winNetStandardGuest'
        elif platform.startswith('win'):
            # Assume Windows 2008
            version = '2008'
            platformName = 'Windows Server 2008'
            ovfId = 1
            osType = 'windows7Server64Guest'
        elif not platform.startswith('other'):
            platformName = self.getBuildData('platformName')
            _, version = self.getPlatformAndVersion()
            is64 = platform.endswith('-64')
            osType = platform.replace('-', '_') + 'Guest'
            if platform.startswith('rhel'):
                ovfId = is64 and 80 or 79
            elif platform.startswith('sles'):
                ovfId = is64 and 85 or 84
            else:
                osType = is64 and 'other26xLinux64Guest' or 'other26xLinuxGuest'
                ovfId = is64 and 107 or 36
        else:
            # Assume Linux
            version = '26'
            platformName = 'Other Linux 2.6'
            if platform.endswith('-64'):
                ovfId = 107
                osType = 'other26xLinux64Guest'
            else:
                ovfId = 36
                osType = 'other26xLinuxGuest'

        if platform.endswith('-64'):
            platformName += ' (64 bit)'
        else:
            platformName += ' (32 bit)'

        return OSInfo(ovfId, version, platformName, osType)

    def customizeOvf(self, ovfImage):
        if self.getBuildData('natNetworking'):
            ovfImage.ovf.ovf_NetworkSection.ovf_Network[0].name = 'nat'
            nwobjs = [ x
                    for x in ovfImage.ovf.ovf_VirtualSystem.ovf_VirtualHardwareSection[0].ovf_Item
                    if x.rasd_ResourceType == '10' ]
            for nwobj in nwobjs:
                nwobj.rasd_Connection = 'nat'

class VMwareESXImage(VMwareImage):

    createType = 'vmfs'
    productName = buildtypes.typeNamesShort[buildtypes.VMWARE_ESX_IMAGE]
    # Mingle #393
    WithCompressedDisks = False
    alwaysOvf10 = True

    def configure(self):
        VMwareImage.configure(self)
        self.adapter = 'lsilogic'
        self.vmSnapshots = False

    @bootable_image.timeMe
    def createOvfVMDK(self, hdImage, outfile, size):
        createVMDK(hdImage, outfile, size, geometry=self.geometry,
                adapter=self.adapter, hwVersion=self.hwVersion,
                streaming=True)

    def writeMachine(self, disk, callback=None):
        """Create VMDK for the OVF processor, but no actual output images."""
        if not callback:
            callback = VMwareCallback()
        vmdkPath = os.path.join(self.workingDir, self.basefilename + '.vmdk')
        self.capacity = disk.totalSize
        # TODO: Add progress to raw2vmdk and pass it to creatingDisk()
        callback.creatingDisk(None, None)
        self.createOvfVMDK(disk.image, vmdkPath, disk.totalSize)
        disk.destroy()
        return vmdkPath


class VMwareCallback(object):

    def creatingDisk(self, completed, total):
        pass

    def creatingArchive(self, completed, total):
        pass


def createVMDK(hdImage, outfile, size, geometry, adapter, hwVersion,
        streaming=False):
    args = [
            '/usr/bin/raw2vmdk',
            '-C', str(geometry.cylindersRequired(size)),
            '-H', str(geometry.heads),
            '-S', str(geometry.sectors),
            '-A', adapter,
            '-V', str(hwVersion),
            ]
    if streaming:
        args += ['-s']
    args += [hdImage, outfile]

    logCall(args)
