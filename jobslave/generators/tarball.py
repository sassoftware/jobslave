#
# Copyright (c) SAS Institute Inc.
#

# python standard library imports
import logging
import os

# jobslave imports
from jobslave.generators import bootable_image, constants
from jobslave.util import logCall

from conary.lib import util
from jobslave import buildtypes

log = logging.getLogger(__name__)


class Tarball(bootable_image.BootableImage):
    fileType = buildtypes.typeNames[buildtypes.TARBALL]

    def write(self):
        self.swapSize = self.getBuildData("swapSize") * 1048576
        basePath = os.path.join(self.workDir, self.basefilename)
        util.mkdirChain(basePath)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        tarball = os.path.join(outputDir, self.basefilename + '.tar.gz')
        self.installFileTree(basePath, no_mbr=True)

        sizes = os.statvfs(basePath)
        installedSize = (sizes.f_blocks - sizes.f_bavail) * sizes.f_frsize
        log.info("Installed size: %.1f MB", installedSize / 1e6)

        self.status('Creating tarball')
        logCall('tar -C %s -cpPsS --to-stdout ./ | gzip > %s' % \
                         (basePath, tarball))
        self.postOutput(((tarball, 'Tar File'),),
                attributes={'installed_size': installedSize})
