#
# Copyright (c) SAS Institute Inc.
#

import logging
import os
import re
import StringIO
import sys
import urllib

from conary import conarycfg
from conary import conaryclient
from conary import versions
from conary.conaryclient.cml import CML
from conary.deps import deps
from conary.lib import formattrace
from conary.lib import util, log as conaryLog

from jobslave import jobstatus
from jobslave import response
from jobslave.generators import constants, ovf_image
from jobslave.job_data import JobData
from jobslave.response import LogHandler
from jobslave.util import getFileSize

from rpath_proddef import api1 as proddef

log = logging.getLogger(__name__)

MSG_INTERVAL = 5


class Generator(object):
    configObject = None

    def __init__(self, cfg, jobData):
        self.cfg = cfg
        self.jobData = JobData(jobData)

        self.response = response.ResponseProxy(cfg.masterUrl, self.jobData)
        self.UUID = self.jobData['UUID'].encode('ascii')
        self.workDir = os.path.join(constants.tmpDir, self.UUID)

        self.logger = None
        self.outputFileList = []

        self.conarycfg = self._getConaryCfg()
        self.cc = conaryclient.ConaryClient(self.conarycfg)
        self.nc = self.cc.getRepos()

    def _getConaryCfg(self):
        ccfg = conarycfg.ConaryConfiguration(False)

        cfgData = StringIO.StringIO(self.jobData['project']['conaryCfg'])
        ccfg.readObject(cfgData, cfgData)

        ccfg.configLine('tmpDir %s' % constants.tmpDir)
        ccfg.configLine('pubRing %s/pubring.gpg' % constants.tmpDir)
        ccfg.configLine('threaded False')
        ccfg.flavor = [self.jobData['troveFlavor']]

        proxy = None
        if self.cfg.conaryProxy:
            proxy = self.cfg.conaryProxy
        if proxy:
            ccfg.configLine('conaryProxy http ' + proxy)
            ccfg.configLine('conaryProxy https ' + proxy)

        # RBL-2461
        util.settempdir(constants.tmpDir)

        return ccfg

    def getBuildData(self, key):
        return self.jobData.getBuildData(key)

    def write(self):
        raise NotImplementedError

    def run(self):
        try:
            # Route log data to the rBuilder's build log.
            self.logger = LogHandler(self.response)
            self.logger.start()
            rootLogger = logging.getLogger()
            self.logger.setFormatter(rootLogger.handlers[0].formatter)
            rootLogger.addHandler(self.logger)

            # Override conary.lib.log so users of that module do the same
            # thing. New code must use the builtin logging, not the conary
            # logger.
            conaryLog.setVerbosity(logging.NOTSET)
            conaryLog.logger.handlers = []

            log.info("Starting job %s", self.UUID)
            self.status('Starting job')
            self.write()

            log.info('Finished job: %s', self.UUID)
            self.status('Job Finished', status=jobstatus.FINISHED)
            self.logger.flush()

        except:
            e_type, e_value, e_tb = sys.exc_info()
            log.exception("Unhandled exception in generator:")

            try:
                self._sendStackTrace(e_type, e_value, e_tb)
            except:
                log.exception("Failed to upload full stack trace:")

            message = 'Job failed (%s: %s)' % (
                    e_type.__name__, str(e_value).replace('\n', ' '))
            self.status(message, status=jobstatus.FAILED)
            if self.logger:
                self.logger.flush()

        if self.logger:
            self.logger.close()
            self.logger = None

    def status(self, message, status=jobstatus.RUNNING):
        log.info("Sending job status: %d %s", status, message)
        self.response.sendStatus(status, message)

    def postOutput(self, fileList, attributes=None):
        self.response.postOutput(fileList, attributes=attributes)

    def _sendStackTrace(self, e_type, e_value, e_tb):
        # Scrub the most likely place for user passwords to appear.
        try:
            self.jobData['project']['conaryCfg'] = '<scrubbed>'
        except:
            pass

        path = '/tmp/trace.txt'
        f = open(path, 'w')
        formattrace.formatTrace(e_type, e_value, e_tb, stream=f,
                withLocals=False)
        f.write("\nFull stack:\n")
        formattrace.formatTrace(e_type, e_value, e_tb, stream=f,
                withLocals=True)
        f.close()

        # Upload the trace but don't update the image file listing, that way it
        # will be hidden.
        self.response.postOutput([ (path, '') ], withMetadata=False)


class ImageGenerator(Generator):
    ovfClass = None
    alwaysOvf10 = False

    def __init__(self, *args, **kwargs):
        Generator.__init__(self, *args, **kwargs)

        #Figure out what group trove to use
        self.baseTrove = self.jobData['troveName'].encode('utf8')
        self.baseVersion = versions.ThawVersion(
                self.jobData['troveVersion'].encode('utf8'))
        self.baseFlavor = deps.ThawFlavor(
                self.jobData['troveFlavor'].encode('utf8'))
        self.baseTup = self.baseTrove, self.baseVersion, self.baseFlavor
        self.baseTroveObj = None
        self.isDomU = self.baseFlavor.stronglySatisfies(
                deps.parseFlavor('domU'))

        self.productDefinition = None
        self.platformDefinition = None
        self.platformTags = set()
        if 'filesystems' not in self.jobData:
            freeSpace = (self.getBuildData("freespace") or 0) * 1048576
            platName, platVer, platTags = self.getPlatformClassifier()
            if 'redhat' in platTags and platVer >= 6:
                fsType = 'ext4'
            else:
                fsType = 'ext3'
            self.jobData['filesystems'] = [('/', 0, freeSpace, fsType)]

        self.mountDict = dict([(x[0], tuple(x[1:]))
            for x in self.jobData['filesystems'] if x[0]])

        try:
            self.arch = \
                self.baseFlavor.members[deps.DEP_CLASS_IS].members.keys()[0]
        except KeyError:
            self.arch = ""

        basefilename = self.getBuildData('baseFileName') or ''
        if basefilename:
            basefilename = re.sub('[^a-zA-Z0-9.-]', '_', basefilename)
        else:
            basefilename = '-'.join((self.jobData['project']['hostname'],
                self.baseVersion.trailingRevision().version, self.arch))

        self.basefilename = basefilename.encode('utf8')
        self.buildOVF10 = self.getBuildData('buildOVF10') or self.alwaysOvf10

        self.cml = CML(self.conarycfg)
        imageModel = self.jobData.get('imageModel')
        if not imageModel:
            imageModel = ['install "%s=%s/%s[%s]"\n' % (
                    self.baseTrove,
                    self.baseVersion.trailingLabel(),
                    self.baseVersion.trailingRevision(),
                    self.baseFlavor)]
        self.cml.parse([str(x) for x in imageModel])

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
            ilp = self._getLabelPath(cclient, self.baseTup)
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
        print >> conaryrcFile, "pinTroves " + self.getPins()
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
            imageName=imageName,
            imageDescription=imageDescription,
            diskFormat=diskFormat,
            diskFilePath=diskFilePath,
            diskFileSize=diskFileSize,
            diskCapacity=diskCapacity,
            diskCompressed=diskCompressed,
            memorySize=self.getBuildData('vmMemory'),
            cpuCount=self.getBuildData('vmCPUs'),
            workingDir=workingDir,
            outputDir=outputDir,
            )

        ovfObj = self.ovfImage.createOvf()
        ovfXml = self.ovfImage.writeOvf()
        self.ovfImage.createManifest()
        ovaPath = self.ovfImage.createOva()

        return ovaPath

    def getProductDefinition(self):
        if self.productDefinition:
            return self.productDefinition

        proddefLabel = self.jobData.get('proddefLabel')
        if not proddefLabel:
            return None

        self.platformDefinition = proddef.ProductDefinition()
        self.platformDefinition.setBaseLabel(proddefLabel)
        self.platformDefinition.loadFromRepository(self.cc)

        info = self.platformDefinition.getPlatformInformation()
        if (info and getattr(info, 'platformClassifier', None)
                and getattr(info.platformClassifier, 'tags', None)):
            self.platformTags = set(info.platformClassifier.tags.split())

        return self.platformDefinition

    def getPlatformClassifier(self):
        self.getProductDefinition()
        if self.platformDefinition:
            info = self.platformDefinition.getPlatformInformation()
            if info and getattr(info, 'platformClassifier', None):
                pc = info.platformClassifier
                try:
                    ver = int(pc.version)
                except ValueError:
                    ver = pc.version
                return (pc.name, ver, self.platformTags)
        return ('rpath', 2, self.platformTags)

    def isPlatform(self, tag):
        self.getProductDefinition()
        return tag in self.platformTags

    def findImageSubtrove(self, name):
        if self.baseTroveObj is None:
            self.baseTroveObj = self.nc.getTrove(withFiles=False,
                    *self.baseTup)

        return set(x for x in self.baseTroveObj.iterTroveList(True, True)
                if x[0] == name)

    def getPins(self):
        if self.isPlatform('redhat'):
            names = 'kernel'
        elif self.isPlatform('suse'):
            names = 'kernel(|-base|-syms)'
        else:
            # rpath platforms pin kernel-* for historical reasons (RBL-3000)
            names = 'kernel(-.*)?'
        return names + '(:.*)?$'
