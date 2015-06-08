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


import jobslave_helper
from jobslave.generators import bootable_image

class UpdateCallbackTest(jobslave_helper.JobSlaveHelper):
    def setUp(self):
        def MockUpdate(msg):
            self.msgs.append(msg)
        self.callback = bootable_image.InstallCallback(None)
        self.msgs = []
        self.callback.update = MockUpdate
        jobslave_helper.JobSlaveHelper.setUp(self)

    def tearDown(self):
        jobslave_helper.JobSlaveHelper.tearDown(self)

    def testRestoreFiles(self):
        self.callback.restoreFiles(1, 100)
        self.failIf(self.msgs != ['Writing files'],
                "callback failed restoreFiles")

    def testRequestingChangeSet(self):
        self.callback.requestingChangeSet()
        self.failIf(self.msgs != ['Requesting changeset'],
                "callback failed requestingChangeSet")

    def testDownloadingChangeSet(self):
        self.callback.downloadingChangeSet(1, 100)
        self.failIf(self.msgs != ['Downloading changeset'],
                "callback failed downloadingChangeSet")

    def testRequestingFileContents(self):
        self.callback.requestingFileContents()
        self.failIf(self.msgs != ['Requesting file contents'],
                "callback failed requestingFileContents")

    def testDownloadingFileContents(self):
        self.callback.downloadingFileContents(1, 100)
        self.failIf(self.msgs != ['Downloading files'],
                "callback failed downloadingFileContents")

    def testPreparingChangeSet(self):
        self.callback.preparingChangeSet()
        self.failIf(self.msgs != ['Preparing changeset'],
                "callback failed preparingChangeSet")

    def testResolvingDependencies(self):
        self.callback.resolvingDependencies()
        self.failIf(self.msgs != ['Resolving dependencies'],
                "callback failed resolvingDependencies")

    def testCreatingRollback(self):
        self.callback.creatingRollback()
        self.failIf(self.msgs != ['Creating rollback'],
                "callback failed creatingRollback")

    def testCreatingDatabaseTransaction(self):
        self.callback.creatingDatabaseTransaction(1, 100)
        self.failIf(self.msgs != ['Creating database transaction'],
                "callback failed creatingDatabaseTransaction")

    def testCommittingTransaction(self):
        self.callback.committingTransaction()
        self.failIf(self.msgs != ['Committing transaction'],
                "callback failed committingTransaction")

    def testSetUpdateHunk(self):
        self.callback.setUpdateHunk(1, 100)
        self.failIf(self.callback.updateHunk != (1, 100),
                "callback failed setUpdateHunk")

    def testUpdate(self):
        def status(msg):
            self.msgs.append(msg)
        callback = bootable_image.InstallCallback(status)
        callback.update('testing')
        self.failIf(self.msgs != ['testing'],
                "update did not propogate message")

    def testUpdateWithHunk(self):
        def status(msg):
            self.msgs.append(msg)
        callback = bootable_image.InstallCallback(status)
        callback.setUpdateHunk(1, 100)
        callback.update('testing')
        self.failIf(self.msgs == ['testing'],
                "update did not propogate update hunk message")
