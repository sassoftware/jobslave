#
# Copyright (c) SAS Institute Inc.
#

import gzip
import os

from jobslave.generators import constants
from jobslave.generators import raw_hd_image, bootable_image
from jobslave.util import logCall

from conary.deps import deps
from conary.lib import util


class XenOVA(raw_hd_image.RawHdImage):
    templateName = 'ova.xml.in'
    suffix = '.xva'

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

        if self.baseFlavor.satisfies(deps.parseFlavor('!xen')) and \
           self.baseFlavor.satisfies(deps.parseFlavor('!domU')):
            hvm = True
        else:
            hvm = False

        template = template.replace('@HVM@', str(hvm).lower())

        vbdLines = '<vbd device="xvda" function="root" mode="w" ' \
            'vdi="vdi_xvda" />'
        vdiLines = '<vdi name="vdi_xvda" size="%d" ' \
            'source="file://xvda" type="dir-gzipped-chunks" ' \
            'variety="system" />' % size
 
        template = template.replace('@VDB_ENTRIES@', vbdLines)
        template = template.replace('@VDI_ENTRIES@', vdiLines)
        # write the file to the proper location
        ofile = file(outfile, 'wb')
        ofile.write(template)
        ofile.close()

    def write(self):
        # Output setup
        topDir = os.path.join(self.workDir, 'ova_base')
        util.mkdirChain(topDir)

        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        deliverable = os.path.join(outputDir, self.basefilename + self.suffix)

        # Build the filesystem images
        #totalSize, sizes = self.getImageSize(realign = 0, offset = 0)
        image_path = os.path.join(self.workDir, 'hdimage')
        disk = self.makeHDImage(image_path)

        # Open a manifest for tar so that it writes out files in the optimal
        # order.
        manifest_path = os.path.join(self.workDir, 'files')
        manifest = open(manifest_path, 'w')

        # Write the ova.xml file
        ovaName = 'ova.xml'
        ovaPath = os.path.join(topDir, ovaName)
        self.createXVA(ovaPath, disk.totalSize)
        print >>manifest, ovaName

        # Split the HD image into 1GB (not GiB) chunks
        label = 'xvda'
        chunk_dir = os.path.join(topDir, label)
        chunkPrefix = os.path.join(chunk_dir, 'chunk-')
        util.mkdirChain(os.path.split(chunkPrefix)[0])

        self.status('Splitting hard disk image')
        infile = open(image_path, 'rb')
        n = 0
        tocopy = os.stat(image_path).st_size
        while True:
            chunkname = '%s%04d.gz' % (chunkPrefix, n)
            outfile = gzip.GzipFile(chunkname, 'wb')
            tocopy -= util.copyfileobj(infile, outfile, sizeLimit=1000000000)
            outfile.close()
            print >>manifest, chunkname
            if not tocopy:
                break
            n += 1
        infile.close()

        # Delete the FS image to free up temp space
        os.unlink(image_path)

        # Create XVA file
        manifest.close()
        self.status('Creating XVA Image')
        logCall('tar -cv -f "%s" -C "%s" -T "%s"' % \
                         (deliverable, topDir, manifest_path))
        self.outputFileList.append((deliverable, 'Citrix XenServer (TM) Image'),)

        self.postOutput(self.outputFileList)            
