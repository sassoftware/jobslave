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


from lxml import etree
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

class BaseVmwareImageTest(JobSlaveHelper):
    GeneratorClass = None
    OvfNsMap = dict(ovf='http://schemas.dmtf.org/ovf/envelope/1',
                vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData",
                rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData",
                vbox="http://www.virtualbox.org/ovf/machine")
    def _mock(self, data=None, buildData=None):
        self.data.update(data or {})
        self.data['data'].update(buildData or {})

        self.vmwareDisk = disk = mock.MockObject()
        def mockMakeHDImage(image):
            buf = ''.join(chr(x) for x in range(32, 128))
            f = file(image, "w")
            for i in range(1024*1024):
                f.write(buf)
            f.flush()
            disk._mock.set(totalSize=f.tell(), image=image)
            return disk
        img = self.GeneratorClass(self.slaveCfg, self.data)
        img.swapSize = 4 * 1024 * 1024
        img.makeHDImage = mockMakeHDImage

        origLogCall = vmware_image.logCall
        self.logCallArgs = logCallArgs = []
        def mockLogCall(cmd, **kw):
            logCallArgs.append((cmd, kw))
            if cmd[0] != '/usr/bin/raw2vmdk':
                return origLogCall(cmd, **kwargs)
            hdImage = cmd[-2]
            outfile = cmd[-1]
            assert os.path.exists(hdImage)
            with open(outfile, 'w') as f:
                f.seek(1000000)
                f.truncate()
        self.mock(vmware_image, 'logCall', mockLogCall)
        mock.mockMethod(img.downloadChangesets)
        mock.mockMethod(img.postOutput)
        self.img = img
        return img

    @classmethod
    def _xpath(cls, et, path):
        return et.xpath(path, namespaces=cls.OvfNsMap)

class VMwareImageTest(BaseVmwareImageTest):
    GeneratorClass = vmware_image.VMwareImage
    OVF_XML = """\
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
        <Display VRAMSize="16" monitorCount="1" accelerate3D="false" accelerate2DVideo="false"/>
        <RemoteDisplay enabled="false"/>
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
"""

    def testOvfProductSection(self):
        self._mock(data=dict(description='Blabbedy'),
                buildData=dict(buildOVF10=True))
        def mockCreateVMDK(hdImage, outfile, size, streaming=False):
            assert os.path.exists(hdImage)
            with open(outfile, 'w') as f:
                f.seek(1000000)
                f.truncate()
        img = self.img
        img._createVMDK = mockCreateVMDK
        img.write()
        self.assertXMLEquals(file(img.ovfImage.ovfPath).read(), self.OVF_XML)

    def testVirtualHardwareVersion(self):
        self._mock(data=dict(description='Blabbedy'),
                buildData=dict(buildOVF10=True, vmCPUs=12))
        img = self.img
        img.write()

        xmlBlob = file(img.ovfImage.ovfPath).read()
        et = etree.fromstring(xmlBlob)
        nsmap = dict(ovf='http://schemas.dmtf.org/ovf/envelope/1',
                vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData",
                rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData",
                vbox="http://www.virtualbox.org/ovf/machine")
        virtHwSect = self._xpath(et, '/ovf:Envelope/ovf:VirtualSystem/ovf:VirtualHardwareSection')[0]
        vsystype = self._xpath(virtHwSect, 'ovf:System/vssd:VirtualSystemType')[0]
        vsystype.text = 'vmx-10'
        # Find instance 1, with the label

        item = self._xpath(virtHwSect, 'ovf:Item[rasd:InstanceID = 1]')[0]
        self._xpath(item, 'rasd:Caption')[0].text = "12 CPUs"
        self._xpath(item, 'rasd:VirtualQuantity')[0].text = "12"

        vboxMachine = self._xpath(et, '/ovf:Envelope/ovf:VirtualSystem/vbox:Machine')[0]
        vboxMachine.xpath('Hardware/CPU')[0].attrib['count'] = '12'

        xml = etree.tostring(et)
        self.assertXMLEquals(file(img.ovfImage.ovfPath).read(), xml)
        diskImagePath = self.vmwareDisk.image
        vmdkPath = os.path.join(os.path.dirname(diskImagePath),
                    'foo-1.0.1-x86/foo-1.0.1-x86.vmdk')
        self.assertEquals(self.logCallArgs[-1],
                (['/usr/bin/raw2vmdk', '-C', '96', '-H', '64', '-S', '32',
                    '-A', 'lsilogic', '-V', '10', diskImagePath, vmdkPath, ],
                    {}),)

        # More memory
        self.data['data'].update(buildOVF10=True, vmCPUs=1, vmMemory=65536)
        # Force hwVersion to be recomputed
        img.configure()

        img.write()
        xmlBlob = file(img.ovfImage.ovfPath).read()
        et = etree.fromstring(xmlBlob)
        virtHwSect = self._xpath(et, '/ovf:Envelope/ovf:VirtualSystem/ovf:VirtualHardwareSection')[0]
        vsystype = self._xpath(virtHwSect, 'ovf:System/vssd:VirtualSystemType')[0]
        vsystype.text = 'vmx-10'
        item = self._xpath(virtHwSect, 'ovf:Item[rasd:InstanceID = 2]')[0]
        self._xpath(item, 'rasd:Caption')[0].text = "65536 MB of Memory"
        self._xpath(item, 'rasd:VirtualQuantity')[0].text = "65536"

        vboxMachine = self._xpath(et, '/ovf:Envelope/ovf:VirtualSystem/vbox:Machine')[0]
        vboxMachine.xpath('Hardware/Memory')[0].attrib['RAMSize'] = '65536'

        xml = etree.tostring(et)
        self.assertXMLEquals(file(img.ovfImage.ovfPath).read(), xml)

        # No need to re-test raw2vmdk invocation, we've validated that
        # hwVersion was properly set

        vmxPath = os.path.join(img.workingDir, 'foo-1.0.1-x86.vmx')
        f = file(vmxPath)
        self.assertIn('virtualHW.version = "10"', f.read())

    def testNameInVMX(self):
        # APPENG-3231
        baseFileName = "obfuscated-orangutan"
        self._mock(data=dict(description='Blabbedy'),
                buildData=dict(baseFileName=baseFileName))
        img = self.img
        img.write()
        vmxPath = os.path.join(img.workingDir, '%s.vmx' % baseFileName)
        f = file(vmxPath)
        self.assertIn('displayName = "%s"' % baseFileName, f.read())

    def testNameInVMXWithSpaces(self):
        # APPENG-3541
        baseFileName = "obfuscated orangutan"
        baseFileNameUnderscores = baseFileName.replace(' ', '_')
        self._mock(data=dict(description='Blabbedy'),
                buildData=dict(baseFileName=baseFileName))
        img = self.img
        img.write()
        vmxPath = os.path.join(img.workingDir, '%s.vmx' % baseFileNameUnderscores)
        f = file(vmxPath)
        vmx = f.read()
        # displayName still has spaces
        self.assertIn('displayName = "%s"' % baseFileName, vmx)
        # other uses of basefilename have spaces replaced by underscores
        self.assertIn('nvram = "%s.nvram"' % baseFileNameUnderscores, vmx)

    def testNameInVboxWithSpaces(self):
        # VAPPEN-1796, APPENG-3740
        baseFileName = "obfuscated orangutan"
        baseFileNameUnderscores = baseFileName.replace(' ', '_')
        self._mock(data=dict(description='Blabbedy'),
                buildData=dict(baseFileName=baseFileName, buildOVF10=True))
        img = self.img
        img.write()
        self.assertEquals(os.path.basename(img.ovfImage.ovfPath),
                baseFileNameUnderscores + '.ovf')
        xmlBlob = file(img.ovfImage.ovfPath).read()
        et = etree.fromstring(xmlBlob)
        virtSystemId = self._xpath(et, '/ovf:Envelope/ovf:VirtualSystem/@ovf:id')[0]
        self.assertEquals(virtSystemId, baseFileName)
        vboxMachineName = self._xpath(et, '/ovf:Envelope/ovf:VirtualSystem/vbox:Machine/@name')[0]
        self.assertEquals(vboxMachineName, baseFileName)

    def testNatNetworking(self):
        baseFileName = "obfuscated-orangutan"
        self._mock(data=dict(description='Blabbedy'),
                buildData=dict(buildOVF10=True, natNetworking=True,
                    baseFileName=baseFileName))
        img = self.img
        img.write()
        ovfPath = os.path.join(img.workingDir, '%s.ovf' % baseFileName)
        f = file(ovfPath)

        et = etree.parse(f)
        virtHwSect = self._xpath(et, '/ovf:Envelope/ovf:VirtualSystem/ovf:VirtualHardwareSection')[0]
        itemsResourceType = self._xpath(virtHwSect, 'ovf:Item/rasd:ResourceType/text()')
        self.assertEquals(itemsResourceType, ['3', '4', '10', '17', '6', ])
        nwItem = self._xpath(virtHwSect, 'ovf:Item')[2]
        conn = self._xpath(nwItem, 'rasd:Connection/text()')
        self.assertEquals(conn, ['nat'])

        nwNames = self._xpath(et, '/ovf:Envelope/ovf:NetworkSection/ovf:Network/@ovf:name')
        self.assertEquals(nwNames, ['nat'])

class VMwareESXImageTest(BaseVmwareImageTest):
    GeneratorClass = vmware_image.VMwareESXImage
