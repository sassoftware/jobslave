#
# Copyright (c) SAS Institute Inc.
#

# python standard library imports
import itertools
import logging
from math import ceil
import os
import sys
import re
import signal
import stat
import subprocess
import time

# mint imports
from jobslave import filesystems
from jobslave import generators
from jobslave import helperfuncs
from jobslave import loophelpers
from jobslave import buildtypes
from jobslave.distro_detect import is_RH, is_SUSE, is_UBUNTU
from jobslave.filesystems import sortMountPoints
from jobslave.geometry import GEOMETRY_REGULAR
from jobslave.imagegen import ImageGenerator, MSG_INTERVAL
from jobslave.generators import constants
from jobslave.util import logCall

# conary imports
from conary import conaryclient
from conary import dbstore
from conary import display
from conary.conaryclient import modelupdate
from conary.callbacks import UpdateCallback
from conary.lib import util
from conary.versions import Label

log = logging.getLogger(__name__)


RPM_ALTERNATES = '/opt'
RPM_DOTS = re.compile('^(.*)[._]')


def timeMe(func):
    def wrapper(self, *args, **kwargs):
        clock = time.clock()
        actual = time.time()
        returner = func(self, *args, **kwargs)
        log.debug("%s: %.5f %.5f" % (func.__name__, time.clock() - clock,
            time.time() - actual))
        return returner
    return wrapper

def copyfile(source, target):
    if not os.path.exists(target):
        return util.copyfile(source, target)

def copytree(source, dest, exceptions=None):
    if not exceptions:
        exceptions = []
    for root, dirs, files in os.walk(source):
        root = root.replace(source, '')
        for f in files:
            if not [x for x in exceptions if \
                        re.match(x, util.joinPaths(root, f))]:
                copyfile(util.joinPaths(source, root, f),
                         util.joinPaths(dest, root, f))
        for d in dirs:
            this_dir = util.joinPaths(dest, root, d)
            if not os.path.exists(this_dir) and not \
                    [x for x in exceptions if \
                         re.match(x, util.joinPaths(root, d))]:
                os.mkdir(this_dir)
                dStat = os.stat(util.joinPaths(source, root, d))
                os.chmod(this_dir, dStat[stat.ST_MODE])

class InstallCallback(UpdateCallback):
    def restoreFiles(self, size, totalSize):
        if totalSize != 0:
            self.restored += size
            self.update('Writing files')

    def requestingChangeSet(self):
        self.update('Requesting changeset')

    def downloadingChangeSet(self, got, need):
        if need != 0:
            self.update('Downloading changeset')

    def requestingFileContents(self):
        self.update('Requesting file contents')

    def downloadingFileContents(self, got, need):
        if need != 0:
            self.update('Downloading files')

    def preparingChangeSet(self):
        self.update('Preparing changeset')

    def resolvingDependencies(self):
        self.update('Resolving dependencies')

    def creatingRollback(self):
        self.update('Creating rollback')

    def creatingDatabaseTransaction(self, troveNum, troveCount):
        self.update('Creating database transaction')

    def committingTransaction(self):
        self.update('Committing transaction')

    def setUpdateHunk(self, num, total):
        self.updateHunk = (num, total)
        self.restored = 0

    def setUpdateJob(self, jobs):
        log.info("Applying update job %d of %d:" % self.updateHunk)
        self.formatter.prepareJobs(jobs)
        for line in self.formatter.formatJobTups(jobs, indent='    '):
            log.info(line)

    def update(self, msg):
        curTime = time.time()
        # only push an update into the database if it differs from the
        # current message
        if self.updateHunk[1] != 0:
            percent = (self.updateHunk[0] * 100) / self.updateHunk[1]
            msg = "Installing image contents: %d%% (%s)" % (percent, msg)

        if self.msg != msg and (curTime - self.timeStamp) > MSG_INTERVAL:
            self.msg = msg
            self.status(msg)
            self.timeStamp = curTime

    def __init__(self, status):
        self.exceptions = []
        self.abortEvent = None
        self.status = status
        self.restored = 0
        self.updateHunk = (0, 0)
        self.msg = ''
        self.changeset = ''
        self.prefix = 'BDI:'
        self.timeStamp = 0
        self.formatter = display.JobTupFormatter()
        self.formatter.dcfg.setTroveDisplay(fullVersions=True,
                fullFlavors=True, showComponents=True)

        UpdateCallback.__init__(self)

    def closeCB(self):
        # Eliminate a reference from ConaryClient (which never frees
        # properly) back to the parent Generator.
        self.status = lambda x: None


class Filesystem(object):
    devPath = None
    offset = None
    mounted = False
    fsType = None

    def __init__(self, fsDev, fsType, size, offset=0, fsLabel=None):
        self.fsDev = fsDev
        self.size = size
        self.offset = offset
        # make the label "safe" so vol_id returns something for
        # ID_FS_LABEL_SAFE and udev creates a link in /dev/disk/by-label/
        if fsLabel is not None:
            fsLabel = fsLabel.replace('/', '')
            if fsLabel == '':
                fsLabel = 'root'
        self.fsLabel = fsLabel
        self.fsType = fsType
        self.mountPoint = None

    def attach(self):
        if self.offset:
            self.devPath = loophelpers.loopAttach(self.fsDev,
                    offset=self.offset, size=self.size)
        else:
            self.devPath = self.fsDev

    def detach(self):
        if self.offset:
            loophelpers.loopDetach(self.devPath)

    def mount(self, mountPoint):
        if self.fsType == "swap":
            return

        self.attach()
        options = []
        fsType = self.fsType
        if self.fsType in ('ext3', 'ext4'):
            # Turn off data integrity during install
            options.append('data=writeback,barrier=0')
        options = '-o %s' % (','.join(options)) if options else ''
        logCall("mount -n -t %s %s %s %s" %
                (fsType, self.devPath, mountPoint, options))
        self.mounted = True
        self.mountPoint = mountPoint

    def umount(self):
        if self.fsType == "swap":
            return

        if not self.devPath or not self.mounted:
            return

        try:
            logCall("umount -n %s" % self.mountPoint)
        except RuntimeError:
            log.warning('Unmount of %s from %s failed - trying again',
                self.devPath, self.mountPoint)

            clean = False
            for x in range(5):
                logCall("sync")
                time.sleep(1)
                try:
                    logCall("umount -n %s" % self.mountPoint)
                except RuntimeError:
                    pass
                else:
                    clean = True
                    break

            if not clean:
                log.error('Unmount failed because these files '
                    'were still open:')
                for path in sorted(
                  helperfuncs.getMountedFiles(self.mountPoint)):
                    log.error(path)

                raise RuntimeError('Failed to unmount %s' % self.devPath)

        self.detach()
        self.mounted = False

    def format(self):
        self.attach()
        try:
            if self.fsType in ('ext3', 'ext4'):
                cmd = ['mkfs.' + self.fsType,
                        '-F',
                        '-b', '4096',
                        '-L', self.fsLabel,
                        self.devPath]
                if self.size:
                    cmd.append(str(self.size / 4096))
                logCall(cmd)
                logCall(['tune2fs',
                    '-i', '0',
                    '-c', '0',
                    self.devPath])
            elif self.fsType == 'xfs':
                logCall(['mkfs.xfs', '-L', self.fsLabel, self.devPath])
            elif self.fsType == 'swap':
                logCall(['mkswap', '-L', self.fsLabel, self.devPath])
            else:
                raise RuntimeError, "Invalid filesystem type: %s" % self.fsType
        finally:
            self.detach()


class StubFilesystem(object):
    def __init__(self):
        self.fsLabel = 'root'
        self.fsType = 'ext4'

    def mount(self, *args):
        pass

    def umount(self, *args):
        pass

    def format(self, *args):
        pass


class BootableImage(ImageGenerator):
    geometry = GEOMETRY_REGULAR

    def __init__(self, cfg, jobData):
        self.filesystems = { '/': StubFilesystem() }
        self.scsiModules = False

        ImageGenerator.__init__(self, cfg, jobData)
        log.info('building trove: %s=%s[%s]' % self.baseTup)

        # Settings
        self.workingDir = os.path.join(self.workDir, self.basefilename)
        self.outputDir = os.path.join(constants.finishedDir, self.UUID)
        self.root = os.path.join(self.workDir, 'root')
        self.tempRoot = os.path.join(self.workDir, 'temp_root')
        self.changesetDir = os.path.join(self.workDir, 'changesets')
        util.mkdirChain(self.outputDir)
        util.mkdirChain(self.workingDir)
        self.swapSize = (self.getBuildData("swapSize") or 0) * 1048576
        self.swapPath = '/var/swap'

        # Runtime variables
        self.bootloader = None
        self.outputFileList = []
        self.uJob = None

        # List of devicePath (realative to the rootPath's /dev), device
        # type 'c' or 'b', major, and minor numbers.
        self.devices = [

            # common character devices
            ('console', 'c', 5, 1, 0600),
            ('null',    'c', 1, 3, 0666),
            ('zero',    'c', 1, 5, 0666),
            ('full',    'c', 1, 7, 0666),
            ('tty',     'c', 5, 0, 0666),
            ('ptmx',    'c', 5, 2, 0666),
            ('random',  'c', 1, 8, 0666),
            ('urandom', 'c', 1, 9, 0666),

            # common block devices
            ('sda',     'b', 8, 0, 0660),
            ('sda1',    'b', 8, 1, 0660),
            ('sda2',    'b', 8, 2, 0660),

        ]

        # SLES 11 is too smart, and finds our loop device by major/minor
        if os.path.exists('/dev/loop0'):
            rootLoopDev = os.stat('/dev/loop0')
            rootLoopMajor = os.major(rootLoopDev.st_rdev)
            rootLoopMinor = os.minor(rootLoopDev.st_rdev)
            self.devices.append(('loop%d' %  rootLoopMinor, 'b', 
                    rootLoopMajor, rootLoopMinor, 0660))

    def addFilesystem(self, mountPoint, fs):
        self.filesystems[mountPoint] = fs

    def mountAll(self):
        rootDir = os.path.join(self.workDir, "root")
        mounts = sortMountPoints(self.filesystems.keys())
        for mountPoint in reversed(mounts):
            util.mkdirChain(rootDir + mountPoint)
            self.filesystems[mountPoint].mount(rootDir + mountPoint)

    def umountAll(self):
        mounts = sortMountPoints(self.filesystems.keys())
        for mountPoint in mounts:
            self.filesystems[mountPoint].umount()

    def findFile(self, baseDir, fileName):
        for base, dirs, files in os.walk(baseDir):
            matches = sorted(x for x in files if re.match(fileName, x))
            if matches:
                path = os.path.join(base, matches[0])
                log.info("match found for %s", path)
                return path
        return None


    ## Script helpers
    def filePath(self, path):
        while path.startswith('/'):
            path = path[1:]
        return os.path.join(self.root, path)

    def fileExists(self, path):
        return os.path.exists(self.filePath(path))

    def readFile(self, path):
        return open(self.filePath(path)).read()

    def createDirectory(self, path, mode=0755):
        path = self.filePath(path)
        if not os.path.isdir(path):
            os.makedirs(path)
            os.chmod(path, mode)

    def createFile(self, path, contents='', mode=0644):
        self.createDirectory(os.path.dirname(path))
        path = self.filePath(path)
        open(path, 'wb').write(contents)
        os.chmod(path, mode)
        return path

    def appendFile(self, path, contents):
        self.createDirectory(os.path.dirname(path))
        open(self.filePath(path), 'ab').write(contents)
        return path

    def deleteFile(self, path):
        os.unlink(self.filePath(path))


    ## Pre/post scripts
    @timeMe
    def preInstallScripts(self):
        # /proc and /sys are already created and mounted
        self.createDirectory('dev')
        self.createDirectory('root')
        self.createDirectory('tmp')
        self.createDirectory('var')
        self.createDirectory('boot/grub')
        self.createDirectory('etc/sysconfig/network-scripts')

        # Create fstab early for RPM scripts to use.  Use normal
        # defaults that will work on RPM-based and Conary-based
        # systems.  If this becomes insufficient, we will need
        # to add default fstab setup to product definition.
        fstab = ""
        for mountPoint in reversed(sortMountPoints(self.filesystems.keys())):
            reqSize, freeSpace, fsType = self.mountDict[mountPoint]
            fs = self.filesystems[mountPoint]

            if fsType != 'swap':
                fstab += "LABEL=%s\t%s\t%s\tdefaults\t1\t%d\n" % (
                    (fs.fsLabel, mountPoint, fsType,
                        (mountPoint == '/') and 1 or 2))
            else:
                fstab += "LABEL=%s\tswap\tswap\tdefaults\t0\t0\n" % mountPoint

        # Add elements that might otherwise be missing:
        if 'devpts ' not in fstab:
            fstab += "devpts                  /dev/pts                devpts  gid=5,mode=620  0 0\n"
        if '/dev/shm ' not in fstab:
            fstab += "tmpfs                   /dev/shm                tmpfs   defaults        0 0\n"
        if '/proc ' not in fstab:
            fstab += "proc                    /proc                   proc    defaults        0 0\n"
        if '/sys ' not in fstab:
            fstab += "sysfs                   /sys                    sysfs   defaults        0 0\n"
        if self.swapSize and self.swapPath and ' swap ' not in fstab:
            fstab += "%s\tswap\tswap\tdefaults\t0\t0\n" % self.swapPath

        self.createFile('etc/fstab', fstab)

        # Create devices that we need most of the time.
        for dev, type, major, minor, mode in self.devices:
            devicePath = self.filePath('dev/%s' % dev)
            if os.path.exists(devicePath):
                os.unlink(devicePath)

            if type == 'c':
                flags = stat.S_IFCHR
            else:
                flags = stat.S_IFBLK

            # Create device.
            devnum = os.makedev(major, minor)
            os.mknod(devicePath, flags, devnum)
            os.chmod(devicePath, mode)

    @timeMe
    def preTagScripts(self):
        fakeRoot = self.root
        #create a swap file
        if self.swapSize:
            swapFile = util.joinPaths(fakeRoot, self.swapPath)
            util.mkdirChain(os.path.dirname(swapFile))
            # sparse files cannot work for swap space
            logCall('dd if=/dev/zero of=%s bs=4096 count=%d' % (
                    swapFile, self.swapSize / 4096))
            logCall('/sbin/mkswap %s' % swapFile)
            os.chmod(swapFile, 0600)

        # Copy a skeleton config tree.
        # Exclude things that are not being installed.
        exceptFiles = []

        # GPM (mouse daemon for virtual terminals)
        if not os.path.isfile(os.path.join(fakeRoot, 'usr', 'sbin', 'gpm')):
            exceptFiles.append(os.path.join(os.path.sep,
                                            'etc', 'sysconfig', 'mouse'))

        # X windows
        start_x = False
        for svc in ('xdm', 'gdm', 'kdm'):
            if not os.path.isfile(os.path.join(fakeRoot, 'etc', 'init.d', svc)):
                continue
            # make sure the binary exists too
            for path in (('usr', 'X11R6', 'bin'),
                         ('usr', 'bin')):
                if os.path.isfile(os.path.join(*(fakeRoot,) + path + (svc,))):
                    start_x = True

        if not start_x:
            exceptFiles.append(os.path.join(os.path.sep, 'etc', 'X11.*'))

        # use the appropriate skeleton files depending on the OS base
        if is_SUSE(fakeRoot):
            skelDir = os.path.join(constants.skelDir, 'sle')
        elif is_UBUNTU(fakeRoot):
            skelDir = os.path.join(constants.skelDir, 'ubuntu')
        else:
            skelDir = os.path.join(constants.skelDir, 'rpl')

        copytree(skelDir, fakeRoot, exceptFiles)

        self.writeConaryRc(os.path.join(fakeRoot, 'etc', 'conaryrc'), self.cc)
        self.writeSystemModel(os.path.join(fakeRoot, 'etc', 'conary',
            'system-model'))

        # If X is available, use runlevel 5 by default, for graphical login
        if start_x:
            inittab = os.path.join(fakeRoot, 'etc', 'inittab')
            if os.path.isfile(inittab):
                cmd = r"/bin/sed -e 's/^\(id\):[0-6]:\(initdefault:\)$/\1:5:\2/' -i %s" % inittab
                logCall(cmd)
            else:
                log.warning("inittab does not appear to be present")

        # copy timezone data into /etc/localtime
        if os.path.exists(os.path.join(fakeRoot, 'usr', 'share', 'zoneinfo', 'UTC')):
            copyfile(os.path.join(fakeRoot, 'usr', 'share', 'zoneinfo', 'UTC'),
                     os.path.join(fakeRoot, 'etc', 'localtime'))

        # Write the /etc/sysconfig/appliance-name for distro-release initscript.
        # Only overwrite if the file is non existent or empty. (RBL-3104)
        appliancePath = os.path.join(fakeRoot, 'etc', 'sysconfig')
        if not os.path.exists(appliancePath):
            util.mkdirChain(appliancePath)

        appNameFile = os.path.join(appliancePath, 'appliance-name')
        if not os.path.exists(appNameFile) or not os.path.getsize(appNameFile):
            f = open(appNameFile, 'w')
            name = self.jobData['project']['name']
            if isinstance(name, unicode):
                name = name.encode('utf8')
            f.write(name + '\n')
            f.close()

        # Disable selinux by default
        selinux = 'etc/selinux/config'
        if self.fileExists(selinux):
            contents = self.readFile(selinux)
            contents = contents.replace('SELINUX=enforcing\n',
                    '# NOTE: This is overridden by rBuilder. To prevent this, '
                    'change it back using a group post-install script.\n'
                    'SELINUX=disabled\n')
            self.createFile(selinux, contents)

        if is_SUSE(self.root):
            # SUSE needs /dev/fd for mkinitrd (RBL-5689)
            os.symlink('/proc/self/fd', self.filePath('dev/fd'))
        elif is_SUSE(self.root, version=11):
            self.createFile('etc/sysconfig/mkinitrd', 'OPTIONS="-A"\n')

        # Configure the bootloader (but don't install it yet).
        self.bootloader.setup()

        self.addScsiModules()
        self.writeDeviceMaps()

    @timeMe
    def postTagScripts(self):
        # misc. stuff that needs to run after tag handlers have finished
        dhcp = self.filePath('etc/sysconfig/network/dhcp')
        if os.path.isfile(dhcp):
            # tell SUSE to set the hostname via DHCP
            cmd = r"""/bin/sed -e 's/DHCLIENT_SET_HOSTNAME=.*/DHCLIENT_SET_HOSTNAME="yes"/g' -i %s""" % dhcp
            logCall(cmd)

        logCall('rm -rf %s/var/lib/conarydb/rollbacks/*' % self.root)

        # set up shadow passwords/md5 passwords
        authConfigCmd = ('chroot %s %%s --kickstart --enablemd5 --enableshadow'
                         ' --disablecache' % self.root)
        if self.fileExists('/usr/sbin/authconfig'):
            logCall(authConfigCmd % '/usr/sbin/authconfig')
        elif self.fileExists('/usr/bin/authconfig'):
            logCall(authConfigCmd % '/usr/bin/authconfig')
        elif self.fileExists('/usr/sbin/pwconv'):
            logCall("chroot %s /usr/sbin/pwconv" % self.root)

        # allow empty password to log in for virtual appliance
        fn = self.filePath('etc/pam.d/common-auth')
        if os.path.exists(fn):
            f = open(fn)
            lines = []
            for line in f:
                line = line.strip()
                if 'pam_unix2.so' in line and 'nullok' not in line:
                    line += ' nullok'
                lines.append(line)
            lines.append('')
            f = open(fn, 'w')
            f.write('\n'.join(lines))
            f.close()

        # Unlock the root account by blanking its password, unless a valid
        # password is already set.
        if (self.fileExists('usr/sbin/usermod') and not
                hasRootPassword(self.root)):
            log.info("Blanking root password.")
            logCall("chroot %s /usr/sbin/usermod -p '' root" % self.root,
                    ignoreErrors=True)
        else:
            log.info("Not changing root password.")

        # Set up selinux autorelabel if appropriate
        selinux = self.filePath('etc/selinux/config')
        if os.path.exists(selinux):
            selinuxLines = [x.strip() for x in file(selinux).readlines()]
            if not 'SELINUX=disabled' in selinuxLines:
                self.createFile('.autorelabel')

        # Install CA certificates for system inventory registration.
        self.installCertificates()

        # write an appropriate SLES inittab for XenServer
        # and update /etc/securetty so that logins work.
        if is_SUSE(self.root):
            if (self.jobData['buildType'] == buildtypes.XEN_OVA):
                cmd = r"/bin/sed -e 's/^#cons:/cons:/' -e 's/^\([1-6]\):/#\1:/' -i %s" % self.filePath('/etc/inittab')
                logCall(cmd)
                cmd = r"echo -e 'console\nxvc0' >> %s" % self.filePath('/etc/securetty')
                logCall(cmd)
            elif (self.jobData['buildType'] == buildtypes.AMI):
                cmd = r"/bin/sed -i 's/^#\(l4\)/\1/g' %s" % self.filePath('/etc/inittab')
                logCall(cmd)
                # This returns a non-zero exit code
                try:
                    if is_SUSE(self.root, version=10):
                        cmd = r"chroot %s /sbin/chkconfig --levels 2345 network on" % self.root
                    else:
                        cmd = r"chroot %s /sbin/chkconfig -s network 2345" % self.root
                    logCall(cmd)
                except:
                    pass

        # RedHat needs a config to tell it it's okay to upgrade the kernel
        if is_RH(self.root) and not self.fileExists('etc/sysconfig/kernel'):
            self.createFile('etc/sysconfig/kernel',
                    "UPDATEDEFAULT=yes\n"
                    "DEFAULTKERNEL=kernel\n"
                    )

        # Finish installation of bootloader
        if not self.fileExists('boot/boot'):
            # So /boot/blah in grub conf still works if /boot is separate
            os.symlink('.', self.filePath('boot/boot'))
        self.bootloader.install()

    def _writeCert(self, dirpath, filename, contents):
        """Write a SSL cert to a certificate directory."""
        relpath = os.path.join(dirpath, filename)
        self.createFile(relpath, contents)

        try:
            f = os.popen("chroot '%s' openssl x509 -noout -hash -in '%s'" %
                    (self.root, relpath))
            hash = f.readline().strip()
            f.close()
        except:
            log.exception("Failed to hash certificate %s:", relpath)
            return
        if not hash:
            log.error("Failed to hash certificate %s", relpath)
            return

        os.symlink(filename,
                self.filePath(os.path.join(dirpath, "%s.0" % hash)))

    def installCertificates(self):
        pki = self.jobData.get('pki', {})

        hg_path = '/etc/conary/rpath-tools/certs'
        hg_ca = pki.get('hg_ca')
        if hg_ca:
            self._writeCert(hg_path, 'rbuilder-hg.pem', hg_ca)

        lg_path = '/etc/conary/sfcb/clients'
        lg_ca = pki.get('lg_ca')
        if lg_ca:
            self._writeCert(lg_path, 'rbuilder-lg.pem', lg_ca)

        inventory_node = self.jobData.get('inventory_node')
        cfg_path = '/etc/conary/rpath-tools/config.d/directMethod'
        if inventory_node and not self.fileExists(cfg_path):
            self.createFile(cfg_path,
                    'directMethod []\n'
                    'directMethod %s\n'
                    % (inventory_node,))
        cfg_path = '/etc/conary/config.d/rpath-tools-conaryProxy'
        if inventory_node and not self.fileExists(cfg_path):
            proxy = inventory_node.replace(':8443', '')
            self.createFile(cfg_path, "proxyMap * conarys://%s\n" % proxy)

    def downloadChangesets(self):
        if self.uJob is not None:
            return
        self.conarycfg.flavor = [self.baseFlavor]
        self.conarycfg.initializeFlavors()
        cclient = self._openClient(self.tempRoot)
        cclient.setUpdateCallback(InstallCallback(self.status))

        uJob = cclient.newUpdateJob()
        tc = modelupdate.CMLTroveCache(cclient.db, cclient.repos)
        ts = cclient.cmlGraph(self.cml)
        cclient._updateFromTroveSetGraph(uJob, ts, tc)
        util.mkdirChain(self.changesetDir)
        cclient.downloadUpdate(uJob, self.changesetDir)
        self.uJob = uJob

    @timeMe
    def getTroveSize(self, mounts):
        self.downloadChangesets()
        return filesystems.calculatePartitionSizes(self.uJob, mounts)

    def getImageSize(self, realign=512, offset=None):
        if offset is None:
            offset = self.geometry.offsetBytes
        mounts = [x[0] for x in self.jobData['filesystems'] if x[0]]
        self.status("Calculating filesystem sizes...")
        sizes, totalSize = self.getTroveSize(mounts)

        swapMount = self.find_mount(self.swapPath)

        totalSize = 0
        realSizes = {}
        for x in self.mountDict.keys():
            requestedSize, minFreeSpace, fsType = self.mountDict[x]

            if requestedSize - sizes[x] < minFreeSpace:
                requestedSize += sizes[x] + minFreeSpace

            # Add swap file to requested size
            if self.swapSize and x == swapMount:
                requestedSize += self.swapSize

            # pad size if ext3
            if fsType != 'swap':
                requestedSize = int(ceil((requestedSize + 20 * 1024 * 1024) / 0.87))
            # realign to sector if requested
            if realign:
                adjust = (realign - (requestedSize % realign)) % realign
                requestedSize += adjust

            totalSize += requestedSize
            realSizes[x] = requestedSize

        totalSize += offset

        return totalSize, realSizes

    @timeMe
    def addScsiModules(self):
        # FIXME: this part of the code needs a rewrite, because any
        # bootable image type / distro combination may need different
        # drivers to be specified here.  It's not a simple True/False.
        # Also, 'Raw HD Image' means QEMU/KVM to me, but someone else
        # might be using it with another environment.
        filePath = self.filePath('etc/modprobe.conf')
        if (self.jobData['buildType'] == buildtypes.AMI):
            moduleList = [ 'xenblk' ]
        else:
            moduleList = [ 'mptbase', 'mptspi' ]

        if is_SUSE(self.root):
           filePath = filePath + '.local'  
           if self.jobData['buildType'] == buildtypes.RAW_HD_IMAGE:
               self.scsiModules = True
               moduleList = [ 'piix', ]

        if not self.scsiModules:
            return

        if not os.path.exists(filePath):
            log.warning('%s not found while adding scsi modules' % \
                        os.path.basename(filePath))

        util.mkdirChain(os.path.split(filePath)[0])
        f = open(filePath, 'a')
        if os.stat(filePath)[6]:
            f.write('\n')
        for idx in range(0,len(moduleList)):
            f.write("alias scsi_hostadapter%s %s\n" % \
                (idx and idx or '', moduleList[idx]))
        f.close()

    @timeMe
    def writeDeviceMaps(self):
        # first write a grub device map
        filePath = self.filePath('boot/grub/device.map')
        util.mkdirChain(os.path.dirname(filePath))
        f = open(filePath, 'w')
        hd0 = '/dev/sda'
        f.write('\n'.join(('# this device map was generated by rBuilder',
                           '(fd0) /dev/fd0',
                           '(hd0) %s' %hd0,
                           '')))
        f.close()

        # next write a blkid cache file
        dev = '/dev/sda1'
        devno = '0x0801'
        # get the uuid of the root filesystem
        p = subprocess.Popen(
            "tune2fs -l /dev/loop0 | grep UUID | awk '{print $3}'",
            shell = True, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        stdout, stderr = p.communicate()
        uuid = stdout.strip()
        root = self.filesystems['/']
        blkid = ('<device DEVNO="%s" TIME="%s" LABEL="root" '
                'UUID="%s" TYPE="%s">%s</device>\n'
                % (devno, int(time.time()), uuid, root.fsType, dev))
        path = self.createFile('etc/blkid/blkid.tab', blkid)
        os.link(path, self.filePath('etc/blkid.tab'))

    @timeMe
    def updateGroupChangeSet(self, cclient):
        cclient.applyUpdateJob(self.uJob, replaceFiles=True, noRestart=True,
            tagScript = os.path.join(self.conarycfg.root, 'root', 'conary-tag-script.in'))

    @timeMe
    def installBootstrapTroves(self, callback):
        pd = self.getProductDefinition()
        if not pd:
            return
        info = pd.getPlatformInformation()
        if not info or not info.bootstrapTroves:
            return
        bootstrapTroves = info.bootstrapTroves

        # TODO: Use the full search path for this, although it's super unlikely
        # to cause problems. To insure against subtle bugs in the future,
        # assert that the trove has no flavor.
        installLabelPath = [Label(x.label.encode('ascii'))
                for x in pd.getGroupSearchPaths()]
        result = self.nc.findTroves(installLabelPath, bootstrapTroves)
        jobList = []
        for query, matches in result.items():
            name, version, flavor = max(matches)
            if not flavor.isEmpty():
                log.error("Bootstrap trove %s=%s[%s] cannot be installed "
                        "because it has a flavor.", name, version, flavor)
                raise RuntimeError("Bootstrap troves must not have a flavor")
            jobList.append((name, (None, None), (version, flavor), True))

        log.info("Installing %d bootstrap trove(s)", len(jobList))
        oldDB = self.conarycfg.dbPath
        tmpDB = oldDB + '.bootstrap'
        cclient = None
        try:
            self.conarycfg.dbPath = tmpDB
            cclient = conaryclient.ConaryClient(self.conarycfg)
            uJob = cclient.newUpdateJob()
            cclient.prepareUpdateJob(uJob, jobList, resolveDeps=False)
            cclient.applyUpdateJob(uJob, replaceFiles=True, noRestart=True)
        finally:
            if cclient:
                cclient.close()
            self.conarycfg.dbPath = oldDB
        util.rmtree(self.filePath(tmpDB))

    @timeMe
    def runTagScripts(self):
        dest = self.root
        self.status("Running tag scripts")

        outScript = os.path.join(dest, 'root', 'conary-tag-script')
        inScript = outScript + '.in'
        outs = open(outScript, 'wt')
        ins = open(inScript, 'rt')
        outs.write('/sbin/ldconfig\n')
        for line in ins:
            if not line.startswith('/sbin/ldconfig'):
                outs.write(line)
        ins.close()
        outs.close()
        os.unlink(os.path.join(dest, 'root', 'conary-tag-script.in'))

        for tagScript in ('conary-tag-script', 'conary-tag-script-kernel'):
            tagPath = util.joinPaths(os.path.sep, 'root', tagScript)
            if not os.path.exists(util.joinPaths(dest, tagPath)):
                continue
            try:
                logCall("chroot %s sh -c 'sh -x %s > %s 2>&1'" %
                        (dest, tagPath, tagPath + '.output'))
            except Exception, e:
                exc, e, bt = sys.exc_info()
                try:
                    log.warning('error executing %s: %s', tagPath, e)
                    log.warning('script contents:')
                    f = file(util.joinPaths(dest, tagPath), 'r')
                    log.warning('----------------\n' + f.read())
                    f.close()
                    log.warning('script output:')
                    f = file(util.joinPaths(dest, tagPath + '.output'), 'r')
                    log.warning('----------------\n' + f.read())
                    f.close()
                except:
                    log.warning('error recording tag handler output')
                raise exc, e, bt

    @classmethod
    def dereferenceLink(cls, fname):
        if not (os.path.islink(fname) and os.access(fname, os.R_OK)):
            return ''
        linkname = os.readlink(fname)
        return linkname

    @classmethod
    def pidHasOpenFiles(cls, dest, pid):
        exeLink = os.path.join(os.path.sep, 'proc', pid, 'exe')
        exepath = cls.dereferenceLink(exeLink)
        if exepath.startswith(dest):
            log.info('Chrooted process %s (%s)', pid, exepath)
            return True
        # More expensive checks
        fdDir = os.path.join(os.path.dirname(exeLink), 'fd')
        if not os.access(fdDir, os.R_OK):
            return False
        ret = False
        for fd in os.listdir(fdDir):
            fdLink = os.path.join(fdDir, fd)
            fdpath = cls.dereferenceLink(fdLink)
            if fdpath.startswith(dest):
                log.info('Process %s (%s) has open file %s', pid, exepath,
                    fdpath)
                #ret = True
        return ret

    @classmethod
    @timeMe
    def killChrootProcesses(cls, dest):
        # kill any lingering processes that were started in the chroot
        pids = set()
        for pid in os.listdir('/proc'):
            if cls.pidHasOpenFiles(dest, pid):
                pids.add(pid)

        sig = signal.SIGTERM
        loops = 0
        while pids:
            # send a kill signal to any process that has an executable
            # from the chroot
            for pid in pids.copy():
                log.info('Killing pid %s with signal %d', pid, sig)
                os.kill(int(pid), sig)

            time.sleep(.1)
            # see what died
            for pid in pids.copy():
                if not os.path.isdir(os.path.join(os.path.sep, 'proc', pid)):
                    pids.remove(pid)

            # for anything left around, kill it harder
            sig = signal.SIGKILL
            loops += 1
            if loops > 10:
                raise RuntimeError(
                    'unable to kill chroot pids: %s' %(', '.join(pids)))

    @timeMe
    def umountChrootMounts(self, dest):
        # umount all mounts inside the chroot.
        mounts = open('/proc/mounts', 'r')
        mntlist = set()
        for line in mounts:
            line = line.strip()
            mntpoint = line.split(' ')[1]
            if not mntpoint.startswith(dest):
                continue
            # Ignore actual managed filesystem mounts
            name = mntpoint[len(dest):]
            if not name:
                name = '/'
            if name in self.mountDict:
                continue
            mntlist.add(mntpoint)
        # unmount in reverse sorted order to get /foo/bar before /foo
        for mntpoint in reversed(sorted(mntlist)):
            logCall('umount -n %s' % mntpoint)

    def _openClient(self, root):
        self.conarycfg.root = root
        # page_size has to be set before the first table is created
        path = util.joinPaths(root, self.conarycfg.dbPath + '/conarydb')
        util.mkdirChain(os.path.dirname(path))
        db = dbstore.connect(path, driver='sqlite')
        cu = db.cursor()
        cu.execute("PRAGMA page_size = 4096")
        db.commit()
        cu.execute("VACUUM")
        db.commit()
        db.close()

        # The rest are per-session and apply only to this install job
        cclient = conaryclient.ConaryClient(self.conarycfg)
        cclient.db.opJournalPath = None
        db = cclient.db.db.db
        cu = db.cursor()
        cu.execute("PRAGMA cache_size = 200000")
        cu.execute("PRAGMA journal_mode = MEMORY")
        db.commit()
        return cclient

    @timeMe
    def installFileTree(self, dest, bootloader_override=None,
            no_mbr=False):
        self.downloadChangesets()
        self.root = dest
        self.status('Installing image contents')
        self.loadRPM()

        if os.access(constants.tmpDir, os.W_OK):
            util.settempdir(constants.tmpDir)
            log.info("Using %s as tmpDir" % constants.tmpDir)
        else:
            log.warning("Using system temporary directory")

        self.conarycfg.root = dest
        self.conarycfg.installLabelPath = [self.baseVersion.trailingLabel()]
        self.conarycfg.configLine("pinTroves " + self.getPins())
        try:
            self.createDirectory('proc')
            self.createDirectory('sys')
            logCall('mount -n -t proc none %s' % os.path.join(dest, 'proc'))
            logCall('mount -n -t sysfs none %s' % os.path.join(dest, 'sys'))

            self.preInstallScripts()

            callback = None
            cclient = self._openClient(dest)
            try:
                callback = InstallCallback(self.status)
                cclient.setUpdateCallback(callback)

                # Tell SLES RPM scripts that we're building a fresh system
                os.environ['YAST_IS_RUNNING'] = 'instsys'

                self.installBootstrapTroves(callback)
                self.updateGroupChangeSet(cclient)

                del os.environ['YAST_IS_RUNNING']

            finally:
                cclient.close()
                if callback:
                    callback.closeCB()
                cclient = callback = None

            self.status('Finalizing install')
            util.rmtree(self.changesetDir)

            if not self.bootloader:
                if (self.isDomU or 
                    self.jobData['buildType'] == buildtypes.AMI):
                    # pygrub requires that grub-install be run
                    bootloader_override = 'grub'
                self.bootloader = generators.get_bootloader(self, dest,
                        self.geometry, bootloader_override)

            if no_mbr:
                self.bootloader.do_install = False
            if self.isDomU:
                self.bootloader.force_domU = True

            self.preTagScripts()
            self.runTagScripts()
            self.postTagScripts()

            return self.bootloader

        finally:
            try:
                self.killChrootProcesses(dest)
            except:
                log.exception("Error during cleanup:")
            try:
                self.umountChrootMounts(dest)
            except:
                log.exception("Error during cleanup:")

    def loadRPM(self):
        """Insert the necessary RPM (if any) into sys.path."""
        pd = self.getProductDefinition()
        if pd:
            info = pd.getPlatformInformation()
            if info:
                # Platform info is present and indicates which RPM to use
                return self._loadRPMFromRequirement(info.rpmRequirements)

        # Platform info is not present, look in the group (legacy support)
        return self._loadRPMFromGroup()

    def _loadRPMFromGroup(self):
        """Locate RPM by inspecting the contents of the group."""
        # NOTE: This is for backwards compatibility with old RHEL platform
        # definitions that do not have a platformInformation segment. It isn't
        # very pretty.
        log.info("Pre-proddef 4.1 platform or no platform available. "
                "Using fallback RPM detection.")
        imageTrove = self.nc.getTrove(withFiles=False, *self.baseTup)

        rpmLabels = set()
        for name, version, flavor in imageTrove.iterTroveList(True, True):
            if name in ('rpm:runtime', 'rpm:rpm'):
                rpmLabels.add(version.trailingLabel().asString())

        rpmPath = None
        for label in rpmLabels:
            if 'rhel-5' in label:
                rpmPath = 'rpm-rhel-5'
            elif 'rhel-4' in label:
                rpmPath = 'rpm-rhel-4'
        if not rpmPath:
            log.info("No RHEL RPM found in image group. "
                    "RPM capsules will not be installable.")
            return
        sitePackages = os.path.join(RPM_ALTERNATES, rpmPath,
                'lib64/python%s.%s/site-packages' % sys.version_info[:2])
        if not os.path.isdir(sitePackages):
            log.warning("RPM import path %s does not exist.", sitePackages)
            return

        self._installRPM(sitePackages)

    def _loadRPMFromRequirement(self, choices):
        """Locate RPM by looking for a trove that provides a given dep."""
        if not choices:
            # No RPM is needed.
            return

        # Find troves that provide the necessary RPM dep.
        log.info("Searching for a RPM trove matching one of these "
                "requirements:")
        for dep in sorted(choices):
            log.info("  %s", dep)
        found = self.cc.db.getTrovesWithProvides(choices)
        tups = list(itertools.chain(*found.values()))
        if tups:
            log.info("Checking these troves for loadable RPM:")
            for tup in sorted(tups):
                log.info("  %s=%s[%s]", *tup)
        else:
            log.error("No matching RPM trove found.")
            raise RuntimeError("Could not locate a RPM trove meeting the "
                    "necessary requirements.")

        # Search those troves for the python import root.
        targetRoot = "/python%s.%s/site-packages" % sys.version_info[:2]
        targetPaths = [ targetRoot + "/rpm/__init__.py",
                        targetRoot + '/rpmmodule.so' ]
        roots = set()
        for trove in self.cc.db.getTroves(tups, pristine=False):
            for pathId, path, fileId, fileVer in trove.iterFileList():
                for targetPath in targetPaths:
                    if path.endswith(targetPath):
                        root = path[:-len(targetPath)] + targetRoot
                        roots.add(root)

        # Insert into the search path and do a test import
        if not roots:
            raise RuntimeError("A required RPM trove was found but did not "
                    "contain a suitable python module (expected python%s.%s)" %
                    sys.version_info[:2])

        sitePackages = sorted(roots)[0]
        self._installRPM(sitePackages)

    def _installRPM(self, path):
        log.info("Using RPM from %s", path)
        if path in sys.path:
            sys.path.remove(path)
        sys.path.insert(0, path)
        __import__('rpm')

    @timeMe
    def gzip(self, source, dest = None):
        if os.path.isdir(source):
            if not dest:
                dest = source + '.tar.gz'
            parDir, targetDir = os.path.split(source)
            logCall('tar -C %s -cv %s | gzip > %s' % (parDir, targetDir, dest))
        else:
            if not dest:
                dest = source + '.gz'
            logCall('gzip -c %s > %s' % (source, dest))
        return dest

    @timeMe
    def zipArchive(self, source, dest=None):
        assert os.path.isdir(source)
        if not dest:
            dest = source + '.zip'
        parDir, targetDir = os.path.split(source)
        logCall(['/usr/bin/zip', '-r', dest, targetDir], cwd=parDir)
        return dest

    def write(self):
        raise NotImplementedError

    def find_mount(self, path):
        '''
        Return the mount point containing the given path.
        '''

        if not path.endswith('/'):
            path += '/'
        path = path.endswith('/') and path or (path + '/')

        for mountPoint in sortMountPoints(self.filesystems.keys()):
            _mountPoint = mountPoint.endswith('/') and mountPoint or (mountPoint + '/')
            if path.startswith(_mountPoint):
                return mountPoint

        return '/'

    def writeSystemModel(self, path):
        util.mkdirChain(os.path.dirname(path))
        with open(path, 'w') as fobj:
            print >> fobj, "# Generated by rPath Cloud Engine"
            self.cml.write(fobj)


def hasRootPassword(dest):
    """
    Return C{True} if the OS at C{dest} has a root password hash other than
    C{'*'} or C{'x'}. This includes blank passwords and explicitly disabled
    accounts, but not accounts that simply never had a password set.
    """
    for path in ('etc/passwd', 'etc/shadow'):
        path = os.path.join(dest, path)
        if not os.path.exists(path):
            continue
        for line in open(path):
            if ':' not in line:
                continue
            username, password = line.rstrip().split(':', 2)[:2]
            if username != 'root':
                continue
            if password not in ('*', 'x'):
                return True

    return False
