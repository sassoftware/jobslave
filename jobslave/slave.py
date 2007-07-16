#
# Copyright (c) 2007 rPath, Inc.
#
# All rights reserved
#

import os, sys
import time
import simplejson
import httplib
import signal
import traceback

from jobslave import jobhandler, imgserver
from jobslave.generators import constants
from jobslave.helperfuncs import getIP, getSlaveRuntimeConfig

from mcp import client, queue, response, jobstatus, slavestatus

from conary.lib import cfgtypes, util

PROTOCOL_VERSIONS = set([1])

def controlMethod(func):
    func._controlMethod = True
    return func

filterArgs = lambda d, *args: dict([x for x in d.iteritems() \
                                        if x[0] not in args])
def protocols(protocolList):
    if type(protocolList) in (int, long):
        protocolList = (protocolList,)
    def deco(func):
        def wrapper(self, *args, **kwargs):
            if kwargs.get('protocolVersion') in protocolList:
                return func(self, *args,
                            **(filterArgs(kwargs, 'protocolVersion')))
            else:
                raise master_error.ProtocolError(\
                    'Unsupported ProtocolVersion: %s' % \
                        str(kwargs.get('protocolVersion')))
        return wrapper
    return deco


def watchdog():
    """Fork and shutdown if parent dies.

    This function forks and simply waits. if the parent thread dies, it emits
    a shutdown command. this prevents jobslave VMs from existing without a
    jobslave process allowing them to me managed by the MCP. This function
    requires superuser privileges."""

    pid = os.fork()
    if not pid:
        try:
            ppid = os.getppid()
            print "jobslave watchdog monitoring pid: %s" % str(ppid)
            while os.getppid() == ppid:
                time.sleep(1)
            print 'watchdog detected parent thread died. shutting down.'
            os.system('poweroff -h')
        except:
            os._exit(1)
        else:
            os._exit(0)

class SlaveConfig(client.MCPClientConfig):
    jobQueueName = (cfgtypes.CfgString, None)
    nodeName = (cfgtypes.CfgString, None)
    TTL = (cfgtypes.CfgInt, 0)
    imageTimeout = (cfgtypes.CfgInt, 600)
    proxy = (cfgtypes.CfgString, None)

def catchErrors(func):
    def wrapper(self, *args, **kwargs):
        try:
            func(self, *args, **kwargs)
        except:
            exc_class, exc, bt = sys.exc_info()
            print >> sys.stderr, "%s %s" % ("Uncaught Exception: (" + \
                exc.__class__.__name__ + ')', str(exc))
            print >> sys.stderr, '\n'.join(traceback.format_tb(bt))
    return wrapper

class JobSlave(object):
    def __init__(self, cfg):
        self.cfg = cfg
        #assert None not in cfg.values()

        self.jobQueue = queue.Queue(cfg.queueHost, cfg.queuePort,
                                    cfg.jobQueueName, namespace = cfg.namespace,
                                    timeOut = 0, queueLimit = 1)

        self.controlTopic = queue.Topic(cfg.queueHost, cfg.queuePort,
                                       'control', namespace = cfg.namespace,
                                       timeOut = 0)

        self.jobControlQueue = None

        self.response = response.MCPResponse(self.cfg.nodeName, cfg)
        self.timeIdle = time.time()
        self.jobHandler = None
        self.outstandingJobs = {}
        self.imageIdle = 0
        self.imageServer = imgserver.getServer(constants.finishedDir)
        self.baseUrl = 'http://%s:%d/' % (getIP(), self.imageServer.server_port)
        self.takingJobs = True
        signal.signal(signal.SIGTERM, self.catchSignal)
        signal.signal(signal.SIGINT, self.catchSignal)

    def catchSignal(self, *args):
        self.running = False

    def run(self):
        print "Listening for jobs:", self.cfg.jobQueueName
        watchdog()
        self.running = True
        self.sendSlaveStatus()
        try:
            while self.running:
                self.checkControlTopic()
                self.checkJobQueue()
                time.sleep(0.1)
        finally:
            self.disconnect()

    def disconnect(self):
        if self.jobHandler:
            self.jobHandler.kill()
        self.imageServer.running = False
        self.imageServer.join()
        for jobId, UUID in self.outstandingJobs.iteritems():
            self.response.jobStatus(jobId, jobstatus.FAILED, 'Image not delivered')
            util.rmtree(os.path.join(constants.finishedDir, UUID),
                        ignore_errors = True)
        mcpClient = client.MCPClient(self.cfg)
        try:
            mcpClient.stopSlave(self.cfg.nodeName, delayed = False)
        except:
            # mask all errors. we're about to shutdown anyways
            pass
        self.jobQueue.disconnect()
        self.controlTopic.disconnect()
        self.response.response.disconnect()
        del self.response
        if self.jobControlQueue:
            self.jobControlQueue.disconnect()
        # redundant protection: attempt to power off the machine in case
        # stop slave command does not get to master right away.

        os.system('poweroff -h')

    @catchErrors
    def checkControlTopic(self):
        dataStr = self.controlTopic.read() or \
            (self.jobControlQueue and self.jobControlQueue.read())
        while dataStr:
            data = simplejson.loads(dataStr)
            if data.get('node') in ('slaves', self.cfg.nodeName):
                action = data['action']
                kwargs = dict([(str(x[0]), x[1]) for x in data.iteritems() \
                                   if x[0] not in ('node', 'action')])
                if action in self.__class__.__dict__:
                    func = self.__class__.__dict__[action]
                    if '_controlMethod' in func.__dict__:
                        return func(self, **kwargs)
                    else:
                        raise master_error.ProtocolError( \
                            'Control method %s is not valid' % action)
                else:
                    raise master_error.ProtocolError( \
                        "Control method %s does not exist" % action)
            dataStr = self.controlTopic.read()

    def servingImages(self):
        (time.time() - self.imageIdle) < self.cfg.imageTimeout

    # Note, ignoring errors at this level can have interesting side effects,
    # since this function is responsible for determining if a slave should go
    # away on it's own.
    @catchErrors
    def checkJobQueue(self):
        # this function is designed to ensure that TTL checks can block
        # the jobQueue from picking up a job when it's time to die. be careful
        # to ensure this is honored when refactoring.
        if (self.timeIdle is not None) and \
                (time.time() - self.timeIdle) > self.cfg.TTL:
            # avoid race conditions by setting queue limit to zero
            self.jobQueue.setLimit(0)
            # this check prevents setting takingJobs to false if one just
            # came in.
            if not self.jobQueue.inbound:
                self.takingJobs = False
        if self.jobHandler and not self.jobHandler.isAlive():
            self.timeIdle = time.time()
            self.jobControlQueue.disconnect()
            self.jobControlQueue = None

            self.jobHandler = None
            if self.takingJobs:
                self.jobQueue.incrementLimit()
        if not (self.takingJobs or self.servingImages()):
            self.running = False
        # we're obligated to take a job if there is one.
        dataStr = self.jobQueue.read()
        if dataStr:
            data = simplejson.loads(dataStr)
            try:
                self.jobHandler = jobhandler.getHandler(data, self)
                self.jobHandler.start()
                self.timeIdle = None
                self.jobControlQueue = queue.Queue( \
                    self.cfg.queueHost, self.cfg.queuePort, data['UUID'],
                    namespace = self.cfg.namespace, timeOut = 0)
            except Exception, e:
                print "Error starting job:", e
                exc_class, exc, bt = sys.exc_info()
                print ''.join(traceback.format_tb(bt))
                self.response.jobStatus(data['UUID'], jobstatus.FAILED,
                                        'Image creation error: %s' % str(e))

    def getBestProtocol(self, protocols):
        common = PROTOCOL_VERSIONS.intersection(protocols)
        return common and max(common) or 0

    def sendSlaveStatus(self):
        self.response.slaveStatus(self.cfg.nodeName,
                                  self.jobHandler \
                                      and slavestatus.ACTIVE \
                                      or slavestatus.IDLE,
                                  self.cfg.jobQueueName.replace('job', ''))

    def sendJobStatus(self):
        if self.jobHandler:
            self.jobHandler.status()

    def handleStopJob(self, jobId):
        # ensure the jobId matches the jobId we're actually servicing to prevent
        # race conditions from killing the wrong job.
        if jobId in self.outstandingJobs:
            util.rmtree(os.path.join(constants.finishedDir,
                                     self.outstandingJobs[jobId][1]),
                        ignore_errors = True)
            del self.outstandingJobs[jobId]
            self.response.jobStatus(jobId, jobstatus.FINISHED, 'Job Finished')
        elif self.jobHandler:
            handlerJobId = self.jobHandler.jobId
            if jobId == handlerJobId:
                self.jobHandler.kill()
                self.jobControlQueue.disconnect()
                self.jobControlQueue = None
        else:
            self.response.jobStatus(jobId, jobstatus.FAILED, 'No Job')

    def recordJobOutput(self, jobId, UUID):
        self.imageIdle = time.time()
        self.outstandingJobs[jobId] = UUID

    def postJobOutput(self, jobId, dest, files):
        urls = []
        for path, name in files:
            urls.append((path.replace(constants.finishedDir, self.baseUrl),
                         name))
        # send a request to the url to come get the files
        self.response.postJobOutput(jobId, dest, urls)

    @controlMethod
    def checkVersion(self, protocols):
        self.response.protocol(self.getBestProtocol(protocols))

    @controlMethod
    @protocols((1,))
    def setTTL(self, TTL):
        self.cfg.TTL = TTL

    @controlMethod
    @protocols((1,))
    def status(self):
        self.sendSlaveStatus()

    @controlMethod
    @protocols((1,))
    def stopJob(self, jobId):
        self.handleStopJob(jobId)

    @controlMethod
    @protocols((1,))
    def receivedJob(self, jobId):
        self.handleReceivedJob(jobId)

def main():
    cfg = SlaveConfig()
    cfg.read(os.path.join(os.path.sep, 'srv', 'jobslave', 'config'))
    slave = JobSlave(cfg)
    slave.run()
