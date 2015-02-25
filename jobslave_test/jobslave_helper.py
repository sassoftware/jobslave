#
# Copyright (c) SAS Institute Inc.
#

import copy
import logging
import os
import subprocess
import sys
import tempfile

from conary_test.rephelp import RepositoryHelper as TestCase

from conary.lib import util
from conary.lib import log as conary_log
from cStringIO import StringIO

from jobslave import jobhandler, slave, generators
from jobslave import buildtypes

log = logging.getLogger()


class DummyHandler(logging.Handler):
    '''
    Dummy log handler. Eats all messages.
    '''
    def emit(self, record):
        # om nom nom nom
        pass


class DummyResponse(object):

    def sendStatus(self, code, message):
        pass

    def sendLog(self, data):
        pass

    def postOutput(self, fileList, withMetadata=None, attributes=None):
        pass


class JobSlaveHelper(TestCase):

    Data = {
        'protocolVersion'   : 1,
        'type'              : 'build',
        'project'           : {'name'       : 'Foo',
                               'hostname'   : 'foo',
                               'label'      : 'foo.rpath.local@rpl:devel',
                               'conaryCfg'  : ''},
        'UUID'              : 'mint.rpath.local-build-25',
        'buildId'           : 25,
        'outputToken'       : '580466f08ddfcfa130ee85f2d48c61ced992d4d4',
        'troveName'         : 'group-core',
        'troveVersion'      : '/conary.rpath.com@rpl:1/0:1.0.1-1-1',
        'troveFlavor'       : '1#x86',
        'projectLabel'      : 'conary.rpath.com@rpl:1',
        'data'              : {
            'jsversion': '3.0.0',
            },
        'outputQueue'       : 'test',
        'name'              : 'Test Project',
        'entitlements'      : {'conary.rpath.com': ('class', 'key')},
        'buildType'         : None,
        'proxy'             : 
            {'http'     : 'http://jim:bar@proxy.example.com:888/',
             'https'    : 'https://jim:bar@proxy.example.com:888/',},
        'imageModel': [
            'install "group-core=/conary.rpath.com@rpl:1/1.0.1-1-1[is: x86]"\n',
            ],
        }

    amiData = {'amiData': {
                'ec2S3Bucket'       : 'fake_s3_bucket',
                'ec2Certificate'    : 'fake_ec2_certificate',
                'ec2CertificateKey' : 'fake_ec2_cert_key',
                'ec2AccountId'      : 'fake_ec2_account_id',
                'ec2PublicKey'      : 'fake_public_key',
                'ec2PrivateKey'     : 'fake_private_key',
                'ec2LaunchGroups'   : True,
                'ec2LaunchUsers'    : True}
              }

    def setUp(self):
        TestCase.setUp(self)

        self.slaveCfg = slave.SlaveConfig()
        self.slaveCfg.configLine('debugMode True')
        self.slaveCfg.configLine('masterUrl http://no.master/api/')

        self.finishedDir = os.path.join(self.tmpDir, "finished-images")
        self.entDir = os.path.join(self.tmpDir, "entitlements")
        generators.constants.tmpDir = os.path.join(self.tmpDir, 'tmp')
        for d in [ self.finishedDir, self.entDir, generators.constants.tmpDir ]:
            util.mkdirChain(d)
        generators.constants.finishedDir = self.finishedDir
        generators.constants.entDir = self.entDir
        self.constants = generators.constants

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
            kwargs['prefix'] = 'test'
            d = self.realMkdtemp(*args, **kwargs)
            self.mkdCreated.append(d)
            return d
        tempfile.mkdtemp = fakeMkdtemp

        data = self.data = copy.deepcopy(self.Data)
        data['project']['conaryCfg'] = 'root %s/_ROOT_' % self.cfg.root

    def tearDown(self):
        self.suppressOutput(util.rmtree, self.finishedDir, ignore_errors = True)
        self.suppressOutput(util.rmtree, self.entDir, ignore_errors = True)

        for x in self.mkdCreated:
            self.suppressOutput(util.rmtree, x, ignore_errors = True)
        tempfile.mkdtemp = self.realMkdtemp

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
                print ''.join(traceback.format_exception_only(*exc_data[:2]))
                del exc_data

        TestCase.tearDown(self)

    def getHandler(self, buildType):
        self.data['buildType'] = buildType
        if buildType == buildtypes.AMI:
            self.data.update(self.amiData)
        handler = jobhandler.getHandler(self.slaveCfg, self.data)
        handler.response = DummyResponse()
        return handler

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
                if 'env' in kwargs:
                    self.callLog.append((cmd, kwargs['env']))
                else:
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
