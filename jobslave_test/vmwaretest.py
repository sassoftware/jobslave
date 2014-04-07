#
# Copyright (c) SAS Institute Inc.
#

import os
from testutils import mock

from jobslave.job_data import JobData
from jobslave.generators import vmware_image
from jobslave_test.jobslave_helper import JobSlaveHelper
from conary.deps import deps

class VMwareTest(JobSlaveHelper):
    def testNoVmEscape(self):
        data = 'test'
        ref = 'test'
        res = vmware_image.vmEscape(data)

        self.failIf(ref != res,
                "vmEscape returned '%s' but expected '%s'" % (res, ref))

    def testVmEscapeNewline(self):
        data = 'test\n'
        ref = 'test'
        res = vmware_image.vmEscape(data, eatNewlines = False)

        self.failIf(ref != res,
                "vmEscape returned '%s' but expected '%s'" % (res, ref))

        data = 'test\ntest'
        ref = 'test|0Atest'
        res = vmware_image.vmEscape(data, eatNewlines = False)

        self.failIf(ref != res,
                "vmEscape returned '%s' but expected '%s'" % (res, ref))

    def testVmEscapeEatNewline(self):
        data = 'test\ntest'
        ref = 'testtest'
        res = vmware_image.vmEscape(data)

        self.failIf(ref != res,
                "vmEscape returned '%s' but expected '%s'" % (res, ref))

    def testVmEscapes(self):
        data = '<test|"test">#'
        ref = '|3Ctest|7C|22test|22|3E|23'
        res = vmware_image.vmEscape(data)

        self.failIf(ref != res,
                "vmEscape returned '%s' but expected '%s'" % (res, ref))

    def testVmEscapeScrub(self):
        data = 'test\x04test'
        ref = 'testtest'
        res = vmware_image.vmEscape(data)

        self.failIf(ref != res,
                "vmEscape returned '%s' but expected '%s'" % (res, ref))

    def _testGuestOS(self, base, platform, flavor, expected):
        class DummyImage(base):
            def __init__(xself):
                xself.baseFlavor = deps.parseFlavor(flavor)
                xself.jobData = JobData(platformName=platform)
            def getPlatformAndVersion(self):
                return 'other26xlinux', '26'
        self.assertEquals(DummyImage().getGuestOS(), expected)

    def testGuestOS(self):
        self._testGuestOS(vmware_image.VMwareImage, '', '',
                'other26xlinux')
        self._testGuestOS(vmware_image.VMwareImage, '', 'is: x86_64',
                'other26xlinux-64')
        self._testGuestOS(vmware_image.VMwareESXImage, '', '',
                'other26xlinux')
        self._testGuestOS(vmware_image.VMwareESXImage, '', 'is: x86_64',
                'other26xlinux-64')

class VMwareImageTest(JobSlaveHelper):
    def testOvfProductSection(self):
        self.constants.templateDir = os.path.join(self.testDir, '..',
                'templates')
        disk = mock.MockObject()
        def mockMakeHDImage(image):
            buf = ''.join(chr(x) for x in range(32, 128))
            f = file(image, "w")
            for i in range(1024*1024):
                f.write(buf)
            f.flush()
            disk._mock.set(totalSize=f.tell(), image=image)
            return disk
        def mockCreateVMDK(hdImage, outfile, size, streaming=False):
            assert os.path.exists(hdImage)
            with open(outfile, 'w') as f:
                f.seek(1000000)
                f.truncate()

        self.data['data'].update(buildOVF10=True)
        self.data.update(description='Blabbedy')
        img = vmware_image.VMwareImage(self.slaveCfg, self.data)
        img.makeHDImage = mockMakeHDImage
        img._createVMDK = mockCreateVMDK

        mock.mockMethod(img.downloadChangesets)
        mock.mockMethod(img.postOutput)
        img.write()
        self.assertXMLEquals(file(img.ovfImage.ovfPath).read(), """\
<?xml version='1.0' encoding='UTF-8'?>
<ovf:Envelope xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData" xmlns:vmw="http://www.vmware.com/schema/ovf" xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1" xmlns:cim="http://schemas.dmtf.org/wbem/wscim/1/common" xmlns:vbox="http://www.virtualbox.org/ovf/machine">
  <ovf:References>
    <ovf:File ovf:href="foo-1.0.1-x86.vmdk.gz" ovf:id="fileId_1" ovf:size="1022" ovf:compression="gzip"/>
  </ovf:References>
  <ovf:DiskSection>
    <ovf:Info>Describes the set of virtual disks</ovf:Info>
    <ovf:Disk ovf:diskId="diskId_1" ovf:capacity="100663296" ovf:fileRef="fileId_1" ovf:format="http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized" vbox:uuid="00000000-0000-4000-8000-000000000001"/>
  </ovf:DiskSection>
  <ovf:NetworkSection>
    <ovf:Info>List of logical networks used in the package</ovf:Info>
    <ovf:Network ovf:name="Network Name">
      <ovf:Description>Network Description</ovf:Description>
    </ovf:Network>
  </ovf:NetworkSection>
  <ovf:VirtualSystem ovf:id="foo-1.0.1-x86">
    <ovf:Info>Blabbedy</ovf:Info>
    <ovf:OperatingSystemSection ovf:version="26" vmw:osType="other26xLinuxGuest" ovf:id="36">
      <ovf:Info>The kind of installed guest operating system</ovf:Info>
      <ovf:Description>Other Linux 2.6 (32 bit)</ovf:Description>
    </ovf:OperatingSystemSection>
    <ovf:VirtualHardwareSection>
      <ovf:Info>Describes the set of virtual hardware</ovf:Info>
      <ovf:System>
        <vssd:ElementName>Virtual Hardware Family</vssd:ElementName>
        <vssd:InstanceID>instanceId_1</vssd:InstanceID>
        <vssd:VirtualSystemType>vmx-07</vssd:VirtualSystemType>
      </ovf:System>
      <ovf:Item>
        <rasd:Caption>1 CPUs</rasd:Caption>
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
    <vbox:Machine ovf:required="false" uuid="{00000000-0000-4000-8000-000000000000}" name="foo-1.0.1-x86">
      <ovf:Info>VirtualBox machine configuration in VirtualBox format</ovf:Info>
      <Hardware version="2">
        <CPU count="1" hotplug="false"/>
        <Memory RAMSize="256" PageFusion="false"/>
        <Chipset type="ICH9"/>
        <BIOS>
          <ACPI enabled="true"/>
          <IOAPIC enabled="true"/>
          <Logo fadeIn="false" fadeOut="false" displayTime="0"/>
          <BootMenu mode="MessageAndMenu"/>
          <TimeOffset value="0"/>
          <PXEDebug enabled="false"/>
        </BIOS>
        <Network>
          <Adapter slot="0" enabled="true" cable="true" type="82540EM">
            <NAT>
              <DNS pass-domain="true" use-proxy="false" use-host-resolver="false"/>
              <Alias logging="false" proxy-only="false" use-same-ports="false"/>
              <Forwarding name="HTTP" proto="1" hostip="127.0.0.1" hostport="10080" guestport="80"/>
              <Forwarding name="HTTPS" proto="1" hostip="127.0.0.1" hostport="10443" guestport="443"/>
            </NAT>
          </Adapter>
        </Network>
      </Hardware>
      <StorageControllers>
        <StorageController name="SCSI Controller" type="LsiLogic" PortCount="16" useHostIOCache="false" Bootable="true">
          <AttachedDevice type="HardDisk" port="0" device="0">
            <Image uuid="{00000000-0000-4000-8000-000000000001}"/>
          </AttachedDevice>
        </StorageController>
      </StorageControllers>
    </vbox:Machine>
  </ovf:VirtualSystem>
</ovf:Envelope>
""")
