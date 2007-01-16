#
# Copyright (c) 2004-2007 rPath, Inc.
#
# All Rights Reserved
#

# python standard library imports
import os

# jobslave imports
from jobslave.generators import bootable_image

from conary.lib import util
from jobslave import buildtypes


class Tarball(bootable_image.BootableImage):
    fileType = buildtypes.typeNames[buildtypes.TARBALL]

    def write(self):
        basePath = os.path.join(os.path.sep, 'tmp', self.basefilename)
        if os.path.exists(basePath):
            util.rmtree(basePath)
        util.mkdirChain(basePath)
        tarball = basePath + '.tgz'
        cwd = os.getcwd()
        try:
            self.installFileTree(basePath)
            os.chdir(basePath)
            util.execute('tar -C %s -cpPs --to-stdout ./ | gzip -9 > %s' % \
                             (basePath, tarball))
            # FIXME: deliver tarball
        finally:
            util.rmtree(basePath, ignore_errors = True)
            try:
                os.chdir(cwd)
            except:
                # block all errors so that real ones can get through
                pass

    def __init__(self, *args, **kwargs):
        bootable_image.BootableImage.__init__(self, *args, **kwargs)
        self.swapSize = self.getBuildData("swapSize") * 1048576
