#
# Copyright (c) 2005-2007 rPath, Inc.
#
# All Rights Reserved
#
import os
from jobslave.imagegen import ImageGenerator
from jobslave.generators import installable_iso

from conary.lib import util

class UpdateIso(installable_iso.InstallableIso):
    # subclass of installable ISO that ships with only changesets.
    # all anaconda related functionality has been stripped.
    def __init__(self, *args, **kwargs):
        # skip the InstallableISO init. it tries to access 'showMediaCheck'
        # from build Data, which isn't there.
        ImageGenerator.__init__(self, *args, **kwargs)
        self.showMediaCheck = False
        self.maxIsoSize = 0

    def prepareTemplates(self, topdir):
        util.mkdirChain(os.path.join(topdir, self.productDir, 'base'))
        csdir = os.path.join(topdir, self.productDir, 'changesets')
        util.mkdirChain(csdir)
        return csdir

    def setupKickStart(self, *args, **kwargs):
        pass

    def writeProductImage(self, *args, **kwargs):
        pass
