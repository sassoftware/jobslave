#
# Copyright (c) 2007 rPath, Inc.
#
# All rights reserved
#

import time
import simplejson

from jobslave import jobhandler

from mcp import client, queue, response

from conary.lib import cfgtypes

PROTOCOL_VERSIONS = set([1])

def controlMethod(func):
    func._controlMethod = True
    return func

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
            self.jobHandler.join()
        mcpClient = client.MCPClient(cfg)
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

    def checkJobQueue(self):
        # this function is designed to ensure that TTL checks can block
        # the jobQueue from picking up a job when it's time to die. be careful
        # to ensure this is honored when refactoring.
        takeJob = False
        if self.jobHandler and not self.jobHandler.isAlive():
            self.timeIdle = time.time()
            self.jobHandler = None
            takeJob = True
        if (self.timeIdle is not None) and \
                (time.time() - self.timeIdle) > self.cfg.TTL:
            self.running = False
        elif takeJob:
            self.jobQueue.incrementLimit()
        # we're obligated to take a job if there is one.
        dataStr = self.jobQueue.read()
        if dataStr:
            data = simplejson.loads(dataStr)
            self.jobHandler = jobhandler.getHandler(data, self.response)
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
                                  self.cfg.jobQueueName)

    def handleStopJob(self, jobId):
        # ensure the jobId matches the jobId we're actually servicing to prevent
        # race conditions from killing the wrong job.
        pass

    # these two items might need to end up in the image building object
    #jobLog
    #jobStatus

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
        self.sendJobStatus()

    @controlMethod
    @protocols((1,))
    def stopJob(jobId):
        self.handleStopJob()


if __name__ == '__main__':
    cfg = SlaveConfig()
    cfg.nodeName = 'testMaster:testSlave'
    cfg.jobQueueName = 'job1.0.3-0.5-14:x86'
    slave = JobSlave(cfg)
    slave.run()
