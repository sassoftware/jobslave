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


BUILD_DEFAULTS = {
        'autoResolve': False,
        'maxIsoSize': '681574400',
        'bugsUrl': 'http://issues.rpath.com/',
        'natNetworking': False,
        'vhdDiskType': 'dynamic',
        'anacondaCustomTrove': '',
        'stringArg': '',
        'mediaTemplateTrove': '',
        'baseFileName': '',
        'vmSnapshots': False,
        'swapSize': 128,
        'betaNag': False,
        'anacondaTemplatesTrove': '',
        'enumArg': '2',
        'vmMemory': 256,
        'installLabelPath': '',
        'intArg': 0,
        'freespace': 250,
        'boolArg': False,
        'mirrorUrl': '',
        'zisofs': True,
        'diskAdapter': 'lsilogic',
        'unionfs': False,
        'showMediaCheck': False,
        'amiHugeDiskMountpoint': '',
        'platformName': '',
        'vmCPUs': 1,
        }


class JobData(dict):

    def getBuildData(self, key):
        value = self.get('data', {}).get(key)
        if value is None:
            value = BUILD_DEFAULTS.get(key)
        return value
