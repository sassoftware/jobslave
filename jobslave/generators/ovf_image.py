#
# Copyright (c) 2009 rPath, Inc.
#
# All Rights Reserved
#

import os
import os.path
import sys

from jobslave import buildtypes
from jobslave.generators import constants

from pyovf import helper, ovf, item

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
    rasd_HostResource = 'ovf://disk/disk_1'
    rasd_InstanceID = '5'
    rasd_Parent = '4'
    rasd_ResourceType = '17'

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

class OvfImage(object):

    def __init__(self, imageName, imageDescription, diskFormat,
                  diskFilePath, diskFileSize, diskCapacity, diskCompressed,
                  workingDir, outputDir):

        self.imageName = imageName
        self.imageDescription = imageDescription
        self.diskFormat = diskFormat
        self.diskFilePath = diskFilePath
        self.diskFileSize = diskFileSize
        self.diskCapacity = diskCapacity
        self.diskCompressed = diskCompressed
        self.workingDir = workingDir
        self.outputDir = outputDir

        self.instanceIdCounter = 0
        self.fileIdCounter = 0
        self.diskIdCounter = 0

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

    def createOvf(self):
        # Initial empty ovf object.
        self.ovf = helper.NewOvf()

        self.diskFileName = os.path.split(self.diskFilePath)[1]

        # Set network and disk info in ovf.
        self.ovf.NetworkSection.Info = constants.NETWORKSECTIONINFO
        self.ovf.DiskSection.Info = constants.DISKSECTIONINFO
        self.ovf.VirtualSystemCollection.id = self.imageName

        # Add file references to ovf.
        fileRef = ovf.FileReference(id=self._getFileId(),
                                    href=self.diskFileName,
                                    size=self.diskFileSize)
        if self.diskCompressed:
            fileRef.compression = constants.FILECOMPRESSION
        self.ovf.addFileReference(fileRef)

        # Add virtual system to ovf with a virutal hardware section.
        virtSystem = ovf.VirtualSystem(id=self.imageName)
        virtSystem.Info = self.imageDescription
        vhws = ovf.VirtualHardwareSection(
                Info=constants.VIRTUALHARDWARESECTIONINFO)
        vhws.addItem(Cpu())
        vhws.addItem(Memory())
        vhws.addItem(Network())
        vhws.addItem(Harddisk())
        vhws.addItem(ScsiController())

        # vhws.System = ovf.System()
        # vhws.System.ElementName = self.imageName
        # vhws.System.InstanceID = self._getInstanceId()
        # vhws.System.VirtualSystemType = 'Virtual System Type'

        virtSystem.addVirtualHardwareSection(vhws)
        self.ovf.addVirtualSystem(virtSystem)

        # Add disk files to ovf.
        format = ovf.DiskFormat(
            constants.DISKFORMATURLS[self.diskFormat])
        disk = ovf.Disk(diskId=self._getDiskId(), fileRef=fileRef,
                        format=format, capacity=self.diskCapacity)
        self.ovf.addDisk(disk)

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

    def createOva(self):
        """
        Create a new tar archive @ self.ovaPath.

        The ova is a tar consisting of the ovf and the disk file(s).
        """
        from jobslave.imagegen import logCall

        self.ovaFileName = self.imageName + '.' + constants.OVA_EXTENSION
        self.ovaPath = os.path.join(self.outputDir, self.ovaFileName)

        # Add the ovf as the first file to the ova tar.
        logCall('tar -C %s -cv %s -f %s' % \
            (self.workingDir, self.ovfFileName, self.ovaPath))
        # Add the disk as the 2nd file.
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
