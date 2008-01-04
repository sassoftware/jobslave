#
# Copyright (c) 2004-2007 rPath, Inc.
#
# All Rights Reserved
#

# python standard library imports
import os

# jobslave imports
from jobslave.generators import bootable_image, constants
from jobslave.imagegen import logCall

from conary.lib import util
from jobslave import buildtypes


class Tarball(bootable_image.BootableImage):
    fileType = buildtypes.typeNames[buildtypes.TARBALL]

    def write(self):
        self.swapSize = self.getBuildData("swapSize") * 1048576
        topDir = os.path.join(constants.tmpDir, self.jobId)
        basePath = os.path.join(topDir, self.basefilename)
        util.mkdirChain(basePath)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        tarball = os.path.join(outputDir, self.basefilename + '.tgz')
        cwd = os.getcwd()
        try:
            self.installFileTree(basePath)
            os.chdir(basePath)
            logCall('tar -C %s -cpPs --to-stdout ./ | gzip > %s' % \
                             (basePath, tarball))
            self.postOutput(((tarball, 'Tar File'),))
        finally:
            try:
                os.chdir(cwd)
            except:
                # block all errors so that real ones can get through
                pass

    def setupGrub(self, fakeRoot):
        bootable_image.BootableImage.setupGrub(self, fakeRoot)
        # grubby will die if there's no / partition
        f = open(os.path.join(fakeRoot, 'boot', 'grub', 'grub.conf'), 'a')
        f.write('LABEL=/ / ext3 defaults 1 1\n')
        f.close()
