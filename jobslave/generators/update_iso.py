#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
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
