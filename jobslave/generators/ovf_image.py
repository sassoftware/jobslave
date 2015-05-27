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

from conary.lib import sha1helper

from jobslave.generators import constants
from jobslave.util import logCall

from pyovf import helper, ovf

class Cpu(ovf.Item):
    rasd_Caption = 'Virtual CPU'
    rasd_Description = 'Number of virtual CPUs'
    rasd_ElementName = 'some virt cpu'
    rasd_InstanceID = '1'
    rasd_ResourceType = '3'
    rasd_VirtualQuantity = '1'

class Memory(ovf.Item):
    rasd_AllocationUnits = 'MegaBytes'
    rasd_Caption = '256 MB of memory'
    rasd_Description = 'Memory Size'
    rasd_ElementName = 'some mem size'
    rasd_InstanceID = '2'
    rasd_ResourceType = '4'
    rasd_VirtualQuantity = '256'

class Harddisk(ovf.Item):
    rasd_Caption = 'Harddisk'
    rasd_ElementName = 'Hard disk'
    rasd_HostResource = 'ovf:/disk/diskId'
    rasd_InstanceID = '5'
    rasd_Parent = '4'
    rasd_ResourceType = '17'
    rasd_AddressOnParent = '0'

class ScsiController(ovf.Item):
    rasd_Caption = 'SCSI Controller 0 - LSI Logic'
    rasd_ElementName = 'LSILOGIC'
    rasd_InstanceID = '4'
    rasd_ResourceSubType = 'LsiLogic'
    rasd_ResourceType = '6'

class Network(ovf.Item):
    rasd_ElementName = 'Network Interface'
    rasd_ResourceType = '10'
    rasd_AllocationUnits = 'Interface'
    rasd_InstanceID = '3'
    rasd_Description = 'Network Interface'

class CdRom(ovf.Item):
    rasd_Caption = 'CD-ROM'
    rasd_ElementName = 'CD-ROM'
    rasd_HostResource = 'ovf:/file/fileId'
    rasd_InstanceID = '6'
    rasd_ResourceType = '15'

class OvfImage(object):

    def __init__(self, imageName, imageDescription, diskFormat,
                 diskFilePath, diskFileSize, diskCapacity, diskCompressed,
                 memorySize, cpuCount, workingDir, outputDir, hwVersion=7):
        self.imageName = imageName
        self.imageDescription = imageDescription
        self.diskFormat = diskFormat
        self.diskFilePath = diskFilePath
        self.diskFileSize = diskFileSize
        self.diskCapacity = diskCapacity
        self.diskCompressed = diskCompressed
        self.memorySize = memorySize
        self.cpuCount = cpuCount
        self.workingDir = workingDir
        self.outputDir = outputDir
        self.hwVersion = hwVersion

        self.diskFileName = os.path.split(self.diskFilePath)[1]

        self.instanceIdCounter = 0
        self.fileIdCounter = 0
        self.diskIdCounter = 0

        # Initial empty ovf object.
        self.ovf = helper.NewOvf()

    def _getInstanceId(self):
        """
        Return a unique (for this jobslave run) file id for use in an ovf.
        """
        self.instanceIdCounter += 1
        return 'instanceId_%s' % str(self.instanceIdCounter)


    def _getFileId(self):
        """
        Return a unique (for this jobslave run) file id for use in an ovf.
        """
        self.fileIdCounter += 1
        return 'fileId_%s' % str(self.fileIdCounter)

    def _getDiskId(self):
        """
        Return a unique (for this jobslave run) disk id for use in an ovf.
        """
        self.diskIdCounter += 1
        return 'diskId_%s' % str(self.diskIdCounter)

    def addFileReferences(self):
        # Add file references to ovf.
        self.fileRef = ovf.FileReference(id=self._getFileId(),
                                    href=self.diskFileName,
                                    size=self.diskFileSize)
        if self.diskCompressed:
            self.fileRef.compression = constants.FILECOMPRESSION
        self.ovf.addFileReference(self.fileRef)

    def addHardwareDefaults(self, VirtualHardware):
        VirtualHardware.addItem(Cpu(
            VirtualQuantity=self.cpuCount, Caption="%s CPUs" % self.cpuCount))
        VirtualHardware.addItem(Memory(VirtualQuantity=self.memorySize,
                                       Caption="%s MB of Memory" % self.memorySize))
        network = Network()
        network.Connection = self.ovf.NetworkSection.Network[0].name
        VirtualHardware.addItem(network)
        hd = Harddisk(AddressOnParent=0)
        hd.HostResource = 'ovf:/disk/%s' % self.diskId
        VirtualHardware.addItem(hd)
        VirtualHardware.addItem(ScsiController())

    def addVirtualHardware(self, virtualSystem):
        vhws = ovf.VirtualHardwareSection(
                Info=constants.VIRTUALHARDWARESECTIONINFO)

        self.addHardwareDefaults(vhws)                

        vhws.System = ovf.System()
        # not in schema
        # vhws.System.VirtualSystemIdentifier = self.imageName
        vhws.System.ElementName = 'Virtual Hardware Family'
        vhws.System.InstanceID = self._getInstanceId()
        vhws.System.VirtualSystemType = 'vmx-%02d' % self.hwVersion

        virtualSystem.addVirtualHardwareSection(vhws)

    def addVirtualSystem(self):
        # Add virtual system to ovf with a virutal hardware section.
        virtSystem = ovf.VirtualSystem(id=self.imageName)
        virtSystem.Info = self.imageDescription
        self.addVirtualHardware(virtSystem)
        self.ovf.addVirtualSystem(virtSystem)

    def addDisks(self):
        # Add disk files to ovf.
        format = ovf.DiskFormat(
            constants.DISKFORMATURLS[self.diskFormat])
        self.diskId = self._getDiskId()
        disk = ovf.Disk(diskId=self.diskId, fileRef=self.fileRef,
                        format=format, capacity=self.diskCapacity)
        self.ovf.addDisk(disk)

    def createOvf(self):
        # Set network and disk info in ovf.
        self.ovf.NetworkSection.Info = constants.NETWORKSECTIONINFO
        self.ovf.DiskSection.Info = constants.DISKSECTIONINFO
        self.ovf.VirtualSystemCollection.id = self.imageName

        self.addFileReferences()
        self.addDisks()
        self.addVirtualSystem()

        return self.ovf

    def writeOvf(self):
        # Write the xml to disk.
        self.ovfXml = self.ovf.toxml()
        self.ovfFileName = self.imageName + '.' + constants.OVF_EXTENSION
        self.ovfPath = os.path.join(self.workingDir, self.ovfFileName)
        out = open(self.ovfPath, 'w')
        out.write(self.ovfXml)
        out.close()

        return self.ovfXml

    def createManifest(self):
        sha1Line = 'SHA1(%s)= %s\n'
        self.manifestFileName = self.imageName + '.' + constants.MF_EXTENSION
        self.manifestPath = os.path.join(self.workingDir, self.manifestFileName)

        mfFile = open(self.manifestPath, 'w')

        ovfSha1 = sha1helper.sha1FileBin(self.ovfPath).encode('hex')
        diskSha1 = sha1helper.sha1FileBin(self.diskFilePath).encode('hex')

        mfFile.write(sha1Line % (self.ovfFileName, ovfSha1))
        mfFile.write(sha1Line % (self.diskFileName, diskSha1))

        mfFile.close()

    def createOva(self):
        """
        Create a new tar archive @ self.ovaPath.

        The ova is a tar consisting of the ovf and the disk file(s).
        """
        self.ovaFileName = self.imageName + '.' + constants.OVA_EXTENSION
        self.ovaPath = os.path.join(self.outputDir, self.ovaFileName)

        # Add the ovf as the first file to the ova tar.
        logCall('tar -C %s -cv %s -f %s' % \
            (self.workingDir, self.ovfFileName, self.ovaPath))
        # Add the manifest as the 2nd file.
        logCall('tar -C %s -rv %s -f %s' % \
            (self.workingDir, self.manifestFileName, self.ovaPath))
        # Add the disk as the 3rd file.
        logCall('tar -C %s -rv %s -f %s' % \
            (self.outputDir, self.diskFileName, self.ovaPath))

        return self.ovaPath

class XenOvfImage(OvfImage):

    def __init__(self, *args, **kw):
        OvfImage.__init__(self, *args, **kw)

    def createOvf(self):
        OvfImage.createOvf(self)

        self.ovf._doc.nameSpaceMap['xenovf'] = \
            'http://schemas.citrix.com/ovf/envelope/1'
        self.ovf._doc.ovf_Envelope._xobj.attributes['xenovf_Name'] = str
        self.ovf._doc.ovf_Envelope._xobj.attributes['xenovf_id'] = str
        self.ovf._doc.ovf_Envelope._xobj.attributes['Version'] = str 

        object.__setattr__(self.ovf._doc.ovf_Envelope,
            'xenovf_Name', self.imageName)
        object.__setattr__(self.ovf._doc.ovf_Envelope,
            'xenovf_id', self.imageName)
        object.__setattr__(self.ovf._doc.ovf_Envelope, 
            'Version', '1.0.0')

        return self.ovf

class ISOOvfImage(OvfImage):        


    def __init__(self, *args, **kw):
        OvfImage.__init__(self, *args, **kw)

    def createOvf(self):
        # Set network and disk info in ovf.
        self.ovf.NetworkSection.Info = constants.NETWORKSECTIONINFO
        self.ovf.DiskSection.Info = constants.DISKSECTIONINFO
        self.ovf.VirtualSystemCollection.id = self.imageName

        self.addFileReferences()
        self.addVirtualSystem()
        c = CdRom()
        c.HostResource = 'ovf:/file/%s' % self.fileRef.id
        self.ovf.ovf_VirtualSystemCollection.ovf_VirtualSystem[0].ovf_VirtualHardwareSection[0].addItem(c)

        return self.ovf

    def addHardwareDefaults(self, VirtualHardware):
        VirtualHardware.addItem(Cpu())
        VirtualHardware.addItem(Memory(VirtualQuantity=self.memorySize,
                                       Caption="%s MB of Memory" % self.memorySize))
        network = Network()
        network.Connection = self.ovf.NetworkSection.Network[0].name
        VirtualHardware.addItem(network)

class VMwareOVFImage(OvfImage):

    def createOvf(self):
        self.ovf._doc.nameSpaceMap['vbox'] = 'http://www.virtualbox.org/ovf/machine'
        # Set network and disk info in ovf.
        self.ovf.NetworkSection.Info = constants.NETWORKSECTIONINFO
        self.ovf.DiskSection.Info = constants.DISKSECTIONINFO

        # VMware doesn't seem to support the systems being inside of the
        # VirtualSystemCollection element.
        self.ovf.__delattr__('ovf_VirtualSystemCollection')

        # This can be removed once there is a newer pyovf that only has
        # ResourceAllocationSection as an element of VirtualSystemCollection
        # instead of as an element of Envelope
        if hasattr(self.ovf, 'ovf_ResourceAllocationSection'):
            self.ovf.__delattr__('ovf_ResourceAllocationSection')

        self.addFileReferences()
        self.addDisks()
        self.addVirtualSystem()

        for i, disk in enumerate(self.ovf.ovf_DiskSection.ovf_Disk):
            disk._xobj.attributes.update(vbox_uuid=str)
            object.__setattr__(disk, 'vbox_uuid',
                    "00000000-0000-4000-8000-%012d" % (i + 1))

        vbox = VBoxMachine(self.ovf.ovf_VirtualSystem.ovf_id,
                cpuCount=self.cpuCount,
                memory=self.memorySize,
                diskCount=i+1)
        object.__setattr__(self.ovf._doc.ovf_Envelope.ovf_VirtualSystem, 'vbox_Machine', vbox)

        # vbox will make schema validation not work
        # reaching inside a private __schema is nasty too
        object.__setattr__(self.ovf._doc, '_Document__schema', None)
        return self.ovf

    def addVirtualSystem(self):
        # We need to override this method from the base class to add
        # VirtualSystem directly as an element of Envelope instead of an
        # elemetn of Virtual System Collection

        # Add virtual system to ovf with a virutal hardware section.
        virtSystem = ovf.VirtualSystem(id=self.imageName)
        virtSystem.Info = self.imageDescription

        # We get osInfo from the vmware image generator.
        osInfo = self.osInfo

        osSection = virtSystem.ovf_OperatingSystemSection(
            id=osInfo.ovfId, version=osInfo.version)
        osSection.Description = osInfo.description
        osSection.Info  = "The kind of installed guest operating system"
        # This attribute is specified in included schemas, but in testing
        # xmlns:vmw="http://www.vmware.com/schema/ovf" was required.
        # Manually set object because the prefix is different
        object.__setattr__(osSection, 'vmw_osType', osInfo.osType)

        virtSystem.ovf_OperatingSystemSection = osSection
        self.addVirtualHardware(virtSystem)
        self.ovf.ovf_VirtualSystem = virtSystem

class VboxCPU(object):
    _xobj = ovf.xobj.XObjMetadata(attributes=dict(count=int, hotplug=str))
    def __init__(self, count):
        self.count = count
        self.hotplug = "false"

class VboxMemory(object):
    _xobj = ovf.xobj.XObjMetadata(attributes=dict(RAMSize=int, PageFusion=str))
    def __init__(self, size):
        self.RAMSize = size
        self.PageFusion = "false"

class VboxChipset(object):
    _xobj = ovf.xobj.XObjMetadata(attributes=dict(type=str))
    def __init__(self):
        self.type = "ICH9"

VboxDisplay = ovf.xobj.parse("""\
<Display VRAMSize="16" monitorCount="1" accelerate3D="false"
accelerate2DVideo="false"/>""").Display

VboxRemoteDisplay = ovf.xobj.parse("""\
<RemoteDisplay enabled="false"/>""").RemoteDisplay

VboxBIOS = ovf.xobj.parse("""\
<BIOS>
  <ACPI enabled="true"/>
  <IOAPIC enabled="true"/>
  <Logo fadeIn="false" fadeOut="false" displayTime="0"/>
  <BootMenu mode="MessageAndMenu"/>
  <TimeOffset value="0"/>
  <PXEDebug enabled="false"/>
</BIOS>""").BIOS

VboxNetwork = ovf.xobj.parse("""\
<Network>
  <Adapter slot="0" enabled="true" cable="true" type="82540EM">
    <NAT>
      <DNS pass-domain="true" use-proxy="false" use-host-resolver="false"/>
      <Alias logging="false" proxy-only="false" use-same-ports="false"/>
      <Forwarding name="HTTP" proto="1" hostip="127.0.0.1" hostport="10080" guestport="80"/>
      <Forwarding name="HTTPS" proto="1" hostip="127.0.0.1" hostport="10443" guestport="443"/>
    </NAT>
  </Adapter>
</Network>""").Network

VboxStorageControllers = ovf.xobj.parse("""\
<StorageControllers>
  <StorageController name="SCSI Controller" type="LsiLogic" PortCount="16" useHostIOCache="false" Bootable="true">
  </StorageController>
</StorageControllers>""").StorageControllers

class VboxAttachedDevice(object):
    _uuidTemplate = "00000000-0000-4000-8000-%012d"
    def __init__(self, deviceNumber):
        self.obj = ovf.xobj.parse("""\
<AttachedDevice type="HardDisk" port="ignoreme" device="0">
  <Image uuid="ignoreme"/>
</AttachedDevice>""").AttachedDevice
        self.obj.port = deviceNumber
        self.obj.Image.uuid = "{%s}" % (self._uuidTemplate % (deviceNumber + 1))

class VboxHardware(object):
    _xobj = ovf.xobj.XObjMetadata(
            elements=[ 'CPU', 'Memory', 'Chipset', 'Display', 'RemoteDisplay', 'BIOS', 'Network' ],
            attributes=dict(version=int))
    def __init__(self, cpuCount, memory):
        self.version = 2
        self.CPU = VboxCPU(cpuCount)
        self.Memory = VboxMemory(memory)
        self.Chipset = VboxChipset()
        self.Display = VboxDisplay
        self.RemoteDisplay = VboxRemoteDisplay
        self.BIOS = VboxBIOS
        self.Network = VboxNetwork

class VBoxMachine(object):
    _xobj = ovf.xobj.XObjMetadata(
            elements = [ "ovf_Info", "Hardware", "StorageControllers" ],
            attributes=dict(ovf_required=str,
                uuid=str, name=str))
    def __init__(self, name, cpuCount, memory, diskCount):
        self.ovf_required = "false"
        self.uuid = "{00000000-0000-4000-8000-000000000000}"
        self.ovf_Info = "VirtualBox machine configuration in VirtualBox format"
        self.name = name
        self.Hardware = VboxHardware(cpuCount, memory)
        self.StorageControllers = VboxStorageControllers
        attachedDevices = self.StorageControllers.StorageController.AttachedDevice = []
        for i in range(diskCount):
            attachedDevices.append(VboxAttachedDevice(i).obj)
