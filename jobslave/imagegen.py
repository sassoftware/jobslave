#
# Copyright (c) 2004-2009 rPath, Inc.
#
# All Rights Reserved
#

import logging
import os
import signal
import stat
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
from conary.lib import util, log as conaryLog

from jobslave.generators import constants, ovf_image
from mcp import jobstatus, response

log = logging.getLogger(__name__)

MSG_INTERVAL = 5

class LogHandler(logging.FileHandler):
    def __init__(self, jobId, response):
        self.jobId = jobId
        self.response = response

        self._msgs = ''
        self.lastSent = 0

        d = tempfile.mkdtemp()
        logfn = os.path.join(d, 'build.log')
        logging.FileHandler.__init__(self, logfn)

    def getFilename(self):
        return self.baseFilename

    def sendMessages(self):
        # We can't call this "flush" or FileHandler will invoke it
        # after every emit() call, which bogs down the mcp.
        self.flush()
        self.lastSent = time.time()
        try:
            msgs = self._msgs
            self._msgs = ''
            self.response.jobLog(self.jobId, msgs)
        except Exception, e:
            if self._msgs:
                print >> sys.stderr, "Warning: log message was lost:", self._msgs
            sys.stderr.flush()

    def emit(self, record):
        logging.FileHandler.emit(self, record)

        self._msgs += self.format(record) + '\n'
        if (len(self._msgs) > 4096) or ((time.time() - self.lastSent) > 4):
            self.sendMessages()

    def close(self):
        logging.FileHandler.close(self)
        self.sendMessages()


def logCall(cmd, ignoreErrors = False, logCmd = True, **kw):
    """
    Run command C{cmd}, logging the command run and all its output.

    If C{cmd} is a string, it will be interpreted as a shell command.
    Otherwise, it should be a list where the first item is the program name and
    subsequent items are arguments to the program.

    @param cmd: Program or shell command to run.
    @type  cmd: C{basestring or list}
    @param ignoreErrors: If C{True}, don't raise an exception on a 
            non-zero return code.
    @type  ignoreErrors: C{bool}
    @param logCmd: If C{False}, don't log the command invoked.
    @type  logCmd: C{bool}
    @param kw: All other keyword arguments are passed to L{subprocess.Popen}
    @type  kw: C{dict}
    """

    if logCmd:
        if isinstance(cmd, basestring):
            niceString = cmd
        else:
            niceString = ' '.join(repr(x) for x in cmd)
        env = kw.get('env', {})
        env = ''.join(['%s="%s "' % (k,v) for k,v in env.iteritems()])
        log.info("+ %s%s", env, niceString)

    p = subprocess.Popen(cmd, shell=isinstance(cmd, basestring),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)

    while p.poll() is None:
        rList, junk, junk = select.select([p.stdout, p.stderr], [], [])
        for rdPipe in rList:
            action = (rdPipe is p.stdout) and log.info or log.debug
            msg = rdPipe.readline().strip()
            if msg:
                action("++ " + msg)

    # pylint: disable-msg=E1103
    stdout, stderr = p.communicate()
    for x in stderr.splitlines():
        log.info("++ (stderr) %s", x)
    for x in stdout.splitlines():
        log.info("++ (stdout) %s", x)

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

def getFileSize(filePath):
    return os.stat(filePath)[stat.ST_SIZE]

class Generator(threading.Thread):
    configObject = None

    def __init__(self, jobData, parent):
        self.pid = None
        self.logger = None
        self.jobData = scrubUnicode(jobData)
        self.parent = weakref.ref(parent)
        self.response = None
        self.workDir = None
        self.outputFileList = []

        self.jobId = self.jobData['UUID']
        self.UUID = \
            ''.join([hex(ord(os.urandom(1)))[2:] for x in range(16)]).upper()

        self.status('Initializing build...')
        log.info('Starting build %s', self.jobId)
        log.info('UUID: %s', self.UUID)

        self.conarycfg = conarycfg.ConaryConfiguration(False)
        cfgData = StringIO.StringIO(self.jobData['project']['conaryCfg'])
        self.conarycfg.readObject(cfgData, cfgData)

        self.conarycfg.configLine('pinTroves %s' % constants.pinKernelRE)
        self.conarycfg.configLine('tmpDir %s' % constants.tmpDir)
        self.conarycfg.configLine('threaded False')

        # XXX need to do this since setting the tmpDir via the
        # configuration object is never enough (RBL-2461)
        util.settempdir(constants.tmpDir)

        if parent and parent.cfg.conaryProxy:
            self.conarycfg.configLine('conaryProxy %s' % parent.cfg.conaryProxy)

        #self.conarycfg.display() # dump conary config for debugging 
        self.cc = conaryclient.ConaryClient(self.conarycfg)
        self.nc = self.cc.getRepos()

        threading.Thread.__init__(self)

    def __del__(self):
        # Close and remove the MCP+file logger since the logging
        # module keeps several references otherwise
        if getattr(self, 'logger', None):
            rootLogger = logging.getLogger('')
            rootLogger.removeHandler(self.logger)
            try:
                self.logger.close()
            except ValueError:
                # file closed
                pass
            self.logger = None

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
            log.info("Sending new job status %s: %s",
                    jobstatus.statusNames[status], msg)
        else:
            msg, status = self._lastStatus

        if self.response:
            # In child with its own response object
            resp = self.response
        else:
            # In parent process
            resp = self.parent().response

        try:
            resp.jobStatus(self.jobId, status, msg)
        except:
            log.traceback("Error logging status to MCP:")

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
        self.postOutput(((fn, 'Failed build log'),))

    def run(self):
        self.pid = os.fork()
        if not self.pid:
            # become session leader for clean job ending.
            os.setpgid(0, 0)
            try:
                try:
                    # Make a new response object (so we don't collide with
                    # the parent process).
                    self.response = response.MCPResponse(self.parent().cfg.nodeName,
                            self.parent().cfg)

                    rootLogger = logging.getLogger()
                    rootLogger.handlers = []
                    # NB: setting DEBUG here creates a recursive loop between
                    # our logger and stomp.py (which logs every frame it sends
                    # as DEBUG).
                    rootLogger.setLevel(logging.INFO)

                    # Log to file/MCP
                    self.logger = LogHandler(self.jobId, self.response)
                    self.logger.setFormatter(logging.Formatter(
                        '%(asctime)s %(levelname)s %(name)s : %(message)s'))
                    rootLogger.addHandler(self.logger)

                    # Log to stderr
                    streamHandler = logging.StreamHandler()
                    streamHandler.setFormatter(logging.Formatter(
                        '%(asctime)s %(levelname)s %(name)s : %(message)s'))
                    rootLogger.addHandler(streamHandler)

                    # Override conary.lib.log so users of that module do the
                    # same thing. New code should get a proper logger.
                    conaryLog.setVerbosity(logging.DEBUG)
                    conaryLog.handlers = []

                    self.status('Starting job')
                    self.write()
                except:
                    exc, e, bt = sys.exc_info()
                    btText = traceback.format_exc(bt)
                    self.status('Job failed (%s)' % (str(e).replace('\n', ' ')), status = jobstatus.FAILED)
                    log.error(btText)
                    log.error('Failed job: %s' % self.jobId)
                    self.logger.sendMessages() #Flush() is a noop
                    try:
                        self.postFailedJobLog()
                    except:
                        tb = traceback.format_exception(*sys.exc_info())
                        log.error('Error publishing failed job log')
                        log.error(''.join(tb))
                    raise exc, e, bt
                else:
                    self.logger.sendMessages() #flush() is a noop
                    self.status('Job Finished',
                                status = jobstatus.FINISHED)
                    log.info('Finished job: %s' % self.jobId)
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

    ovfClass = None

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
        self.buildOVF10 = self.getBuildData('buildOVF10')

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
        print >> conaryrcFile, "pinTroves %s" % constants.pinKernelRE
        if self.getBuildData("autoResolve"):
            print >> conaryrcFile, "autoResolve True"
        print >> conaryrcFile, "includeConfigFile /etc/conary/config.d/*"
        conaryrcFile.close()

    def createOvf(self, imageName, imageDescription, diskFormat,
                  diskFilePath, diskCapacity, diskCompressed,
                  workingDir, outputDir):

        if self.ovfClass is None:
            self.ovfClass = ovf_image.OvfImage

        diskFileSize = getFileSize(diskFilePath)

        self.ovfImage = self.ovfClass(
            imageName, imageDescription, diskFormat,
            diskFilePath, diskFileSize, diskCapacity, diskCompressed,
            workingDir, outputDir)

        ovfObj = self.ovfImage.createOvf()
        ovfXml = self.ovfImage.writeOvf()
        self.ovfImage.createManifest()
        ovaPath = self.ovfImage.createOva()

        return ovaPath
      
