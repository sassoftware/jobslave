#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import os
import tempfile

from jobslave.generators import raw_hd_image, constants

from conary.lib import util

class RawFsImage(raw_hd_image.RawHdImage):
    def getImageSize(self):
        return raw_hd_image.RawHdImage.getImageSize(self) - \
            constants.partitionOffset

    def makeFSImage(self, image, size = None):
        if not size:
            size = self.getImageSize()
        mountPoint = tempfile.mkdtemp()
        try:
            self.makeBlankFS(image, size)
            util.execute('sudo mount -o loop %s %s' % (image, mountPoint))
            self.installFileTree(mountPoint)
            util.execute('sudo umount %s' % mountPoint)
        finally:
            util.rmtree(mountPoint, ignore_errors = True)

    def write(self):
        size = self.getImageSize()
        image = os.path.join(os.path.sep, 'tmp', self.basefilename + '.ext3')
        try:
            self.makeFSImage(image, size)
            outFile = self.gzip(image)
            import epdb
            epdb.st()
            # FIXME: deliver the final image somewhere
        finally:
            util.rmtree(image, ignore_errors = True)
