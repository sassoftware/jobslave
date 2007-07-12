#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

# python standard library imports
import errno
from math import ceil
import os
import sys
import re
import pwd
import stat
import time
import tempfile

# mint imports
from jobslave import buildtypes, jobslave_error
from jobslave import filesystems
from jobslave import loophelpers
from jobslave.filesystems import sortMountPoints
from jobslave.imagegen import ImageGenerator, MSG_INTERVAL, logCall
from jobslave.generators import constants

# conary imports
from conary import conaryclient
from conary import flavorcfg
from conary import versions
from conary.conarycfg import ConfigFile, CfgDict, CfgString, CfgBool
from conary.callbacks import UpdateCallback
from conary.conaryclient.cmdline import parseTroveSpec
from conary.deps import deps
from conary.lib import log, util
from conary.repository import errors

def getGrubConf(name, hasInitrd = True, xen = False, dom0 = False):
    xen = xen or dom0
    macros = {'name': name,
              'kversion'  : 'template',
              'initrdCmd' : '',
              'moduleCmd' : '',
              'timeOut'   : '5',
              'bootDev'   : 'hda',
              'kernelCmd' : 'kernel /boot/vmlinuz-%(kversion)s ro root=LABEL=/'}
    if hasInitrd:
        if dom0:
            macros['initrdCmd'] = 'module /boot/initrd-%(kversion)s.img'
        else:
            macros['initrdCmd'] = 'initrd /boot/initrd-%(kversion)s.img'
    macros['moduleCmd'] = ''
    if xen and not dom0:
        macros['bootDev'] = 'xvda'
        macros['timeOut'] = '0'
        macros['kernelCmd'] += ' quiet'
    elif xen and dom0:
        macros['moduleCmd'] = 'module /boot/vmlinuz-%(kversion)s ro ' \
            'root=LABEL=/'
        macros['kernelCmd'] = 'kernel /boot/xen.gz-%(kversion)s'
    r = '\n'.join(('#grub.conf generated by rBuilder',
                   '#',
                   '# Note that you do not have to rerun grub after ' \
                       'making changes to this file',
                   '#boot=%(bootDev)s',
                   'default=0',
                   'timeout=%(timeOut)s',
                   'title %(name)s (%(kversion)s)',
                   '    root (hd0,0)',
                   '    %(kernelCmd)s',
                   '    %(initrdCmd)s',
                   '    %(moduleCmd)s'
                   ))
    while '%' in r:
        r = r % macros
    r = '\n'.join([x for x in r.split('\n') if x.strip()])
    r += '\n\n'
    return r

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

def copytree(source, dest, exceptions = []):
    for root, dirs, files in os.walk(source):
        root = root.replace(source, '')
        for f in files:
            if not [x for x in exceptions if \
                        re.match(x, util.joinPaths(root, f))]:
                copyfile(util.joinPaths(source, root, f),
                         util.joinPaths(dest, root, f))
        for d in dirs:
            dir = util.joinPaths(dest, root, d)
            if not os.path.exists(dir) and not \
                    [x for x in exceptions if \
                         re.match(x, util.joinPaths(root, d))]:
                os.mkdir(dir)
                dStat = os.stat(util.joinPaths(source, root, d))
                os.chmod(dir, dStat[stat.ST_MODE])

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


class Filesystem:
    loopDev = None
    offset = None
    mounted = False
    fsType = None

    def __init__(self, fsDev, fsType, size, offset = 0, fsLabel = None):
        self.fsDev = fsDev
        self.size = size
        self.offset = offset
        self.fsLabel = fsLabel
        self.fsType = fsType

    def mount(self, mountPoint):
        if self.fsType == "swap":
            return

        self.loopDev = loophelpers.loopAttach(self.fsDev, offset = self.offset)
        logCall("mount %s %s" % (self.loopDev, mountPoint))
        self.mounted = True

    def umount(self):
        if not self.loopDev or not self.mounted:
            return

        if self.fsType == "swap":
            return

        logCall("umount %s" % self.loopDev)
        loophelpers.loopDetach(self.loopDev)
        self.mounted = False

    def format(self):
        if self.offset:
            loopDev = loophelpers.loopAttach(self.fsDev, offset = self.offset)
        else:
            loopDev = self.fsDev
        try:
            if self.fsType == 'ext3':
                cmd = 'mke2fs -L / -F -b 4096 %s' % loopDev
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


class BootableImage(ImageGenerator):
    filesystems = {}

    def __init__(self, *args, **kwargs):
        self.scsiModules = False

        ImageGenerator.__init__(self, *args, **kwargs)
        log.info('building trove: (%s, %s, %s)' % \
                 (self.baseTrove, self.baseVersion, str(self.baseFlavor)))

        self.workDir = os.path.join(constants.tmpDir, self.jobId)
        self.outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(self.outputDir)

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

    def makeImage(self):
        rootDir = os.path.join(self.workDir, "root")
        self.installFileTree(rootDir)

    @timeMe
    def setupGrub(self, fakeRoot):
        if not os.path.exists(os.path.join(fakeRoot, 'sbin', 'grub')):
            log.info("grub not found. skipping setup.")
            return
        util.copytree(os.path.join(fakeRoot, 'usr', 'share', 'grub', '*', '*'), os.path.join(fakeRoot, 'boot', 'grub'))

        #Create a stub grub.conf
        if os.path.exists(os.path.join(fakeRoot, 'etc', 'issue')):
            f = open(os.path.join(fakeRoot, 'etc', 'issue'))
            name = f.readline().strip()
            f.close()
        else:
            name = self.jobData['project']['name']
        bootDirFiles = os.listdir(os.path.join(fakeRoot, 'boot'))
        xen = bool([x for x in bootDirFiles if re.match('vmlinuz-.*xen.*', x)])
        dom0 = bool([x for x in bootDirFiles if re.match('xen.gz-.*', x)])
        hasInitrd = bool([x for x in bootDirFiles \
                              if re.match('initrd-.*.img', x)])
        conf = getGrubConf(name, hasInitrd, xen, dom0)

        f = open(os.path.join(fakeRoot, 'boot', 'grub', 'grub.conf'), 'w')
        f.write(conf)
        f.close()

        os.chmod(os.path.join(fakeRoot, 'boot/grub/grub.conf'), 0600)
        #create the appropriate links
        os.symlink('grub.conf', os.path.join(fakeRoot, 'boot', 'grub', 'menu.lst'))
        os.symlink('../boot/grub/grub.conf', os.path.join(fakeRoot, 'etc', 'grub.conf'))

    def findFile(self, baseDir, fileName):
        for base, dirs, files in os.walk(baseDir):
            matches = [x for x in files if re.match(fileName, x)]
            if matches:
                print >> sys.stderr, "match found for %s" % \
                      os.path.join(base, matches[0])
                return os.path.join(base, matches[0])
        return None

    @timeMe
    def createTemporaryRoot(self, fakeRoot):
        for d in ('etc', 'etc/sysconfig', 'etc/sysconfig/network-scripts',
                  'boot/grub', 'tmp', 'proc', 'sys', 'root', 'var'):
            util.mkdirChain(os.path.join(fakeRoot, d))


    @timeMe
    def fileSystemOddsNEnds(self, fakeRoot):
        rnl5 = False
        for svc in ('xdm', 'gdm', 'kdm'):
            rnl5 |= os.path.isfile(os.path.join(fakeRoot, 'etc', 'init.d', svc))

        gpm = os.path.isfile(os.path.join(fakeRoot, 'usr', 'sbin', 'gpm'))

        exceptFiles = []
        if not rnl5:
            exceptFiles.append(os.path.join(os.path.sep, 'etc', 'X11.*'))
        if not gpm:
            exceptFiles.append(os.path.join(os.path.sep,
                                            'etc', 'sysconfig', 'mouse'))
        copytree(constants.skelDir, fakeRoot, exceptFiles)

        self.writeConaryRc(os.path.join(fakeRoot, 'etc', 'conary', 'config.d',
                                        self.basefilename), self.cc)

        if rnl5:
            #tweak the inittab to start at level 5
            cmd = r"/bin/sed -e 's/^\(id\):[0-6]:\(initdefault:\)$/\1:5:\2/' -i %s" % os.path.join(fakeRoot, 'etc', 'inittab')
            logCall(cmd)

        # copy timezone data into /etc/localtime
        if os.path.exists(os.path.join(fakeRoot, 'usr', 'share', 'zoneinfo', 'UTC')):
            copyfile(os.path.join(fakeRoot, 'usr', 'share', 'zoneinfo', 'UTC'),
                     os.path.join(fakeRoot, 'etc', 'localtime'))

        # extend fstab based on the list of filesystems we have added
        f = open(os.path.join(fakeRoot, 'etc', 'fstab'))
        oldFstab = f.read()
        f.close()

        fstabExtra = ""
        for mountPoint in reversed(sortMountPoints(self.filesystems.keys())):
            reqSize, freeSpace, fsType = self.mountDict[mountPoint]

            if fsType == "ext3":
                fstabExtra += "LABEL=%s\t%s\text3\tdefaults\t1\t%d\n" % \
                    (mountPoint, mountPoint, (mountPoint == '/') and 1 or 2)
            elif fsType == "swap":
                fstabExtra += "LABEL=%s\tswap\tswap\tdefaults\t0\t0\n" % mountPoint
        fstab = open(os.path.join(fakeRoot, 'etc', 'fstab'), 'w')
        fstab.write(fstabExtra)
        fstab.write(oldFstab)
        fstab.close()

        # write the /etc/sysconfig/appliance-name for rpl:2 initscripts
        util.mkdirChain(os.path.join(fakeRoot, 'etc', 'sysconfig'))
        appName = open(os.path.join(fakeRoot, 'etc', 'sysconfig', 'appliance-name'), 'w')
        print >> appName, self.jobData['project']['name']
        appName.close()

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

        totalSize = 0
        realSizes = {}
        for x in self.mountDict.keys():
            requestedSize, minFreeSpace, fsType = self.mountDict[x]

            if requestedSize - sizes[x] < minFreeSpace:
                requestedSize += sizes[x] + minFreeSpace

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
        filePath = os.path.join(dest, 'etc', 'modprobe.conf')
        f = open(filePath, 'a')
        if os.stat(filePath)[6]:
            f.write('\n')
        f.write('\n'.join(('alias scsi_hostadapter mptbase',
                           'alias scsi_hostadapter1 mptspi')))
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
    def installFileTree(self, dest):
        self.status('Installing image contents')
        self.createTemporaryRoot(dest)
        fd, cfgPath = tempfile.mkstemp(dir=constants.tmpDir)
        try:
            os.close(fd)
            self.saveConaryRC(cfgPath)
            logCall('mount -t proc none %s' % os.path.join(dest, 'proc'))
            logCall('mount -t sysfs none %s' % os.path.join(dest, 'sys'))

            self.conarycfg.root = dest
            self.conarycfg.installLabelPath = [versions.VersionFromString(self.baseVersion).branch().label()]

            cclient = conaryclient.ConaryClient(self.conarycfg)
            cclient.setUpdateCallback(InstallCallback(self.status))
            self.updateGroupChangeSet(cclient)

            # set up the flavor for the kernel install based on the 
            # rooted flavor setup.
            self.conarycfg.useDirs = [os.path.join(dest, 'etc/conary/use')]
            self.conarycfg.initializeFlavors()
            self.saveConaryRC(cfgPath)
            if not self.findFile(os.path.join(dest, 'boot'), 'vmlinuz.*'):
                self.updateKernelChangeSet(cclient)
            else:
                log.info('Kernel detected, skipping.')

            self.fileSystemOddsNEnds(dest)
            if self.scsiModules:
                self.addScsiModules(dest)
            self.setupGrub(dest)
            outScript = os.path.join(dest, 'root', 'conary-tag-script')
            inScript = outScript + '.in'
            logCall('echo "/sbin/ldconfig" > %s; cat %s | sed "s|/sbin/ldconfig||g" | grep -vx "" >> %s' % (outScript, inScript, outScript))
            os.unlink(os.path.join(dest, 'root', 'conary-tag-script.in'))
            for tagScript in ('conary-tag-script', 'conary-tag-script-kernel'):
                tagPath = util.joinPaths(os.path.sep, 'root', tagScript)
                if os.path.exists(util.joinPaths(dest, tagPath)):
                    logCall("chroot %s bash -c 'sh -x %s > %s 2>&1'" % \
                                     (dest, tagPath, tagPath + '.output'))
        finally:
            logCall('umount %s' % os.path.join(dest, 'proc'))
            logCall('umount %s' % os.path.join(dest, 'sys'))
            os.unlink(cfgPath)

        logCall('rm -rf %s' % os.path.join( \
                dest, 'var', 'lib', 'conarydb', 'rollbacks', '*'))

        # remove root password
        logCall("chroot %s /usr/sbin/authconfig --kickstart --enablemd5 --enableshadow --disablecache" % dest)
        logCall("chroot %s /usr/sbin/usermod -p '' root" % dest)

        # remove template kernel entry
        logCall('chroot %s /sbin/grubby --remove-kernel=/boot/vmlinuz-template' % dest)

    @timeMe
    def installGrub(self, fakeRoot, image, size):
        grubPath = os.path.join(fakeRoot, 'sbin', 'grub')
        if not os.path.exists(grubPath):
            log.info("grub not found. skipping execution.")
            return

        cylinders = size / constants.cylindersize
        grubCmds = "device (hd0) %s\n" \
                   "geometry (hd0) %d %d %d\n" \
                   "root (hd0,0)\n" \
                   "setup (hd0)" % (image, cylinders, constants.heads, constants.sectors)

        # add fakeRoot's libraries to LD_LIBRARY_PATH for grub
        libPaths = [('lib',), ('lib64',), ('usr', 'lib'), ('usr', 'lib64')]
        os.environ['LD_LIBRARY_PATH'] = ":".join(os.path.join(fakeRoot, *x) for x in libPaths)

        logCall('echo -e "%s" | '
                '%s --no-floppy --batch' % (grubCmds, grubPath))

    @timeMe
    def gzip(self, source, dest = None):
        if os.path.isdir(source):
            if not dest:
                dest = source + '.tgz'
            parDir, targetDir = os.path.split(source)
            logCall('tar -czv -C %s %s > %s' % (parDir, targetDir, dest))
            pass
        else:
            if not dest:
                dest = source + '.gz'
            logCall('gzip -c %s > %s' % (source, dest))
        return dest

    def write(self):
        raise NotImplementedError
