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
from jobslave import helperfuncs
from jobslave_test.jobslave_helper import JobSlaveHelper


class HelperFunctionsTest(JobSlaveHelper):

    def testGetMountedFiles(self):
        class mock_popen:
            def read(xself):
                return ' 1234 5678'
        class mock_os:
            def __init__(xself, listdir_hits, readlink_hits):
                xself.listdir_hits = listdir_hits
                xself.readlink_hits = readlink_hits
                xself.path = os.path
            def listdir(xself, path):
                xself.listdir_hits.add(path)
                if path == '/proc/1234/fd':
                    return ['1', '2']
                elif path == '/proc/5678/fd':
                    return ['3']
            def readlink(xself, path):
                xself.readlink_hits.add(path)
                return paths[path.split('/')[-1]]
            def popen(xself, path, mode):
                self.failUnlessEqual(path, 'fuser -m /mnt/null 2>/dev/null')
                self.failUnlessEqual(mode, 'r')
                return mock_popen()

        listdir_hits = set()
        listdir_want = set(['/proc/1234/fd', '/proc/5678/fd'])
        readlink_hits = set()
        readlink_want = set(['/proc/1234/fd/1', '/proc/1234/fd/2',
            '/proc/5678/fd/3'])
        paths = { '1': '/irrelevant', '2': '/mnt/null/foo',
            '3': '/mnt/null/bar'}

        _os = helperfuncs.os
        try:
            helperfuncs.os = mock_os(listdir_hits, readlink_hits)

            paths = helperfuncs.getMountedFiles('/mnt/null')
            self.failUnlessEqual(paths,
                set(['/mnt/null/foo', '/mnt/null/bar']))

            self.failUnlessEqual(listdir_hits, listdir_want)
            self.failUnlessEqual(readlink_hits, readlink_want)
        finally:
            helperfuncs.os = _os
