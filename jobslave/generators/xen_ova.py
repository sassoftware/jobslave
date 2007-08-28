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
from jobslave.imagegen import logCall
from jobslave.generators import constants
from jobslave.generators import raw_fs_image, bootable_image

from conary.lib import util, log

def ordToAscii(index):
    res = ''
    while index >= 0:
        modulus = index % 26
        res = chr(97 + modulus) + res
        index = (index - modulus) / 26 - 1
    return res

def sortMountPoints(mountDict):
    res = {}
    res['sda'] = '/boot' in mountDict and '/boot' or '/'
    index = 1
    for partition in sorted([x[0] for x in mountDict.iteritems() \
            if x[1][-1] == 'swap']):
        res['sd%s' % ordToAscii(index)] = partition
        index += 1
    for partition in sorted([x for x in mountDict if x not in res.values()]):
        res['sd%s' % ordToAscii(index)] = partition
        index += 1
    return res

class XenOVA(raw_fs_image.RawFsImage):
    templateName = 'ova.xml.in'
    suffix = '.xva.tar'

    @bootable_image.timeMe
    def createXVA(self, outfile, sizes):
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
        vbdLines = ''
        vdiLines = ''
        for label, mountPoint in self.mountLabels.iteritems():
            settings = {'label': label, 'diskSize': sizes[mountPoint]}
            vbdLine = '            <vbd device="%(label)s" function="root" ' \
                    'mode="w" vdi="vdi_%(label)s"/>\n'
            vbdLine %= settings
            vbdLines += vbdLine
            vdiLine = '    <vdi name="vdi_%(label)s" size="%(diskSize)d" '\
                    'source="file://%(label)s" type="dir-gzipped-chunks"/>\n'
            vdiLine %= settings
            vdiLines += vdiLine

        template = template.replace('@VDB_ENTRIES@', vbdLines[:-1])
        template = template.replace('@VDI_ENTRIES@', vdiLines[:-1])
        # write the file to the proper location
        ofile = file(outfile, 'wb')
        ofile.write(template)
        ofile.close()

    def write(self):
        topDir = os.path.join(constants.tmpDir, self.jobId)
        baseDir = os.path.join(topDir, self.basefilename)
        #util.rmtree(baseDir, ignore_errors = True)
        util.mkdirChain(baseDir)
        ovaPath = os.path.join(baseDir, 'ova.xml')
        imagePath = baseDir + '.ext3'
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        deliverable = os.path.join(outputDir, self.basefilename + self.suffix)

        # image building stage.
        totalSize, sizes = self.getImageSize(realign = 0, partitionOffset = 0)
        self.makeFSImage(sizes)

        self.mountLabels = sortMountPoints(self.mountDict)

        self.createXVA(ovaPath, sizes)
        for label, mntPoint in self.mountLabels.iteritems():
            fn = self.mntPointFileName(mntPoint)
            assert os.path.exists(fn), "Missing partition File: %s" % fn
            chunkPrefix = os.path.join(baseDir, label, 'chunk-')
            util.mkdirChain(os.path.split(chunkPrefix)[0])

            logCall('split -b 1000000000 -a 8 -d %s "%s"' % \
                             (fn, chunkPrefix))

            logCall('for a in "%s*"; do gzip $a; done' % chunkPrefix)
        tarBase, tarTarget = os.path.split(baseDir)
        logCall('tar -cv -C %s %s > %s' % \
                         (tarBase, tarTarget, deliverable))
