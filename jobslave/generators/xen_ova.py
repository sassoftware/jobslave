#
# Copyright (c) 2006 rPath, Inc.
#
# All Rights Reserved
#

import os
import tempfile
import stat
import zipfile

from jobslave import buildtypes
from jobslave.generators import constants
from jobslave.generators import raw_fs_image, bootable_image

from conary.lib import util, log

class XenOVA(raw_fs_image.RawFsImage):
    templateName = 'ova.xml.in'
    suffix = '.xva.zip'

    @bootable_image.timeMe
    def createXVA(self, outfile, size):
        # Read in the stub file
        infile = file(os.path.join(constants.templateDir, self.templateName),
                      'rb')

        # Replace the @DELIMITED@ text with the appropriate values
        template = infile.read()
        infile.close()

        template = template.replace('@TITLE@', self.jobData['name'])
        template = template.replace('@DESCRIPTION@',
            'Created by rPath rBuilder')
        template = template.replace('@MEMORY@', str(self.getBuildData('vmMemory') * 1024 * 1024))
        template = template.replace('@DISKSIZE@', str(size))

        # write the file to the proper location
        ofile = file(outfile, 'wb')
        ofile.write(template)
        ofile.close()

    def write(self):
        baseDir = os.path.join(os.path.sep, 'tmp', self.basefilename)
        util.rmtree(baseDir, ignore_errors = True)
        os.mkdir(baseDir)
        ovaPath = os.path.join(baseDir, 'ova.xml')
        chunkPrefix = os.path.join(baseDir, 'sda', 'chunk-')
        os.mkdir(os.path.split(chunkPrefix)[0])
        imagePath = baseDir + '.ext3'
        deliverable = baseDir + self.suffix
        try:
            size = self.getImageSize()
            self.makeFSImage(imagePath, size)

            self.createXVA(ovaPath, size)
            util.execute('split -b 1000000000 -a 8 -d %s "%s"' % \
                             (imagePath, chunkPrefix))
            util.execute('for a in "%s*"; do gzip $a; done' % chunkPrefix)
            self.zip(baseDir, deliverable, extraArgs = '0')
            # FIXME: deliver final image
            import epdb
            epdb.st()
        finally:
            util.rmtree(baseDir, ignore_errors = True)
            util.rmtree(imagePath, ignore_errors = True)
