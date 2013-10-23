#
# Copyright (c) SAS Institute Inc.
#

import logging
import os
import random
import struct
import time

from jobslave.generators import bootable_image

log = logging.getLogger(__name__)

UUID_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
LABEL_SIZE = 512
LABEL_ID = "LABELONE"
FMTT_MAGIC = "\040\114\126\115\062\040\170\133\065\101\045\162\060\116\052\076"
FMTT_VERS = 1
MDA_HEADER_SIZE = 512
LVM2_LABEL = "LVM2 001"


class LVMContainer(object):
    volGroupName = "vg00"

    # number of bytes in an extent
    extent_size = 1048576
    # byte offset where label begins
    loc_label = 512
    # byte offset where metadata begins
    loc_mda = 4096
    # byte offset where data begins
    loc_data = 1048576

    def __init__(self, totalSize, image, offset=0):
        self.totalSize = totalSize
        self.image = image
        self.offset = offset

        self.names = set()
        self.filesystems = []
        self.lvs = []
        self.current_pe = 0
        self.pe_count = (totalSize - self.loc_data) // self.extent_size
        self.pvid = lvm_uuid()
        if not os.path.exists(image):
            open(image, 'w').close()

    def lvname(self, mountPoint, fsType):
        base = str(mountPoint).replace('/', '')
        if not base:
            if fsType == 'swap':
                base = 'swap'
            else:
                base = 'root'
        name = base
        n = 2
        while name in self.names:
            name = '%s%d' % (base, n)
            n += 1
        self.names.add(name)
        return name

    def addFilesystem(self, mountPoint, fsType, size):
        name = self.lvname(mountPoint, fsType)
        pe_count = (size + self.extent_size - 1) // self.extent_size
        size = pe_count * self.extent_size
        # Allocate extents for this volume
        pe_offset = self.current_pe
        self.current_pe += pe_count
        if self.current_pe > self.pe_count:
            raise LVMOverflowError("overflow while allocating logical volume")
        self.lvs.append("""\
%(lvname)s {
id = "%(lvid)s"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_host = "localhost.localdomain"
creation_time = %(now)s
segment_count = 1

segment1 {
start_extent = 0
extent_count = %(pe_count)s

type = "striped"
stripe_count = 1\t# linear

stripes = [
"pv0", %(pe_offset)s
]
}
}
""" % dict(
            lvname=name,
            lvid=lvm_uuid(),
            now=int(time.time()),
            pe_count=pe_count,
            pe_offset=pe_offset,
            ))

        offset = self.offset + self.loc_data + self.extent_size * pe_offset
        log.info("Adding LVM volume %r at offset %d size %d", name, offset, size)
        fs = bootable_image.Filesystem(self.image, fsType, size=size,
                offset=offset, fsLabel=mountPoint)
        self.filesystems.append(fs)
        return fs

    def unmount(self):
        for fs in self.filesystems:
            fs.umount()
        self.writeHeader()

    def writeHeader(self):
        mda = self.getMetadata()
        with open(self.image, 'r+') as f:
            self._writeLabel(f)
            self._writeMeta(f, mda)

    def _writeLabel(self, f):
        sector = 1
        pvheader = struct.pack('<32s9Q',
                self.pvid.replace('-', ''),
                self.totalSize,
                # Data areas
                self.loc_data,  # offset
                0,              # size
                0, 0,           # end of list
                # Metadata areas
                self.loc_mda,   # offset
                self.loc_data - self.loc_mda, # size
                0, 0,           # end of list
                )
        label1_fmt = '<8sQI'
        label2 = struct.pack('<I8s',
                32, # offset from start of label to start of pvheader
                LVM2_LABEL,     # type
                )
        label2 += pvheader
        label2 += '\0' * (LABEL_SIZE - len(label2)
                - struct.calcsize(label1_fmt))
        crc = lvm_crc(label2)
        label = struct.pack(label1_fmt,
                LABEL_ID,       # magic
                sector,         # sector where this label is written to
                crc,            # crc of the whole remainder of sector
                ) + label2
        assert len(label) == LABEL_SIZE
        f.seek(self.offset + 512 * sector)
        f.write(label)

    def _writeMeta(self, f, mda):
        # Metadata header
        mda += '\0'
        mdah1_fmt = '<I'
        mdah2 = struct.pack('<16sIQQQQIIQQII',
            FMTT_MAGIC,         # magic
            1,                  # version
            self.loc_mda,       # offset of this header
            self.loc_data - self.loc_mda, # size of this header
            # Metadata slots
            MDA_HEADER_SIZE,    # offset from loc_mda to metadata
            len(mda),           # size of metadata
            lvm_crc(mda),       # checksum of metadata
            0,                  # flags
            0, 0, 0, 0,         # end of list
            )
        mdah2 += '\0' * (MDA_HEADER_SIZE - len(mdah2)
                - struct.calcsize(mdah1_fmt))
        mdah = struct.pack(mdah1_fmt, lvm_crc(mdah2)) + mdah2
        assert len(mdah) == MDA_HEADER_SIZE
        f.seek(self.offset + self.loc_mda)
        f.write(mdah)
        f.write(mda)

    def getMetadata(self):
        return """\
%(vgname)s {
id = "%(vgid)s"
seqno = 1
format = "lvm2" # informational
status = ["RESIZEABLE", "READ", "WRITE"]
flags = []
extent_size = %(extent_size)s
max_lv = 0
max_pv = 0
metadata_copies = 0

physical_volumes {

pv0 {
id = "%(pvid)s"
device = "/dev/sda2"

status = ["ALLOCATABLE"]
flags = []
dev_size = %(dev_size)s
pe_start = %(pe_start)s
pe_count = %(pe_count)s
}
}

logical_volumes {

%(lvs)s

}
}
contents = "Text Format Volume Group"
version = 1
description = ""
creation_host = "localhost.localdomain"
creation_time = %(now)s
# Created by SAS App Engine
""" % dict(
                vgname=self.volGroupName,
                vgid=lvm_uuid(),
                extent_size=self.extent_size / 512,
                pvid=self.pvid,
                dev_size=self.totalSize,
                pe_start=self.loc_data / 512,
                pe_count=self.pe_count,
                lvs='\n'.join(self.lvs),
                now=int(time.time()),
                )


def lvm_uuid():
    return '-'.join(
                (''.join(random.choice(UUID_CHARS) for x in range(n))
            for n in [6, 4, 4, 4, 4, 4, 6]))


def lvm_crc(stuff):
    tab = [
            0x00000000, 0x1db71064, 0x3b6e20c8, 0x26d930ac,
            0x76dc4190, 0x6b6b51f4, 0x4db26158, 0x5005713c,
            0xedb88320, 0xf00f9344, 0xd6d6a3e8, 0xcb61b38c,
            0x9b64c2b0, 0x86d3d2d4, 0xa00ae278, 0xbdbdf21c,
            ]
    val = 0xf597a6cf
    for x in stuff:
        val ^= ord(x)
        val = (val >> 4) ^ tab[val & 0xf]
        val = (val >> 4) ^ tab[val & 0xf]
    return val


class LVMOverflowError(RuntimeError):
    pass
