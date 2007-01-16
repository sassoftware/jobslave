#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#
import errno
import random
import os
import signal
import socket
import sys
import time
import traceback
from xmlrpclib import ProtocolError

# conary imports
from conary import conaryclient
from conary.conarycfg import ConfigFile
from conary.lib import coveragehook
from conary.conarycfg import CfgList, CfgString, CfgBool, CfgInt, CfgDict, \
     CfgEnum

# mint imports
from mint import cooktypes
from mint import jobstatus
from mint import buildtypes
from mint import scriptlibrary
from mint.client import MintClient
from mint.config import CfgBuildEnum
from mint.constants import mintVersion

# image generators
from mint.distro.installable_iso import InstallableIso
from mint.distro.live_iso import LiveIso
from mint.distro.raw_hd_image import RawHdImage
from mint.distro.vmware_image import VMwareImage, VMwareESXImage
from mint.distro.stub_image import StubImage
from mint.distro.netboot_image import NetbootImage
from mint.distro.group_trove import GroupTroveCook
from mint.distro.bootable_image import BootableImage
from mint.distro.raw_fs_image import RawFsImage
from mint.distro.tarball import Tarball
from mint.distro.vpc import VirtualPCImage

generators = {
    buildtypes.INSTALLABLE_ISO:   InstallableIso,
    buildtypes.STUB_IMAGE:        StubImage,
    buildtypes.LIVE_ISO:          LiveIso,
    buildtypes.RAW_HD_IMAGE:      RawHdImage,
    buildtypes.VMWARE_IMAGE:      VMwareImage,
    buildtypes.VMWARE_ESX_IMAGE:  VMwareESXImage,
    buildtypes.RAW_FS_IMAGE:      RawFsImage,
    buildtypes.TARBALL:           Tarball,
    buildtypes.NETBOOT_IMAGE:     NetbootImage,
    buildtypes.VIRTUAL_PC_IMAGE:  VirtualPCImage,
}

SUPPORTED_ARCHS = ('x86', 'x86_64')
# JOB_IDLE_INTERVAL: interval is in seconds. format is (min, max)
JOB_IDLE_INTERVAL = (5, 10)

class JobRunner:
    def __init__(self, cfg, client, job):
        self.cfg = cfg
        self.client = client
        self.job = job

    def getSignalName(self, signalNum):
        if signalNum == signal.SIGTERM:
            return 'SIGTERM'
        elif signalNum == signal.SIGINT:
            return 'SIGINT'
        else:
            return 'UNKNOWN'

    def sigHandler(self, signalNum, frame):
        sigName = self.getSignalName(signalNum)
        slog = scriptlibrary.getScriptLogger()
        slog.error('Job was killed by %s signal' % sigName)
        self.job.setStatus(jobstatus.ERROR, 'Job was killed by %s signal' % \
                           sigName)
        os._exit(1)

    def run(self):
        # ensure each job thread has it's own process space
        pid = os.fork()
        if not pid:
            signal.signal(signal.SIGTERM, self.sigHandler)
            signal.signal(signal.SIGINT, self.sigHandler)
            try:
                coveragehook.install()
                self.doWork()
            except:
                os._exit(1)
            else:
                os._exit(0)
        else:
            return pid

    def doWork(self):
        ret = None
        error = None
        jobId = self.job.getId()
        slog = scriptlibrary.getScriptLogger()

        self.job.setStatus(jobstatus.RUNNING, 'Running')

        if self.cfg.saveChildOutput:
            joboutputPath = os.path.join(self.cfg.logPath, 'joboutput')
            if not os.path.exists(joboutputPath):
                os.mkdir(joboutputPath)
            logFile = os.path.join(self.cfg.logPath, "joboutput",
                    "%s_%d.out" % (time.strftime('%Y%m%d%H%M%S'), jobId))
            slog.debug("Output logged to %s" % logFile)

            sys.stdout.flush()
            sys.stderr.flush()

            logfd = os.open(logFile, os.O_WRONLY | os.O_CREAT, 0664)

            os.dup2(logfd, sys.stdout.fileno())
            os.dup2(logfd, sys.stderr.fileno())

            sys.stdout.flush()

        # make sure conary's logger instance is logging (almost) all output
        # N.B. debug is probably *too* verbose, really
        from conary.lib import log
        from logging import INFO
        log.setVerbosity(INFO)

        if self.job.buildId:
            build = self.client.getBuild(self.job.buildId)
            project = self.client.getProject(build.getProjectId())

            # save the current working directory in case the generator
            # (or scripts that change the wd)
            cwd = os.getcwd()
            try:
                # this line assumes that there's only one image per job.
                generator = generators[build.getBuildType()]
                slog.info("%s job for %s started (id %d)" % \
                         (generator.__name__, project.getHostname(), jobId))
                imageFilenames = generator(self.client, self.cfg, self.job,
                                           build, project).write()
            except Exception, e:
                traceback.print_exc()
                sys.stdout.flush()
                error = sys.exc_info()
            else:
                build.setFiles(imageFilenames)
                slog.info("Job %d finished: %s", jobId, str(imageFilenames))

            try:
                os.chdir(cwd)
            except:
                pass

        elif self.job.getGroupTroveId():
            try:
                slog.info("Group trove cook job started (id %d)" % jobId)
                ret = GroupTroveCook(self.client, self.cfg, self.job).write()
            except Exception, e:
                traceback.print_exc()
                sys.stdout.flush()
                error = sys.exc_info()
            else:
                slog.info("Job %d succeeded: %s" % (jobId, str(ret)))

        if error:
            errorStr = error[0].__name__
            if str(error[1]):
                errorStr +=  " (%s)" % str(error[1])

            slog.error("Job %d failed: %s", jobId, errorStr)
            self.job.setStatus(jobstatus.ERROR, errorStr)
            raise error
        else:
            self.job.setStatus(jobstatus.FINISHED, "Finished")


class JobDaemon:
    def __init__(self, cfg):
        coveragehook.install()
        client = MintClient(cfg.serverUrl)

        confirmedAlive = False

        self.takingJobs = True

        slog = scriptlibrary.getScriptLogger()

        # FIXME, get the job ID
        jobId = 9
        client.getJob(jobId)

        th = JobRunner(cfg, client, job)
        jobPid = th.run()
        os.waitpid(jobPid, 0)


class CfgCookEnum(CfgEnum):
    validValues = cooktypes.validCookTypes

class IsoGenConfig(ConfigFile):
    serverUrl       = 'serverUrl http://mintauth:mintpass@mint.rpath.local/xmlrpc-private/'
    SSL             = (CfgBool, False)
    logPath         = '/srv/rbuilder/logs'
    imagesPath      = '/srv/rbuilder/images/'
    finishedPath    = '/srv/rbuilder/finished-images/'
    configPath      = '/srv/rbuilder/'

    def read(cfg, path, exception = False):
        slog = scriptlibrary.getScriptLogger()
        ConfigFile.read(cfg, path, exception)
        cfg.configPath = os.path.dirname(path)

        if cfg.serverUrl is None:
            slog.error("A server URL must be specified in the config file. For example:")
            slog.error("    serverUrl http://username:userpass@www.example.com/xmlrpc-private/")
            sys.exit(1)
