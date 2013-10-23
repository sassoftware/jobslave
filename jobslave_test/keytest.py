#
# Copyright (c) SAS Institute Inc.
#

import os, sys
import tempfile

from jobslave.generators import installable_iso
from jobslave_test.jobslave_helper import JobSlaveHelper

from conary import versions
from conary.repository import changeset
from conary import trove
from conary.deps import deps
from conary.lib import openpgpfile, util

TROVE_NAME = 'group-dummy'
TROVE_VERSION = versions.VersionFromString('/test.rpath.local@rpl:devel/1-1-1')
TROVE_FLAVOR = deps.parseFlavor('is: x86')

class DummyTroveInfo(object):
    def __init__(self):
        self.sigs = self
        self.digitalSigs = self

    def iter(self):
        for base in ('0123456789', '9876543210'):
            yield [4 * base]

class DummyVersion(object):
    def __init__(self):
        self.v = self

    def trailingLabel(self):
        return 'test.rpath.local@rpl:devel'

class DummyTrove(object):
    def __init__(self, *args, **kwargs):
        self.version = DummyVersion()
        self.troveInfo = DummyTroveInfo()

    def getName(self):
        return TROVE_NAME

    def getVersion(self):
        return TROVE_VERSION

    def getFlavor(self):
        return TROVE_FLAVOR

    def count(self, *args, **kwargs):
        return 0

class DummyChangeSet(object):
    def __init__(self, *args, **kwargs):
        pass

    def iterNewTroveList(self):
        return [DummyTrove()]


class DummyRepos(object):
    def findTrove(self, *args, **kwargs):
        raise NotImplementedError

    def getTrove(self, *args, **kwargs):
        return DummyTrove()

    def walkTroveSet(self, *args, **kwargs):
        yield DummyTrove()

    def getAsciiOpenPGPKey(self, label, fp):
        if fp == 4 * '0123456789':
            return ''
        raise openpgpfile.KeyNotFound(fp)

class DummyConfig(object):
    flavor = []

class DummyClient(object):
    def __init__(self):
        self.repos = DummyRepos()
        self.cfg = DummyConfig()

class DummyFlavor(object):
    def freeze(self):
        return '1#x86'

class DummyBuild(object):
    def getArchFlavor(self):
        return DummyFlavor()

class DummyIso(installable_iso.InstallableIso):
    def __init__(self):
        self.statusList = []
        self.conaryClient = DummyClient()
        self.build = DummyBuild()
        self.troveName = TROVE_NAME
        self.troveVersion = TROVE_VERSION
        self.troveFlavor = TROVE_FLAVOR
        self.baseFlavor = self.troveFlavor
        self.isocfg = self.configObject

    def status(self, status):
        self.statusList.append(status)

    def getConaryClient(self, *args, **kwargs):
        return self.conaryClient

class KeyTest(JobSlaveHelper):

    def setUp(self):
        self._call = installable_iso.call
        installable_iso.call = lambda *args, **kwargs: None

    def tearDown(self):
        installable_iso.call = self._call

    def testMissingKey(self):
        DummyRepos.findTrove = lambda *args, **kwargs: (('', '', ''),)
        d = DummyIso()

        csdir = tempfile.mkdtemp()
        logFd, logFile = tempfile.mkstemp()
        oldErr = os.dup(sys.stderr.fileno())
        os.dup2(logFd, sys.stderr.fileno())
        os.close(logFd)
        ChangeSetFromFile = changeset.ChangeSetFromFile
        Trove = trove.Trove
        try:
            f = open(os.path.join(csdir, 'test.ccs'), 'w')
            f.write('')
            f.close()
            changeset.ChangeSetFromFile = DummyChangeSet
            trove.Trove = DummyTrove

            try:
                d.extractPublicKeys('', '', csdir)
            except RuntimeError:
                pass
            else:
                self.fail('Missing keys did not raise runtime error')
        finally:
            trove.Trove = Trove
            changeset.ChangeSetFromFile = ChangeSetFromFile
            os.dup2(oldErr, sys.stderr.fileno())
            os.close(oldErr)
            util.rmtree(csdir)
            util.rmtree(logFile)


    def testFoundAll(self):
        DummyRepos.findTrove = lambda *args, **kwargs: (('', '', ''),)
        d = DummyIso()

        getAsciiOpenPGPKey = DummyRepos.getAsciiOpenPGPKey
        csdir = tempfile.mkdtemp()
        try:
            DummyRepos.getAsciiOpenPGPKey = lambda *args : ''
            d.extractPublicKeys('', '', csdir)
        finally:
            DummyRepos.getAsciiOpenPGPKey = getAsciiOpenPGPKey
            util.rmtree(csdir)

        assert d.statusList == ['Extracting Public Keys']
