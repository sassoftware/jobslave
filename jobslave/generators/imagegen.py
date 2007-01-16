#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

import os
import sys
import urllib
import weakref
import StringIO

import logging

from conary import conarycfg
from conary import conaryclient
from conary.lib import util, log
import subprocess
from conary import versions

from conary.deps import deps

MSG_INTERVAL = 5

class NoConfigFile(Exception):
    def __init__(self, path = ""):
        self._path = path

    def __str__(self):
        return "Unable to access configuration file: %s" % self._path

class LogHandler(logging.Handler):
    def __init__(self, jobId, response):
        self.jobId = jobId
        self.response = weakref.ref(response)
        logging.Handler.__init__(self)

    def emit(self, record):
        try:
            self.response().jobLog(jobId, record.getMessage())
        except:
            print >> sys.stderr, "Warning: log message was lost:", \
                record.getMessage()
            sys.stderr.flush()

def logPipe(l, p):
    running = True
    while running:
        try:
            line = p.next()
            l(line)
        except StopIteration:
            running = False

def system(command):
    log.info(command)
    p = subprocess.Popen(command, shell = True,
                         stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    p.wait()
    logPipe(log.info, p.stdout)
    logPipe(log.error, p.stderr)

os.system = system

class Generator:
    configObject = None

    def __init__(self, jobData, response):
        self.jobData = jobData
        self.response = weakref.ref(response)
        self.jobId = jobData['UUID']

        self.conarycfg = conarycfg.ConaryConfiguration(False)
        cfgData = StringIO.StringIO(jobData['project']['conaryCfg'])
        self.conarycfg.readObject(cfgData, cfgData)

        self.cc = conaryclient.ConaryClient(self.conarycfg)
        self.nc = self.cc.getRepos()

        rootLogger = logging.getLogger('')
        for handler in rootLogger.handlers[:]:
            rootLogger.removeHandler(handler)
        rootLogger.addHandler(LogHandler(self.jobId, response))
        log.setVerbosity(logging.INFO)

    def getJobData(self, key):
        return self.jobData.get('jobData', {}).get(key)

    def getBuildData(self, key):
        return self.jobData.get('data', {}).get(key)

    def readConaryRc(self, cfg):
        conarycfgFile = os.path.join('etc', 'conaryrc')
        if os.path.exists(conarycfgFile):
            cfg.read(conarycfgFile)
        return conarycfgFile

    def write(self):
        raise NotImplementedError

    def status(self, msg, level = 'running'):
        try:
            self.response().jobStatus(self.jobId, level, msg)
        except Exception, e:
            print >> sys.stderr, "Error logging status to MCP:", e


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
        self.baseFlavor = deps.ThawFlavor(flavorStr)

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
        util.mkdirChain(tmpPath)
        conaryrcFile = open(os.path.join(tmpPath, "conaryrc"), "w")
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
