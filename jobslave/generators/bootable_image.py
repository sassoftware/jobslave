#
# Copyright (c) 2004-2009 rPath, Inc.
#
# All Rights Reserved
#

# python standard library imports
import logging
from math import ceil
import os
import sys
import re
import signal
import stat
import subprocess
import time
import traceback

# mint imports
from jobslave import filesystems
from jobslave import generators
from jobslave import helperfuncs
from jobslave import loophelpers
from jobslave.distro_detect import *
from jobslave.filesystems import sortMountPoints
from jobslave.imagegen import ImageGenerator, MSG_INTERVAL, logCall
from jobslave.generators import constants

# conary imports
from conary import conaryclient
from conary import versions
from conary.callbacks import UpdateCallback
from conary.conaryclient.cmdline import parseTroveSpec
from conary.deps import deps
from conary.lib import util
from conary.repository import errors

log = logging.getLogger(__name__)


def timeMe(func):
    def wrapper(self, *args, **kwargs):
        clock = time.clock()
        actual = time.time()
        returner = func(self, *args, **kwargs)
        log.info("%s: %.5f %.5f" % (func.__name__, time.clock() - clock, time.time() - actual))
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

        UpdateCallback.__init__(self)

    def closeCB(self):
        # Eliminate a reference from ConaryClient (which never frees
        # properly) back to the parent Generator.
        self.status = lambda x: None


class Filesystem:
    loopDev = None
    offset = None
    mounted = False
    fsType = None

    def __init__(self, fsDev, fsType, size, offset = 0, fsLabel = None):
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

    def mount(self, mountPoint):
        if self.fsType == "swap":
            return

        self.loopDev = loophelpers.loopAttach(self.fsDev, offset = self.offset)
        logCall("mount %s %s" % (self.loopDev, mountPoint))
        self.mounted = True
        self.mountPoint = mountPoint

    def umount(self):
        if self.fsType == "swap":
            return

        if not self.loopDev or not self.mounted:
            return

        try:
            logCall("umount %s" % self.loopDev)
        except RuntimeError:
            log.warning('Unmount of %s from %s failed - trying again',
                self.loopDev, self.mountPoint)

            clean = False
            for x in range(5):
                logCall("sync")
                time.sleep(1)
                try:
                    logCall("umount %s" % self.loopDev)
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

                raise RuntimeError('Failed to unmount %s' % self.loopDev)

        loophelpers.loopDetach(self.loopDev)
        self.mounted = False

    def format(self):
        if self.offset:
            loopDev = loophelpers.loopAttach(self.fsDev, offset = self.offset)
        else:
            loopDev = self.fsDev
        try:
            if self.fsType == 'ext3':
                cmd = 'mke2fs -F -b 4096 -I 128 %s' % loopDev
                if self.size:
                    cmd += ' %s' % (self.size / 4096)
                logCall(cmd)

                labelCmd = '-L "%s"' % self.fsLabel
                logCall('tune2fs -i 0 -c 0 -j %s %s' % (labelCmd, loopDev))
            elif self.fsType == 'swap':
                cmd = 'mkswap -L %s %s' % (self.fsLabel, loopDev)
                logCall(cmd)
            else:
                raise RuntimeError, "Invalid filesystem type: %s" % self.fsType
        finally:
            if self.offset:
                loophelpers.loopDetach(loopDev)

class StubFilesystem:
    def __init__(self):
        self.fsLabel = 'root'

    def mount(self, *args):
        pass

    def umount(self, *args):
        pass

    def format(self, *args):
        pass

class BootableImage(ImageGenerator):
    heads = constants.heads
    sectors = constants.sectors

    def __init__(self, *args, **kwargs):
        self.filesystems = { '/': StubFilesystem() }
        self.scsiModules = False

        ImageGenerator.__init__(self, *args, **kwargs)
        log.info('building trove: (%s, %s, %s)' % \
                 (self.baseTrove, self.baseVersion, str(self.baseFlavor)))

        self.workDir = os.path.join(constants.tmpDir, self.jobId)
        self.workingDir = os.path.join(self.workDir, self.basefilename)
        self.outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(self.outputDir)
        util.mkdirChain(self.workingDir)
        self.swapSize = self.getBuildData("swapSize") * 1048576
        self.swapPath = '/var/swap'
        self.outputFileList = []

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

    @timeMe
    def createTemporaryRoot(self, fakeRoot):
        for d in ('etc', 'etc/sysconfig', 'etc/sysconfig/network-scripts',
                  'boot/grub', 'tmp', 'proc', 'sys', 'root', 'var'):
            util.mkdirChain(os.path.join(fakeRoot, d))


    @timeMe
    def fileSystemOddsNEnds(self, fakeRoot):
        #create a swap file
        if self.swapSize:
            swapFile = util.joinPaths(fakeRoot, self.swapPath)
            util.mkdirChain(os.path.dirname(swapFile))
            # sparse files cannot work for swap space
            logCall('dd if=/dev/zero of=%s bs=4096 count=%d' % (
                    swapFile, self.swapSize / 4096))
            logCall('/sbin/mkswap %s' % swapFile)

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

        # extend fstab based on the list of filesystems we have added
        util.mkdirChain(os.path.join(fakeRoot, 'etc'))
        fstab = os.path.join(fakeRoot, 'etc', 'fstab')
        if os.path.exists(fstab):
            f = open(fstab)
            oldFstab = f.read()
            f.close()
        else:
            oldFstab = ""

        if not self.swapSize:
            oldFstab = '\n'.join([x for x in oldFstab.splitlines() \
                    if 'swap' not in x])

        fstabExtra = ""
        for mountPoint in reversed(sortMountPoints(self.filesystems.keys())):
            reqSize, freeSpace, fsType = self.mountDict[mountPoint]
            fs = self.filesystems[mountPoint]

            if fsType == "ext3":
                fstabExtra += "LABEL=%s\t%s\text3\tdefaults\t1\t%d\n" % \
                    (fs.fsLabel, mountPoint, (mountPoint == '/') and 1 or 2)
            elif fsType == "swap":
                fstabExtra += "LABEL=%s\tswap\tswap\tdefaults\t0\t0\n" % mountPoint
        fstab = open(os.path.join(fakeRoot, 'etc', 'fstab'), 'w')
        fstab.write(fstabExtra)
        fstab.write(oldFstab)
        fstab.close()

        # Write the /etc/sysconfig/appliance-name for distro-release initscript.
        # Only overwrite if the file is non existent or empty. (RBL-3104)
        appliancePath = os.path.join(fakeRoot, 'etc', 'sysconfig')
        if not os.path.exists(appliancePath):
            util.mkdirChain(appliancePath)

        appNameFile = os.path.join(appliancePath, 'appliance-name')
        if not os.path.exists(appNameFile) or not os.path.getsize(appNameFile):
            f = open(appNameFile, 'w')
            f.write('%s\n' % self.jobData['project']['name'])
            f.close()

    @timeMe
    def fileSystemOddsNEndsFinal(self, fakeRoot):
        # misc. stuff that needs to run after tag handlers have finished
        dhcp = os.path.join(fakeRoot, 'etc', 'sysconfig', 'network', 'dhcp')
        if os.path.isfile(dhcp):
            # tell SUSE to set the hostname via DHCP
            cmd = r"""/bin/sed -e 's/DHCLIENT_SET_HOSTNAME=.*/DHCLIENT_SET_HOSTNAME="yes"/g' -i %s""" % dhcp
            logCall(cmd)

    @timeMe
    def getTroveSize(self, mounts):
        log.info("getting changeset for partition sizing")
        job = (self.baseTrove, (None, None), (versions.VersionFromString(self.baseVersion), self.baseFlavor), True)
        cs = self.nc.createChangeSet([job], withFiles = True, withFileContents = False)
        sizes, totalSize = filesystems.calculatePartitionSizes(cs, mounts)

        return sizes, totalSize

    def getImageSize(self, realign = constants.sectorSize, partitionOffset = constants.partitionOffset):
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
            if fsType == "ext3":
                requestedSize = int(ceil((requestedSize + 20 * 1024 * 1024) / 0.87))
            # realign to sector if requested
            if realign:
                adjust = (realign - (requestedSize % realign)) % realign
                requestedSize += adjust

            totalSize += requestedSize
            realSizes[x] = requestedSize

        totalSize += constants.partitionOffset

        return totalSize, realSizes

    @timeMe
    def getKernelFlavor(self):
        flavor = ''
        if not self.baseFlavor.stronglySatisfies(deps.parseFlavor('use: xen')):
            flavor = '!kernel.smp is: %s' % self.arch
        return flavor

    @timeMe
    def addScsiModules(self, dest):
        if not self.scsiModules:
            return
        filePath = os.path.join(dest, 'etc', 'modprobe.conf')
        if not os.path.exists(filePath):
            log.warning('modprobe.conf not found while adding scsi modules')

        util.mkdirChain(os.path.split(filePath)[0])
        f = open(filePath, 'a')
        if os.stat(filePath)[6]:
            f.write('\n')
        f.write('\n'.join(('alias scsi_hostadapter mptbase',
                           'alias scsi_hostadapter1 mptspi',
                           '')))
        f.close()

    @timeMe
    def writeDeviceMaps(self, dest):
        # first write a grub device map
        filePath = os.path.join(dest, 'boot', 'grub', 'device.map')
        util.mkdirChain(os.path.dirname(filePath))
        f = open(filePath, 'w')
        if self.scsiModules:
            hd0 = '/dev/sda'
        else:
            hd0 = '/dev/hda'
        f.write('\n'.join(('# this device map was generated by rBuilder',
                           '(fd0) /dev/fd0',
                           '(hd0) %s' %hd0,
                           '')))
        f.close()

        # next write a blkid cache file
        filePath = os.path.join(dest, 'etc', 'blkid.tab')
        util.mkdirChain(os.path.dirname(filePath))
        f = open(filePath, 'w')
        if self.scsiModules:
            dev = '/dev/sda1'
            devno = '0x0801'
        else:
            dev = '/dev/hda1'
            devno = '0x0301'
        # get the uuid of the root filesystem
        p = subprocess.Popen(
            "tune2fs -l /dev/loop0 | grep UUID | awk '{print $3}'",
            shell = True, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        stdout, stderr = p.communicate()
        uuid = stdout.strip()
        f.write('<device DEVNO="%s" TIME="%s" LABEL="root" '
                'UUID="%s" SEC_TYPE="ext2" TYPE="ext3">%s</device>\n'
                % (devno, int(time.time()), uuid, dev))
        f.close()


    @timeMe
    def updateGroupChangeSet(self, cclient):
        itemList = [(self.baseTrove, (None, None), (self.baseVersion, self.baseFlavor), True)]

        uJob = cclient.newUpdateJob()
        cclient.prepareUpdateJob(uJob, itemList, resolveDeps = False)
        cclient.applyUpdateJob(uJob, replaceFiles = True, noRestart = True,
            tagScript = os.path.join(self.conarycfg.root, 'root', 'conary-tag-script.in'))

    @timeMe
    def updateKernelChangeSet(self, cclient):
        kernel, version, flavor = parseTroveSpec('kernel:runtime[%s]' % self.getKernelFlavor())
        itemList = [(kernel, (None, None), (version, flavor), True)]
        uJob = cclient.newUpdateJob()
        cclient.prepareUpdateJob(uJob, itemList, resolveDeps = False, sync = True)
        cclient.applyUpdateJob(uJob, replaceFiles = True, noRestart = False,
            tagScript = os.path.join(self.conarycfg.root, 'root', 'conary-tag-script-kernel'))

    @timeMe
    def runTagScripts(self, dest):
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

        if is_SUSE(dest, version=10):
            # SUSE needs udev to be started in the chroot in order to
            # run mkinitrd
            logCall("chroot %s sh -c '/etc/rc.d/boot.udev stop'" %dest)
            logCall("chroot %s sh -c '/etc/rc.d/boot.udev start'" %dest)
            logCall("chroot %s sh -c '/etc/rc.d/boot.udev force-reload'" %dest)
        elif is_SUSE(dest, version=11):
            # SLES 11 won't start udev since the socket already exists, must
            # bind mount dev instead.
            open('%s/etc/sysconfig/mkinitrd' % dest, 'w').write('OPTIONS="-A"\n')
            logCall("mount -o bind /dev %s/dev" % dest)

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

        if is_SUSE(dest, version=11):
            logCall("umount %s/dev" % dest)

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
            if mntpoint.startswith(dest) and mntpoint != dest:
                mntlist.add(mntpoint)
        # unmount in reverse sorted order to get /foo/bar before /foo
        for mntpoint in reversed(sorted(mntlist)):
            logCall('umount %s' % mntpoint)

    @timeMe
    def installFileTree(self, dest, bootloader_override=None):
        self.status('Installing image contents')
        self.createTemporaryRoot(dest)
        try:
            logCall('mount -t proc none %s' % os.path.join(dest, 'proc'))
            logCall('mount -t sysfs none %s' % os.path.join(dest, 'sys'))

            if os.access(constants.tmpDir, os.W_OK):
                util.settempdir(constants.tmpDir)
                log.info("Using %s as tmpDir" % constants.tmpDir)
            else:
                log.warning("Using system temporary directory")

            self.conarycfg.root = dest
            self.conarycfg.installLabelPath = [versions.VersionFromString(self.baseVersion).branch().label()]

            callback = None
            cclient = conaryclient.ConaryClient(self.conarycfg)
            try:
                callback = InstallCallback(self.status)
                cclient.setUpdateCallback(callback)

                self.updateGroupChangeSet(cclient)

                # set up the flavor for the kernel install based on the 
                # rooted flavor setup.
                self.conarycfg.useDirs = [os.path.join(dest, 'etc/conary/use')]
                self.conarycfg.initializeFlavors()
                if not self.findFile(os.path.join(dest, 'boot'), 'vmlinuz.*'):
                    self.status('Installing kernel')
                    try:
                        self.updateKernelChangeSet(cclient)
                    except conaryclient.NoNewTrovesError:
                        log.info('strongly-included kernel found--no new kernel trove to sync')
                    except errors.TroveNotFound:
                        log.info('no kernel found at all. skipping.')
                else:
                    log.info('Kernel detected, skipping.')
            finally:
                cclient.close()
                if callback:
                    callback.closeCB()
                cclient = callback = None

            self.status('Finalizing install')

            self.fileSystemOddsNEnds(dest)

            # Get a bootloader installer and pre-configure before running
            # tag scripts
            if self.baseFlavor.stronglySatisfies(deps.parseFlavor('domU')):
                # pygrub requires that grub-install be run
                bootloader_override = 'grub'

            bootloader_installer = generators.get_bootloader(self, dest,
                    self.sectors, self.heads, bootloader_override)
            bootloader_installer.setup()

            self.addScsiModules(dest)
            self.writeDeviceMaps(dest)
            self.runTagScripts(dest)
            self.fileSystemOddsNEndsFinal(dest)

            self.killChrootProcesses(dest)
            self.umountChrootMounts(dest)
        except:
            log.exception("Error building image:")
            e_type, e_value, e_tb = sys.exc_info()
            try:
                self.killChrootProcesses(dest)
            except:
                log.exception("Error during cleanup:")
            try:
                self.umountChrootMounts(dest)
            except:
                log.exception("Error during cleanup:")
            raise e_type, e_value, e_tb

        logCall('rm -rf %s' % os.path.join( \
                dest, 'var', 'lib', 'conarydb', 'rollbacks', '*'))

        # set up shadow passwords/md5 passwords
        authConfigCmd = ('chroot %s %%s --kickstart --enablemd5 --enableshadow'
                         ' --disablecach' % dest)
        if os.path.exists(os.path.join(dest, 'usr/sbin/authconfig')):
            logCall(authConfigCmd % '/usr/sbin/authconfig')
        elif os.path.exists(os.path.join(dest, 'usr/bin/authconfig')):
            logCall(authConfigCmd % '/usr/bin/authconfig')
        elif os.path.exists(os.path.join(dest, 'usr/sbin/pwconv')):
            logCall("chroot %s /usr/sbin/pwconv" % dest)

        # allow empty password to log in for virtual appliance
        fn = os.path.join(dest, 'etc/pam.d/common-auth')
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

        # Unlock the root account by blanking its password, unless a valid
        # password is already set.
        if (os.path.exists(os.path.join(dest, 'usr/sbin/usermod'))
                and not hasRootPassword(dest)):
            log.info("Blanking root password.")
            logCall("chroot %s /usr/sbin/usermod -p '' root" % dest,
                    ignoreErrors=True)
        else:
            log.info("Not changing root password.")

        # Finish installation of bootloader
        bootloader_installer.install()

        return bootloader_installer

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
