#!/usr/bin/python
#
# Copyright (c) 2011 rPath, Inc.
#

import testsuite
testsuite.setup()

from jobslave.job_data import JobData
from jobslave.generators import vmware_image
from conary.deps import deps


class VMwareTest(testsuite.TestCase):
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


if __name__ == "__main__":
    testsuite.main()
