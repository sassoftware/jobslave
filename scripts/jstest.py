# This script runs the jobslave code as if your development system was the
# jobslave.  Tweak the jobData to change options like which group to build,
# image type, etc.

# The final image will be deposited in constants.tmpDir/UUID/

# the jobslave and mcp code must be in your PYTHONPATH

import jobslave.slave

import jobslave.jobhandler


#First get the jobdata
from jobslave import buildtypes

from jobslave.generators import constants

import os
import sys
import conary.lib.util

constants.tmpDir = os.path.join(os.environ.get('HOME', '/') , 'tmp')
if not os.path.isdir(constants.tmpDir):
    conary.lib.util.mkdirChain(constants.tmpDir)

jobData = {
    "buildType": buildtypes.RAW_HD_IMAGE,
    "protocolVersion": 1,
    "data": {
        "jsversion": "3.1.3",
        "baseFileName": "",
        "media-template": ""
    },
    "description": "this is a test",
    "outputToken": "580466f08ddfcfa130ee85f2d48c61ced992d4d4",
    "troveVersion": "/ubuntu.rb.rpath.com@rpath:ubuntu-hardy-devel/0.000:hardy.200809031428-1-1", #this has to be a full version (frozen with timestamp) for now
    "UUID": "omnomnomnom",
    "project": {
        "conaryCfg": "",
        "hostname": "test",
        "name": "Test Ubuntu Linux",
        "label": "test.rpath.local@rpl:devel"
    },
    "troveFlavor": '1#x86_64|5#use:~!vmware:~!xen',
    "troveName": "group-ubuntu-packages",
    "outputUrl": "http://nowhere:31337/",
    "type": "build",
    "name": "Test Ubuntu Linux"
}

#Stubs for the parent
class Response(object):
    pass

class JobSlave(object):
    def __init__(self):
        self.response = Response()
        self.cfg = jobslave.slave.SlaveConfig()

import epdb

#Create the image generator object
generator = jobslave.jobhandler.getHandler(jobData, JobSlave())

try:
    generator.write()
except:
    epdb.post_mortem(sys.exc_info()[2])
