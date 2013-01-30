#
# Copyright (c) 2011 rPath, Inc.
#

import hashlib
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
                 memorySize, workingDir, outputDir):
        self.imageName = imageName
        self.imageDescription = imageDescription
        self.diskFormat = diskFormat
        self.diskFilePath = diskFilePath
        self.diskFileSize = diskFileSize
        self.diskCapacity = diskCapacity
        self.diskCompressed = diskCompressed
        self.memorySize = memorySize
        self.workingDir = workingDir
        self.outputDir = outputDir

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
        VirtualHardware.addItem(Cpu())
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
        vhws.System.VirtualSystemType = 'vmx-07'

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

        ovfSha1 = sha1helper.sha1FileBin(self.ovfPath).hexdigest()
        diskSha1 = sha1helper.sha1FileBin(self.diskFilePath).hexdigest()

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

