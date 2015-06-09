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


from collections import namedtuple
import logging
import math
import os
import struct
import sys
import zlib

log = logging.getLogger(__name__)

class VMDK(object):
    __slots__ = ['_streamIn', '_streamOut', 'header', 'descriptor', ]
    _SECT = 512
    _HEADER = namedtuple('Header', 'magicNumber version flags capacity '
        'grainSize descriptorOffset descriptorSize numGTEsPerGT rgdOffset '
        'gdOffset overHead uncleanShutdown singleEndLineChar nonEndLineChar '
        'doubleEndLineChar1 doubleEndLineChar2 compressAlgorithm pad')
    _MARKER = namedtuple('Marker', 'val size data')
    _GRAIN_MARKER = namedtuple('GrainMarker', 'lba size data offset')
    _METADATA_MARKER = namedtuple('Metadata', 'numSectors size type pad metadata offset')

    class Marker(object):
        EOS = 0
        GT = 1
        GD = 2
        FOOTER = 3

        Pad = '\0' * 496

        _StringRepr = [ 'EOS', 'GT', 'GD', 'FOOTER', ]

        @classmethod
        def DecodeType(cls, data):
            return struct.unpack("<I", data)[0]

        @classmethod
        def toTypeString(cls, intVal):
            return cls._StringRepr[intVal]

    class BaseGrainTable(object):
        __slots__ = [ 'map' ]

        def __init__(self):
            self.reset()

        def reset(self):
            self.map = self.empty()

        def asTuple(self):
            return tuple(self.map)

        @classmethod
        def fromData(cls, data):
            sformat = "<%sI" % (len(data) / 4)
            arr = struct.unpack(sformat, data)
            ret = cls()
            ret.map = arr
            return ret

    class GrainTable(BaseGrainTable):
        __slots__ = [ 'offset', 'lba', ]
        _format = "<512I"
        BLOCK_SIZE = 65536

        def __init__(self):
            VMDK.BaseGrainTable.__init__(self)
            self.offset = 0
            self.lba = -1

        def add(self, marker):
            idx = (marker.lba % self.BLOCK_SIZE) / 128
            self.map[idx] = marker.offset
            self.lba = marker.lba / self.BLOCK_SIZE

        def fromMarker(self, marker):
            self.offset = marker.offset + 1

        @classmethod
        def decode(cls, marker, data):
            if len(data) != 2048:
                return []
            return struct.unpack(cls._format, data)

        @classmethod
        def empty(cls):
            return [ 0 ] * 512

        def isEmpty(self):
            for i in self.map:
                if i != 0:
                    return False
            return True

    class GrainDirectory(BaseGrainTable):
        __slots__ = []
        GD_AT_END = 0xffffffffffffffff

        def add(self, grainTable):
            if grainTable.isEmpty():
                return
            idx = grainTable.lba
            mapLen = len(self.map)
            # We may have skipped some tables, but we need to add a full
            # block of 128
            while mapLen <= idx:
                self.map.extend([ 0 ] * 128)
                mapLen += 128
            self.map[idx] = grainTable.offset

        @classmethod
        def decode(cls, marker, data):
            sformat = "<%sI" % (marker.val * VMDK._SECT / 4)
            metadata = struct.unpack(sformat, data)
            return metadata

        def empty(self):
            return []

    def __init__(self, fobj, outputStream):
        self._streamIn = fobj
        self._streamOut = outputStream
        self._streamOut.seek(0)

    def inspect(self):
        fout = self._streamOut

        headerData = self._streamIn.read(self._SECT)
        self.header = self._HEADER(*struct.unpack("<4sIIQQQQIQQQBccccI431s", headerData))
        self.assertEquals(self.header.magicNumber, 'KDMV')
        log.debug("Header: %s", self.header)
        fout.seek(self.header.capacity * self._SECT)
        fout.truncate()
        if self.header.descriptorSize > 0:
            # skip to descriptor
            self._streamIn.read(self._SECT * (self.header.descriptorOffset - 1))
            self.descriptor = self._streamIn.read(self._SECT * self.header.descriptorSize)
            log.debug("Descriptor: %s", self.descriptor)
        if self.header.gdOffset != self.GrainDirectory.GD_AT_END:
            self.assertEquals(self.header.compressAlgorithm, 0)
            return self.inspectNonStreamOptimized()

        # skip over the overhead
        self._streamIn.seek(self.header.overHead * self._SECT, 0)
        grainTable = self.GrainTable()
        grainDirectory = self.GrainDirectory()
        while 1:
            marker = self._readMarker()
            self._align()
            if isinstance(marker, self._METADATA_MARKER):
                log.debug("%08x: Read metadata marker of type %s",
                        marker.offset, self.Marker.toTypeString(marker.type))
                if marker.type == self.Marker.GT:
                    grainTable.fromMarker(marker)
                    grainDirectory.add(grainTable)
                    grainTable.reset()
                    continue
                if marker.type == self.Marker.GD:
                    self.assertEquals(marker.metadata, grainDirectory.asTuple())
                    # We're done reading extents, we now need to read
                    # the footer
                    break
                continue
            log.debug("Data: %08x: %d bytes", marker.lba, marker.size)
            fout.seek(marker.lba * self._SECT)
            fout.write(zlib.decompress(marker.data))
            grainTable.add(marker)

        footerMarker = self._readMarker()
        self.assertEquals(footerMarker.type, self.Marker.FOOTER)
        footer = self._HEADER(*struct.unpack("<4sIIQQQQIQQQBccccI431s",
            footerMarker.metadata))
        self.assertEquals(footer.magicNumber, 'KDMV')
        eosMarker = self._readMarker()
        self.assertEquals(eosMarker.type, self.Marker.EOS)

    def inspectNonStreamOptimized(self):
        fout = self.outputStream
        grainDirectory = self.GrainDirectory()

        # Compute size of GD
        numGTs = math.ceil(self.header.capacity / float(self.header.grainSize))
        gdSize = int(math.ceil(numGTs / self.header.numGTEsPerGT))
        # gd is aligned to a sector size, which is 512, with each entry
        # being 4 bytes
        gdSize = self.pad(gdSize, 512/4)

        self._streamIn.seek(self.header.gdOffset * self._SECT, 0)
        grainDirectory = self.GrainDirectory.fromData(self._streamIn.read(gdSize * 4))
        self._streamIn.seek(self.header.rgdOffset * self._SECT, 0)
        rgrainDirectory = self.GrainDirectory.fromData(self._streamIn.read(gdSize * 4))
        #self.assertEquals(grainDirectory.map, rgrainDirectory.map)

        grainSizeBytes = self.header.grainSize * self._SECT
        for gtNum in range(gdSize):
            self._streamIn.seek(grainDirectory.map[gtNum] * self._SECT, 0)
            gt = self.GrainTable.fromData(self._streamIn.read(512 * 4))
            assert len(gt.map) == 512
            self._streamIn.seek(rgrainDirectory.map[gtNum] * self._SECT, 0)
            rgt = self.GrainTable.fromData(self._streamIn.read(512 * 4))
            self.assertEquals(gt.map, rgt.map)

            for (gteNum, gte) in enumerate(gt.map):
                pos = gtNum * self.header.numGTEsPerGT + gteNum
                if pos >= numGTs:
                    break
                self.assertEquals(gte, rgt.map[gteNum])

                self._streamIn.seek(self.header.gdOffset * self._SECT + gdSize * 4 + pos * 4)
                data = self._streamIn.read(4)
                gteOther = struct.unpack("<I", data)[0]
                self.assertEquals(gte, gteOther)

                if fout and gte > 0:
                    self._streamIn.seek(gte * self._SECT)
                    fout.seek((gtNum * 512 + gteNum) * grainSizeBytes)
                    data = self._streamIn.read(grainSizeBytes)
                    assert len(data) == grainSizeBytes
                    fout.write(data)

            if (gtNum + 1) * self.header.numGTEsPerGT > numGTs:
                break


    @classmethod
    def pad(cls, number, paddingSize):
        remainder = number % paddingSize
        if remainder == 0:
            return number
        return number + paddingSize - remainder

    def assertEquals(self, first, second):
        assert first == second, "%s != %s" % (first, second)

    def _readMarker(self):
        offset = self._streamIn.tell()
        assert offset % self._SECT == 0
        offset /= self._SECT
        markerData = self._streamIn.read(16)
        marker, markerType = self._readMarkerFromData(markerData)
        if marker.size:
            grainData = marker.data + self._streamIn.read(marker.size - 4)
            marker = self._GRAIN_MARKER(marker.val, marker.size, grainData, offset)
        else:
            # Realign to read the metadata
            self._align()
            metadata = self._streamIn.read(marker.val * self._SECT)
            if markerType == self.Marker.GD:
                # Grain directories have a variable number of
                # entries, depending on the extent size, and contain
                # an unsigned int (4 byte)
                metadata = self.GrainDirectory.decode(marker, metadata)
            elif markerType == self.Marker.GT:
                metadata = self.GrainTable.decode(marker, metadata)
            marker = self._METADATA_MARKER(marker.val, marker.size, markerType,
                self.Marker.Pad, metadata, offset)
        return marker

    @classmethod
    def _readMarkerFromData(cls, markerData, checkMarkerType=True):
        marker = cls._MARKER(*struct.unpack("<QI4s", markerData[:16]))
        if marker.size:
            # Compressed grain. Type not needed
            markerType = -1
        else:
            markerType = cls.Marker.DecodeType(marker.data)
            if checkMarkerType:
                assert 0 <= markerType < len(cls.Marker._StringRepr)
        return marker, markerType

    def _align(self):
        "Align to 512 byte boundary"
        pos = self._streamIn.tell()
        padding = pos % self._SECT
        if padding:
            self._streamIn.seek(self._SECT - padding, os.SEEK_CUR)

def main():
    logging.basicConfig(level=logging.DEBUG)
    if len(sys.argv) < 2:
        print "Usage: %s <file-in> <file-out>" % sys.argv[0]
        return 1
    vmdkFile = file(sys.argv[1])
    fileOut = file(sys.argv[2], "w")
    vmdk = VMDK(vmdkFile, fileOut)
    vmdk.inspect()

if __name__ == '__main__':
    sys.exit(main())
