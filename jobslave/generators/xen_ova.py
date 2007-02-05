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
    suffix = '.xva.tar'

    @bootable_image.timeMe
    def createXVA(self, outfile, size):
        # Read in the stub file
        infile = file(os.path.join(constants.templateDir, self.templateName),
                      'rb')

        # Replace the @DELIMITED@ text with the appropriate values
        template = infile.read()
        infile.close()

        template = template.replace('@TITLE@', self.jobData['project']['name'])
        template = template.replace('@DESCRIPTION@',
            'Created by rPath rBuilder')
        template = template.replace('@MEMORY@', str(self.getBuildData('vmMemory') * 1024 * 1024))
        template = template.replace('@DISKSIZE@', str(size))

        # write the file to the proper location
        ofile = file(outfile, 'wb')
        ofile.write(template)
        ofile.close()

    def write(self):
        topDir = os.path.join(os.path.sep, 'tmp', self.jobId)
        baseDir = os.path.join(topDir, self.basefilename)
        util.rmtree(baseDir, ignore_errors = True)
        util.mkdirChain(baseDir)
        ovaPath = os.path.join(baseDir, 'ova.xml')
        chunkPrefix = os.path.join(baseDir, 'sda', 'chunk-')
        os.mkdir(os.path.split(chunkPrefix)[0])
        imagePath = baseDir + '.ext3'
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        deliverable = os.path.join(outputDir, self.basefilename + self.suffix)
        try:
            size = self.getImageSize()
            self.makeFSImage(imagePath, size)

            self.createXVA(ovaPath, size)
            util.execute('split -b 1000000000 -a 8 -d %s "%s"' % \
                             (imagePath, chunkPrefix))
            util.execute('for a in "%s*"; do gzip $a; done' % chunkPrefix)
            tarBase, tarTarget = os.path.split(baseDir)
            util.execute('tar -cv -C %s %s > %s' % \
                             (tarBase, tarTarget, deliverable))
            self.postOutput(((deliverable, 'Xen OVA'),))
        finally:
            util.rmtree(topDir, ignore_errors = True)
