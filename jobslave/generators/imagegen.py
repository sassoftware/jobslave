#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import os
import sys
import signal
import urllib
import weakref
import StringIO

import logging
import threading

from conary import conarycfg
from conary import conaryclient
from conary.lib import util, log
import subprocess
from conary import versions

from conary.deps import deps

from jobslave.generators import constants

MSG_INTERVAL = 5

class NoConfigFile(Exception):
    def __init__(self, path = ""):
        self._path = path

    def __str__(self):
        return "Unable to access configuration file: %s" % self._path

import time
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

def system(command):
    log.info(command)
    p = subprocess.Popen(command, shell = True,
                         stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    while p.poll() is None:
        d = p.stdout.readline()
        if d:
            log.info(d)
        d = p.stdout.readline()
        if d:
            log.error(d)

#os.system = system

class Generator(threading.Thread):
    configObject = None

    def __init__(self, jobData, parent):
        self.pid = None
        self.jobData = jobData
        self.response = weakref.ref(parent.response)
        self.parent = weakref.ref(parent)

        # FIXME: once conary handles unicode better, remove these items
        # coerce to str if possible due to conary not handling unicode well
        for key, val in jobData.iteritems():
            if type(val) is unicode:
                jobData[key] = str(val)
        self.jobId = str(jobData['UUID'])
        #self.jobData['project']['name'] = str(self.jobData['project']['name'])
        #self.jobData['project']['label'] = str(self.jobData['project']['label'])
        #self.jobData['troveName'] = str(self.jobData['troveName'])
        # end str coercions

        self.UUID = \
            ''.join([hex(ord(os.urandom(1)))[2:] for x in range(16)]).upper()

        self.status('initializing')

        self.conarycfg = conarycfg.ConaryConfiguration(False)
        cfgData = StringIO.StringIO(jobData['project']['conaryCfg'])
        self.conarycfg.readObject(cfgData, cfgData)

        self.conarycfg.configLine('tmpDir %s' % constants.tmpDir)
        self.conarycfg.configLine( \
            'entitlementDirectory /srv/jobslave/entitlements')

        if parent.cfg.proxy:
            self.conarycfg.configLine('proxy %s' % parent.cfg.proxy)

        self.cc = conaryclient.ConaryClient(self.conarycfg)
        self.nc = self.cc.getRepos()

        rootLogger = logging.getLogger('')
        for handler in rootLogger.handlers[:]:
            rootLogger.removeHandler(handler)
        self.logger = LogHandler(self.jobId, parent.response)
        rootLogger.addHandler(self.logger)
        log.setVerbosity(logging.INFO)

        self.doneStatus = 'finished'
        self.doneStatusMessage = 'Finished'

        threading.Thread.__init__(self)

    def getJobData(self, key):
        return self.jobData.get('jobData', {}).get(key)

    def getBuildData(self, key):
        val = self.jobData.get('data', {}).get(key)
        if val is None:
            serialVersion = \
                self.jobData.get('serialVersion')
            if serialVersion == 1:
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
                     'showMediaCheck': False}
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

    def status(self, msg = None, status = 'running'):
        if msg:
            self._lastStatus = msg, status
        else:
            msg, status = self._lastStatus

        try:
            self.response().jobStatus(self.jobId, status, msg)
        except:
            print >> sys.stderr, "Error logging status to MCP:", msg

    def recordOutput(self):
        # this function runs in parent process space to record that a build had
        # output that needs to be tracked
        parent = self.parent and self.parent()
        if parent:
            parent.recordJobOutput(self.jobId, self.UUID)
        else:
            log.error("couldn't record output")

    def postOutput(self, fileList):
        # this function runs in the child process to actually post the output
        # of a build.

        # it doesn't matter what we send, just not ''
        os.write(self.parentPipe, 'post')
        self.doneStatus = 'built'
        self.doneStatusMessage = 'Done building image(s)'
        parent = self.parent and self.parent()
        if parent:
            parent.postJobOutput(self.jobId, self.jobData['outputQueue'],
                                 fileList)
        else:
            log.error("couldn't post output")

    def run(self):
        # use a pipe to communicate if a job posted build data
        inF, outF = os.pipe()
        self.pid = os.fork()
        if not self.pid:
            # become session leader for clean job ending.
            os.setsid()
            try:
                try:
                    os.close(inF)
                    self.parentPipe = outF
                    self.status('starting')
                    self.write()
                    os.close(outF)
                except:
                    exc, e, bt = sys.exc_info()
                    # exceptions should *never* cross this point, so it's always
                    # an internal server error
                    self.logger.flush()
                    self.status('Internal Server Error', status = 'failed')
                    import traceback
                    log.error(traceback.format_exc(bt))
                    log.error(str(e))
                    log.error('Failed job: %s' % self.jobId)
                    raise
                else:
                    self.logger.flush()
                    self.status(self.doneStatusMessage,
                                status = self.doneStatus)
                    log.info('Finished job: %s' % self.jobId)
            # place sys.exit handlers in their own exception handling layer
            # to ensure that under no circumstances can it escape
            except:
                sys.exit(1)
            else:
                sys.exit(0)
        os.close(outF)
        data = os.read(inF, 255)
        if data:
            self.recordOutput()
        else:
            util.rmtree(os.path.join(constants.finishedDir, self.UUID),
                        ignore_errors = True)
        os.close(inF)
        os.waitpid(self.pid, 0)

    def kill(self):
        if self.pid:
            try:
                # this might be considered fairly dangerous since this command
                # is executed as superuser, but chances of hitting the wrong pid
                # are astronomically small.
                os.kill(self.pid, signal.SIGKILL)
            except OSError, e:
                # errno 3 is "no such process"
                if e.errno != 3:
                    raise
        self.join()
        self.status('Job Killed', status = 'failed')
        log.error('Job killed: %s' % self.jobId)
        util.rmtree(os.path.join(constants.finishedDir, self.UUID),
                    ignore_errors = True)

class ImageGenerator(Generator):
    def __init__(self, *args, **kwargs):
        Generator.__init__(self, *args, **kwargs)
        #Figure out what group trove to use
        self.baseTrove = self.jobData['troveName']
        versionStr = self.jobData['troveVersion']
        flavorStr = self.jobData['troveFlavor']

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
