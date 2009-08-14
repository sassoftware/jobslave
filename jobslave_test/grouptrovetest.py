#!/usr/bin/python
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import os
import tempfile

from jobslave.generators import constants
from jobslave.generators import group_trove

import jobslave_helper
import image_stubs

from conary.lib import util
from conary import checkin
from conary import conarycfg
from conary import conaryclient
from conary.build import cook
from conary.build.errors import GroupPathConflicts
from conary.deps import deps
from conary import versions

class TroveInGroupTest(jobslave_helper.JobSlaveHelper):
    def testNoVersion(self):
        name = 'test'
        version = ''
        flavor = '1#x86'
        trvItems = [{'trvName': 'test', 'useLock': False, 'instSetLock': False}]
        res = group_trove.troveInGroup(trvItems, name, version, flavor)
        self.failIf(not res, "trove should have matched")

    def testLockedIS(self):
        name = 'test'
        version = '/test.rpath.local@rpl:1/1-1-1'
        flavor = '1#x86'
        trvItems = [{'trvName': 'test', 'useLock': False, 'instSetLock': True,
            'trvFlavor': 'is: x86', 'trvVersion': version, 'versionLock': True}]
        res = group_trove.troveInGroup(trvItems, name, version, flavor)
        self.failIf(not res, "trove should have matched")

    def testLockedUse(self):
        name = 'test'
        version = '/test.rpath.local@rpl:1/1-1-1'
        flavor = '1#x86|5#use:domU:xen'
        trvItems = [{'trvName': 'test', 'useLock': True, 'instSetLock': False,
            'trvFlavor': 'domU,xen',
            'trvLabel': 'test.rpath.local@rpl:1', 'versionLock': False}]
        res = group_trove.troveInGroup(trvItems, name, version, flavor)
        self.failIf(not res, "trove should have matched")

    def testBothLocked(self):
        name = 'test'
        version = '/test.rpath.local@rpl:1/1-1-1'
        flavor = '1#x86|5#use:domU:xen'
        trvItems = [{'trvName': 'test', 'useLock': True, 'instSetLock': True,
            'trvFlavor': 'domU,xen is: x86_64',
            'trvLabel': 'test.rpath.local@rpl:1', 'versionLock': False}]
        res = group_trove.troveInGroup(trvItems, name, version, flavor)
        self.failIf(res, "trove should not have matched")

    def testGetRecipe(self):
        jobData = {'recipeName' : 'group-test',
                'upstreamVersion' : '1.0.0',
                'autoResolve': False,
                'labelPath': ['test.rpath.local@rpl:1',
                    'conary.rpath.com@rpl:1'],
                'removedComponents': ['doc'],
                'troveItems': [{'trvName': 'group-core',
                    'useLock': False,
                    'instLock': False,
                    'versionLock': False,
                    'trvLabel': 'conary.rpath.com@rpl:1',
                    'trvFlavor': 'domU,xen is: x86',
                    'subGroup': 'group-test'},
                    {'trvName': 'trash',
                    'useLock': False,
                    'instLock': False,
                    'versionLock': False,
                    'trvLabel': 'conary.rpath.com@rpl:1',
                    'trvFlavor': '',
                    'subGroup': 'group-test'}]}
        res = group_trove.getRecipe(jobData)
        self.failIf("name = 'group-test'" not in res)
        self.failIf("version = '1.0.0'" not in res)
        self.failIf("autoResolve = False" not in res)
        self.failIf("r.removeComponents(('doc'))" not in res)

class GroupTroveTest2(jobslave_helper.ExecuteLoggerTest):
    bases = {}

    def setUp(self):
        self.messages = []
        self.savedTmpDir = constants.tmpDir
        constants.tmpDir = tempfile.mkdtemp()
        jobslave_helper.ExecuteLoggerTest.setUp(self)

        self.bases['GroupTroveCook'] = group_trove.GroupTroveCook.__bases__
        group_trove.GroupTroveCook.__bases__ = (image_stubs.GeneratorStub,)

        constants.templateDir = os.path.join(os.path.dirname( \
                os.path.dirname(os.path.abspath(__file__))), 'templates')

    def tearDown(self):
        group_trove.GroupTroveCook.__bases__ = self.bases['GroupTroveCook']
        util.rmtree(constants.tmpDir, ignore_errors = True)
        constants.tmpDir = self.savedTmpDir
        jobslave_helper.ExecuteLoggerTest.tearDown(self)

    def testBasicWrite(self):
        jobData = {'recipeName' : 'group-test',
                'upstreamVersion' : '1.0.0',
                'autoResolve': False,
                'labelPath': ['test.rpath.local@rpl:1',
                    'conary.rpath.com@rpl:1'],
                'removedComponents': ['doc'],
                'troveItems': [{'trvName': 'group-core',
                    'useLock': False,
                    'instLock': False,
                    'versionLock': False,
                    'trvLabel': 'conary.rpath.com@rpl:1',
                    'trvFlavor': 'domU,xen is: x86',
                    'subGroup': 'group-test'},
                    {'trvName': 'trash',
                    'useLock': False,
                    'instLock': False,
                    'versionLock': False,
                    'trvLabel': 'conary.rpath.com@rpl:1',
                    'trvFlavor': '',
                    'subGroup': 'group-test'}],
                    'project': {'label': 'test.rpath.local@rpl:1'},
                    'description': ''}
        class FakeClient(object):
            __init__ = lambda *args, **kwargs: None
            getRepos = lambda x, *args, **kwargs: x
            getTroveLeavesByLabel = lambda x, *args, **kwargs: {}
            get = lambda x, *args, **kwargs: x

        ConaryClient = conaryclient.ConaryClient
        checkout = checkin.checkout
        commit = checkin.commit
        cookItem = cook.cookItem
        try:
            cook.cookItem = lambda *args, **kwargs: \
                    [[[]]]
            checkin.commit = lambda *args, **kwargs: None
            checkin.checkout = lambda *args, **kwargs: None
            conaryclient.ConaryClient = FakeClient
            g = group_trove.GroupTroveCook(jobData, [])
            g.conarycfg = conarycfg.ConaryConfiguration()
            g.conarycfg.initializeFlavors = lambda *args, **kwargs: None
            g.write()
        finally:
            cook.cookItem = cookItem
            checkin.commit = commit
            checkin.checkout = checkout
            conaryclient.ConaryClient = ConaryClient

    def testConflictsWrite(self):
        jobData = {'recipeName' : 'group-test',
                'upstreamVersion' : '1.0.0',
                'autoResolve': False,
                'labelPath': ['test.rpath.local@rpl:1',
                    'conary.rpath.com@rpl:1'],
                'removedComponents': ['doc'],
                'troveItems': [{'trvName': 'group-core',
                    'useLock': False,
                    'instLock': False,
                    'versionLock': False,
                    'trvLabel': 'conary.rpath.com@rpl:1',
                    'trvFlavor': 'domU,xen is: x86',
                    'subGroup': 'group-test'},
                    {'trvName': 'trash',
                    'useLock': False,
                    'instLock': False,
                    'versionLock': False,
                    'trvLabel': 'conary.rpath.com@rpl:1',
                    'trvFlavor': '',
                    'subGroup': 'group-test'}],
                    'project': {'label': 'test.rpath.local@rpl:1'},
                    'description': ''}
        class FakeClient(object):
            __init__ = lambda *args, **kwargs: None
            getRepos = lambda x, *args, **kwargs: x
            getTroveLeavesByLabel = lambda x, *args, **kwargs: x
            get = lambda x, *args, **kwargs: x

        class FakeReason(object):
            def __init__(x, reason):
                x.reason = reason
            def getReasonString(x, *args, **kwargs):
                return x.reason

        self.count = 0
        def fakeCook(*args, **kwargs):
            count = self.count
            self.count += 1
            if not count:
                conflicts = {'group-trash':
                        [((('test', versions.VersionFromString('/test.rpath.local@rpl:1/1-1-1'), deps.Flavor()), ('test', versions.VersionFromString('/test.rpath.local@rpl:1/1-1-1'), deps.Flavor())), ('/tmp/trash',))]}
                groupDict = {'group-trash': FakeReason('included to test')}
                raise GroupPathConflicts(conflicts, groupDict)
            else:
                return [[['test', '1', deps.Flavor()]]]
        ConaryClient = conaryclient.ConaryClient
        checkout = checkin.checkout
        commit = checkin.commit
        cookItem = cook.cookItem
        troveInGroup = group_trove.troveInGroup
        try:
            group_trove.troveInGroup = lambda *args, **kwargs: True
            cook.cookItem = fakeCook
            checkin.commit = lambda *args, **kwargs: None
            checkin.checkout = lambda *args, **kwargs: None
            conaryclient.ConaryClient = FakeClient
            g = group_trove.GroupTroveCook(jobData, [])
            g.conarycfg = conarycfg.ConaryConfiguration()
            g.conarycfg.initializeFlavors = lambda *args, **kwargs: None
            g.write()
        finally:
            group_trove.troveInGroup = troveInGroup
            cook.cookItem = cookItem
            checkin.commit = commit
            checkin.checkout = checkout
            conaryclient.ConaryClient = ConaryClient

    def testUnresolvableWrite(self):
        jobData = {'recipeName' : 'group-test',
                'upstreamVersion' : '1.0.0',
                'autoResolve': False,
                'labelPath': ['test.rpath.local@rpl:1',
                    'conary.rpath.com@rpl:1'],
                'removedComponents': ['doc'],
                'troveItems': [{'trvName': 'group-core',
                    'useLock': False,
                    'instLock': False,
                    'versionLock': False,
                    'trvLabel': 'conary.rpath.com@rpl:1',
                    'trvFlavor': 'domU,xen is: x86',
                    'subGroup': 'group-test'},
                    {'trvName': 'trash',
                    'useLock': False,
                    'instLock': False,
                    'versionLock': False,
                    'trvLabel': 'conary.rpath.com@rpl:1',
                    'trvFlavor': '',
                    'subGroup': 'group-test'}],
                    'project': {'label': 'test.rpath.local@rpl:1'},
                    'description': ''}
        class FakeClient(object):
            __init__ = lambda *args, **kwargs: None
            getRepos = lambda x, *args, **kwargs: x
            getTroveLeavesByLabel = lambda x, *args, **kwargs: x
            get = lambda x, *args, **kwargs: x

        class FakeReason(object):
            def __init__(x, reason):
                x.reason = reason
            def getReasonString(x, *args, **kwargs):
                return x.reason

        def fakeCook(*args, **kwargs):
            conflicts = {'group-trash':
                    [((('test', versions.VersionFromString('/test.rpath.local@rpl:1/1-1-1'), deps.Flavor()), ('test', versions.VersionFromString('/test.rpath.local@rpl:1/1-1-1'), deps.Flavor())), ('/tmp/trash',))]}
            groupDict = {'group-trash': FakeReason('included to test')}
            raise GroupPathConflicts(conflicts, groupDict)
        ConaryClient = conaryclient.ConaryClient
        checkout = checkin.checkout
        commit = checkin.commit
        cookItem = cook.cookItem
        troveInGroup = group_trove.troveInGroup
        try:
            group_trove.troveInGroup = lambda *args, **kwargs: True
            cook.cookItem = fakeCook
            checkin.commit = lambda *args, **kwargs: None
            checkin.checkout = lambda *args, **kwargs: None
            conaryclient.ConaryClient = FakeClient
            g = group_trove.GroupTroveCook(jobData, [])
            g.conarycfg = conarycfg.ConaryConfiguration()
            g.conarycfg.initializeFlavors = lambda *args, **kwargs: None
            self.assertRaises(RuntimeError, g.write)
        finally:
            group_trove.troveInGroup = troveInGroup
            cook.cookItem = cookItem
            checkin.commit = commit
            checkin.checkout = checkout
            conaryclient.ConaryClient = ConaryClient


if __name__ == "__main__":
    testsuite.main()
