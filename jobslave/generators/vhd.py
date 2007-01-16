#
# Copyright (c) 2006 rPath, Inc.
#
# All Rights Reserved
#

import md5
import struct
import stat
import os
import sys
import time

SEEK_SET = 0
SEEK_CUR = 1
SEEK_END = 2

Y2K_UTC = 946684800

class VHDDiskType:
    NoneType = 0
    Reserved = 1
    Fixed = 2
    Dynamic = 3
    Differencing = 4
    Reserved2 = 5

class PackedHeader(object):
    fmtDict = {}

    def __getattribute__(self, name):
        try:
            item = object.__getattribute__(self, name)
        except AttributeError:
            fmtDict = self.fmtDict

            if fmtDict and name in fmtDict:
                item = fmtDict[name]
            else:
                raise

        return item

    def __setattr__(self, name, val):
        if name in self.fmtDict:
            if name != 'checksum':
                self._recalcChecksum = True
            self.fmtDict[name] = val
        else:
            return object.__setattr__(self, name, val)

    def __init__(self):
        assert self.fmtList
        self.fmt = "".join(x[1] for x in self.fmtList)
        self.fmtDict = dict((x[0], x[2]) for x in self.fmtList)

        self.uuid = os.urandom(16)
        self.timeStamp = time.time() - Y2K_UTC

    def updateChecksum(self):
        self.checksum = 0
        self._recalcChecksum = False
        footer = PackedHeader.pack(self)
        for x in struct.unpack("%sB" % struct.calcsize(self.fmt), footer):
            self.checksum += x
        self.checksum = int(~self.checksum)

    def pack(self):
        assert None not in self.fmtDict.values()
        if self._recalcChecksum:
            self.updateChecksum()

        args = [self.fmtDict[x[0]] for x in self.fmtList]

        footer = struct.pack(self.fmt, *args)
        return footer

    def unpack(self, data):
        dataList = struct.unpack(self.fmt, data)
        for key, val in zip([x[0] for x in self.fmtList], dataList):
            self.__setattr__(key, val)


class SparseDiskHeader(PackedHeader):
    fmtList = [
        ("cookie",              ">8s",  "cxsparse"),
        ("dataOffset",          "Q",    0xffffffffffffffff),
        ("tableOffset",         "Q",    1536),
        ("headerVersion",       "I",    0x00010000),
        ("maxTableEntries",     "I",    None),
        ("blockSize",           "I",    0x00200000),
        ("checksum",            "I",    0),
        ("parentUuid",          "16s",  ''),
        ("parentTimeStamp",     "I",    0),
        ("reserved",            "4s",   ''),
        ("parentName",          "512s", ""),
        ("parentLocator1",      "24s", ""),
        ("parentLocator2",      "24s", ""),
        ("parentLocator3",      "24s", ""),
        ("parentLocator4",      "24s", ""),
        ("parentLocator5",      "24s", ""),
        ("parentLocator6",      "24s", ""),
        ("parentLocator7",      "24s", ""),
        ("parentLocator8",      "24s", ""),
        ("reserved2",           "256s", ""),
    ]


class VHDFooter(PackedHeader):
    fmtList = [
         ("cookie",         ">8s",  "conectix"),
         ("features",       "I",    0x00000002),
         ("fileFmtVersion", "I",    0x00010000),
         ("dataOffset",     "Q",    0xffffffff),
         ("timeStamp",      "I",    None),
         ("creatorApp",     "4s",   "rba "),
         ("creatorVersion", "I",    0x00050000),
         ("creatorHostOS",  "4s",   "rPth"),
         ("originalSize",   "Q",    None),
         ("currentSize",    "Q",    None),
         ("diskGeometry",   "4s",   None),
         ("diskType",       "I",    VHDDiskType.Fixed),
         ("checksum",       "i",    0),
         ("uuid",           "16s",  None),
         ("savedState",     "1b",   0),
         ("reserved",       "427s", "")
    ]

    cylinderSize = 516096
    sectors = 63
    heads = 16

    def __setattr__(self, name, val):
        if name == 'originalSize':
            cyl = val / self.cylinderSize
            self.diskGeometry = \
                struct.pack(">Hbb", cyl, self.heads, self.sectors)
        PackedHeader.__setattr__(self, name, val)


class BlockAllocationTable(object):
    def __init__(self, numEntries):
        self.blocks = numEntries * [0xFFFFFFFF]

    def __setitem__(self, key, val):
        self.blocks[key] = val

    def __getitem__(self, kek):
        return self.blocks[key]

    def pack(self):
        res = struct.pack('>%dL' % len(self.blocks), *self.blocks)
        res += ((512 - (len(res) % 512)) % 512) * chr(0)
        return res


class SectorBitmap(object):
    def __init__(self, numSectors):
        # split the bit field into 64 bit chunks for ease of integrating with
        # struct.pack()
        self.sectors = (int(bool(numSectors % 64)) + numSectors / 64) * [0]

    def touch(self, sector):
        self.sectors[sector / 64] |= 1 << (63 - (sector % 64))

    def pack(self):
        res = struct.pack('>%dQ' % len(self.sectors), *self.sectors)
        # per VHD spec, pad result to next 512 byte boundary.
        # noted that VPC adds one more block than we do.
        res += ((512 - (len(res) % 512)) % 512) * chr(0)
        return res


class DataBlock(object):
    sectorsPerBlock = 4096
    sectorSize = 512

    def __init__(self, data):
        assert len(data) <= (self.sectorsPerBlock * self.sectorSize)
        self.sectorBitmap = SectorBitmap(self.sectorsPerBlock)
        self.setData(data)

    def setData(self, data):
        self.data = data
        ref = self.sectorSize * chr(0)
        for i in range(self.sectorsPerBlock):
            chunk = data[i * self.sectorSize: (i + 1) * self.sectorSize]
            if chunk != ref:
                self.sectorBitmap.touch(i)

    def isEmpty(self):
        return not max(x for x in self.sectorBitmap.sectors)

    def pack(self):
        return self.sectorBitmap.pack() + self.data


class ParentLocatorEntry(PackedHeader):
    fmtList = [
        ('platformCode', '>4s', None),
        ('dataSpace',    'I',   None),
        ('dataLength',   'I',   None),
        ('reserved',     '4s',  ''),
        ('dataOffset',   'Q',   None)
        ]

    def __init__(self, platformCode):
        PackedHeader.__init__(self)
        assert platformCode in ('Wi2r', 'Wi2k', 'W2ru', 'W2ku', 'Mac ', 'MacX')
        self.platformCode = platformCode

    def __setattr__(self, key, val):
        if key == 'parentName':
            if self.platformCode.startswith('W2'):
                dataLength = len(val.encode('utf-16le'))
            else:
                dataLength = len(val)
            self.dataLength = dataLength
            self.dataSpace = ((dataLength / 512) + \
                                  int(bool(dataLength % 512))) * 512
        PackedHeader.__setattr__(self, key, val)

    def getLocator(self):
        if self.platformCode.startswith('W2'):
            res = self.parentName.encode('utf-16le')
        else:
            res = self.parentName
        res += (self.dataSpace - len(res)) * chr(0)
        # fixme: add padding
        return res


def makeDynamic(inFn, outFn):
    st = os.stat(inFn)

    inF = open(inFn)
    outF = open(outFn, 'w')
    footer = VHDFooter()
    footer.originalSize = footer.currentSize = st[stat.ST_SIZE]
    footer.dataOffset = 512
    footer.diskType = VHDDiskType.Dynamic

    header = SparseDiskHeader()

    blockSize = DataBlock.sectorsPerBlock * DataBlock.sectorSize
    numBatEntries = footer.originalSize / blockSize + \
        int(bool(footer.originalSize % blockSize))

    bat = BlockAllocationTable(numBatEntries)
    header.maxTableEntries = numBatEntries

    outF.write(footer.pack())
    outF.write(header.pack())
    batIndex = outF.tell()
    outF.write(bat.pack())

    data = None
    blockIndex = 0
    while data != '':
        data = inF.read(blockSize)
        if not data:
            break
        block = DataBlock(data)
        if not block.isEmpty():
            assert not (outF.tell() % DataBlock.sectorSize)
            bat[blockIndex] = outF.tell() / DataBlock.sectorSize
            outF.write(block.pack())
        blockIndex += 1

    outF.write(footer.pack())
    outF.seek(batIndex)
    outF.write(bat.pack())
    outF.close()

def makeFlat(inFn):
    st = os.stat(inFn)
    inF = open(inFn, "a")
    footer = VHDFooter()
    footer.originalSize = footer.currentSize = st[stat.ST_SIZE]
    inF.seek(st[stat.ST_SIZE])
    inF.write(footer.pack())
    inF.close()

def makeDifference(inFn, outFn, parentName = None):
    """Make a difference virtual hard disk image

       inFn is path to a virtual hard disk image to use as a base.
       outFn is path to save difference virtual hard disk.
       parentName is the name to use for the parent disk. This will be set to
       inFn if no input is provided.
       Please note, the function assumes these images will end up in the same
       directory, so the basename of inFn will be used inside the difference
       image."""
    inF = open(inFn)
    inF.seek(-512, SEEK_END)
    footer = VHDFooter()
    footer.unpack(inF.read())
    inF.close()
    parentName = parentName or os.path.basename(inFn)

    footer.diskType = VHDDiskType.Differencing

    header = SparseDiskHeader()

    blockSize = DataBlock.sectorsPerBlock * DataBlock.sectorSize
    numBatEntries = footer.currentSize / blockSize + \
        int(bool(footer.currentSize % blockSize))

    bat = BlockAllocationTable(numBatEntries)
    header.maxTableEntries = numBatEntries
    header.parentUuid = footer.uuid
    header.parentTimeStamp = os.stat(inFn)[stat.ST_MTIME] - Y2K_UTC

    footer.timeStamp = time.time() - Y2K_UTC
    # VHD specification indicates this field must be utf-16
    header.parentName = parentName.encode('utf-16be')

    loc1 = ParentLocatorEntry('W2ru')
    loc2 = ParentLocatorEntry('Wi2r')

    loc1.parentName = parentName
    loc2.parentName = parentName

    outF = open(outFn, 'w')
    outF.write(footer.pack())
    headerLoc = outF.tell()
    outF.write(header.pack())
    outF.write(bat.pack())

    loc1.dataOffset = outF.tell()
    outF.write(loc1.getLocator())
    loc2.dataOffset = outF.tell()
    outF.write(loc2.getLocator())

    outF.write(footer.pack())

    # now fix the parent locators in the header
    outF.seek(headerLoc)
    header.parentLocator1 = loc1.pack()
    header.parentLocator2 = loc2.pack()
    outF.write(header.pack())

    outF.close()
