# Copyright (c) 2012 rPath, Inc.
# All rights reserved.

from collections import namedtuple
import struct
import sys


class VMDK(object):
    _SECT = 512
    _HEADER = namedtuple('Header', 'magicNumber version flags capacity '
        'grainSize descriptorOffset descriptorSize numGTEsPerGT rgdOffet '
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

    def __init__(self, fobj):
        self._fobj = fobj

    def inspect(self):
        headerData = self._fobj.read(self._SECT)
        self.header = self._HEADER(*struct.unpack("<4sIIQQQQIQQQBccccI431s", headerData))
        self.assertEquals(self.header.magicNumber, 'KDMV')
        print self.header
        # skip to descriptor
        self._fobj.read(self._SECT * (self.header.descriptorOffset - 1))
        self.descriptor = self._fobj.read(self._SECT * self.header.descriptorSize)
        print self.descriptor

        # skip over the overhead
        self._fobj.seek(self.header.overHead * self._SECT, 0)
        grainTable = self.GrainTable()
        grainDirectory = self.GrainDirectory()
        while 1:
            marker = self._readMarker(withData=False)
            self._align()
            if isinstance(marker, self._METADATA_MARKER):
                print "Read metadata marker of type %s" % self.Marker.toTypeString(marker.type)
                if marker.type == self.Marker.GT:
                    grainTable.fromMarker(marker)
                    grainDirectory.add(grainTable)
                    self.assertEquals(marker.metadata, grainTable.asTuple())
                    grainTable.reset()
                    continue
                if marker.type == self.Marker.GD:
                    self.assertEquals(marker.metadata, grainDirectory.asTuple())
                    # We're done reading extents, we now need to read
                    # the footer
                    break
                continue
            print marker.lba, marker.size
            grainTable.add(marker)

        footerMarker = self._readMarker()
        self.footer = self._HEADER(*struct.unpack("<4sIIQQQQIQQQBccccI431s",
            footerMarker.metadata))
        self.assertEquals(self.footer.magicNumber, 'KDMV')
        eosMarker = self._readMarker()
        self.assertEquals(eosMarker.type, self.Marker.EOS)

    def assertEquals(self, first, second):
        assert first == second, "%s != %s" % (first, second)

    def _readMarker(self, withData=False):
        offset = self._fobj.tell()
        assert offset % self._SECT == 0
        offset /= self._SECT
        markerData = self._fobj.read(16)
        marker, markerType = self._readMarkerFromData(markerData)
        if marker.size:
            if withData:
                grainData = marker.data + self._fobj.read(marker.size - 4)
            else:
                grainData = "..."
                # Seek from current position, to pretend we're reading
                self._fobj.seek(marker.size - 4, 1)
            marker = self._GRAIN_MARKER(marker.val, marker.size, grainData, offset)
        else:
            # Realign to read the metadata
            self._align()
            metadata = self._fobj.read(marker.val * self._SECT)
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
        pos = self._fobj.tell()
        padding = pos % self._SECT
        if padding:
            self._fobj.read(self._SECT - padding)

def main():
    if len(sys.argv) != 2:
        print "Usage: %s <file>" % sys.argv[0]
        return 1
    vmdkFile = file(sys.argv[1])

    vmdk = VMDK(vmdkFile)
    vmdk.inspect()

if __name__ == '__main__':
    sys.exit(main())

