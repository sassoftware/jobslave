#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import os
import subprocess
import tempfile
import time
from StringIO import StringIO

from conary import versions
from conary.lib import util
from conary.deps import deps

import jobslave_helper
from jobslave import helperfuncs
from jobslave.generators import constants
from jobslave.generators import bootable_image
import jobslave.loophelpers

from testutils import mock


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
        fsm.devPath = '/dev/loop0'
        fsm.umount()
        self.failIf(fsm.devPath != '/dev/loop0',
                "allowed to umount an unmounted partition")

    def testUmount(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext3', 104857600,
                offset=65536)
        logCall = bootable_image.logCall
        loopDetach = jobslave.loophelpers.loopDetach
        try:
            bootable_image.logCall = lambda *args, **kwargs: None
            jobslave.loophelpers.loopDetach = lambda *args, **kwargs: None
            fsm.devPath = '/dev/loop0'
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
            fsm.devPath = '/dev/loop0'
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
        mock.mock(bootable_image, 'logCall')
        mock.mockFunction(jobslave.loophelpers.loopDetach)
        mock.mockFunction(jobslave.loophelpers.loopAttach)
        jobslave.loophelpers.loopAttach._mock.setDefaultReturn('/dev/loop0')
        mock.mock(subprocess, 'Popen')
        subprocess.Popen()._mock.set(stdout=StringIO('abc123'))
        subprocess.Popen().wait._mock.setDefaultReturn(0)
        fsm.format()
        self.assertEqual(fsm.uuid, 'abc123')
        self.assertEqual(bootable_image.logCall._mock.calls[0][0][0][0], 'mkswap')
        self.assertEqual(len(jobslave.loophelpers.loopDetach._mock.calls), 1)

    def testFormatExt4(self):
        fsm = bootable_image.Filesystem('/dev/null', 'ext4', 104857600,
                offset = 512)
        mock.mock(bootable_image, 'logCall')
        mock.mockFunction(jobslave.loophelpers.loopDetach)
        mock.mockFunction(jobslave.loophelpers.loopAttach)
        jobslave.loophelpers.loopAttach._mock.setDefaultReturn('/dev/loop0')
        mock.mock(subprocess, 'Popen')
        subprocess.Popen()._mock.set(stdout=StringIO('abc123'))
        subprocess.Popen().wait._mock.setDefaultReturn(0)
        fsm.format()
        self.assertEqual(fsm.uuid, 'abc123')
        self.assertEqual(bootable_image.logCall._mock.calls[0][0][0][0], 'mkfs.ext4')
        self.assertEqual(len(jobslave.loophelpers.loopDetach._mock.calls), 1)


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

        constants.finishedDir = "/tmp"
        self.mock(bootable_image.BootableImage, 'status', lambda *args, **kwargs: None)
        self.bootable = bootable_image.BootableImage(self.slaveCfg, self.data)
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

    def testZipDir(self):
        # RCE-2074
        tmpDir = tempfile.mkdtemp()
        try:
            src = os.path.join(tmpDir, 'test')
            util.mkdirChain(src)
            self.touch(os.path.join(src, 'junk'), contents = '\n')
            dest = src + '.zip'
            self.bootable.zipArchive(src)
            self.failIf(not os.path.exists(dest),
                    "zip did not function for directory")
        finally:
            util.rmtree(tmpDir)


    def testAddMissingScsiModules(self):
        modpath = self.bootable.filePath('etc/modprobe.conf')
        self.touch(modpath, 'dummy line')
        self.bootable.scsiModules = True
        self.bootable.addScsiModules()

    def testAddScsiModules(self):
        modpath = self.bootable.filePath('etc/modprobe.conf')
        self.touch(modpath, 'dummy line')
        self.bootable.scsiModules = True
        self.bootable.addScsiModules()
        data = open(modpath).read()
        self.failIf('scsi_hostadapter' not in data,
                    "scsi modules not added to modprobe.conf")

    def testGetImageSize(self):
        self.bootable.mountDict = {
            '/':     bootable_image.FsRequest('root', '/',     'ext4', 0, 500000000),
            '/boot': bootable_image.FsRequest('boot', '/boot', 'ext4',    200000000, 0),
            }
        self.bootable.getTroveSize = lambda *a, **k: ({'/boot': 10240}, 0)
        realSizes = self.bootable.getImageSize()
        self.assertEqual(realSizes, {'/boot': 200000000, '/': 598865408})

    def testAddFilesystem(self):
        self.bootable.addFilesystem('/', 'ext3')
        self.failIf(self.bootable.filesystems != {'/': 'ext3'},
            "addFilesystem did not operate correcly")

    def testPreInstallScripts(self):
        mock.mock(os, 'mknod')
        mock.mock(os, 'chmod')
        self.bootable.preInstallScripts()
        self.failUnlessEqual(set(os.listdir(self.bootable.root)),
                set(['root', 'tmp', 'var', 'boot', 'etc', 'dev']))
        self.failUnlessEqual(open(self.bootable.filePath('etc/fstab')).read(),
        '''\
LABEL=root\t/\text4\tdefaults\t1\t1
devpts                  /dev/pts                devpts  gid=5,mode=620  0 0
tmpfs                   /dev/shm                tmpfs   defaults        0 0
proc                    /proc                   proc    defaults        0 0
sysfs                   /sys                    sysfs   defaults        0 0
/var/swap\tswap\tswap\tdefaults\t0\t0
''')
        os.mknod._mock.assertCalled(self.bootable.filePath('dev/null'), 8192, 259)

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
        mknod = os.mknod
        chmod = os.chmod
        try:
            self.touch(os.path.join(tmpDir, 'root', 'conary-tag-script.in'))
            self.touch(os.path.join(tmpDir, 'root', 'conary-tag-script'))
            self.touch(os.path.join(tmpDir, 'usr/sbin/authconfig'))
            self.touch(os.path.join(tmpDir, 'usr/sbin/usermod'))
            os.mkdir(self.bootable.changesetDir)
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

            self.touch(os.path.join(tmpDir, 'etc/selinux/config'), '''\
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

            self.bootable.downloadChangesets = lambda: None
            self.bootable.updateGroupChangeSet = lambda *args, **kwargs: None
            self.bootable.mountDict = {'/': None}
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
            os.mknod = lambda *args: None
            os.chmod = lambda *args: None
            self.bootable.inspectGroup = lambda: None
            self.bootable.loadRPM = lambda: None
            self.bootable._getLabelPath = lambda *args: ''
            self.bootable.installFileTree(tmpDir)
            self.failUnless('pam_unix2.so nullok' in file(common_auth).read())
            self.failIf('etc' not in os.listdir(tmpDir),
                    "installFileTree did not run to completion")
            self.failIf('SELINUX=disabled\n' not in open(
                os.path.join(tmpDir, 'etc/selinux/config')).read(),
                "selinux not disabled")
            # make sure we unmount things in the right order
            self.failUnlessEqual(self.cmds[-3:],
                                 ['umount -n %s/sys/bar' %tmpDir,
                                  'umount -n %s/sys' %tmpDir,
                                  'umount -n %s/proc' %tmpDir])
        finally:
            util.rmtree(tmpDir)
            util.rmtree(constants.tmpDir)
            constants.tmpDir = saved_tmpDir
            bootable_image.logCall = logCall
            bootable_image.open = open
            bootable_image.file = file
            os.mknod = mknod
            os.chmod = chmod

    def _getStubCClient(self):
        data = self.bootable.jobData
        name = data['troveName']
        version = versions.ThawVersion(data['troveVersion'])
        flavor = deps.ThawFlavor(data['troveFlavor'])
        expectedItems = [(name, (None, None), (version, flavor), True)]

        class CClient(object):
            def __init__(x):
                x.uJob = object()
                x.applied = False
            def newUpdateJob(x):
                return x.uJob
            def applyUpdateJob(x, uJob, tagScript=None, **kwargs):
                self.failUnless(uJob is x.uJob)
                self.failUnless(tagScript is not None)
                x.applied = True
            def failUnlessRun(x):
                self.failUnless(x.applied, "Kernel was not installed")
        return CClient()

    def testUpdateGroupChangeSet(self):
        cclient = self._getStubCClient()
        self.bootable.uJob = cclient.newUpdateJob()
        self.bootable.updateGroupChangeSet(cclient)
        cclient.failUnlessRun()
