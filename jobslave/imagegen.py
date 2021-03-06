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
from conary.trovetup import TroveTuple

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

        if cfg.masterUrl:
            self.response = response.ResponseProxy(cfg.masterUrl, self.jobData)
        else:
            self.response = response.BaseResponseProxy()
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

    def _response(self, forJobData):
        if forJobData:
            return response.ResponseProxy(self.cfg.masterUrl, forJobData)
        return self.response

    def status(self, message, status=jobstatus.RUNNING, forJobData=None):
        log.info("Sending job status: %d %s", status, message)
        response = self._response(forJobData)
        response.sendStatus(status, message)

    def postOutput(self, fileList, attributes=None, forJobData=None):
        response = self._response(forJobData)
        response.postOutput(fileList, attributes=attributes)

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
        self.baseTup = TroveTuple(self.baseTrove, self.baseVersion, self.baseFlavor)
        self.baseTroveObj = None
        self.isDomU = self.baseFlavor.stronglySatisfies(
                deps.parseFlavor('domU'))

        self.productDefinition = None
        self.platformTags = set()
        self._loadProddef()

        self.arch = self.getArchFromFlavor(self.baseFlavor)
        (self.basefilename, self.original_basefilename) = self.getBaseFileName()
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

    @classmethod
    def getArchFromFlavor(cls, flv):
        try:
            return flv.members[deps.DEP_CLASS_IS].members.keys()[0]
        except KeyError:
            return ""

    def getBaseFileName(self, version=None, arch=None, jobData=None):
        if jobData is None:
            jobData = self.jobData
        if arch is None:
            arch = self.arch
        if version is None:
            version = self.baseVersion
        basefilename = jobData.getBuildData('baseFileName') or ''
        if basefilename:
            orig_basefilename = basefilename
            basefilename = self.sanitizeBaseFileName(basefilename)
        else:
            basefilename = '-'.join((jobData['project']['hostname'],
                version.trailingRevision().version, arch))
            orig_basefilename = basefilename
        return (basefilename.encode('utf8'), orig_basefilename.encode('utf8'))

    @classmethod
    def sanitizeBaseFileName(cls, basefilename):
        return re.sub('[^a-zA-Z0-9.-]', '_', basefilename)

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

    def createOvf(self, diskFormat,
                  diskFilePath, diskCapacity, diskCompressed,
                  workingDir, outputDir, hwVersion=7):

        if self.ovfClass is None:
            self.ovfClass = ovf_image.OvfImage

        diskFileSize = getFileSize(diskFilePath)

        self.ovfImage = self.ovfClass(
            imageName=self.original_basefilename,
            sanitizedImageName=self.basefilename,
            imageDescription=self.jobData['description'],
            diskFormat=diskFormat,
            diskFilePath=diskFilePath,
            diskFileSize=diskFileSize,
            diskCapacity=diskCapacity,
            diskCompressed=diskCompressed,
            memorySize=self.getBuildData('vmMemory'),
            cpuCount=self.getBuildData('vmCPUs'),
            workingDir=workingDir,
            outputDir=outputDir,
            hwVersion=hwVersion,
            )

        ovfObj = self.ovfImage.createOvf()
        self.customizeOvf(self.ovfImage)
        ovfXml = self.ovfImage.writeOvf()
        self.ovfImage.createManifest()
        ovaPath = self.ovfImage.createOva()

        return ovaPath

    def customizeOvf(self, ovfImage):
        pass

    def _loadProddef(self):
        proddefLabel = self.jobData.get('proddefLabel')
        if not proddefLabel:
            return None
        proddefVersion = self.jobData.get('proddefVersion')

        self.productDefinition = proddef.ProductDefinition()
        self.productDefinition.setBaseLabel(proddefLabel)
        self.productDefinition.loadFromRepository(self.cc,
                sourceTrove=proddefVersion)

        info = self.productDefinition.getPlatformInformation()
        if (info and getattr(info, 'platformClassifier', None)
                and getattr(info.platformClassifier, 'tags', None)):
            self.platformTags = set(info.platformClassifier.tags.split())

        return self.productDefinition

    def getPlatformClassifier(self):
        if self.productDefinition:
            info = self.productDefinition.getPlatformInformation()
            if info and getattr(info, 'platformClassifier', None):
                pc = info.platformClassifier
                try:
                    ver = int(pc.version)
                except ValueError:
                    ver = pc.version
                return (pc.name, ver, self.platformTags)
        return ('rpath', 2, self.platformTags)

    def isPlatform(self, tag):
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
