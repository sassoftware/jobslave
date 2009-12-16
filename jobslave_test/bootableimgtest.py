#!/usr/bin/python
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import os
import re
import tempfile
import time
import simplejson
import xmlrpclib
from StringIO import StringIO

from conary import versions
from conary.lib import util
from conary.deps import deps

import jobslave_helper
from jobslave import filesystems
from jobslave import helperfuncs
from jobslave import slave
from jobslave.generators import constants
from jobslave.generators import bootable_image
from jobslave.generators import ami
import jobslave.loophelpers

from testrunner import pathManager

class BootableImageHelperTest(jobslave_helper.JobSlaveHelper):
    def testCopyFile(self):
        tmpDir = tempfile.mkdtemp()
        try:
            srcFile = os.path.join(tmpDir, 'a')
            destFile = os.path.join(tmpDir, 'b')
            self.touch(srcFile)
            bootable_image.copyfile(srcFile, destFile)
            self.failIf(not os.path.exists(destFile),
                    "copyfile didn't operate properly")
        finally:
            util.rmtree(tmpDir)

    def testCopyTree(self):
        tmpDir = tempfile.mkdtemp()
        try:
            srcDir = os.path.join(tmpDir, 'a')
            util.mkdirChain(srcDir)
            subDir = os.path.join(srcDir, 'a')
            util.mkdirChain(subDir)
            destDir = os.path.join(tmpDir, 'b')
            util.mkdirChain(destDir)
            srcFile = os.path.join(subDir, 'a')
            self.touch(srcFile, contents = 'test')
            bootable_image.copytree(srcDir, destDir)
            self.failIf(not os.path.exists(os.path.join(destDir, 'a')),
                    "copytree didn't operate properly")
            self.failIf(not os.path.exists(os.path.join(destDir, 'a', 'a')),
                    "expected file to be copied by copytree")
        finally:
            util.rmtree(tmpDir)

    def testMount(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600)
        logCall = bootable_image.logCall
        loopAttach = jobslave.loophelpers.loopAttach
        try:
            bootable_image.logCall = lambda *args, **kwargs: None
            jobslave.loophelpers.loopAttach = lambda *args, **kwargs: '/dev/loop0'
            fsm.mount('/tmp')
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopAttach = loopAttach
        self.failIf(not fsm.mounted, "Couldn't mount an ext3 partition")

    def testSwapMount(self):
        fsm = bootable_image.Filesystem('/dev/null', 'swap', 104857600)
        fsm.mount('/tmp')
        self.failIf(fsm.mounted, "Allowed to mount a swap partition")

    def testSwapUnmount(self):
        fsm = bootable_image.Filesystem('/dev/null', 'swap', 104857600)
        fsm.umount()
        self.failIf(fsm.mounted, "Allowed to unmount a swap partition")

    def testUmountNotMounted(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600)
        fsm.loopDev = '/dev/loop0'
        fsm.umount()
        self.failIf(fsm.loopDev != '/dev/loop0',
                "allowed to umount an unmounted partition")

    def testUmount(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600)
        logCall = bootable_image.logCall
        loopDetach = jobslave.loophelpers.loopDetach
        try:
            bootable_image.logCall = lambda *args, **kwargs: None
            jobslave.loophelpers.loopDetach = lambda *args, **kwargs: None
            fsm.loopDev = '/dev/loop0'
            fsm.mounted = True
            fsm.mountPoint = '/mnt/null'
            fsm.umount()
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopDetach = loopDetach
        self.failIf(fsm.mounted, "Couldn't umount an ext3 partition")

    def testUmountFail(self):
        log_hits = []
        log_want = [
            ('Unmount of %s from %s failed - trying again', '/dev/loop0',
                '/mnt/null'),
            ('Unmount failed because these files were still open:',),
            ('/mnt/null/bar',),
            ('/mnt/null/foo',),
            ]
        class mock_log:
            def __init__(xself, log_hits):
                xself.log_hits = log_hits
            def error(xself, *P):
                xself.log_hits.append(tuple(P))
            warning = error
        def mock_logCall(args):
            if args.startswith('umount'):
                raise RuntimeError('asplode!')

        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600)
        _logCall = bootable_image.logCall
        _log = bootable_image.log
        _sleep = time.sleep
        _getMountedFiles = helperfuncs.getMountedFiles
        _loopDetach = jobslave.loophelpers.loopDetach
        try:
            bootable_image.logCall = mock_logCall
            bootable_image.log = mock_log(log_hits)
            helperfuncs.getMountedFiles = lambda path: set(
                ['/mnt/null/foo', '/mnt/null/bar'])
            time.sleep = lambda dur: None
            jobslave.loophelpers.loopDetach = lambda *args, **kwargs: None
            fsm.loopDev = '/dev/loop0'
            fsm.mounted = True
            fsm.mountPoint = '/mnt/null'

            self.failUnlessRaises(RuntimeError, fsm.umount)

            self.failUnlessEqual(log_hits, log_want)
        finally:
            bootable_image.logCall = _logCall
            bootable_image.log = _log
            helperfuncs.getMountedFiles = _getMountedFiles
            time.sleep = _sleep
            jobslave.loophelpers.loopDetach = _loopDetach
        self.failUnless(fsm.mounted,
            "Partition got marked as unmounted when umount failed")

    def testFormatInvalid(self):
        fsm = bootable_image.Filesystem('/dev/null', 'notta_fs', 104857600)
        logCall = bootable_image.logCall
        loopDetach = jobslave.loophelpers.loopDetach
        loopAttach = jobslave.loophelpers.loopAttach
        try:
            bootable_image.logCall = lambda *args, **kwargs: None
            jobslave.loophelpers.loopDetach = lambda *args, **kwargs: None
            jobslave.loophelpers.loopAttach = lambda *args, **kwargs: '/dev/loop0'
            self.assertRaises(RuntimeError, fsm.format)
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopDetach = loopDetach
            jobslave.loophelpers.loopAttach = loopAttach

    def testFormatSwap(self):
        fsm = bootable_image.Filesystem('/dev/null', 'swap', 104857600)
        def DummyLogCall(cmd):
            # this is the line that actually tests the format call
            assert 'mkswap' in cmd
        logCall = bootable_image.logCall
        loopDetach = jobslave.loophelpers.loopDetach
        loopAttach = jobslave.loophelpers.loopAttach
        try:
            bootable_image.logCall = DummyLogCall
            jobslave.loophelpers.loopDetach = lambda *args, **kwargs: None
            jobslave.loophelpers.loopAttach = lambda *args, **kwargs: '/dev/loop0'
            fsm.format()
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopDetach = loopDetach
            jobslave.loophelpers.loopAttach = loopAttach

    def testFormatExt3(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600,
                offset = 512)
        def DummyLoopDetach(*args, **kwargs):
            self.detachCalled = True
        self.detachCalled = False
        logCall = bootable_image.logCall
        loopDetach = jobslave.loophelpers.loopDetach
        loopAttach = jobslave.loophelpers.loopAttach
        try:
            bootable_image.logCall = lambda *args, **kwargs: None
            jobslave.loophelpers.loopDetach = DummyLoopDetach
            jobslave.loophelpers.loopAttach = lambda *args, **kwargs: '/dev/loop0'
            fsm.format()
        finally:
            bootable_image.logCall = logCall
            jobslave.loophelpers.loopDetach = loopDetach
            jobslave.loophelpers.loopAttach = loopAttach
        self.failIf(not self.detachCalled,
                "ext3 format did not reach completion")

class MockJobSlave(object):
    def __init__(self):
        self.response = jobslave_helper.DummyResponse()
        self.cfg = slave.SlaveConfig()

class StubFilesystem(object):
    def __init__(self):
        self.fsLabel = 'label'

    def mount(self, *args, **kwargs):
        pass

    def umount(self, *args, **kwargs):
        pass

class BootableImageTest(jobslave_helper.JobSlaveHelper):
    def setUp(self):
        jobslave_helper.JobSlaveHelper.setUp(self)

        fp = os.path.join(pathManager.getPath('JOB_SLAVE_ARCHIVE_PATH'),'jobdata.txt')
        data = simplejson.loads( open(fp).read())
        self.mockJobSlave = MockJobSlave()
        from jobslave.generators import constants
        constants.finishedDir = "/tmp"
        bootable_image.BootableImage.status = lambda *args, **kwargs: None
        self.bootable = bootable_image.BootableImage(data, self.mockJobSlave)
        self.bootable.swapSize = 40960

    def tearDown(self):
        del self.bootable
        jobslave_helper.JobSlaveHelper.tearDown(self)

    def testBootableImageNotWritable(self):
        self.assertRaises(NotImplementedError, self.bootable.write)

    def testGzipDir(self):
        tmpDir = tempfile.mkdtemp()
        try:
            src = os.path.join(tmpDir, 'test')
            util.mkdirChain(src)
            self.touch(os.path.join(src, 'junk'), contents = '\n')
            dest = src + '.tar.gz'
            self.bootable.gzip(src)
            self.failIf(not os.path.exists(dest),
                    "gzip did not function for directory")
        finally:
            util.rmtree(tmpDir)

    def testGzipFile(self):
        tmpDir = tempfile.mkdtemp()
        try:
            src = os.path.join(tmpDir, 'test')
            self.touch(src, contents = '\n')
            dest = src + '.gz'
            self.bootable.gzip(src)
            self.failIf(not os.path.exists(dest),
                    "gzip did not function for file")
        finally:
            util.rmtree(tmpDir)

    def testAddMissingScsiModules(self):
        tmpDir = tempfile.mkdtemp()
        util.mkdirChain(tmpDir + "/etc/")
        try:
            self.bootable.scsiModules = True
            self.bootable.addScsiModules(tmpDir)
        finally:
            util.rmtree(tmpDir)

    def testAddScsiModules(self):
        tmpDir = tempfile.mkdtemp()
        try:
            self.touch(os.path.join(tmpDir, 'etc', 'modprobe.conf'),
                    'dummy line')
            self.bootable.scsiModules = True
            self.bootable.addScsiModules(tmpDir)
            data = open(os.path.join(tmpDir, 'etc', 'modprobe.conf')).read()
            self.failIf('scsi_hostadapter' not in data,
                        "scsi modules not added to modprobe.conf")
        finally:
            util.rmtree(tmpDir)

    def testGetKernelFlavor(self):
        self.failIf('!kernel.smp' not in self.bootable.getKernelFlavor(),
                "non-xen kernel returned wrong flavor")
        self.bootable.baseFlavor = deps.parseFlavor('xen,domU is: x86')
        self.failIf(self.bootable.getKernelFlavor() != '',
                "getKernelFlavor favored non-xen flavor for xen group")

    def testGetImageSize(self):
        self.bootable.mountDict = {'/boot' : (0, 10240, 'ext3')}
        self.bootable.getTroveSize = \
                lambda *args, **kwargs: ({'/boot': 10240}, 0)
        totalSize, realSizes = self.bootable.getImageSize()
        self.failIf(totalSize != 24194560, \
                "Expected total size of 24194560 but got %d" % totalSize)
        self.failIf(realSizes != {'/boot': 24129024}, \
                "Expected real sizes of {'/boot': 24129024} but got %s" % \
                str(realSizes))

    def testGetImageSizeWithSwap(self):
        """
        Verify that self.bootable.swapSize (40960) gets added to the
        filesystem mounted at /var.
        """
        self.bootable.mountDict = {'/boot': (0, 10240, 'ext3'),
                                   '/var' : (0, 0, 'swap')}
        self.bootable.filesystems['/var'] = '/var/swap'
        self.bootable.getTroveSize = \
                lambda *args, **kwargs: ({'/boot': 10240,
                                          '/var' : 0}, 0)
        totalSize, realSizes = self.bootable.getImageSize()
        self.failIf(totalSize != 24235520, \
                "Expected total size of 24194560 but got %d" % totalSize)
        self.failIf(realSizes != {'/boot': 24129024, '/var':40960}, \
                "Expected real sizes of {'/boot': 24129024, '/var': 40960} but got %s" % \
                str(realSizes))

    def testFSOddsNEnds(self):
        # deliberately run fsoddsnends with a blank chroot to ensure it
        # won't backtrace
        _logCall, bootable_image.logCall = bootable_image.logCall, lambda *P, **K: None
        tmpDir = tempfile.mkdtemp()
        self.bootable.writeConaryRc = lambda *args, **kwargs: None
        try:
            self.bootable.fileSystemOddsNEnds(tmpDir)
            self.failIf(os.listdir(tmpDir) == [],
                    "FilesystemOddsNEnds should have added content")
        finally:
            util.rmtree(tmpDir)
            bootable_image.logCall = _logCall

    def testFSOddsNEnds2(self):
        _logCall, bootable_image.logCall = bootable_image.logCall, lambda *P, **K: None
        tmpDir = tempfile.mkdtemp()
        self.touch(os.path.join(tmpDir, 'etc', 'init.d', 'xdm'))
        self.touch(os.path.join(tmpDir, 'usr', 'bin', 'xdm'))
        self.touch(os.path.join(tmpDir, 'etc', 'inittab'))
        self.touch(os.path.join(tmpDir, 'usr', 'share', 'zoneinfo', 'UTC'))
        self.bootable.writeConaryRc = lambda *args, **kwargs: None
        try:
            self.bootable.fileSystemOddsNEnds(tmpDir)
            self.failIf(os.listdir(tmpDir) == [],
                    "FilesystemOddsNEnds should have added content")
        finally:
            util.rmtree(tmpDir)
            bootable_image.logCall = _logCall

    def testFSOddsNEnds3(self):
        _logCall, bootable_image.logCall = bootable_image.logCall, lambda *P, **K: None
        tmpDir = tempfile.mkdtemp()
        # trigger runlevel five, but leave out /etc/inittab just to see
        # what happens.
        self.touch(os.path.join(tmpDir, 'etc', 'init.d', 'xdm'))
        self.touch(os.path.join(tmpDir, 'usr', 'bin', 'xdm'))
        self.bootable.writeConaryRc = lambda *args, **kwargs: None
        try:
            self.bootable.fileSystemOddsNEnds(tmpDir)
            self.failIf(os.listdir(tmpDir) == [],
                    "FilesystemOddsNEnds should have added content")
        finally:
            util.rmtree(tmpDir)
            bootable_image.logCall = _logCall

    def testFSOddsNEnds4(self):
        _logCall, bootable_image.logCall = bootable_image.logCall, lambda *P, **K: None
        tmpDir = tempfile.mkdtemp()
        # set filesystems, but no /etc/fstab
        self.bootable.mountDict = {'/' : (0, 100, 'ext3'),
                                     '/boot': (0, 100, 'ext3'),
                                     'swap' : (0, 100, 'swap')}
        self.bootable.filesystems = dict.fromkeys(self.bootable.mountDict.keys(),
                                                  StubFilesystem())
        self.bootable.writeConaryRc = lambda *args, **kwargs: None
        try:
            self.bootable.fileSystemOddsNEnds(tmpDir)
            self.failIf('fstab' not in os.listdir(os.path.join(tmpDir, 'etc')),
                    "FilesystemOddsNEnds should have added /etc/fstab")
            f = open(os.path.join(tmpDir, 'etc', 'fstab'))
            self.failUnlessEqual(f.read(), '''LABEL=label\t/\text3\tdefaults\t1\t1
LABEL=swap\tswap\tswap\tdefaults\t0\t0
LABEL=label\t/boot\text3\tdefaults\t1\t2
''')
        finally:
            util.rmtree(tmpDir)
            bootable_image.logCall = _logCall

    def testAddFilesystem(self):
        self.bootable.addFilesystem('/', 'ext3')
        self.failIf(self.bootable.filesystems != {'/': 'ext3'},
            "addFilesystem did not operate correcly")

    def testCreateTempRoot(self):
        tmpDir = tempfile.mkdtemp()
        try:
            self.bootable.createTemporaryRoot(tmpDir)
            self.failUnlessEqual(set(os.listdir(tmpDir)),
                    set(['etc', 'boot', 'tmp', 'proc', 'sys', 'root', 'var']),
                    "unexpected results from createTemporaryRoot")
        finally:
            util.rmtree(tmpDir)

    def testGetTroveSize(self):
        calculatePartitionSizes = filesystems.calculatePartitionSizes
        try:
            self.bootable.nc.createChangeSet = lambda *args, **kwargs: None
            filesystems.calculatePartitionSizes = \
                    lambda *args, **kwargs: (None, None)
            self.failIf(self.bootable.getTroveSize(None) != (None, None),
                    "results from getTroveSize did not come from filesystem")
        finally:
            filesystems.calculatePartitionSizes = calculatePartitionSizes

    def testMountAll(self):
        self.bootable.workDir = tempfile.mkdtemp()
        sortMountPoints = bootable_image.sortMountPoints
        try:
            bootable_image.sortMountPoints = lambda *args, **kwargs: ['/boot']
            self.bootable.filesystems['/boot'] = StubFilesystem()
            self.bootable.mountAll()
            self.failIf(os.listdir(os.path.join(self.bootable.workDir,
                'root')) != ['boot'],
                "expected mountAll to create mount points")
        finally:
            bootable_image.sortMountPoints = sortMountPoints
            util.rmtree(self.bootable.workDir)

    def testUmountAll(self):
        sortMountPoints = bootable_image.sortMountPoints
        try:
            bootable_image.sortMountPoints = lambda *args, **kwargs: ['/boot']
            self.bootable.filesystems['/boot'] = StubFilesystem()
            self.bootable.umountAll()
        finally:
            bootable_image.sortMountPoints = sortMountPoints

    def testMakeImage(self):
        self.bootable.workDir = tempfile.mkdtemp()
        try:
            def dummyInstall(*args, **kwargs):
                self.called = True
            self.called = False
            self.bootable.installFileTree = dummyInstall
            root_dir = os.path.join(self.bootable.workDir, "root")
            self.bootable.installFileTree(root_dir)
            self.failIf(not self.called, "installFileTree was not called")
        finally:
            util.rmtree(self.bootable.workDir)

    def testFindFile(self):
        tmpDir = tempfile.mkdtemp()
        try:
            self.touch(os.path.join(tmpDir, 'a', 'b'))
            res = self.bootable.findFile(tmpDir, os.path.join('b'))
            self.failIf(not res, "findFile didn't detect file")
            res = self.bootable.findFile(tmpDir, os.path.join('c'))
            self.failIf(res, "findFile incorrectly detected file")
        finally:
            util.rmtree(tmpDir)

    def testInstallFileTree(self):
        self.bootable.scsiModules = True
        tmpDir = tempfile.mkdtemp()
        saved_tmpDir = constants.tmpDir
        constants.tmpDir = tempfile.mkdtemp()
        logCall = bootable_image.logCall
        try:
            self.touch(os.path.join(tmpDir, 'root', 'conary-tag-script.in'))
            self.touch(os.path.join(tmpDir, 'root', 'conary-tag-script'))
            self.touch(os.path.join(tmpDir, 'usr/sbin/authconfig'))
            self.touch(os.path.join(tmpDir, 'usr/sbin/usermod'))
            common_auth = os.path.join(tmpDir, 'etc/pam.d/common-auth')
            self.touch(common_auth)
            f = file(common_auth, 'w')
            f.write("""#
# /etc/pam.d/common-auth - authentication settings common to all services
#
# This file is included from other service-specific PAM config files,
# and should contain a list of the authentication modules that define
# the central authentication scheme for use on the system
# (e.g., /etc/shadow, LDAP, Kerberos, etc.).  The default is to use the
# traditional Unix authentication mechanisms.
#
auth	required	pam_env.so
auth	required	pam_unix2.so
""")
            f.close()

            selinux = os.path.join(tmpDir, 'etc/selinux/config')
            file(selinux, 'w').write('''
# This file controls the state of SELinux on the system.
# SELINUX= can take one of these three values:
# enforcing - SELinux security policy is enforced.
# permissive - SELinux prints warnings instead of enforcing.
# disabled - SELinux is fully disabled.
SELINUX=enforcing
# SELINUXTYPE= type of policy in use. Possible values are:
# targeted - Only targeted network daemons are protected.
# strict - Full SELinux protection.
SELINUXTYPE=targeted
''')

            self.bootable.updateKernelChangeSet = \
                    self.bootable.updateGroupChangeSet = \
                    self.bootable.fileSystemOddsNEnds = \
                    lambda *args, **kwargs: None
            def mockLog(cmd, ignoreErrors=False):
                self.cmds.append(cmd)
            def mockOpen(*args):
                if args[0] == '/proc/mounts':
                    return StringIO("""proc %(d)s/proc blah
sysfs %(d)s/sys blah
sysfs %(d)s/sys/bar blah
loop0 %(d)s blah""" %dict(d=tmpDir))
                return open(*args)
            self.cmds = []
            bootable_image.logCall = mockLog
            bootable_image.open = mockOpen
            bootable_image.file = mockOpen
            self.bootable.installFileTree(tmpDir)
            self.failUnless('pam_unix2.so nullok' in file(common_auth).read())
            self.failIf('etc' not in os.listdir(tmpDir),
                    "installFileTree did not run to completion")
            self.failIf('.autorelabel' not in os.listdir(tmpDir),
                    "selinux .autorelabel not created")
            self.failIf(len(self.cmds) != 9,
                    "unexpected number of external calls")
            # make sure we unmount things in the right order
            self.failUnlessEqual(self.cmds[3:6],
                                 ['umount %s/sys/bar' %tmpDir,
                                  'umount %s/sys' %tmpDir,
                                  'umount %s/proc' %tmpDir])
        finally:
            util.rmtree(tmpDir)
            util.rmtree(constants.tmpDir)
            constants.tmpDir = saved_tmpDir
            bootable_image.logCall = logCall
            bootable_image.open = open
            bootable_image.file = file

    def _getStubCClient(self, isKernel):
        data = self.bootable.jobData
        if isKernel:
            name = 'kernel:runtime'
            version = None
            flavor = deps.parseFlavor(self.bootable.getKernelFlavor())
        else:
            name = data['troveName']
            version = versions.ThawVersion(data['troveVersion']).asString()
            flavor = deps.ThawFlavor(data['troveFlavor'])
        expectedItems = [(name, (None, None), (version, flavor), True)]

        class CClient(object):
            def __init__(x):
                x.uJob = object()
                x.prepared = x.applied = False
            def newUpdateJob(x):
                return x.uJob
            def prepareUpdateJob(x, uJob, items, **kwargs):
                self.failUnless(uJob is x.uJob)
                self.failUnlessEqual(expectedItems, items)
                x.prepared = True
            def applyUpdateJob(x, uJob, tagScript=None, **kwargs):
                self.failUnless(uJob is x.uJob)
                self.failUnless(tagScript is not None)
                x.applied = True
            def failUnlessRun(x):
                self.failUnless(x.prepared, "Image trove was not installed")
                self.failUnless(x.applied, "Kernel was not installed")
        return CClient()

    def testUpdateGroupChangeSet(self):
        cclient = self._getStubCClient(False)
        self.bootable.updateGroupChangeSet(cclient)
        cclient.failUnlessRun()

    def testUpdateKernelChangeSet(self):
        cclient = self._getStubCClient(True)
        self.bootable.updateKernelChangeSet(cclient)
        cclient.failUnlessRun()

    def testPostAMIOutput(self):
        class DummyProxy(object):
            def setBuildAMIDataSafe(*args, **kwargs):
                return False, True
            def __init__(*args, **kwargs):
                pass
        ServerProxy = slave.xmlrpclib.ServerProxy
        try:
            xmlrpclib.ServerProxy = DummyProxy
            self.jobSlave.postAMIOutput('test.rpath.local-build-4-3',
                    'buildId', 'desturl', 'outputToken', 'amiId',
                    'amiManifestName')
        finally:
            slave.xmlrpclib.ServerProxy = ServerProxy
        self.failIf('Job Finished' not in \
                self.jobSlave.response.response.connection.sent[0][1],
                "post AMI output did not succeed")


if __name__ == "__main__":
    testsuite.main()
