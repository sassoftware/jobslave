#
# Copyright (c) 2004-2008 rPath, Inc.
#
# All Rights Reserved
#

import logging
import os
import signal
import StringIO
import subprocess
import select
import shutil
import sys
import tempfile
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
        d = tempfile.mkdtemp()
        self.logfn = os.path.join(d, 'build.log')
        self.logfd = os.open(self.logfn, os.O_CREAT|os.O_WRONLY)

    def __del__(self):
        os.close(self.logfd)

    def getFilename(self):
        return self.logfn

    def flush(self):
        self.lastSent = time.time()
        try:
            msgs = self._msgs
            self._msgs = ''
            self.response().jobLog(self.jobId, msgs)
        except Exception, e:
            if self._msgs:
                print >> sys.stderr, "Warning: log message was lost:", self._msgs
            sys.stderr.flush()

    def emit(self, record):
        os.write(self.logfd, record.getMessage() + '\n')
        self._msgs += record.getMessage() + '\n'
        if (len(self._msgs) > 4096) or ((time.time() - self.lastSent) > 1):
            self.flush()


def logCall(cmd, ignoreErrors = False):
    log.info("+ " + cmd)
    p = subprocess.Popen(cmd, shell = True,
        stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    while p.poll() is None:
        rList, junk, junk = select.select([p.stdout, p.stderr], [], [])
        for rdPipe in rList:
            action = (rdPipe is p.stdout) and log.info or log.debug
            msg = rdPipe.readline().strip()
            if msg:
                action("++ " + msg)

    stdout, stderr = p.communicate()
    [log.info("++ " + outLine) for outLine in stdout.splitlines()]
    [log.debug("++ " + errLine) for errLine in stderr.splitlines()]
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
        log.info('Starting build %s', self.jobId)
        log.info('UUID: %s', self.UUID)

        self.conarycfg = conarycfg.ConaryConfiguration(False)
        cfgData = StringIO.StringIO(self.jobData['project']['conaryCfg'])
        self.conarycfg.readObject(cfgData, cfgData)

        self.conarycfg.configLine('pinTroves kernel.*')
        self.conarycfg.configLine('tmpDir %s' % constants.tmpDir)

        # XXX need to do this since setting the tmpDir via the
        # configuration object is never enough (RBL-2461)
        util.settempdir(constants.tmpDir)

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

    def postAMI(self, amiId, amiManifestName):
        # this function runs in the child process to actually post the output
        # of a build.
        parent = self.parent and self.parent()
        if parent:
            parent.postAMIOutput(self.jobId, self.jobData['buildId'],
                    self.jobData['outputUrl'], self.jobData['outputToken'],
                    amiId, amiManifestName)
        else:
            log.error("couldn't post output")

    def postFailedJobLog(self):
        if not self.jobData.has_key('buildId'):
            return
        fn = self.logger.getFilename()
        # append some useful log files to the build log
        f = open(fn, 'a')
        for filename in ('conary-tag-script',
                         'conary-tag-script.output'):
            logfile = os.path.join(self.conarycfg.root,
                                   'root', filename)
            if os.path.exists(logfile):
                f.write('--- /root/%s ---\n' %filename)
                inf = open(logfile)
                shutil.copyfileobj(inf, f)
                inf.close()
        f.close()
        self.postOutput(((fn, 'Failed build log'),))

    def run(self):
        self.pid = os.fork()
        if not self.pid:
            # become session leader for clean job ending.
            os.setpgid(0, 0)
            try:
                try:
                    self.status('Starting job')
                    self.write()
                except:
                    exc, e, bt = sys.exc_info()
                    btText = traceback.format_exc(bt)
                    self.status('Job failed (%s)' % (str(e).replace('\n', ' ')), status = jobstatus.FAILED)
                    log.error(btText)
                    log.error('Failed job: %s' % self.jobId)
                    self.logger.flush()
                    try:
                        self.postFailedJobLog()
                    except:
                        tb = traceback.format_exception(*sys.exc_info())
                        log.error('Error publishing failed job log')
                        log.error(''.join(tb))
                    raise exc, e, bt
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
        if self.getBuildData("autoResolve"):
            print >> conaryrcFile, "autoResolve True"
        print >> conaryrcFile, "includeConfigFile /etc/conary/config.d/*"
        conaryrcFile.close()
