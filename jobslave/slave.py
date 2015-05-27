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


import logging
import json
import sys
from conary.lib.cfg import ConfigFile
from conary.lib.cfgtypes import CfgBool, CfgString, CfgPath

from jobslave import jobhandler
from jobslave.util import setupLogging


class SlaveConfig(ConfigFile):
    debugMode = (CfgBool, False)
    masterUrl = (CfgString, None)
    conaryProxy = (CfgString, None)
    jobDataPath = (CfgPath, '/tmp/jobData')
    templateCache = (CfgPath, '/mnt/anaconda-templates')
    binPath = (CfgPath, '/usr/bin')


def main(args):
    if len(args) > 1:
        sys.exit("Usage: %s [config]" % sys.argv[0])
    elif args:
        configPath = args.pop(0)
    else:
        configPath = '/srv/jobslave/config'

    setupLogging(logLevel=logging.DEBUG)

    cfg = SlaveConfig()
    cfg.read(configPath)

    jobData = json.load(open(cfg.jobDataPath))
    handler = jobhandler.getHandler(cfg, jobData)
    handler.run()
