#
# Copyright (c) 2007 rPath, Inc.
#
# All rights reserved
#

import os
import time
import simplejson
import httplib
import signal

from jobslave import jobhandler, imgserver
from jobslave.generators import constants

from mcp import client, queue, response

from conary.lib import cfgtypes, util

PROTOCOL_VERSIONS = set([1])

def controlMethod(func):
    func._controlMethod = True
    return func

filterArgs = lambda d, *args: dict([x for x in d.iteritems() \
                                        if x[0] not in args])

def getIP():
    p = os.popen("""ifconfig `route | grep "^default" | sed "s/.* //"` | grep "inet addr" | awk -F: '{print $2}' | sed 's/ .*//'""")
    data = p.read().strip()
    p.close()
    return data

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

class SlaveConfig(client.MCPClientConfig):
    jobQueueName = (cfgtypes.CfgString, None)
    nodeName = (cfgtypes.CfgString, None)
    TTL = (cfgtypes.CfgInt, 300)
    imageTimeout = (cfgtypes.CfgInt, 600)

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

        self.response = response.MCPResponse(self.cfg.nodeName, cfg)
        self.timeIdle = time.time()
        self.jobHandler = None
        self.outstandingJobs = {}
        self.imageIdle = 0
        self.imageServer = imgserver.getServer(constants.finishedDir)
        self.baseUrl = 'http://%s:%d/' % (getIP(), self.imageServer.server_port)
        self.takingJobs = True

    def catchSignal(self, *args):
        self.running = False

    def run(self):
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
            self.response.jobStatus(jobId, 'failed', 'Image not delivered')
            util.rmtree(os.path.join(constants.finishedDir, UUID),
                        ignore_errors = True)
        mcpClient = client.MCPClient(self.cfg)
        mcpClient.stopSlave(self.cfg.nodeName, delayed = False)
        self.jobQueue.disconnect()
        self.controlTopic.disconnect()
        del self.response
        # redundant protection: attempt to power off the machine in case
        # stop slave command does not get to master right away.

        # FIXME: disabled during testing. reenable before deployment
        #os.system('poweroff -h')

    # FIXME: decorate with a catchall exception logger
    def checkControlTopic(self):
        dataStr = self.controlTopic.read()
        while dataStr:
            data = simplejson.loads(dataStr)
            if data.get('node') in ('masters', self.cfg.nodeName):
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

    def checkJobQueue(self):
        # this function is designed to ensure that TTL checks can block
        # the jobQueue from picking up a job when it's time to die. be careful
        # to ensure this is honored when refactoring.
        if (self.timeIdle is not None) and \
                (time.time() - self.timeIdle) > self.cfg.TTL:
            self.takingJobs = False
        if self.jobHandler and not self.jobHandler.isAlive():
            self.timeIdle = time.time()
            self.jobHandler = None
            if self.takingJobs:
                self.jobQueue.incrementLimit()
        if not (self.takingJobs or self.servingImages()):
            self.running = False
        # we're obligated to take a job if there is one.
        dataStr = self.jobQueue.read()
        if dataStr:
            data = simplejson.loads(dataStr)
            self.jobHandler = jobhandler.getHandler(data, self)
            if self.jobHandler:
                self.jobHandler.start()
                self.timeIdle = None
            else:
                self.response.jobStatus(data['UUID'], 'failed',
                                        'Unsupported Output type')

    def getBestProtocol(self, protocols):
        common = PROTOCOL_VERSIONS.intersection(protocols)
        return common and max(common) or 0

    def sendSlaveStatus(self):
        self.response.slaveStatus(self.cfg.nodeName,
                                  self.jobHandler and 'running' or 'idle',
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
            self.response.jobStatus(jobId, 'finished', 'Job Finished')
        if self.jobHandler:
            handlerJobId = self.jobHandler.jobId
            if jobId == handlerJobId:
                self.jobHandler.kill()
        else:
            self.response.jobStatus(jobId, 'failed', 'No Job')

    def postJobOutput(self, jobId, dest, UUID, files):
        self.imageIdle = time.time()
        self.outstandingJobs[jobId] = UUID
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
