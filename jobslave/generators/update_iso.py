#
# Copyright (c) 2010 rPath, Inc.
#
# All Rights Reserved
#
import os
from jobslave.generators import installable_iso

from conary.lib import util

class UpdateIso(installable_iso.InstallableIso):
    # subclass of installable ISO that ships with only changesets.
    # all anaconda related functionality has been stripped.
    def __init__(self, *args, **kwargs):
        # skip the InstallableISO init. it tries to access 'showMediaCheck'
        # from build Data, which isn't there.
        self.__class__.__base__.__base__.__init__(self, *args, **kwargs)
        self.showMediaCheck = False
        self.maxIsoSize = 0

    def prepareTemplates(self, topdir, templateDir):
        util.mkdirChain(os.path.join(topdir, self.productDir, 'base'))
        csdir = os.path.join(topdir, self.productDir, 'changesets')
        util.mkdirChain(csdir)
        return csdir

    def setupKickstart(self, topdir):
        pass

    def writeProductImage(self, topdir, arch):
        pass

    def retrieveTemplates(self):
        return None, None
