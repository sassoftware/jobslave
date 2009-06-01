#
# Copyright (c) 2006 rPath, Inc.
#
# All Rights Reserved
#

import os

from jobslave.imagegen import logCall
from jobslave.generators import constants
from jobslave.generators import raw_hd_image, bootable_image

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
        #totalSize, sizes = self.getImageSize(realign = 0, partitionOffset = 0)
        image_path = os.path.join(self.workDir, 'hdimage')
        size = self.makeHDImage(image_path)

        # Open a manifest for tar so that it writes out files in the optimal
        # order.
        manifest_path = os.path.join(self.workDir, 'files')
        manifest = open(manifest_path, 'w')

        # Write the ova.xml file
        ovaName = 'ova.xml'
        ovaPath = os.path.join(topDir, ovaName)
        self.createXVA(ovaPath, size)
        print >>manifest, ovaName

        # Split the HD image into 1GB (not GiB) chunks
        label = 'xvda'
        chunk_dir = os.path.join(topDir, label)
        chunkPrefix = os.path.join(chunk_dir, 'chunk-')
        util.mkdirChain(os.path.split(chunkPrefix)[0])

        self.status('Splitting hard disk image')
        logCall('split -b 1000000000 -a 9 -d %s "%s"' % \
            (image_path, chunkPrefix))

        # Delete the FS image to free up temp space
        os.unlink(image_path)

        # Compress the chunks and add them to the manifest
        self.status('Compressing image chunks')
        for chunk_name in sorted(os.listdir(chunk_dir)):
            logCall('gzip "%s"' % os.path.join(chunk_dir, chunk_name))
            print >>manifest, os.path.join(label, chunk_name) + '.gz'

        # Create XVA file
        manifest.close()
        self.status('Creating XVA Image')
        logCall('tar -cv -f "%s" -C "%s" -T "%s"' % \
                         (deliverable, topDir, manifest_path))
        self.outputFileList.append((deliverable, 'Citrix XenServer (TM) Image'),)

        self.postOutput(self.outputFileList)            
