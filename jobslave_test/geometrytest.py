#!/usr/bin/python
#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

import testsuite
testsuite.setup()

from jobslave import geometry


def fromhex(hexstr):
    return ''.join(chr(int(x, 16)) for x in hexstr.split())


class GeometryTest(testsuite.TestCase):
    def testNewStyle(self):
        g = geometry.Geometry(64, 32)
        self.assertEquals(g.heads, 64)
        self.assertEquals(g.sectors, 32)
        self.assertEquals(g.offsetBytes, 65536)
        self.assertEquals(g.bytesPerCylinder, 1048576)

        # Test edge cases - one under and over a cylinder boundary
        self.assertEquals(g.cylindersRequired(34027339775), 32451)
        self.assertEquals(g.cylindersRequired(34027339776), 32451)
        self.assertEquals(g.cylindersRequired(34027339777), 32452)
        self.assertEquals(g.roundToCylinder(34027339775), 34027339776)
        self.assertEquals(g.roundToCylinder(34027339776), 34027339776)
        self.assertEquals(g.roundToCylinder(34027339777), 34028388352)

        self.assertEquals(g.toCHS(1), (0, 0, 2))
        self.assertEquals(g.toCHS(32), (0, 1, 1))
        self.assertEquals(g.toCHS(65535), (31, 63, 32))

        self.assertEquals(g.makePart(32, 126944, True),
                fromhex('80 01 01 00 83 3F 20 3D 20 00 00 00 E0 EF 01 00'))
        self.assertEquals(g.makePart(126976, 2048),
                fromhex('00 00 01 3E 83 3F 20 3E 00 F0 01 00 00 08 00 00'))

    def testOldStyle(self):
        g = geometry.Geometry(16, 63)
        self.assertEquals(g.heads, 16)
        self.assertEquals(g.sectors, 63)
        self.assertEquals(g.offsetBytes, 65536)
        self.assertEquals(g.bytesPerCylinder, 516096)

        # Test edge cases - one under and over a cylinder boundary
        self.assertEquals(g.cylindersRequired(34027241471), 65932)
        self.assertEquals(g.cylindersRequired(34027241472), 65932)
        self.assertEquals(g.cylindersRequired(34027241473), 65933)
        self.assertEquals(g.roundToCylinder(34027241471), 34027241472)
        self.assertEquals(g.roundToCylinder(34027241472), 34027241472)
        self.assertEquals(g.roundToCylinder(34027241473), 34027757568)

        self.assertEquals(g.toCHS(1), (0, 0, 2))
        self.assertEquals(g.toCHS(63), (0, 1, 1))
        self.assertEquals(g.toCHS(100799), (99, 15, 63))

        self.assertEquals(g.makePart(63, 100737, True),
                fromhex('80 01 01 00 83 0F 3F 63 3F 00 00 00 81 89 01 00'))
        self.assertEquals(g.makePart(100800, 1008),
                fromhex('00 00 01 64 83 0F 3F 64 C0 89 01 00 F0 03 00 00'))
