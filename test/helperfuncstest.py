#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import copy
import os
import sys
import tempfile

from jobslave.slave import watchdog
from jobslave import helperfuncs
from jobslave import imagegen

class HelperFunctionsTest(testsuite.TestCase):
    def captureAllOutput(self, func, *args, **kwargs):
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

    def testWatchdog(self):
        self.dummyPid = 3
        self.commands = []

        def dummySystem(*args, **kwargs):
            print args, kwargs
            sys.stdout.flush()

        system = os.system
        fork = os.fork
        _exit = os._exit
        getppid = os.getppid
        def dummyGetppid():
            self.dummyPid -= 1
            return self.dummyPid

        def dummySystem(command):
            self.commands.append(command)

        try:
            os.system = dummySystem
            os.fork = lambda: 0
            os._exit = lambda x: None
            os.getppid = dummyGetppid
            self.captureAllOutput(watchdog)
            self.failIf(self.commands != ['poweroff -h'],
                        "shutdown command not issued")
        finally:
            os.system = system
            os.fork = fork
            os._exit = _exit
            os.getppid = getppid

    def testScrubUnicode(self):
        data = {u'string' : u'val1',
                u'dict' : { 'subkey' : u'subval'},
                u'list' : [u'foo'],
                u'set' : set([u'bar']),
                u'tuple' : (u'baz',),
                'normal': 'not unicode',
                'double_nest': [[u'foo']],
                'unicode' : u'Andr\xe9'}
        orig = copy.deepcopy(data)
        res = imagegen.scrubUnicode(data)
        self.failIf(data != orig,
                "scrubUnicode caused side effects on orginal data")

        self.failIf(type(res['string']) is unicode,
                "failed to cast direct key/val")
        self.failIf(type(res['dict']['subkey']) is unicode,
                "failed to cast dict key/val")
        self.failIf(type(res['list'][0]) is unicode,
                "failed to cast list items")
        self.failIf(type([x for x in res['set']][0]) is unicode,
                "failed to cast set items")
        self.failIf(type(res['tuple'][0]) is unicode,
                "failed to cast tuple items")
        self.failIf('normal' not in res, "non unicode item was not included")
        self.failIf(type(res['double_nest'][0][0]) is unicode,
                "failed to cast nested iterable items")
        self.failIf(res['unicode'] != 'Andr?',
                "Unsafe replacement mode for unicode")

    def testGetIp(self):
        refIP = '127.0.0.1'
        class MockPipe(object):
            def read(x):
                return '%s\n' % refIP
            close = lambda *args: None
        popen = os.popen
        try:
            os.popen = lambda *args, **kwargs: MockPipe()
            IP = helperfuncs.getIP()
            self.failIf(IP != refIP, "expected %s, but got %s" % (refIP, IP))
        finally:
            os.popen = popen

    def testGetSlaveRuntimeConfig(self):
        fd, tmpFile = tempfile.mkstemp()
        os.close(fd)
        f = open(tmpFile, 'w')
        f.write('\n'.join(('# test',
            '     a  = b', ' test = 1 ')))
        f.close()
        res = helperfuncs.getSlaveRuntimeConfig(cfgPath = tmpFile)
        ref = {'a': 'b', 'test': '1'}
        self.failIf(res != ref, "expected %s but got %s" % \
                (str(ref), str(res)))

    def testGetMissingSlaveConfig(self):
        tmpDir = tempfile.mkdtemp()
        tmpFile = os.path.join(tmpDir, 'missing')
        res = helperfuncs.getSlaveRuntimeConfig(cfgPath = tmpFile)
        ref = {}
        self.failIf(res != ref, "expected %s but got %s" % \
                (str(ref), str(res)))


if __name__ == "__main__":
    testsuite.main()
