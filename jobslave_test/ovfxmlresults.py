#!/usr/bin/python

VMwareOvfXml = """\
<?xml version='1.0' encoding='UTF-8'?>
<ovf:Envelope xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common">
  <ovf:References>
    <ovf:File ovf:href="image.vmdk.gz" ovf:id="fileId_1" ovf:size="1234567890" ovf:compression="gzip"/>
  </ovf:References>
  <ovf:DiskSection>
    <ovf:Info>Describes the set of virtual disks</ovf:Info>
    <ovf:Disk ovf:diskId="diskId_1" ovf:capacity="12345678900" ovf:fileRef="fileId_1" ovf:format="http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized"/>
  </ovf:DiskSection>
  <ovf:NetworkSection>
    <ovf:Info>List of logical networks used in the package</ovf:Info>
    <ovf:Network ovf:name="Network Name">
      <ovf:Description>Network Description</ovf:Description>
    </ovf:Network>
  </ovf:NetworkSection>
  <ovf:VirtualSystem ovf:id="image">
    <ovf:Info>Test Description</ovf:Info>
    <ovf:VirtualHardwareSection>
      <ovf:Info>Describes the set of virtual hardware</ovf:Info>
      <ovf:Item>
        <rasd:Caption>Virtual CPU</rasd:Caption>
        <rasd:Description>Number of virtual CPUs</rasd:Description>
        <rasd:ElementName>some virt cpu</rasd:ElementName>
        <rasd:InstanceID>1</rasd:InstanceID>
        <rasd:ResourceType>3</rasd:ResourceType>
        <rasd:VirtualQuantity>1</rasd:VirtualQuantity>
      </ovf:Item>
      <ovf:Item>
        <rasd:AllocationUnits>MegaBytes</rasd:AllocationUnits>
        <rasd:Caption>256 MB of Memory</rasd:Caption>
        <rasd:Description>Memory Size</rasd:Description>
        <rasd:ElementName>some mem size</rasd:ElementName>
        <rasd:InstanceID>2</rasd:InstanceID>
        <rasd:ResourceType>4</rasd:ResourceType>
        <rasd:VirtualQuantity>256</rasd:VirtualQuantity>
      </ovf:Item>
      <ovf:Item>
        <rasd:AllocationUnits>Interface</rasd:AllocationUnits>
        <rasd:Connection>Network Name</rasd:Connection>
        <rasd:Description>Network Interface</rasd:Description>
        <rasd:ElementName>Network Interface</rasd:ElementName>
        <rasd:InstanceID>3</rasd:InstanceID>
        <rasd:ResourceType>10</rasd:ResourceType>
      </ovf:Item>
      <ovf:Item>
        <rasd:AddressOnParent>0</rasd:AddressOnParent>
        <rasd:Caption>Harddisk</rasd:Caption>
        <rasd:ElementName>Hard disk</rasd:ElementName>
        <rasd:HostResource>ovf:/disk/diskId_1</rasd:HostResource>
        <rasd:InstanceID>5</rasd:InstanceID>
        <rasd:Parent>4</rasd:Parent>
        <rasd:ResourceType>17</rasd:ResourceType>
      </ovf:Item>
      <ovf:Item>
        <rasd:Caption>SCSI Controller 0 - LSI Logic</rasd:Caption>
        <rasd:ElementName>LSILOGIC</rasd:ElementName>
        <rasd:InstanceID>4</rasd:InstanceID>
        <rasd:ResourceSubType>LsiLogic</rasd:ResourceSubType>
        <rasd:ResourceType>6</rasd:ResourceType>
      </ovf:Item>
    </ovf:VirtualHardwareSection>
  </ovf:VirtualSystem>
</ovf:Envelope>
"""

amiOvfXml = """\
<?xml version='1.0' encoding='UTF-8'?>
<ovf:Envelope xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common">
  <ovf:References>
    <ovf:File ovf:href="image-root.ext3" ovf:id="fileId_1" ovf:size="1234567890" ovf:compression="gzip"/>
  </ovf:References>
  <ovf:DiskSection>
    <ovf:Info>Describes the set of virtual disks</ovf:Info>
    <ovf:Disk ovf:diskId="diskId_1" ovf:capacity="100" ovf:fileRef="fileId_1" ovf:format="http://wiki.rpath.com/wiki/rBuilder_Online:Raw_Filesystem_Image"/>
  </ovf:DiskSection>
  <ovf:NetworkSection>
    <ovf:Info>List of logical networks used in the package</ovf:Info>
    <ovf:Network ovf:name="Network Name">
      <ovf:Description>Network Description</ovf:Description>
    </ovf:Network>
  </ovf:NetworkSection>
  <ovf:VirtualSystemCollection ovf:id="image">
    <ovf:Info>Virtual System Collection Info</ovf:Info>
    <ovf:ResourceAllocationSection>
      <ovf:Info>Resource Allocation Section Info</ovf:Info>
    </ovf:ResourceAllocationSection>
    <ovf:VirtualSystem ovf:id="image">
      <ovf:Info>Test Description</ovf:Info>
      <ovf:VirtualHardwareSection>
        <ovf:Info>Describes the set of virtual hardware</ovf:Info>
        <ovf:Item>
          <rasd:Caption>Virtual CPU</rasd:Caption>
          <rasd:Description>Number of virtual CPUs</rasd:Description>
          <rasd:ElementName>some virt cpu</rasd:ElementName>
          <rasd:InstanceID>1</rasd:InstanceID>
          <rasd:ResourceType>3</rasd:ResourceType>
          <rasd:VirtualQuantity>1</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>MegaBytes</rasd:AllocationUnits>
          <rasd:Caption>256 MB of Memory</rasd:Caption>
          <rasd:Description>Memory Size</rasd:Description>
          <rasd:ElementName>some mem size</rasd:ElementName>
          <rasd:InstanceID>2</rasd:InstanceID>
          <rasd:ResourceType>4</rasd:ResourceType>
          <rasd:VirtualQuantity>256</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>Interface</rasd:AllocationUnits>
          <rasd:Connection>Network Name</rasd:Connection>
          <rasd:Description>Network Interface</rasd:Description>
          <rasd:ElementName>Network Interface</rasd:ElementName>
          <rasd:InstanceID>3</rasd:InstanceID>
          <rasd:ResourceType>10</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:AddressOnParent>0</rasd:AddressOnParent>
          <rasd:Caption>Harddisk</rasd:Caption>
          <rasd:ElementName>Hard disk</rasd:ElementName>
          <rasd:HostResource>ovf:/disk/diskId_1</rasd:HostResource>
          <rasd:InstanceID>5</rasd:InstanceID>
          <rasd:Parent>4</rasd:Parent>
          <rasd:ResourceType>17</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:Caption>SCSI Controller 0 - LSI Logic</rasd:Caption>
          <rasd:ElementName>LSILOGIC</rasd:ElementName>
          <rasd:InstanceID>4</rasd:InstanceID>
          <rasd:ResourceSubType>LsiLogic</rasd:ResourceSubType>
          <rasd:ResourceType>6</rasd:ResourceType>
        </ovf:Item>
      </ovf:VirtualHardwareSection>
    </ovf:VirtualSystem>
  </ovf:VirtualSystemCollection>
</ovf:Envelope>
"""

rawHdOvfXml = """\
<?xml version='1.0' encoding='UTF-8'?>
<ovf:Envelope xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common">
  <ovf:References>
    <ovf:File ovf:href="image.hdd.gz" ovf:id="fileId_1" ovf:size="1234567890" ovf:compression="gzip"/>
  </ovf:References>
  <ovf:DiskSection>
    <ovf:Info>Describes the set of virtual disks</ovf:Info>
    <ovf:Disk ovf:diskId="diskId_1" ovf:capacity="2097152" ovf:fileRef="fileId_1" ovf:format="http://wiki.rpath.com/wiki/rBuilder_Online:Raw_Hard_Disk_Image"/>
  </ovf:DiskSection>
  <ovf:NetworkSection>
    <ovf:Info>List of logical networks used in the package</ovf:Info>
    <ovf:Network ovf:name="Network Name">
      <ovf:Description>Network Description</ovf:Description>
    </ovf:Network>
  </ovf:NetworkSection>
  <ovf:VirtualSystemCollection ovf:id="image">
    <ovf:Info>Virtual System Collection Info</ovf:Info>
    <ovf:ResourceAllocationSection>
      <ovf:Info>Resource Allocation Section Info</ovf:Info>
    </ovf:ResourceAllocationSection>
    <ovf:VirtualSystem ovf:id="image">
      <ovf:Info>Test Description</ovf:Info>
      <ovf:VirtualHardwareSection>
        <ovf:Info>Describes the set of virtual hardware</ovf:Info>
        <ovf:Item>
          <rasd:Caption>Virtual CPU</rasd:Caption>
          <rasd:Description>Number of virtual CPUs</rasd:Description>
          <rasd:ElementName>some virt cpu</rasd:ElementName>
          <rasd:InstanceID>1</rasd:InstanceID>
          <rasd:ResourceType>3</rasd:ResourceType>
          <rasd:VirtualQuantity>1</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>MegaBytes</rasd:AllocationUnits>
          <rasd:Caption>256 MB of Memory</rasd:Caption>
          <rasd:Description>Memory Size</rasd:Description>
          <rasd:ElementName>some mem size</rasd:ElementName>
          <rasd:InstanceID>2</rasd:InstanceID>
          <rasd:ResourceType>4</rasd:ResourceType>
          <rasd:VirtualQuantity>256</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>Interface</rasd:AllocationUnits>
          <rasd:Connection>Network Name</rasd:Connection>
          <rasd:Description>Network Interface</rasd:Description>
          <rasd:ElementName>Network Interface</rasd:ElementName>
          <rasd:InstanceID>3</rasd:InstanceID>
          <rasd:ResourceType>10</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:AddressOnParent>0</rasd:AddressOnParent>
          <rasd:Caption>Harddisk</rasd:Caption>
          <rasd:ElementName>Hard disk</rasd:ElementName>
          <rasd:HostResource>ovf:/disk/diskId_1</rasd:HostResource>
          <rasd:InstanceID>5</rasd:InstanceID>
          <rasd:Parent>4</rasd:Parent>
          <rasd:ResourceType>17</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:Caption>SCSI Controller 0 - LSI Logic</rasd:Caption>
          <rasd:ElementName>LSILOGIC</rasd:ElementName>
          <rasd:InstanceID>4</rasd:InstanceID>
          <rasd:ResourceSubType>LsiLogic</rasd:ResourceSubType>
          <rasd:ResourceType>6</rasd:ResourceType>
        </ovf:Item>
      </ovf:VirtualHardwareSection>
    </ovf:VirtualSystem>
  </ovf:VirtualSystemCollection>
</ovf:Envelope>
"""

rawFsOvfXml = """\
<?xml version='1.0' encoding='UTF-8'?>
<ovf:Envelope xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common">
  <ovf:References>
    <ovf:File ovf:href="image-root.ext3.gz" ovf:id="fileId_1" ovf:size="1234567890" ovf:compression="gzip"/>
  </ovf:References>
  <ovf:DiskSection>
    <ovf:Info>Describes the set of virtual disks</ovf:Info>
    <ovf:Disk ovf:diskId="diskId_1" ovf:capacity="100" ovf:fileRef="fileId_1" ovf:format="http://wiki.rpath.com/wiki/rBuilder_Online:Raw_Filesystem_Image"/>
  </ovf:DiskSection>
  <ovf:NetworkSection>
    <ovf:Info>List of logical networks used in the package</ovf:Info>
    <ovf:Network ovf:name="Network Name">
      <ovf:Description>Network Description</ovf:Description>
    </ovf:Network>
  </ovf:NetworkSection>
  <ovf:VirtualSystemCollection ovf:id="image">
    <ovf:Info>Virtual System Collection Info</ovf:Info>
    <ovf:ResourceAllocationSection>
      <ovf:Info>Resource Allocation Section Info</ovf:Info>
    </ovf:ResourceAllocationSection>
    <ovf:VirtualSystem ovf:id="image">
      <ovf:Info>Test Description</ovf:Info>
      <ovf:VirtualHardwareSection>
        <ovf:Info>Describes the set of virtual hardware</ovf:Info>
        <ovf:Item>
          <rasd:Caption>Virtual CPU</rasd:Caption>
          <rasd:Description>Number of virtual CPUs</rasd:Description>
          <rasd:ElementName>some virt cpu</rasd:ElementName>
          <rasd:InstanceID>1</rasd:InstanceID>
          <rasd:ResourceType>3</rasd:ResourceType>
          <rasd:VirtualQuantity>1</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>MegaBytes</rasd:AllocationUnits>
          <rasd:Caption>256 MB of Memory</rasd:Caption>
          <rasd:Description>Memory Size</rasd:Description>
          <rasd:ElementName>some mem size</rasd:ElementName>
          <rasd:InstanceID>2</rasd:InstanceID>
          <rasd:ResourceType>4</rasd:ResourceType>
          <rasd:VirtualQuantity>256</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>Interface</rasd:AllocationUnits>
          <rasd:Connection>Network Name</rasd:Connection>
          <rasd:Description>Network Interface</rasd:Description>
          <rasd:ElementName>Network Interface</rasd:ElementName>
          <rasd:InstanceID>3</rasd:InstanceID>
          <rasd:ResourceType>10</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:AddressOnParent>0</rasd:AddressOnParent>
          <rasd:Caption>Harddisk</rasd:Caption>
          <rasd:ElementName>Hard disk</rasd:ElementName>
          <rasd:HostResource>ovf:/disk/diskId_1</rasd:HostResource>
          <rasd:InstanceID>5</rasd:InstanceID>
          <rasd:Parent>4</rasd:Parent>
          <rasd:ResourceType>17</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:Caption>SCSI Controller 0 - LSI Logic</rasd:Caption>
          <rasd:ElementName>LSILOGIC</rasd:ElementName>
          <rasd:InstanceID>4</rasd:InstanceID>
          <rasd:ResourceSubType>LsiLogic</rasd:ResourceSubType>
          <rasd:ResourceType>6</rasd:ResourceType>
        </ovf:Item>
      </ovf:VirtualHardwareSection>
    </ovf:VirtualSystem>
  </ovf:VirtualSystemCollection>
</ovf:Envelope>
"""

vpcOvfXml = """\
<?xml version='1.0' encoding='UTF-8'?>
<ovf:Envelope xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:xenovf="http://schemas.citrix.com/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common" Version="1.0.0" xenovf:id="image" xenovf:Name="image">
  <ovf:References>
    <ovf:File ovf:href="image.vpc.tar.gz" ovf:id="fileId_1" ovf:size="1234567890" ovf:compression="gzip"/>
  </ovf:References>
  <ovf:DiskSection>
    <ovf:Info>Describes the set of virtual disks</ovf:Info>
    <ovf:Disk ovf:diskId="diskId_1" ovf:capacity="10000" ovf:fileRef="fileId_1" ovf:format="http://www.microsoft.com/technet/virtualserver/downloads/vhdspec.mspx"/>
  </ovf:DiskSection>
  <ovf:NetworkSection>
    <ovf:Info>List of logical networks used in the package</ovf:Info>
    <ovf:Network ovf:name="Network Name">
      <ovf:Description>Network Description</ovf:Description>
    </ovf:Network>
  </ovf:NetworkSection>
  <ovf:VirtualSystemCollection ovf:id="image">
    <ovf:Info>Virtual System Collection Info</ovf:Info>
    <ovf:ResourceAllocationSection>
      <ovf:Info>Resource Allocation Section Info</ovf:Info>
    </ovf:ResourceAllocationSection>
    <ovf:VirtualSystem ovf:id="image">
      <ovf:Info>Test Description</ovf:Info>
      <ovf:VirtualHardwareSection>
        <ovf:Info>Describes the set of virtual hardware</ovf:Info>
        <ovf:Item>
          <rasd:Caption>Virtual CPU</rasd:Caption>
          <rasd:Description>Number of virtual CPUs</rasd:Description>
          <rasd:ElementName>some virt cpu</rasd:ElementName>
          <rasd:InstanceID>1</rasd:InstanceID>
          <rasd:ResourceType>3</rasd:ResourceType>
          <rasd:VirtualQuantity>1</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>MegaBytes</rasd:AllocationUnits>
          <rasd:Caption>0 MB of Memory</rasd:Caption>
          <rasd:Description>Memory Size</rasd:Description>
          <rasd:ElementName>some mem size</rasd:ElementName>
          <rasd:InstanceID>2</rasd:InstanceID>
          <rasd:ResourceType>4</rasd:ResourceType>
          <rasd:VirtualQuantity>0</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>Interface</rasd:AllocationUnits>
          <rasd:Connection>Network Name</rasd:Connection>
          <rasd:Description>Network Interface</rasd:Description>
          <rasd:ElementName>Network Interface</rasd:ElementName>
          <rasd:InstanceID>3</rasd:InstanceID>
          <rasd:ResourceType>10</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:AddressOnParent>0</rasd:AddressOnParent>
          <rasd:Caption>Harddisk</rasd:Caption>
          <rasd:ElementName>Hard disk</rasd:ElementName>
          <rasd:HostResource>ovf:/disk/diskId_1</rasd:HostResource>
          <rasd:InstanceID>5</rasd:InstanceID>
          <rasd:Parent>4</rasd:Parent>
          <rasd:ResourceType>17</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:Caption>SCSI Controller 0 - LSI Logic</rasd:Caption>
          <rasd:ElementName>LSILOGIC</rasd:ElementName>
          <rasd:InstanceID>4</rasd:InstanceID>
          <rasd:ResourceSubType>LsiLogic</rasd:ResourceSubType>
          <rasd:ResourceType>6</rasd:ResourceType>
        </ovf:Item>
      </ovf:VirtualHardwareSection>
    </ovf:VirtualSystem>
  </ovf:VirtualSystemCollection>
</ovf:Envelope>
"""

appIsoOvfXml = """\
<?xml version='1.0' encoding='UTF-8'?>
<ovf:Envelope xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common">
  <ovf:References>
    <ovf:File ovf:href="file.iso" ovf:size="1234567890" ovf:id="fileId_1"/>
  </ovf:References>
  <ovf:DiskSection>
    <ovf:Info>Describes the set of virtual disks</ovf:Info>
  </ovf:DiskSection>
  <ovf:NetworkSection>
    <ovf:Info>List of logical networks used in the package</ovf:Info>
    <ovf:Network ovf:name="Network Name">
      <ovf:Description>Network Description</ovf:Description>
    </ovf:Network>
  </ovf:NetworkSection>
  <ovf:VirtualSystemCollection ovf:id="testproject-1-x86">
    <ovf:Info>Virtual System Collection Info</ovf:Info>
    <ovf:ResourceAllocationSection>
      <ovf:Info>Resource Allocation Section Info</ovf:Info>
    </ovf:ResourceAllocationSection>
    <ovf:VirtualSystem ovf:id="testproject-1-x86">
      <ovf:Info>Test Description</ovf:Info>
      <ovf:VirtualHardwareSection>
        <ovf:Info>Describes the set of virtual hardware</ovf:Info>
        <ovf:Item>
          <rasd:Caption>Virtual CPU</rasd:Caption>
          <rasd:Description>Number of virtual CPUs</rasd:Description>
          <rasd:ElementName>some virt cpu</rasd:ElementName>
          <rasd:InstanceID>1</rasd:InstanceID>
          <rasd:ResourceType>3</rasd:ResourceType>
          <rasd:VirtualQuantity>1</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>MegaBytes</rasd:AllocationUnits>
          <rasd:Caption>256 MB of Memory</rasd:Caption>
          <rasd:Description>Memory Size</rasd:Description>
          <rasd:ElementName>some mem size</rasd:ElementName>
          <rasd:InstanceID>2</rasd:InstanceID>
          <rasd:ResourceType>4</rasd:ResourceType>
          <rasd:VirtualQuantity>256</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>Interface</rasd:AllocationUnits>
          <rasd:Connection>Network Name</rasd:Connection>
          <rasd:Description>Network Interface</rasd:Description>
          <rasd:ElementName>Network Interface</rasd:ElementName>
          <rasd:InstanceID>3</rasd:InstanceID>
          <rasd:ResourceType>10</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:Caption>CD-ROM</rasd:Caption>
          <rasd:ElementName>CD-ROM</rasd:ElementName>
          <rasd:HostResource>ovf:/file/fileId_1</rasd:HostResource>
          <rasd:InstanceID>6</rasd:InstanceID>
          <rasd:ResourceType>15</rasd:ResourceType>
        </ovf:Item>
      </ovf:VirtualHardwareSection>
    </ovf:VirtualSystem>
  </ovf:VirtualSystemCollection>
</ovf:Envelope>
"""

instIsoOvfXml = """\
<?xml version='1.0' encoding='UTF-8'?>
<ovf:Envelope xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common">
  <ovf:References>
    <ovf:File ovf:href="file.iso" ovf:size="1234567890" ovf:id="fileId_1"/>
  </ovf:References>
  <ovf:DiskSection>
    <ovf:Info>Describes the set of virtual disks</ovf:Info>
  </ovf:DiskSection>
  <ovf:NetworkSection>
    <ovf:Info>List of logical networks used in the package</ovf:Info>
    <ovf:Network ovf:name="Network Name">
      <ovf:Description>Network Description</ovf:Description>
    </ovf:Network>
  </ovf:NetworkSection>
  <ovf:VirtualSystemCollection ovf:id="testinstiso">
    <ovf:Info>Virtual System Collection Info</ovf:Info>
    <ovf:ResourceAllocationSection>
      <ovf:Info>Resource Allocation Section Info</ovf:Info>
    </ovf:ResourceAllocationSection>
    <ovf:VirtualSystem ovf:id="testinstiso">
      <ovf:Info>Test Description</ovf:Info>
      <ovf:VirtualHardwareSection>
        <ovf:Info>Describes the set of virtual hardware</ovf:Info>
        <ovf:Item>
          <rasd:Caption>Virtual CPU</rasd:Caption>
          <rasd:Description>Number of virtual CPUs</rasd:Description>
          <rasd:ElementName>some virt cpu</rasd:ElementName>
          <rasd:InstanceID>1</rasd:InstanceID>
          <rasd:ResourceType>3</rasd:ResourceType>
          <rasd:VirtualQuantity>1</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>MegaBytes</rasd:AllocationUnits>
          <rasd:Caption>256 MB of Memory</rasd:Caption>
          <rasd:Description>Memory Size</rasd:Description>
          <rasd:ElementName>some mem size</rasd:ElementName>
          <rasd:InstanceID>2</rasd:InstanceID>
          <rasd:ResourceType>4</rasd:ResourceType>
          <rasd:VirtualQuantity>256</rasd:VirtualQuantity>
        </ovf:Item>
        <ovf:Item>
          <rasd:AllocationUnits>Interface</rasd:AllocationUnits>
          <rasd:Connection>Network Name</rasd:Connection>
          <rasd:Description>Network Interface</rasd:Description>
          <rasd:ElementName>Network Interface</rasd:ElementName>
          <rasd:InstanceID>3</rasd:InstanceID>
          <rasd:ResourceType>10</rasd:ResourceType>
        </ovf:Item>
        <ovf:Item>
          <rasd:Caption>CD-ROM</rasd:Caption>
          <rasd:ElementName>CD-ROM</rasd:ElementName>
          <rasd:HostResource>ovf:/file/fileId_1</rasd:HostResource>
          <rasd:InstanceID>6</rasd:InstanceID>
          <rasd:ResourceType>15</rasd:ResourceType>
        </ovf:Item>
      </ovf:VirtualHardwareSection>
    </ovf:VirtualSystem>
  </ovf:VirtualSystemCollection>
</ovf:Envelope>
"""
