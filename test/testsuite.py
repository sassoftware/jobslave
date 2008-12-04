#!/usr/bin/python2.4
# -*- mode: python -*-
#
# Copyright (c) 2004-2006 rPath, Inc.
#

import bdb
import cPickle
import grp
import sys
import os
import os.path
import pwd
import socket
import re
import tempfile
import time
import types
import unittest
import __builtin__

testPath = None

#from pychecker import checker

def enforceBuiltin(result):
    failure = False
    if isinstance(result, (list, tuple)):
        for item in result:
            failure = failure or enforceBuiltin(item)
    elif isinstance(result, dict):
        for item in result.values():
            failure = failure or enforceBuiltin(item)
    failure =  failure or (result.__class__.__name__ \
                           not in __builtin__.__dict__)
    return failure

def filteredCall(self, *args, **kwargs):
    isException, result = self._server.callWrapper(self._name,
                                                   self._authToken, args)

    if not isException:
        if enforceBuiltin(result):
            # if the return type appears to be correct, check the types
            # some items get cast to look like built-ins for str()
            # an extremely common example is sql result rows.
            raise AssertionError('XML cannot marshall return value: %s '
                                 'for method %s' % (str(result), self._name))
        return result
    else:
        self.handleError(result)

conaryDir = None
_setupPath = None
def setup():
    global _setupPath
    if _setupPath:
        return _setupPath
    global testPath

    if not os.environ.has_key('CONARY_PATH'):
        print "please set CONARY_PATH"

    conaryPath      = os.getenv('CONARY_PATH')
    conaryTestPath  = os.getenv('CONARY_TEST_PATH',     os.path.join(conaryPath, '..', 'conary-test'))
    mcpPath         = os.getenv('MCP_PATH',             '../../mcp')
    jobslavePath    = os.getenv('JOB_SLAVE_PATH',       os.path.join(os.getcwd(), '..'))
    jsTestPath      = os.getenv('JOB_SLAVE_TEST_PATH',  os.getcwd())
    testUtilsPath   = os.getenv('TESTUTILS_PATH', os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    sys.path = [os.path.realpath(x) for x in (jobslavePath, jsTestPath, mcpPath,
        conaryPath, conaryTestPath, testUtilsPath)] + sys.path
    os.environ.update(dict(CONARY_PATH=conaryPath, CONARY_TEST_PATH=conaryTestPath,
        MCP_PATH=mcpPath, JOB_SLAVE_PATH=jobslavePath, JOB_SLAVE_TEST_PATH=jsTestPath,
        PYTHONPATH=(':'.join(sys.path))))

    from testrunner import testhelp
    testPath = testhelp.getTestPath()

    global conaryDir
    conaryDir = os.environ['CONARY_PATH']

    from conary.lib import util
    sys.excepthook = util.genExcepthook(True)

    # if we're running with COVERAGE_DIR, we'll start covering now
    from conary.lib import coveragehook

    # import tools normally expected in findTrove.
    from testrunner.testhelp import context, TestCase, findPorts, SkipTestException
    sys.modules[__name__].context = context
    sys.modules[__name__].TestCase = TestCase
    sys.modules[__name__].findPorts = findPorts
    sys.modules[__name__].SkipTestException = SkipTestException

    # MCP specific tweaks
    import jobslave_helper
    import stomp
    stomp.Connection = jobslave_helper.DummyConnection
    from jobslave.generators import bootable_image
    bootable_image.BootableImage._orig_status = \
            bootable_image.BootableImage.status
    bootable_image.BootableImage.status = \
            lambda *args, **kwargs: None
    #end MCP specific tweaks

    from testrunner.runner import setup as runnerSetup
    runnerSetup()

    _setupPath = testPath
    return testPath

_individual = False

def isIndividual():
    global _individual
    return _individual


EXCLUDED_PATHS = ['dist/', '/build/', 'test', 'setup.py', 'trovebucket.py', 'gencslist.py']

def main(argv=None, individual=True):
    from testrunner import testhelp
    testhelp.isIndividual = isIndividual
    class rBuilderTestSuiteHandler(testhelp.TestSuiteHandler):
        suiteClass = testhelp.ConaryTestSuite

        def getCoverageDirs(self, environ):
            return os.environ['JOB_SLAVE_PATH']

        def getCoverageExclusions(self, environ):
            return EXCLUDED_PATHS

    global _handler
    global _individual
    _individual = individual
    if argv is None:
        argv = list(sys.argv)
    topdir = testhelp.getTestPath()
    cwd = os.getcwd()
    if topdir not in sys.path:
        sys.path.insert(0, topdir)
    if cwd != topdir and cwd not in sys.path:
        sys.path.insert(0, cwd)

    handler = rBuilderTestSuiteHandler(individual=individual, topdir=topdir,
                                       testPath=testPath, conaryDir=conaryDir)
    _handler = handler
    results = handler.main(argv)
    return (not results.wasSuccessful())

if __name__ == '__main__':
    setup()
    sys.exit(main(sys.argv, individual=False))
