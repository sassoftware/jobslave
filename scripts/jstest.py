#!/usr/bin/python
#
# This script runs the jobslave code as if your development system was the
# jobslave.  Tweak the jobData to change options like which group to build,
# image type, etc.

# The final image will be deposited in constants.tmpDir/UUID/

# the jobslave and mcp code must be in your PYTHONPATH

import os
import sys
import tempfile
from conary.lib import util

sys.execepthook = util.genExcepthook()

sys.path.insert(0, os.environ['HOME'] + '/hg/jobslave')
sys.path.insert(0, os.environ['HOME'] + '/hg/mcp')
sys.path.insert(0, os.environ['HOME'] + '/hg/boto')

os.environ['PATH'] = ':'.join(['../bin', os.environ['PATH']])

import jobslave.slave
import jobslave.jobhandler
from jobslave import buildtypes
from jobslave.generators import constants

# leave the resulting image writeable by the group.  This means that you can
# set g+s on tmpDir and be able to write the results without doing chown
# muckery
os.umask(0002)

constants.tmpDir = util.joinPaths(os.environ.get('HOME', '/') , 'tmp')
constants.skelDir = util.joinPaths(os.getcwd(), '../', 'skel')
constants.templateDir = util.joinPaths(os.getcwd(), '../', 'templates')

if not os.path.exists(constants.tmpDir):
    util.mkdirChain(constants.tmpDir)

jobData = {
    'buildType': buildtypes.VMWARE_IMAGE,
    'protocolVersion': 1,
    'data': {
        'jsversion': '3.1.3',
        'baseFileName': '',
        'media-template': '',
        'diskAdapter': 'lsilogic',
    },
    'description': 'this is a test',
    'outputToken': '580466f08ddfcfa130ee85f2d48c61ced992d4d4',
    # This has to be a full version (frozen with timestamp) for now
    # To be filled in by __main__
    'troveName': None,
    'troveVersion': None,
    'troveFlavor': None,
    'UUID': tempfile.mktemp(prefix='jobslave', dir=''),
    'project': {
        'conaryCfg': '',
        'hostname': 'flatpress-ubuntu',
        'name': 'Test Ubuntu Linux',
        'label': 'test.rpath.local@rpl:devel'
    },
    'outputUrl': 'http://nowhere:31337/',
    'type': 'build',
    'name': 'Test JobSlave',
}

#Stubs for the parent
class Response(object):
    pass

class JobSlave(object):
    def __init__(self):
        self.response = Response()
        self.cfg = jobslave.slave.SlaveConfig()


if __name__ == '__main__':
    import epdb

    from conary import updatecmd
    from conary import conarycfg
    from conary import conaryclient

    def usage():
        print 'Usage: %s <groupTroveSpec>' % sys.argv[0]
        sys.exit(1)

    if len(sys.argv) < 2:
        usage()

    group = sys.argv[1]

    cfg = conarycfg.ConaryConfiguration(True)
    cfg.setContext(cfg.context)
    cfg.dbPath = ':memory:'
    cfg.root = ':memory:'
    cfg.initializeFlavors()
    client = conaryclient.ConaryClient(cfg)

    name, ver, flv = updatecmd.parseTroveSpec(group)
    trvList = client.repos.findTrove(cfg.installLabelPath[0],
                                     (name, ver, flv),
                                     defaultFlavor = cfg.flavor)

    if not trvList:
        print >> sys.stderr, 'no match for', groupName
        raise RuntimeException
    elif len(trvList) > 1:
        print >> sys.stderr, 'multiple matches for', groupName
        raise RuntimeException

    name, version, flavor = trvList[0]
    frzVer = version.freeze()
    frzFlav = flavor.freeze()

    jobData['troveName'] = name
    jobData['troveVersion'] = frzVer
    jobData['troveFlavor'] = frzFlav

    #Create the image generator object
    generator = jobslave.jobhandler.getHandler(jobData, JobSlave())

    try:
        generator.write()
    except:
        epdb.post_mortem(sys.exc_info()[2])
