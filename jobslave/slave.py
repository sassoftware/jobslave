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

from conary.repository.transport import XMLOpener
import urllib
import xmlrpclib

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
    conaryProxy = (cfgtypes.CfgString, None)
    watchdog = (cfgtypes.CfgBool, True)

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

def alwaysExit(func):
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except:
            exc_class, exc, bt = sys.exc_info()
            print >> sys.stderr, "%s %s" % ("Uncaught Exception: (" + \
                exc.__class__.__name__ + ')', str(exc))
            print >> sys.stderr, '\n'.join(traceback.format_tb(bt))
            os._exit(1)
        else:
            os._exit(0)
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

    @alwaysExit
    def run(self):
        if self.cfg.watchdog:
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
            mcpClient.stopSlave(self.cfg.nodeName)
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

    def getBestProtocol(self, protocols):
        common = PROTOCOL_VERSIONS.intersection(protocols)
        return common and max(common) or 0

    def sendSlaveStatus(self):
        self.response.slaveStatus(self.cfg.nodeName,
                                  slavestatus.ACTIVE,
                                  self.cfg.jobQueueName.replace('job', ''),
                                  jobId = self.jobData['UUID'])

    def sendJobStatus(self):
        if self.jobHandler:
            self.jobHandler.status()

    def handleStopJob(self, jobId):
        # ensure the jobId matches the jobId we're actually servicing to prevent
        # race conditions from killing the wrong job.
        if self.jobHandler and (jobId == self.jobHandler.jobId):
            self.jobHandler.kill()

    def postJobOutput(self, jobId, buildId, destUrl, outputToken, files):
        opener = XMLOpener()

        filenames = []
        destUrl += '/uploadBuild/%d/%s' % (buildId, os.path.basename(fn))
        for fn, desc in files:
            size = os.stat(fn)[stat.ST_SIZE]

            sha1 = sha.new()
            httpPutFile(destUrl, fn, size, chunked = True,
                extraHeaders = {'X-rBuilder-OutputToken': outputToken},
                digest = sha1)

            sha1 = sha1ToString(sha1.digest())
            filenames.append((fn, desc, size, sha1))
            logging.info("wrote %d bytes of %s (%s)" % (size, fn, sha1))

        rba = xmlrpclib.ServerProxy("%s/xmlrpc/" % destUrl)
        r = rba.setBuildFilenamesSafe(buildId, outputToken, filenames)
        if r[0]:
            raise RuntimeError(str(r[1]))

        self.response.jobStatus(jobId, jobstatus.FINISHED, 'Job Finished')

    def postAmiOutput(self, jobId, buildId, destUrl, outputToken, amiId,
            amiManifestName):
        rba = xmlrpclib.ServerProxy("%s/xmlrpc/" % destUrl)
        r = rba.setBuildAmiDataSafe(buildId, outputToken, amiId,
                amiManifestName)
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


def httpPutFile(url, inFile, size, rateLimit = None,
                proxies = None, chunked=False,
                extraHeaders = {}, digest = None):
    """
    Send a file to a url.
    """

    protocol, uri = urllib.splittype(url)
    assert(protocol in ('http', 'https'))

    opener = XMLOpener(proxies=proxies)
    c, urlstr, selector, headers = opener.createConnection(uri,
        ssl = (protocol == 'https'), withProxy=True)

    BUFSIZE = 8192

    c.connect()
    c.putrequest("PUT", selector)

    headers.update(extraHeaders)
    for k, v in headers:
        c.putheader(k, v)

    if chunked:
        c.putheader('Transfer-Encoding', 'chunked')
        c.endheaders()

        total = 0
        while size:
            # send in 256k chunks
            chunk = 262144
            if chunk > size:
                chunk = size
            # first send the hex-encoded size
            c.send('%x\r\n' %chunk)
            # then the chunk of data
            util.copyfileobj(inFile, c, bufSize = chunk,
                             rateLimit = rateLimit, sizeLimit = chunk,
                             total = total, digest = digest)
            # send \r\n after the chunked data
            c.send("\r\n")
            total =+ chunk
            size -= chunk
        # terminate the chunked encoding
        c.send('0\r\n\r\n')
    else:
        c.putheader('Content-length', str(size))
        c.endheaders()

        util.copyfileobj(inFile, c, bufSize = BUFSIZE, rateLimit = rateLimit,
                         sizeLimit = size, digest = digest)

    resp = c.getresponse()
    c.close()
    return resp.status, resp.reason


def main():
    cfg = SlaveConfig()
    cfg.read(os.path.join(os.path.sep, 'srv', 'jobslave', 'config'))
    jobStr = open(os.path.join(os.path.sep, 'srv', 'jobslave', 'data')).read()
    jobData = simplejson.loads(jobStr)
    slave = JobSlave(cfg, jobData)
    slave.run()
