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

scsiSectors = 32
scsiHeads = 128

partitionOffset = 512

import os

finishedDir          = os.path.join(os.path.sep, 'srv', 'jobslave',
                                    'finished-images')

#directory containing file tree with fstab and other hooks
skelDir         = os.path.join(os.path.sep, 'srv', 'jobslave', 'skel')

# where to look for tools needed to boot a live ISO.
fallbackDir     = os.path.join(os.path.sep, 'srv', 'jobslave', 'fallback')

# directory to get direct image templates from, eg vmx files
templateDir = os.path.join(os.path.sep, 'srv', 'jobslave', 'templates')

# temporary directory
tmpDir = os.path.join(os.path.sep, 'srv', 'jobslave', 'tmp')

scriptPath            = '/usr/share/jobslave/scripts/'
cachePath             = '/srv/jobslave/changesets/'
implantIsoMd5         = '/usr/bin/implantisomd5'
anacondaImagesPath    = '/srv/jobslave/pixmaps'
anacondaTemplatesPath = '/srv/jobslave/anaconda_templates'
templatesLabel        = 'conary.rpath.com@rpl:1'
