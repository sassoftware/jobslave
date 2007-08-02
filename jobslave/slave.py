#
# Copyright (c) 2007 rPath, Inc.
#
# All rights reserved
#

import os, sys
import time
import sha
import simplejson
import stat
import httplib
import signal
import traceback
import urlparse
import logging

from jobslave import jobhandler
from jobslave.generators import constants
from jobslave.helperfuncs import getIP, getSlaveRuntimeConfig

from mcp import client, queue, response, jobstatus, slavestatus

from conary.lib import cfgtypes, util
from conary.lib.sha1helper import sha1ToString

PROTOCOL_VERSIONS = set([1])
BUFFER = 256 * 1024

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
    def __init__(self, cfg, jobData):
        self.cfg = cfg
        self.jobData = jobData
        #assert None not in cfg.values()

        self.controlTopic = queue.Topic(cfg.queueHost, cfg.queuePort,
                                       'control', namespace = cfg.namespace,
                                       timeOut = 0)

        self.jobControlQueue = queue.Queue( \
            self.cfg.queueHost, self.cfg.queuePort, jobData['UUID'],
            namespace = self.cfg.namespace, timeOut = 0)

        self.response = response.MCPResponse(self.cfg.nodeName, cfg)
        signal.signal(signal.SIGTERM, self.catchSignal)
        signal.signal(signal.SIGINT, self.catchSignal)

    def catchSignal(self, *args):
        self.running = False

    def run(self):
        watchdog()
        UUID = self.jobData['UUID']
        print "serving job: %s" % UUID
        self.running = True
        try:
            self.jobHandler = jobhandler.getHandler(self.jobData, self)
            self.jobHandler.start()
        except Exception, e:
            self.jobHandler = None
            print "Error starting job:", e
            exc_class, exc, bt = sys.exc_info()
            print ''.join(traceback.format_tb(bt))
            self.response.jobStatus(UUID, jobstatus.FAILED,
                                    'Image creation error: %s' % str(e))
            self.running = False
        else:
            self.sendSlaveStatus()

        try:
            while self.running:
                self.checkControlTopic()
                self.running = self.jobHandler.isAlive()
                time.sleep(0.1)
        finally:
            self.disconnect()

    def disconnect(self):
        if self.jobHandler:
            self.jobHandler.kill()
        try:
            # client can fail to be instantiated if stompserver is not running
            mcpClient = client.MCPClient(self.cfg)
            mcpClient.stopSlave(self.cfg.nodeName, delayed = False)
        except:
            # mask all errors. we're about to shutdown anyways
            pass
        self.controlTopic.disconnect()
        self.response.response.disconnect()
        del self.response
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
                                  slavestatus.ACTIVE,
                                  self.cfg.jobQueueName.replace('job', ''))

    def sendJobStatus(self):
        if self.jobHandler:
            self.jobHandler.status()

    def handleStopJob(self, jobId):
        # ensure the jobId matches the jobId we're actually servicing to prevent
        # race conditions from killing the wrong job.
        if self.jobHandler and (jobId == self.jobHandler.jobId):
            self.jobHandler.kill()

    def recordJobOutput(self, jobId, UUID):
        self.imageIdle = time.time()
        self.outstandingJobs[jobId] = UUID

    def postJobOutput(self, jobId, buildId, destUrl, outputToken, files):
        from conary.repository.transport import XMLOpener
        import urllib
        import xmlrpclib

        opener = XMLOpener()

        filenames = []
        for fn, desc in files:
            protocol, uri = urllib.splittype(destUrl + 'uploadBuild/%d/%s' % \
                (buildId, os.path.basename(fn)))
            c, urlstr, selector, headers = opener.createConnection(str(uri),
                ssl = (protocol == "https"))

            c.connect()
            c.putrequest("PUT", selector)

            size = os.stat(files[0][0])[stat.ST_SIZE]
            c.putheader('Content-length', str(size))
            c.putheader('X-rBuilder-OutputToken', outputToken)
            c.endheaders()

            sha1 = sha.new()
            f = open(fn)
            l = util.copyfileobj(f, c, digest = sha1)

            sha1 = sha1ToString(sha1.digest())
            filenames.append((fn, desc, size, sha1))
            logging.info("wrote %d bytes of %s (%s)" % (l, fn, sha1))

        rba = xmlrpclib.ServerProxy("%s/xmlrpc/" % destUrl)
        r = rba.setBuildFilenamesSafe(buildId, outputToken, filenames)
        if r[0]:
            raise RuntimeError(str(r[1]))

        self.response.jobStatus(jobId, jobstatus.FINISHED, 'Job Finished')

    @controlMethod
    def checkVersion(self, protocols):
        self.response.protocol(self.getBestProtocol(protocols))

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
    jobStr = open(os.path.join(os.path.sep, 'srv', 'jobslave', 'data')).read()
    jobData = simplejson.loads(jobStr)
    slave = JobSlave(cfg, jobData)
    slave.run()
