#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

# python standard library imports
import os

# jobslave imports
from jobslave.generators import bootable_image

# conary imports
from conary.lib import util

class NetbootImage(bootable_image.BootableImage):
    def write(self):
        basePath = os.path.join(os.path.sep, 'tmp', self.basefilename)
        if os.path.exists(basePath):
            util.rmtree(basePath)
        util.mkdirChain(basePath)
        cpioImage = basePath + '.cpio'
        cwd = os.getcwd()
        try:
            self.installFileTree(basePath)
            os.chdir(basePath)
            util.execute('cpio -o | gzip -9 > %s' % cpioImage)
            kernel = self.findFile(os.path.join(self.fakeroot, 'boot'),
                                   'vmlinuz.*')
            # FIXME: deliver cpio and kernel
        finally:
            util.rmtree(basePath, ignore_errors = True)
            try:
                os.chdir(cwd)
            except:
                # block all errors so that real ones can get through
                pass

    def __init__(self, *args, **kwargs):
        bootable_image.BootableImage.__init__(self, *args, **kwargs)
        self.swapSize = 0
