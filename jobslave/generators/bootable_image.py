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
from jobslave.generators import gencslist, constants
from jobslave.generators.imagegen import ImageGenerator, MSG_INTERVAL
#from mint.client import upstream

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

def getTroveSize(troveSpec):
    from conary import versions
    from conary.deps import deps
    from conary import conaryclient
    cc = conaryclient.ConaryClient()
    repos = cc.getRepos()
    n, v, f = conaryclient.cmdline.parseTroveSpec(troveSpec)
    NVF = repos.findTrove(None, (n, v, f), cc.cfg.flavor)[0]
    trove = repos.getTrove(*NVF)
    return trove.troveInfo.size()

def roundUpSize(size):
    # 13% accounts for reserved block and inode consumption
    size = int(math.ceil((size + TAGSCRIPT_GROWTH + SWAP_SIZE) / 0.87))
    # now round up to next cylinder size
    return size + ((CYLINDERSIZE - (size % CYLINDERSIZE)) % CYLINDERSIZE)

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

# this function is no longer used.
def getManifest(xorg = True, gpm = True):
    manifest = {
        'fstab' : os.path.join('etc', 'fstab'),
        'hosts' : os.path.join('etc', 'hosts'),
        'ifcfg-eth0' : os.path.join('etc', 'sysconfig', 'network-scripts',
                                    'ifcfg-eth0'),
        'init.sh' : os.path.join('tmp', 'init.sh'),
        'keyboard' : os.path.join('etc', 'sysconfig', 'keyboard'),
        'network' : os.path.join('etc', 'sysconfig', 'network')
        }
    xorgFiles = {
        'xorg.conf' : os.path.join('etc', 'X11', 'xorg.conf')
        }
    gpmFiles = {
        'mouse' : os.path.join('etc', 'sysconfig', 'mouse'),
        }
    if xorg:
        manifest.update(xorgFiles)
    if gpm:
        manifest.update(gpmFiles)
    return manifest

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
            msg = "Updating changesets: %d%% (%s)" % (percent, msg)

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


class BootableImage(ImageGenerator):
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
        conf = getGrubConf(hasInitrd, xen, dom0)

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
    def fileSystemOddsNEnds(self, fakeRoot, swapSize):
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

        # fix the fstab if needed
        if not swapSize:
            util.execute('sed -i "s/.*swap.*//" %s' % \
                             os.path.join(fakeRoot, 'etc', 'fstab'))
        else:
            cmd = 'dd if=/dev/zero of=%s count=%d bs=%d; /sbin/mkswap %s' % \
                (os.path.join(fakeRoot, 'var', 'swap'), swapSize / 512, 512,
                 os.path.join(fakeRoot, 'var', 'swap'))
            util.execute(cmd)

        if rnl5:
            #tweak the inittab to start at level 5
            cmd = r"/bin/sed -e 's/^\(id\):[0-6]:\(initdefault:\)$/\1:5:\2/' -i %s" % os.path.join(fakeRoot, 'etc', 'inittab')
            util.execute(cmd)

        # copy timezone data into /etc/localtime
        if not os.path.exists(os.path.join(fakeRoot, 'etc', 'localtime')):
            os.copy(os.path.join('usr', 'share', 'zoneinfo', 'UTC'),
                    os.path.join('etc', 'localtime'))

    def __init__(self, *args, **kwargs):
        ImageGenerator.__init__(self, *args, **kwargs)
        self.scsiModules = False

        log.info('building trove: (%s, %s, %s)' % \
                 (self.baseTrove, self.baseVersion, str(self.baseFlavor)))

    @timeMe
    def getTroveSize(self):
        NVF = self.nc.findTrove(None,
                                (self.baseTrove,
                                 self.baseVersion,
                                 self.baseFlavor),
                                self.conarycfg.flavor)[0]

        trv = self.nc.getTrove(NVF[0], NVF[1], NVF[2], withFiles = False)

        return trv.getSize()

    def getImageSize(self):
        # override this function as appropriate
        return self.getTroveSize()

    @timeMe
    def makeBlankDisk(self, image, size):
        if os.path.exists(image):
            util.rmtree(image)
        util.mkdirChain(os.path.split(image)[0])
        util.execute('dd if=/dev/zero of=%s count=1 seek=%d bs=512' % \
                      (image, (size / 512) - 1))

        cylinders = size / constants.cylindersize
        cmd = '/sbin/sfdisk -C %d -S %d -H %d %s' % \
            (cylinders, constants.sectors, constants.heads, image)

        input = "0 %d L *\n" % cylinders

        sfdisk = util.popen(cmd, 'w')
        sfdisk.write(input)
        sfdisk.close()

        try:
            dev = self.loop(image, offset = 512)
            util.execute('mke2fs -L / -F %s' % dev)
            os.system('tune2fs -i 0 -c 0 -j %s' % dev)
        finally:
            if 'dev' in locals():
                util.execute('losetup -d %s' % dev)

    @timeMe
    def makeBlankFS(self, image, size):
        if os.path.exists(image):
            util.rmtree(image)
        util.mkdirChain(os.path.split(image)[0])
        util.execute('dd if=/dev/zero of=%s count=1 seek=%d bs=512' % \
                      (image, (size / 512) - 1))

        util.execute('mke2fs -L / -F %s' % image)
        util.execute('tune2fs -i 0 -c 0 -j %s' % image)

    @timeMe
    def loop(self, image, offset = 0):
        p = os.popen('losetup -f')
        dev = p.read().strip()
        p.close()
        util.execute('losetup %s %s %s' % \
                         (offset and ('-o%d' % offset) or '', dev, image))
        util.execute('sync')
        return dev

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
    def installFileTree(self, dest):
        self.status('Installing image contents')
        self.createTemporaryRoot(dest)
        self.fileSystemOddsNEnds(dest, self.swapSize)
        fd, cfgPath = tempfile.mkstemp(dir=constants.tmpDir)
        try:
            os.close(fd)
            self.saveConaryRC(cfgPath)
            util.execute('mount -t proc none %s' % os.path.join(dest, 'proc'))
            util.execute('mount -t sysfs none %s' % os.path.join(dest, 'sys'))
            #copy the files needed by grub and set up the links
            self.setupGrub(dest)
            util.execute( \
                ("conary update '%s=%s[%s]' --root %s --config-file %s "
                 "--replace-files") % \
                    (self.baseTrove, self.baseVersion,
                     str(self.baseFlavor), dest, cfgPath))

            if self.scsiModules:
                self.addScsiModules(dest)
            if not self.findFile(os.path.join(dest, 'boot'), 'vmlinuz.*'):
                util.execute(("conary update --sync-to-parents "
                              "'kernel:runtime[%s]' --root %s "
                              "--config-file %s") % \
                                 (self.getKernelFlavor(), dest, cfgPath))
            else:
                log.info('Kernel detected, skipping.')
        finally:
            util.execute('umount %s' % os.path.join(dest, 'proc'))
            util.execute('umount %s' % os.path.join(dest, 'sys'))
            os.unlink(cfgPath)

        util.execute('rm -rf %s' % os.path.join( \
                dest, 'var', 'lib', 'conarydb', 'rollbacks', '*'))

        # remove root password
        os.system("chroot %s /usr/bin/authconfig --kickstart --enablemd5 --enableshadow --disablecache" % dest)
        os.system("chroot %s /usr/sbin/usermod -p '' root" % dest)

        # remove template kernel entry
        os.system('grubby --remove-kernel=/boot/vmlinuz-template --config-file=%s' % os.path.join(dest, 'boot', 'grub', 'grub.conf'))

    @timeMe
    def installGrub(self, fakeRoot, image):
        grubPath = os.path.join(fakeRoot, 'sbin', 'grub')
        if not os.path.exists(grubPath):
            log.info("grub not found. skipping execution.")
            return

        os.system(('echo -e "device (hd0) %s\nroot (hd0,0)\nsetup (hd0)\n" | '
                   '%s --batch') % (image, grubPath))
        #os.system(('echo -e "device (hd0) %s\nroot (hd0,0)\nsetup (hd0)\n" | '
        #           '%s --device-map=/dev/null --batch') % (image, grubPath))

        #p = os.popen('%s --device-map=/dev/null --batch' % grubPath, 'w')
        #p.write('device (hd0) %s\n' % image)
        #p.write('root (hd0,0)\n')
        #p.write('setup (hd0)\n')

    @timeMe
    def gzip(self, source, dest = None):
        if os.path.isdir(source):
            if not dest:
                dest = source + '.tgz'
            parDir, targetDir = os.path.split(source)
            util.execute('tar -czv -C %s %s > %s' % (parDir, targetDir, dest))
            pass
        else:
            if not dest:
                dest = source + '.gz'
            util.execute('gzip -c %s > %s' % (source, dest))
        return dest

    def write(self):
        raise NotImplementedError
