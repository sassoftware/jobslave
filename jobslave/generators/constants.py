#
# Copyright (c) 2004-2008 rPath, Inc.
#
# All Rights Reserved
#

import os

## Disk geometry
sectorSize          = 512 # bytes per block ("sector")
sectors             = 63  # sectors per disk
heads               = 16  # heads per disk

bytesPerCylinder    = sectors * sectorSize * heads
partitionOffset     = 128 * sectorSize # offset of first partition (bytes)


# path for temporary finished images
finishedDir = os.path.join(os.path.sep, 'tmp', 'finished-images')

# directory containing file tree with fstab and other hooks
skelDir         = os.path.join(os.path.sep, 'srv', 'jobslave', 'skel')

# where to look for tools needed to boot a live ISO.
fallbackDir     = os.path.join(os.path.sep, 'srv', 'jobslave', 'fallback')

# directory to get direct image templates from, eg vmx files
templateDir = os.path.join(os.path.sep, 'srv', 'jobslave', 'templates')

# temporary directory
tmpDir = os.path.join(os.path.sep, 'tmp')

scriptPath = os.path.join(os.path.sep, 'usr', 'share', 'jobslave', 'scripts')
cachePath = os.path.join(os.path.sep, 'tmp', 'changesets')
implantIsoMd5 = os.path.join(os.path.sep, 'usr', 'bin', 'implantisomd5')
anacondaImagesPath = os.path.join(os.path.sep, 'srv', 'jobslave', 'pixmaps')
anacondaTemplatesPath = os.path.join(os.path.sep, 'tmp', 'anaconda-templates')
templatesLabel = 'conary.rpath.com@rpl:1'
entDir =  os.path.join(os.path.sep, 'srv', 'jobslave', 'entitlements')
