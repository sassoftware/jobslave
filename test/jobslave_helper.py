#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import os, sys
import testhelp

import subprocess
import threading
import tempfile

from cStringIO import StringIO
from jobslave import jobhandler, slave, constants, generators
from conary.lib import util

class DummyConnection(object):
    def __init__(self, *args, **kwargs):
        self.sent = []
        self.listeners = []
        self.subscriptions = []
        self.unsubscriptions = []
        self.acks = []

    def send(self, dest, message):
        self.sent.insert(0, (dest, message))

    def receive(self, message):
        for listener in self.listeners:
            listener.receive(message)

    def subscribe(self, dest, ack = 'auto'):
        if dest.startswith('/queue/'):
            assert ack == 'client', 'Queue will not be able to refuse a message'
        self.subscriptions.insert(0, dest)

    def unsubscribe(self, dest):
        self.unsubscriptions.insert(0, dest)

    def addlistener(self, listener):
        if listener not in self.listeners:
            self.listeners.append(listener)

    def dellistener(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def start(self):
        pass

    def ack(self, messageId):
        self.acks.append(messageId)

    def insertMessage(self, message):
        message = 'message-id: dummy-message\n\n\n' + message
        self.receive(message)

    def disconnect(self):
        pass

class DummyResponse(object):
    response = DummyConnection()

class ThreadedJobSlave(slave.JobSlave, threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        slave.JobSlave.__init__(self, *args, **kwargs)

    def disconnect(self):
        self.imageServer.running = False

class JobSlaveHelper(testhelp.TestCase):
    def setUp(self):
        testhelp.TestCase.setUp(self)

        self.slaveCfg = slave.SlaveConfig()
        self.slaveCfg.configLine('TTL 0')
        self.slaveCfg.configLine('imageTimeout 0')
        self.slaveCfg.configLine('namespace test')
        self.slaveCfg.configLine('nodeName testMaster:testSlave')
        self.slaveCfg.configLine('jobQueueName job3.0.0:x86')
        self.jobSlave = ThreadedJobSlave(self.slaveCfg)

        self.finishedDir = tempfile.mkdtemp(prefix="jobslave-test-finished-images")
        self.entDir = tempfile.mkdtemp(prefix="jobslave-test-ent")
        generators.constants.finishedDir = self.finishedDir
        generators.constants.entDir = self.entDir

    def tearDown(self):
        util.rmtree(self.finishedDir)
        util.rmtree(self.entDir)
        self.jobSlave.imageServer.stop()
        testhelp.TestCase.tearDown(self)

    def getHandler(self, buildType):
        return jobhandler.getHandler( \
            {'serialVersion': 1,
             'type' : 'build',
             'project' : {'name': 'Foo',
                          'hostname' : 'foo',
                          'label': 'foo.rpath.local@rpl:devel',
                          'conaryCfg': ''},
             'UUID' : 'mint.rpath.local-build-25',
             'troveName' : 'group-core',
             'troveVersion' : '/conary.rpath.com@rpl:1/0:1.0.1-1-1',
             'troveFlavor': '1#x86',
             'data' : {'jsversion': '3.0.0'},
             'outputQueue': 'test',
             'entitlements': {'conary.rpath.com': ('class', 'key')},
             'buildType' : buildType},
            self.jobSlave)

    def supressOutput(self, func, *args, **kwargs):
        oldErr = os.dup(sys.stderr.fileno())
        oldOut = os.dup(sys.stdout.fileno())
        fd = os.open(os.devnull, os.W_OK)
        os.dup2(fd, sys.stderr.fileno())
        os.dup2(fd, sys.stdout.fileno())
        os.close(fd)
        try:
            return func(*args, **kwargs)
        finally:
            os.dup2(oldErr, sys.stderr.fileno())
            os.dup2(oldOut, sys.stdout.fileno())


class ExecuteLoggerTest(JobSlaveHelper):
    def setUp(self):
        self.oldOsSystem = os.system
        self.oldSubprocessCall = subprocess.call
        self.callLog = []

        def osSystem(cmd):
            self.callLog.append(cmd)

        def subprocessCall(cmd, **kwargs):
            self.callLog.append(cmd)
            return 0

        os.system = osSystem
        subprocess.call = subprocessCall
        JobSlaveHelper.setUp(self)

    def injectPopen(self, output):
        self.oldPopen = os.popen
        cs = StringIO()
        cs.write(output)
        cs.seek(0)

        def popen(cmd):
            os.popen = self.oldPopen
            return cs

        os.popen = popen

    def tearDown(self):
        JobSlaveHelper.tearDown(self)
        os.system = self.oldOsSystem
        subprocess.call = self.oldSubprocessCall

    def reset(self):
        self.callLog = []
