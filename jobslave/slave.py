#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved.
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
