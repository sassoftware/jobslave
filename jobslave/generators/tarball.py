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
        if os.path.exists(basePath):
            util.rmtree(basePath)
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
            util.rmtree(topDir, ignore_errors = True)
            try:
                os.chdir(cwd)
            except:
                # block all errors so that real ones can get through
                pass
