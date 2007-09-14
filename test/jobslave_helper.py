#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import os, sys
import testhelp

import simplejson
import subprocess
import threading
import tempfile

from cStringIO import StringIO
from jobslave import jobhandler, slave, constants, generators
from jobslave import imagegen
from jobslave import buildtypes
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


class JobSlaveHelper(testhelp.TestCase):
    def setUp(self):
        testhelp.TestCase.setUp(self)

        self.slaveCfg = slave.SlaveConfig()
        self.slaveCfg.configLine('namespace test')
        self.slaveCfg.configLine('nodeName testMaster:testSlave')
        self.slaveCfg.configLine('jobQueueName job3.0.0:x86')
        self.slaveCfg.configLine('debugMode True')

        f = open ('archive/jobdata.txt')
        self.jobSlave = ThreadedJobSlave(self.slaveCfg,
                simplejson.loads(f.read()))
        f.close()

        self.finishedDir = tempfile.mkdtemp(prefix="jobslave-test-finished-images")
        self.entDir = tempfile.mkdtemp(prefix="jobslave-test-ent")
        generators.constants.finishedDir = self.finishedDir
        generators.constants.entDir = self.entDir

        self.testDir = os.path.join(os.path.dirname(os.path.abspath(__file__)))

        import logging
        log = logging.getLogger()
        logging.DEBUG = logging.FATAL
        log.setLevel(logging.FATAL)

        # make sure we always delete mkdtemp directories
        self.mkdCreated = []
        self.realMkdtemp = tempfile.mkdtemp

        def fakeMkdtemp(*args, **kwargs):
            kwargs["prefix"] = self._TestCase__testMethodName
            d = self.realMkdtemp(*args, **kwargs)
            self.mkdCreated.append(d)
            return d
        tempfile.mkdtemp = fakeMkdtemp

    def tearDown(self):
        self.suppressOutput(util.rmtree, self.finishedDir, ignore_errors = True)
        self.suppressOutput(util.rmtree, self.entDir, ignore_errors = True)

        for x in self.mkdCreated:
            self.suppressOutput(util.rmtree, x, ignore_errors = True)
        tempfile.mkdtemp = self.realMkdtemp

        testhelp.TestCase.tearDown(self)

    def getHandler(self, buildType):
        data = {
            'protocolVersion': 1,
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
            'name': 'Test Project',
            'entitlements': {'conary.rpath.com': ('class', 'key')},
            'buildType' : buildType}
        if buildType == buildtypes.AMI:
            data['amiData'] = {'ec2S3Bucket' : 'fake_s3_bucket',
                    'ec2Certificate' : 'fake_ec2_certificate',
                    'ec2CertificateKey' : 'fake_ec2_cert_key',
                    'ec2AccountId' : 'fake_ec2_account_id',
                    'ec2PublicKey' : 'fake_public_key',
                    'ec2PrivateKey' : 'fake_private_key',
                    'ec2LaunchGroups' : True,
                    'ec2LaunchUsers' : True}
        return jobhandler.getHandler(data, self.jobSlave)

    def suppressOutput(self, func, *args, **kwargs):
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

    def touch(self, fn, contents = ''):
        if not os.path.exists(fn):
            util.mkdirChain(os.path.split(fn)[0])
            f = open(fn, 'w')
            f.write(contents)
            f.close()

class ExecuteLoggerTest(JobSlaveHelper):
    def setUp(self):
        self.oldOsSystem = os.system
        self.oldSubprocessCall = subprocess.call
        self.oldSubprocessPopen = subprocess.Popen
        self.callLog = []
        self.mkdirs = []

        def osSystem(cmd):
            self.callLog.append(cmd)

        def subprocessCall(cmd, **kwargs):
            self.callLog.append(cmd)
            return 0

        def logCall(cmd, **kwargs):
            self.callLog.append(cmd)
            return 0

        class FakePopen:
            def __init__(self2, cmd, *args, **kwargs):
                self.callLog.append(cmd)
                self2.stderr = StringIO()
                self2.stdout = StringIO()
                self2.returncode = 0

            def poll(self2):
                return True

            def wait(self):
                return 0

        os.system = osSystem
        subprocess.call = subprocessCall
        subprocess.Popen = FakePopen
        JobSlaveHelper.setUp(self)

    def injectPopen(self, output):
        self.oldPopen = os.popen
        self.oldUtilPopen = util.popen
        def popen(cmd, mode = 'w'):
            cs = StringIO()
            cs.write(output)
            cs.seek(0)
            return cs

        os.popen = popen
        util.popen = popen

    def resetPopen(self):
        os.popen = self.oldPopen
        util.popen = self.oldUtilPopen

    def tearDown(self):
        JobSlaveHelper.tearDown(self)
        os.system = self.oldOsSystem
        subprocess.call = self.oldSubprocessCall
        subprocess.Popen = self.oldSubprocessPopen

    def reset(self):
        self.callLog = []
