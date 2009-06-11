#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

import struct


BLOCK = 512


class Geometry(object):
    def __init__(self, heads, sectors):
        self._heads = heads
        self._sectors = sectors

    # Constants / inputs
    @property
    def heads(self):
        return self._heads
    @property
    def sectors(self):
        return self._sectors
    @property
    def sectorSize(self):
        return BLOCK

    # Derived constants
    @property
    def bytesPerCylinder(self):
        return self.sectors * self.heads * BLOCK

    # Conversion methods
    def toCHS(self, offset):
        """
        Convert a block offset to a CHS tuple.
        """
        cylSize = self.sectors * self.heads
        cylinder = offset / cylSize
        offset = offset % cylSize

        head = offset / self.sectors
        sector = offset % self.sectors + 1

        return cylinder, head, sector

    def makePart(self, start, length, bootable=False, fsType=0x83):
        """
        Return an IBM-compatible partition entry (16 bytes) for a partition
        starting at C{start} blocks and with a length of C{length} blocks,
        optionally flagged as C{booble}, and optionally with a type of
        C{fsType} (defaulting to 0x83, Linux).
        """
        startCHS = packCHS(self.toCHS(start))
        endCHS = packCHS(self.toCHS(start + length - 1))
        bootable = bootable and 0x80 or 0
        return struct.pack('<B3sB3s2I', bootable, startCHS, fsType, endCHS,
                start, length)


def packCHS((cylinder, head, sector)):
    """
    Pack a CHS tuple for use in an IBM-compatible partition table. Overflows
    will be clamped to the maximum value.
    """
    pack_cylinder = min(cylinder, 0x3FF)
    pack_head = min(head, 0xFF)
    pack_sector = min(sector, 0x3F)
    byte_2 = pack_sector | ((pack_cylinder & 0x300) >> 2)
    byte_3 = pack_cylinder & 0xFF
    return struct.pack('<3B', pack_head, byte_2, byte_3)
