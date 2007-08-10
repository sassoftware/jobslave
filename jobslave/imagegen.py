#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import logging
import os
import signal
import StringIO
import subprocess
import sys
import time
import threading
import traceback
import urllib
import weakref

from conary import conarycfg
from conary import conaryclient
from conary import versions
from conary.deps import deps
from conary.lib import util, log

from jobslave.generators import constants
from mcp import jobstatus

MSG_INTERVAL = 5

class LogHandler(logging.Handler):
    def __init__(self, jobId, response):
        self.jobId = jobId
        self.response = weakref.ref(response)
        self._msgs = ''
        self.lastSent = 0
        logging.Handler.__init__(self)

    def flush(self):
        self.lastSent = time.time()
        try:
            msgs = self._msgs
            self._msgs = ''
            self.response().jobLog(self.jobId, msgs)
        except Exception, e:
            print >> sys.stderr, "Warning: log message was lost:", self._msgs
            sys.stderr.flush()

    def emit(self, record):
        self._msgs += record.getMessage() + '\n'
        if (len(self._msgs) > 4096) or ((time.time() - self.lastSent) > 1):
            self.flush()


def logCall(cmd, ignoreErrors = False):
    log.info("+ " + cmd)
    p = subprocess.Popen(cmd, shell = True,
        stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    while p.poll() is None:
        [log.info("++ " + errLine.strip()) for errLine in p.stdout.readlines()]
        [log.debug("++ " + errLine.strip()) for errLine in p.stderr.readlines()]

    if p.returncode and not ignoreErrors:
        raise RuntimeError("Error executing command: %s (return code %d)" % (cmd, p.returncode))
    else:
        return p.returncode

def scrubUnicode(data):
    if isinstance(data, unicode):
        return data.encode('ascii', 'replace')
    elif isinstance(data, dict):
        res = {}
        for key, val in data.iteritems():
            res[key] = scrubUnicode(val)
        return res
    elif isinstance(data, (list, set, tuple)):
        return type(data)([scrubUnicode(x) for x in data])
    else:
        return data


class Generator(threading.Thread):
    configObject = None

    def __init__(self, jobData, parent):
        self.pid = None
        self.jobData = scrubUnicode(jobData)
        self.response = weakref.ref(parent.response)
        self.parent = weakref.ref(parent)
        self.workDir = None

        self.jobId = self.jobData['UUID']
        self.UUID = \
            ''.join([hex(ord(os.urandom(1)))[2:] for x in range(16)]).upper()

        self.status('Initializing build...')

        self.conarycfg = conarycfg.ConaryConfiguration(False)
        cfgData = StringIO.StringIO(self.jobData['project']['conaryCfg'])
        self.conarycfg.readObject(cfgData, cfgData)

        self.conarycfg.configLine('tmpDir %s' % constants.tmpDir)

        if parent and parent.cfg.conaryProxy:
            self.conarycfg.configLine('conaryProxy %s' % parent.cfg.conaryProxy)

        #self.conarycfg.display() # dump conary config for debugging 
        self.cc = conaryclient.ConaryClient(self.conarycfg)
        self.nc = self.cc.getRepos()

        rootLogger = logging.getLogger('')
        for handler in rootLogger.handlers[:]:
            rootLogger.removeHandler(handler)
        self.logger = LogHandler(self.jobId, parent.response)
        rootLogger.addHandler(self.logger)
        log.setVerbosity(logging.DEBUG)

        threading.Thread.__init__(self)

    def getCookData(self, key):
        return self.jobData.get('data', {}).get(key)

    def getBuildData(self, key):
        val = self.jobData.get('data', {}).get(key)
        if val is None:
            protocolVersion = \
                self.jobData.get('protocolVersion')
            if protocolVersion == 1:
                defaults = \
                    {'autoResolve': False,
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
                     'amiHugeDiskMountpoint': ''}
            else:
                defaults = {}
            val = defaults.get(key)
        return val

    def readConaryRc(self, cfg):
        conarycfgFile = os.path.join('etc', 'conaryrc')
        if os.path.exists(conarycfgFile):
            cfg.read(conarycfgFile)
        return conarycfgFile

    def write(self):
        raise NotImplementedError

    def status(self, msg = None, status = jobstatus.RUNNING):
        if msg:
            self._lastStatus = msg, status
        else:
            msg, status = self._lastStatus

        try:
            self.response().jobStatus(self.jobId, status, msg)
        except:
            print >> sys.stderr, "Error logging status to MCP:", msg

    def postOutput(self, fileList):
        # this function runs in the child process to actually post the output
        # of a build.
        parent = self.parent and self.parent()
        if parent:
            parent.postJobOutput(self.jobId, self.jobData['buildId'],
                    self.jobData['outputUrl'], self.jobData['outputToken'],
                    fileList)
        else:
            log.error("couldn't post output")

    def postAmi(self, amiId, amiManifestName):
        # this function runs in the child process to actually post the output
        # of a build.
        parent = self.parent and self.parent()
        if parent:
            parent.postAmiOutput(self.jobId, self.jobData['buildId'],
                    self.jobData['outputUrl'], self.jobData['outputToken'],
                    amiId, amiManifestName)
        else:
            log.error("couldn't post output")

    def run(self):
        self.pid = os.fork()
        if not self.pid:
            # become session leader for clean job ending.
            os.setpgid(0, 0)
            try:
                try:
                    self.status('Starting job')
                    self.write()
                    try:
                        if self.workDir and os.path.exists(self.workDir):
                            util.rmtree(self.workDir)
                    except Exception, e:
                        log.error("couldn't clean up afterwards: %s" % str(e))
                except:
                    exc, e, bt = sys.exc_info()
                    btText = traceback.format_exc(bt)
                    self.status('Job failed (%s)' % (btText.split('\n')[-2]), status = jobstatus.FAILED)
                    log.error(btText)
                    log.error('Failed job: %s' % self.jobId)
                    self.logger.flush()
                    raise
                else:
                    self.status('Job Finished',
                                status = jobstatus.FINISHED)
                    log.info('Finished job: %s' % self.jobId)
                    self.logger.flush()
            # place exit handlers in their own exception handling layer
            # to ensure that under no circumstances can it escape
            # use os._exit to force ending now.
            except:
                os._exit(1)
            else:
                os._exit(0)
        os.waitpid(self.pid, 0)

    def kill(self):
        if self.isAlive():
            self.status('Job Killed', status = jobstatus.FAILED)
            log.error('Job killed: %s' % self.jobId)

        if self.pid:
            try:
                # send kill signal to entire process group
                os.kill(-self.pid, signal.SIGKILL)
            except OSError, e:
                # errno 3 is "no such process"
                if e.errno != 3:
                    raise
        self.join()


class ImageGenerator(Generator):
    def __init__(self, *args, **kwargs):
        Generator.__init__(self, *args, **kwargs)
        #Figure out what group trove to use
        self.baseTrove = self.jobData['troveName']
        versionStr = self.jobData['troveVersion']
        flavorStr = self.jobData['troveFlavor']

        if 'filesystems' not in self.jobData:
            # support for legacy requests
            freeSpace = self.getBuildData("freespace") * 1048576

            self.jobData['filesystems'] = [
                ('/', 0, freeSpace, 'ext3'),
            ]

        self.mountDict = dict([(x[0], tuple(x[1:])) for x in self.jobData['filesystems'] if x[0]])

        #Thaw the version string
        ver = versions.ThawVersion(versionStr)
        self.baseVersion = ver.asString()

        #Thaw the flavor string
        self.baseFlavor = deps.ThawFlavor(str(flavorStr))

        try:
            self.arch = \
                self.baseFlavor.members[deps.DEP_CLASS_IS].members.keys()[0]
        except KeyError:
            self.arch = ""

        basefilename = self.getBuildData('baseFileName') or ''
        basefilename = ''.join([(x.isalnum() or x in ('-', '.')) and x or '_' \
                                for x in basefilename])
        basefilename = basefilename or \
                       "%(name)s-%(version)s-%(arch)s" % {
                           'name': self.jobData['project']['hostname'],
                           'version': ver.trailingRevision().asString().split('-')[0],
                           'arch': self.arch}

        self.basefilename = basefilename

    def _getLabelPath(self, cclient, trove):
        repos = cclient.getRepos()
        trv = repos.getTroves([trove])
        return " ".join(trv[0].getTroveInfo().labelPath)

    def writeConaryRc(self, tmpPath, cclient):
        # write the conaryrc file
        util.mkdirChain(os.path.split(tmpPath)[0])
        conaryrcFile = open(tmpPath, "w")
        ilp = self.getBuildData("installLabelPath")
        if not ilp: # allow a BuildData ILP to override the group label path
            ilp = self._getLabelPath( \
                cclient, (self.jobData['troveName'],
                          versions.VersionFromString(self.baseVersion),
                          self.baseFlavor))
        if not ilp: # fall back to a reasonable default if group trove was
                    # cooked before conary0.90 and builddata is blank
            ilp = self.jobData['projectLabel'] + " conary.rpath.com@rpl:1"
        mu = self.getBuildData('mirrorUrl')
        if mu:
            type, url = urllib.splittype(mu)
            relativeLink = ''
            if not type:
                type = 'http'
            if not url.startswith('//'):
                url = '//' + url
            if not urllib.splithost(url)[1]:
                relativeLink = '/conaryrc'
            mirrorUrl = type + ':' + url + relativeLink

        print >> conaryrcFile, "installLabelPath " + ilp
        if mu:
            print >> conaryrcFile, 'includeConfigFile ' + mirrorUrl
        print >> conaryrcFile, "pinTroves kernel.*"
        print >> conaryrcFile, "includeConfigFile /etc/conary/config.d/*"
        if self.getBuildData("autoResolve"):
            print >> conaryrcFile, "autoResolve True"
        conaryrcFile.close()

    def saveConaryRC(self, cfgPath):
        f = open(cfgPath, 'w')
        self.conarycfg.display(f)
        f.close()
        return cfgPath
