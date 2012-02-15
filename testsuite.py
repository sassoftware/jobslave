#!/usr/bin/python
# -*- mode: python -*-
#
# Copyright (c) 2010 rPath, Inc.
#

import sys
import unittest
from jobslave_test import bootstrap
from testrunner import pathManager

EXCLUDED_PATHS = ['dist/', '/build/', 'test', 'setup.py', 'trovebucket.py',
        'gencslist.py', 'scripts', 'pylint']


def setup():
    pathManager.addExecPath('PYOVF_PATH')
    pathManager.addExecPath('RESTLIB_PATH')
    pathManager.addExecPath('PRODUCT_DEFINITION_PATH')
    pathManager.addExecPath('XOBJ_PATH')

    jsPath = pathManager.addExecPath('JOB_SLAVE_PATH', isTestRoot=True)
    pathManager.addResourcePath('JOB_SLAVE_ARCHIVE_PATH',
            path=jsPath + '/jobslave_test/archive')

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
    from jobslave.generators import bootable_image
    bootable_image.BootableImage._orig_status = \
            bootable_image.BootableImage.status
    bootable_image.BootableImage.status = \
            lambda *args, **kwargs: None
    #end MCP specific tweaks

    from conary.lib import util
    sys.excepthook = util.genExcepthook(True, catchSIGUSR1=False)



def main(argv=None):
    from testrunner import testhelp, pathManager
    class rBuilderTestSuiteHandler(testhelp.TestSuiteHandler):
        suiteClass = testhelp.ConaryTestSuite

        def getCoverageDirs(self, environ):
            return pathManager.getPath('JOB_SLAVE_PATH')

        def getCoverageExclusions(self, environ):
            return EXCLUDED_PATHS

    global _handler
    if argv is None:
        argv = list(sys.argv)

    _handler = rBuilderTestSuiteHandler(individual=False)
    results = _handler.main(argv)
    return results.getExitCode()


_individual = False


if __name__ == '__main__':
    setup()
    sys.exit(main(sys.argv))
