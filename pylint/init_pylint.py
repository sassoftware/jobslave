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
import sys

# set default JOBSLAVE_PATH, if it was not set.
parDir = '/'.join(os.path.realpath(__file__).split('/')[:-2])
parDir = os.path.dirname(parDir)
jobslavePath = os.getenv('JOBSLAVE_PATH', parDir)
os.environ['JOBSLAVE_PATH'] = jobslavePath

def setPathFromEnv(variable, directory):
    parDir = '/'.join(os.path.realpath(__file__).split('/')[:-3])
    parDir = os.path.dirname(parDir) + '/' + directory
    thisPath = os.getenv(variable, parDir)
    os.environ[variable] = thisPath
    if thisPath not in sys.path:
        sys.path.insert(0, thisPath)
    return thisPath

# set default CONARY_PATH, if it was not set.
conaryPath = setPathFromEnv('CONARY_PATH', 'conary')

# set default MCP_PATH, if it was not set.
mcpPath = setPathFromEnv('MCP_PATH', 'mcp')

# paths end up in the opposite order than they are listed.
for path in mcpPath, conaryPath, jobslavePath:
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
