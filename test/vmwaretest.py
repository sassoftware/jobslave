#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

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

    def testGuestOS(self):
        class DummyImage(vmware_image.VMwareImage):
            def __init__(x, flav):
                x.baseFlavor = deps.parseFlavor(flav)
        gen = DummyImage('')
        self.assertEquals(gen.getGuestOS(), "other26xlinux")

    def testGuestOS64(self):
        class DummyImage(vmware_image.VMwareImage):
            def __init__(x, flav):
                x.baseFlavor = deps.parseFlavor(flav)
        gen = DummyImage('is: x86_64')
        self.assertEquals(gen.getGuestOS(), "other26xlinux-64")

    def testGuestOSESX(self):
        class DummyImage(vmware_image.VMwareESXImage):
            def __init__(x, flav):
                x.baseFlavor = deps.parseFlavor(flav)
        gen = DummyImage('')
        self.assertEquals(gen.getGuestOS(), "linux")

    def testGuestOSESX64(self):
        class DummyImage(vmware_image.VMwareESXImage):
            def __init__(x, flav):
                x.baseFlavor = deps.parseFlavor(flav)
        gen = DummyImage('is: x86_64')
        self.assertEquals(gen.getGuestOS(), "otherlinux-64")


if __name__ == "__main__":
    testsuite.main()
