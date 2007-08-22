#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#

# python standard library imports
import os, sys
import re
import subprocess
import tempfile

# mint imports
from jobslave import buildtypes
from jobslave.generators import bootable_image, constants
from jobslave.imagegen import logCall

# conary imports
from conary import conaryclient
from conary import deps
from conary import flavorcfg
from conary import versions
from conary.callbacks import UpdateCallback, ChangesetCallback
from conary.conarycfg import ConfigFile
from conary.lib import log, util

linuxrc = """#!/bin/nash
mount -t proc /proc /proc/
mount -t sysfs none /sys
mount -o mode=0755 -t tmpfs /dev /dev

%(modules)s
/sbin/udevstart

mkrootdev /dev/root
echo 0x0100 > /proc/sys/kernel/real-root-dev

mount -o defaults --ro -t iso9660 /dev/root /cdrom
%(mountCmd)s
pivot_root /sysroot /sysroot/initrd
umount /initrd/proc
umount /initrd/sys
"""

isolinuxCfg= '\n'.join(('say Welcome to %s.',
                        'default linux',
                        'timeout 100',
                        'prompt 1',
                        'label linux',
                        'kernel vmlinuz',
                        'append initrd=initrd.img root=LABEL=%s'))


class LiveIso(bootable_image.BootableImage):
    fileType = buildtypes.typeNames[buildtypes.LIVE_ISO]

    def iterFiles(self, baseDir, fileName):
        for base, dirs, files in os.walk(baseDir):
            for match in [x for x in files if re.match(fileName, x)]:
                yield os.path.join(base, match)

    def copyFallback(self, src, dest):
        # some binaries are statically linked with a ".static" suffix. attempt
        # to locate a file by that name if src doesn't appear to be suitable.
        for src in (src, src + ".static"):
            tFile = os.path.basename(src)
            pFile = os.popen('file %s' % src)
            fileStr = pFile.read()
            pFile.close()
            fallback = not ('statically' in fileStr or \
                            fileStr.endswith(': data\n'))
            if not fallback:
                break

        if fallback:
            tFile = tFile.replace('.static', '')
            print >> sys.stderr, "Using fallback for: %s" % tFile
            # named executable isn't suitable, use precompiled static one
            util.copyfile(os.path.join(self.fallback, tFile), dest)
        else:
            print >> sys.stderr, "Using user defined: %s" % tFile
            util.copyfile(src, dest)
        return not fallback

    def getVolName(self):
        name = self.jobData['project']['name']
        # srcub all non alphanumeric characters. we use this in a system call.
        # limit name to 32 chars--max volumne name for iso-9660
        return ''.join([x.isalnum() and x or '_' for x in name][:32])

    def mkinitrd(self, liveDir, fakeRoot):
        initrdDir = os.path.join(constants.tmpDir, self.basefilename + '_initrd')
        util.mkdirChain(initrdDir)
        try:
            macros = {'modules' : 'echo Inserting Kernel Modules',
                      'mountCmd': ''}

            for subDir in ('bin', 'dev', 'lib', 'proc', 'sys', 'sysroot',
                           'etc', os.path.join('etc', 'udev'), 'cdrom'):
                os.mkdir(os.path.join(initrdDir, subDir))

            # soft link sbin to bin
            os.symlink('bin', os.path.join(initrdDir, 'sbin'))

            # set up the binaries to copy into new filesystem.
            binaries = ('nash', 'insmod', 'udev', 'udevstart')
            # copy the udev config file
            util.copyfile(os.path.join(fakeRoot, 'etc', 'udev', 'udev.conf'),
                          os.path.join(initrdDir, 'etc', 'udev', 'udev.conf'))

            # copy binaries from fileSystem image to initrd
            for tFile in binaries:
                self.copyFallback(os.path.join(fakeRoot, 'sbin', tFile),
                                  os.path.join(initrdDir, 'bin', tFile))
                os.chmod(os.path.join(initrdDir, 'bin', tFile), 0755) # octal

            # FIXME: remove once nash has proper losetup args in place
            print >> sys.stderr, "Forcing temporary nash fallback (for losetup)"
            util.copyfile(os.path.join(self.fallback, 'nash'),
                          os.path.join(initrdDir, 'bin', 'nash'))
            os.chmod(os.path.join(initrdDir, 'bin', 'nash'), 0755) # octal 755
            # end nash-losetup FIXME

            # soft link modprobe and hotplug to nash for udev
            for tFile in ('modprobe', 'hotplug'):
                os.symlink('/sbin/nash', os.path.join(initrdDir, 'bin', tFile))

            kMods = ('loop',)
            if self.getBuildData('unionfs'):
                kMods += ('unionfs',)
            for modName in kMods:
                modName += '.ko'
                # copy loop.ko module into intird
                modPath = self.findFile( \
                os.path.join(fakeRoot, 'lib', 'modules'), modName)
                if modPath:
                    util.copyfile(modPath,
                                  os.path.join(initrdDir, 'lib', modName))
                    if modName == 'loop.ko':
                        macros['modules'] += \
                            '\n/bin/insmod /lib/%s max_loop=256' % modName
                    else:
                        macros['modules'] += '\n/bin/insmod /lib/%s' % modName
                else:
                    raise AssertionError( \
                        'Missing required Module: %s' % modName)

            if self.getBuildData('unionfs'):
                macros['mountCmd'] = """echo Making system mount points
    mkdir /sysroot1
    mkdir /sysroot2

    echo Mounting root filesystem
    losetup --ro /dev/loop0 /cdrom/livecd.img
    mount -o defaults --ro -t iso9660 /dev/loop0 /sysroot1
    mount -o defaults -t tmpfs /dev/shm /sysroot2
    mount -o dirs=sysroot2=rw:sysroot1=ro -t unionfs none /sysroot
    """
            else:
                macros['mountCmd'] = """
    echo Mounting root filesystem
    losetup --ro /dev/loop0 /cdrom/livecd.img
    mount -o defaults --ro -t iso9660 /dev/loop0 /sysroot
    """

            # make linuxrc file
            f = open(os.path.join(initrdDir, 'linuxrc'), 'w')
            f.write(linuxrc % macros)
            f.close()
            os.chmod(os.path.join(initrdDir, 'linuxrc'), 0755) # octal 755

            nonZipped = os.path.join(liveDir, 'initrd.nogz')
            zippedImg = os.path.join(liveDir, 'initrd.img')
            logCall('e2fsimage -v -d %s -u 0 -g 0 -f %s -s 8000' % \
                         (initrdDir, nonZipped))
            logCall('gzip < %s > %s' % (nonZipped, zippedImg))
            os.unlink(nonZipped)
        finally:
            util.rmtree(initrdDir, ignore_errors = True)

    def makeLiveCdTree(self, liveDir, fileTree):
        os.chmod(liveDir, 0755)
        # for pivotroot
        os.mkdir(os.path.join(liveDir, 'initrd'))

        # for fuse-based copy on write
        util.mkdirChain(os.path.join(fileTree, 'readwriteroot'))

        self.mkinitrd(liveDir, fileTree)

        allKernels = [x for x in self.iterFiles( \
            os.path.join(fileTree, 'boot'), 'vmlinuz.*')]

        if len(allKernels) > 1:
            if self.getBuildData('unionfs'):
                raise AssertionError("Multiple kernels detected. The most "
                                     "likely cause is a mismatch between the "
                                     "kernel in group-core and the kernel "
                                     "that unionfs was compiled for.")
            else:
                raise AssertionError("Multiple kernels detected. Please check "
                                     " that your group contains only one.")

        util.copyfile(allKernels[0], os.path.join(liveDir, 'vmlinuz'))

        self.copyFallback(os.path.join(fileTree, 'usr', 'lib', 'syslinux',
                                       'isolinux.bin'),
                          os.path.join(liveDir, 'isolinux.bin'))

        f = open(os.path.join(liveDir, 'isolinux.cfg'), 'w')
        f.write(isolinuxCfg % (self.jobData['name'], self.getVolName()))
        f.close()

        # tweaks to make read-only filesystem possible.
        if not self.getBuildData('unionfs'):
            util.mkdirChain(os.path.join(fileTree, 'ramdisk'))
            util.mkdirChain(os.path.join(fileTree, 'etc', 'sysconfig'))
            f = open(os.path.join(fileTree, 'etc', 'sysconfig',
                                  'readonly-root'), 'w')
            f.write("READONLY=yes\n")
            f.close()

    def isoName(self, file):
        f = os.popen('isosize %s' % file, 'r')
        size = int(f.read())
        f.close()
        if size > 734003200:
            return self.fileType.replace('CD/DVD', 'DVD')
        else:
            return self.fileType.replace('CD/DVD', 'CD')


    def write(self):
        topDir = os.path.join(constants.tmpDir, self.jobId)
        fileTree = os.path.join(topDir, self.basefilename + '_base')
        zFileTree = os.path.join(topDir, self.basefilename + '_zbase')
        liveDir = os.path.join(topDir, self.basefilename + '_live')
        util.mkdirChain(liveDir)
        innerIsoImage = os.path.join(liveDir, 'livecd.img')
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        finalIsoImage = os.path.join(outputDir, self.basefilename + '.iso')
        zippedIsoImage = finalIsoImage + '.gz'

        # instantiate contents of actual distro
        self.installFileTree(fileTree)
        # Symlink /proc/mounts to /etc/mtab
        logCall('ln -s %s %s' % (os.path.join(os.path.sep, 'proc', 'mounts'), os.path.join(fileTree, 'etc', 'mtab')))
        activeTree = fileTree
        extraArgs = ''

        # make the contents of the base iso. note there are side effects
        # on the main file tree.
        self.makeLiveCdTree(liveDir, fileTree)

        # and compress them if needed
        if self.zisofs:
            logCall('mkzftree %s %s' % (fileTree, zFileTree))
            activeTree = zFileTree
            extraArgs = '-z'

        # make the inner image
        logCall('mkisofs -quiet -v -J -R -U %s -o %s %s' % (extraArgs, innerIsoImage, activeTree))
        os.chmod(innerIsoImage, 0755)

        # make the outer image
        logCall('mkisofs -v -o %s -J -R -b isolinux.bin -c boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -V %s %s' % (finalIsoImage, self.getVolName(), liveDir))
        os.chmod(finalIsoImage, 0755)

        # If the inner image wasn't compressed, compress the final image
        deliveryImage = finalIsoImage
        if not self.zisofs:
            logCall('gzip < %s > %s' % (finalIsoImage, zippedIsoImage))
            os.chmod(zippedIsoImage, 0755)
            deliveryImage = zippedIsoImage

        # FIXME: make the name of cd or dvd based on disc size
        self.postOutput(((deliveryImage, 'Demo CD/DVD'),))

    def __init__(self, *args, **kwargs):
        res = bootable_image.BootableImage.__init__(self, *args, **kwargs)
        self.swapSize = 0

        self.fallback = os.path.join(constants.fallbackDir, self.arch)
        self.zisofs = self.getBuildData('zisofs')
        self.swapSize = 0
        return res
