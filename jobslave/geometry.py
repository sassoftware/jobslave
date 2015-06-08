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


import struct
from jobslave.util import divCeil


FSTYPE_LINUX_SWAP   = 0x82
FSTYPE_LINUX        = 0x83
FSTYPE_LINUX_LVM    = 0x8e


class Geometry(tuple):
    BLOCK = 512
    offsetBlocks = 128
    offsetBytes = offsetBlocks * BLOCK

    def __new__(cls, heads, sectors):
        return tuple.__new__(cls, (heads, sectors))

    # Constants / inputs
    @property
    def heads(self):
        return self[0]
    @property
    def sectors(self):
        return self[1]

    # Derived constants
    @property
    def bytesPerCylinder(self):
        return self.sectors * self.heads * self.BLOCK

    # Arithmetic methods
    def cylindersRequired(self, minBytes):
        return divCeil(minBytes, self.bytesPerCylinder)

    def roundToCylinder(self, minBytes):
        return divCeil(minBytes, self.bytesPerCylinder) * self.bytesPerCylinder

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

    def makePart(self, start, length, bootable=False, fsType=FSTYPE_LINUX):
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


GEOMETRY_REGULAR    = Geometry(64, 32)
GEOMETRY_VHD        = Geometry(16, 63)
