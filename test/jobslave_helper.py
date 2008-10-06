#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import logging
import os
import signal
import simplejson
import subprocess
import sys
import threading
import tempfile

import testhelp

from conary.lib import util
from conary.lib import log as conary_log
from cStringIO import StringIO
from mcp import mcp_log

from jobslave import jobhandler, slave, constants, generators
from jobslave import imagegen
from jobslave import buildtypes


log = logging.getLogger('')


class DummyConnection(object):
    def __init__(self, *args, **kwargs):
        self.sent = []
        self.listeners = []
        self.subscriptions = []
        self.unsubscriptions = []
        self.acks = []

    def send(self, message, destination):
        self.sent.insert(0, (destination, message))

    def on_message(self, headers, message):
        for listener in self.listeners:
            listener.on_message(headers, message)

    def subscribe(self, destination, ack = 'auto'):
        if destination.startswith('/queue/'):
            assert ack == 'client', 'Queue will not be able to refuse a message'
        self.subscriptions.insert(0, destination)

    def unsubscribe(self, dest):
        self.unsubscriptions.insert(0, dest)

    def add_listener(self, listener):
        if listener not in self.listeners:
            self.listeners.append(listener)

    def dellistener(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def start(self):
        pass

    def connect(self):
        pass

    def is_connected(self):
        return True

    def ack(self, messageId):
        self.acks.append(messageId)

    def insertMessage(self, message):
        message = 'message-id: dummy-message\n\n\n' + message
        self.on_message({}, message)

    def disconnect(self):
        pass

class DummyResponse(object):
    response = DummyConnection()

class ThreadedJobSlave(slave.JobSlave, threading.Thread):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        slave.JobSlave.__init__(self, *args, **kwargs)


class DummyHandler(logging.Handler):
    '''
    Dummy log handler. Eats all messages.
    '''
    def emit(self, record):
        # om nom nom nom
        pass


class JobSlaveHelper(testhelp.TestCase):
    def setUp(self):
        testhelp.TestCase.setUp(self)

        self.slaveCfg = slave.SlaveConfig()
        self.slaveCfg.configLine('namespace test')
        self.slaveCfg.configLine('nodeName testMaster:testSlave')
        self.slaveCfg.configLine('jobQueueName job3.0.0:x86')
        self.slaveCfg.configLine('debugMode True')

        f = open ('archive/jobdata.txt')
        _signal = signal.signal
        try:
            signal.signal = lambda x, y: None
            self.jobSlave = ThreadedJobSlave(self.slaveCfg,
                    simplejson.loads(f.read()))
        finally:
            signal.signal = _signal
            f.close()

        self.finishedDir = tempfile.mkdtemp(prefix="jobslave-test-finished-images")
        self.entDir = tempfile.mkdtemp(prefix="jobslave-test-ent")
        generators.constants.finishedDir = self.finishedDir
        generators.constants.entDir = self.entDir

        self.testDir = os.path.join(os.path.dirname(os.path.abspath(__file__)))

        # Suppress warning messages logged during tests since they are
        # supposed to be exercising these paths.
        conary_log.setVerbosity(conary_log.ERROR)

        # Neuter a few functions that might result in unwanted output
        # during the testsuite run:
        # - don't let conary set the loglevel when cooking
        conary_log.setVerbosity = lambda x: None
        # - add a dummy handler so that logging doesn't open a
        #   default one
        log.addHandler(DummyHandler())

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

        # Sanity check: make sure no-one other than us has a reference
        # to the jobslave (the second reference is from the copy we're
        # passing to getrefcount)
        references = sys.getrefcount(self.jobSlave) - 2
        if references:
            print "WARNING: %d extra references to jobslave."
            print "Expect unfreed resources!"

        # Delete our reference to the jobslave now so that any
        # resources it holds are freed and we can check for stragglers.
        del self.jobSlave

        # Make sure logfiles get closed
        for handler in log.handlers:
            log.removeHandler(handler)
            if isinstance(handler, DummyHandler):
                continue

            print 'WARNING: Handler %r left open' % handler
            try:
                handler.close()
            except:
                import traceback
                exc_data = sys.exc_info()
                print '... and failed to close:'
                print ''.join(traceback.format_exception_only(*exc_data))
                del exc_data

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
            os.close(oldErr)
            os.close(oldOut)

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

            def communicate(self):
                return ('', '')

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
