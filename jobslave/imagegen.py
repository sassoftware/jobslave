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
import traceback
import urllib

from conary import conarycfg
from conary import conaryclient
from conary import versions
from conary.deps import deps
from conary.lib import util, log as conaryLog

from jobslave import jobstatus
from jobslave import response
from jobslave.generators import constants, ovf_image
from jobslave.response import LogHandler
from jobslave.util import getFileSize

log = logging.getLogger(__name__)

MSG_INTERVAL = 5


class Generator(object):
    configObject = None

    def __init__(self, cfg, jobData):
        self.cfg = cfg
        self.jobData = jobData

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

        ccfg.configLine('pinTroves %s' % constants.pinKernelRE)
        ccfg.configLine('tmpDir %s' % constants.tmpDir)
        ccfg.configLine('pubRing %s/pubring.gpg' % constants.tmpDir)
        ccfg.configLine('threaded False')

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
        return self.jobData.get('data', {}).get(key)

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
            conaryLog.handlers = []

            log.info("Starting job %s", self.UUID)
            self.status('Starting job')
            self.write()

        except Exception, err:
            log.exception("Job failed:")

            message = 'Job failed (%s)' % str(err).replace('\n', ' ')
            self.status(message, status=jobstatus.FAILED)
            self.logger.flush()

            if self.cfg.debugMode:
                raise

        else:
            log.info('Finished job: %s', self.UUID)
            self.status('Job Finished', status=jobstatus.FINISHED)
            self.logger.flush()

    def status(self, message, status=jobstatus.RUNNING):
        log.info("Sending job status: %d %s", status, message)
        self.response.sendStatus(status, message)

    def postOutput(self, fileList):
        self.response.postOutput(fileList)


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

        self.basefilename = basefilename.encode('utf8')
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
      
