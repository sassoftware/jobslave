#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

# python standard library imports
import os

# jobslave imports
from jobslave.generators import bootable_image, constants
from jobslave.util import logCall

# conary imports
from conary.lib import util

class NetbootImage(bootable_image.BootableImage):
    def write(self):
        basePath = os.path.join(self.workDir, self.basefilename)
        if os.path.exists(basePath):
            util.rmtree(basePath)
        util.mkdirChain(basePath)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        cpioImage = os.path.join(outputDir, self.basefilename + '.initrd')
        cwd = os.getcwd()
        try:
            self.installFileTree(basePath)
            os.chdir(basePath)
            logCall('find . -depth | cpio -o | gzip > %s' % cpioImage)
            kernel = self.findFile(os.path.join(basePath, 'boot'),
                                   'vmlinuz.*')
            outputKernel = os.path.join(outputDir, os.path.basename(kernel))
            util.copyfile(kernel, outputKernel)
            # FIXME: using a name such as vmlinuz-2.6.17.14-0.4.x86.i686.cmov
            # may not be the best convention
            self.postOutput(((cpioImage, 'initrd'),
                             (outputKernel, 'kernel')))
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
