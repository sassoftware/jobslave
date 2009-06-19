#
# Copyright (c) 2004-2009 rPath, Inc.
#
# All Rights Reserved
#
import os
import sys

from conary.lib import util

## Disk geometry
sectorSize          = 512 # bytes per block ("sector")
sectors             = 32  # sectors per disk
heads               = 64  # heads per disk

VHDsectors          = 63  # sectors per disk for VHD
VHDheads            = 16  # heads per disk for VHD

bytesPerCylinder    = sectors * sectorSize * heads  # DEPRECATED
partitionOffset     = 128 * sectorSize # offset of first partition (bytes)


# path for temporary finished images
finishedDir = util.joinPaths(os.path.sep, 'tmp', 'finished-images')

# directory containing file tree with fstab and other hooks
skelDir         = util.joinPaths(os.path.sep, 'srv', 'jobslave', 'skel')

# where to look for tools needed to boot a live ISO.
fallbackDir     = util.joinPaths(os.path.sep, 'srv', 'jobslave', 'fallback')

# directory to get direct image templates from, eg vmx files
templateDir = util.joinPaths(os.path.sep, 'srv', 'jobslave', 'templates')

# temporary directory
tmpDir = util.joinPaths(os.path.sep, 'tmp')

scriptPath = util.joinPaths(os.path.sep, 'usr', 'share', 'jobslave', 'scripts')
cachePath = util.joinPaths(os.path.sep, 'tmp', 'changesets')
implantIsoMd5 = util.joinPaths(os.path.sep, 'usr', 'bin', 'implantisomd5')
anacondaImagesPath = util.joinPaths(os.path.sep, 'srv', 'jobslave', 'pixmaps')
anacondaTemplatesPath = util.joinPaths(os.path.sep, 'tmp', 'anaconda-templates')
templatesLabel = 'conary.rpath.com@rpl:1'
entDir =  util.joinPaths(os.path.sep, 'srv', 'jobslave', 'entitlements')

pinKernelRE = '(kernel|linux-image-2\.6\.[0-9]+-[0-9]+(-[a-z]+)?)([:-].*|$)'

# ovf related constants
OVF_EXTENSION = 'ovf'
OVA_EXTENSION = 'ova'
MF_EXTENSION = 'mf'

DISKFORMATS = {
    'VMDK'      : 1,
    'VHD'       : 2,
    'RAWFS'     : 3,
    'RAWHD'     : 4,
}

sys.modules[__name__].__dict__.update(DISKFORMATS)

DISKFORMATURLS = {
    VMDK : 'http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized',
    RAWFS : 'http://wiki.rpath.com/wiki/rBuilder_Online:Raw_Filesystem_Image',
    RAWHD : 'http://wiki.rpath.com/wiki/rBuilder_Online:Raw_Hard_Disk_Image',
    VHD  : 'http://www.microsoft.com/technet/virtualserver/downloads/vhdspec.mspx'
}

NETWORKSECTIONINFO = 'List of logical networks used in the package'
DISKSECTIONINFO = 'Describes the set of virtual disks'
VIRTUALHARDWARESECTIONINFO = 'Describes the set of virtual hardware'
FILECOMPRESSION = 'gzip'
OVFIMAGETAG = 'OVF 1.0 Image'
