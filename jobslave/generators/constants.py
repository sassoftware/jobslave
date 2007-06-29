#
# Copyright (c) 2004-2007 rPath, Inc.
#
# All Rights Reserved
#

#Different cylinder sizes.  I don't know which is better, but I've seen
#both: 8225280 or 516096
cylindersize    = 516096
sectors         = 63
heads           = 16

sectorSize = 512 # in bytes

scsiSectors = 32
scsiHeads = 128

partitionOffset = 65536

import os

# path for temporary finished images
finishedDir = os.path.join(os.path.sep, 'srv', 'jobslave', 'tmp', 'finished-images')

# directory containing file tree with fstab and other hooks
skelDir         = os.path.join(os.path.sep, 'srv', 'jobslave', 'skel')

# where to look for tools needed to boot a live ISO.
fallbackDir     = os.path.join(os.path.sep, 'srv', 'jobslave', 'fallback')

# directory to get direct image templates from, eg vmx files
templateDir = os.path.join(os.path.sep, 'srv', 'jobslave', 'templates')

# temporary directory
tmpDir = os.path.join(os.path.sep, 'srv', 'jobslave', 'tmp')

scriptPath = os.path.join(os.path.sep, 'usr', 'share', 'jobslave', 'scripts')
cachePath = os.path.join(os.path.sep, 'srv', 'jobslave', 'tmp', 'changesets')
implantIsoMd5 = os.path.join(os.path.sep, 'usr', 'bin', 'implantisomd5')
anacondaImagesPath = os.path.join(os.path.sep, 'srv', 'jobslave', 'pixmaps')
anacondaTemplatesPath = os.path.join(os.path.sep, 'srv', 'jobslave', 'tmp', 'anaconda-templates')
templatesLabel = 'conary.rpath.com@rpl:1'
entDir =  os.path.join(os.path.sep, 'srv', 'jobslave', 'entitlements')
