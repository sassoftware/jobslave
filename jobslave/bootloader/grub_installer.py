#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved
#

import logging
import os
import re
import shlex
import stat

from conary.lib import util

from jobslave import bootloader
from jobslave import buildtypes
from jobslave.distro_detect import is_RH, is_SUSE, is_UBUNTU
from jobslave.util import logCall

log = logging.getLogger(__name__)


def getGrubConf(name, hasInitrd = True, xen = False, dom0 = False, clock = "",
        includeTemplate=True, kversions=()):
    xen = xen or dom0
    macros = {
        'name': name,
        'kversion'  : 'template',
        'initrdCmd' : '',
        'moduleCmd' : '',
        'timeOut'   : '5',
        'bootDev'   : 'hda',
        'kernelCmd' : 'kernel /boot/vmlinuz-%(kversion)s ro root=LABEL=root %(clock)s',
        'clock'     : clock,
        }

    if hasInitrd:
        if dom0:
            macros['initrdCmd'] = 'module /boot/initrd-%(kversion)s.img'
        else:
            macros['initrdCmd'] = 'initrd /boot/initrd-%(kversion)s.img'

    if xen:
        if dom0:
            macros['moduleCmd'] = (
                    'module /boot/vmlinuz-%(kversion)s ro root=LABEL=root')
            macros['kernelCmd'] = 'kernel /boot/xen.gz-%(kversion)s'
        else:
            macros['bootDev'] = 'xvda'
            macros['timeOut'] = '0'
            macros['kernelCmd'] += ' quiet'

    header = """
# GRUB configuration generated by rBuilder
#
# Note that you do not have to rerun grub after making changes to this file
#boot=%(bootDev)s
default=0
timeout=%(timeOut)s
hiddenmenu
""".lstrip()

    template = """
title %(name)s (%(kversion)s)
    root (hd0,0)
    %(kernelCmd)s
    %(initrdCmd)s
    %(moduleCmd)s
"""

    config = header % macros

    if kversions:
        for kver in kversions:
            macros['kversion'] = kver
            # This one is nested two levels deep.
            config += (template % macros) % macros
    elif includeTemplate:
        config += (template % macros) % macros

    return config

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
        for _dir in dirs:
            this_dir = util.joinPaths(dest, root, _dir)
            if not os.path.exists(this_dir) and not \
                    [x for x in exceptions if \
                         re.match(x, util.joinPaths(root, _dir))]:
                os.mkdir(this_dir)
                dStat = os.stat(util.joinPaths(source, root, _dir))
                os.chmod(this_dir, dStat[stat.ST_MODE])

class GrubInstaller(bootloader.BootloaderInstaller):
    def __init__(self, parent, image_root, geometry, grub_path='/sbin/grub'):
        bootloader.BootloaderInstaller.__init__(self, parent, image_root,
                geometry)
        self.grub_path = grub_path
        self.name = None

    def _get_grub_conf(self):
        if is_SUSE(self.image_root) or is_UBUNTU(self.image_root):
            return 'menu.lst'
        return 'grub.conf'

    def setup(self):
        util.mkdirChain(util.joinPaths(self.image_root, 'boot', 'grub'))
        # path to grub stage1/stage2 files in rPL/rLS
        util.copytree(
            util.joinPaths(self.image_root, 'usr', 'share', 'grub', '*', '*'),
            util.joinPaths(self.image_root, 'boot', 'grub'))
        # path to grub files in SLES
        if is_SUSE(self.image_root):
            util.copytree(
                util.joinPaths(self.image_root, 'usr', 'lib', 'grub', '*'),
                util.joinPaths(self.image_root, 'boot', 'grub'))
        if is_UBUNTU(self.image_root):
            # path to grub files in x86 Ubuntu
            util.copytree(
                util.joinPaths(self.image_root, 'usr', 'lib', 'grub', 'i386-pc', '*'),
                util.joinPaths(self.image_root, 'boot', 'grub'))
            # path to grub files in x86_64 Ubuntu
            util.copytree(
                util.joinPaths(self.image_root, 'usr', 'lib', 'grub', 'x86_64-pc', '*'),
                util.joinPaths(self.image_root, 'boot', 'grub'))
        util.mkdirChain(util.joinPaths(self.image_root, 'etc'))

        # Create a stub grub.conf
        self.writeConf()

        # Create the appropriate links
        if self._get_grub_conf() != 'menu.lst':
            os.symlink('grub.conf', util.joinPaths(
                self.image_root, 'boot', 'grub', 'menu.lst'))
            os.symlink('../boot/grub/grub.conf',
                       util.joinPaths(self.image_root, 'etc', 'grub.conf'))
        if is_SUSE(self.image_root):
            self._suse_grub_stub()

    def _suse_grub_stub(self):
        self.createFile('etc/grub.conf', 'setup (hd0)\nquit\n')

    def _suse_sysconfig_bootloader(self):
        # write /etc/sysconfig/bootloader for SUSE systems
        contents = (
                'CYCLE_DETECTION="no"\n'
                'CYCLE_NEXT_ENTRY="1"\n'
                'LOADER_LOCATION=""\n'
                'LOADER_TYPE="grub"\n'
                )
        if is_SUSE(self.image_root, version=11):
            consoleArgs = ''
            if (self.jobData['buildType'] == buildtypes.validBuildTypes['XEN_OVA']):
                consoleArgs = ' console=ttyS0 xencons=ttyS'
            contents += (
                'DEFAULT_APPEND="root=LABEL=root showopts%s"\n' 
                'FAILSAFE_APPEND="root=LABEL=root%s"\n' % (consoleArgs, consoleArgs)
                )
        self.createFile('etc/sysconfig/bootloader', contents)

    def writeConf(self, kernels=()):
        if os.path.exists(util.joinPaths(self.image_root, 'etc', 'issue')):
            f = open(util.joinPaths(self.image_root, 'etc', 'issue'))
            name = f.readline().strip()
            if not name:
                name = self.jobData['project']['name']
            f.close()
        else:
            name = self.jobData['project']['name']
        bootDirFiles = os.listdir(util.joinPaths(self.image_root, 'boot'))
        xen = bool([x for x in bootDirFiles
            if re.match('vmlinuz-.*xen.*', x)])
        dom0 = bool([x for x in bootDirFiles
            if re.match('xen.gz-.*', x)])
        hasInitrd = bool([x for x in bootDirFiles
            if re.match('initrd-.*.img', x)])

        # RH-alikes ship a combo dom0/domU kernel so we have to use the image
        # flavor to determine whether to use the dom0 bootloader configuration.
        if self.force_domU:
           dom0 = False

        clock = ""
        if self.jobData['buildType'] == buildtypes.VMWARE_IMAGE:
            if self.arch == 'x86':
                clock = "clock=pit"
            elif self.arch == 'x86_64':
                clock = "notsc"

        conf = getGrubConf(name, hasInitrd, xen, dom0, clock,
                includeTemplate=not is_SUSE(self.image_root, version=11),
                kversions=kernels)

        cfgfile = self._get_grub_conf()
        if cfgfile == 'menu.lst' and is_SUSE(self.image_root):
            self._suse_sysconfig_bootloader()

        f = open(util.joinPaths(self.image_root, 'boot', 'grub', cfgfile), 'w')
        f.write(conf)
        f.close()

        os.chmod(util.joinPaths(self.image_root, 'boot', 'grub', cfgfile), 0600)

    def install(self):
        cfgfile = self._get_grub_conf()
        grub_conf = util.joinPaths(self.image_root, 'boot/grub', cfgfile)
        # RPM-based images will not populate grub.conf, so do it here.
        for line in open(grub_conf):
            line = line.split()
            if len(line) < 2 or 'vmlinuz-' not in line[1]:
                continue
            kver = os.path.basename(line[1])[8:]
            if kver != 'template':
                break
        else:
            # No non-template kernel entry was found, so populate it by hand.
            self.add_kernels()

        # Now that grubby has had a chance to add the new kernel,
        # remove the template entry added in setup()
        if os.path.exists(util.joinPaths(self.image_root, 'sbin', 'grubby')):
            logCall('chroot %s /sbin/grubby '
                    '--remove-kernel=/boot/vmlinuz-template' % self.image_root,
                    ignoreErrors=True)

        # If bootman is present, configure it for grub and run it
        if os.path.exists(util.joinPaths(self.image_root, 'sbin', 'bootman')):
            bootman_config = open(util.joinPaths(self.image_root, 'etc',
                'bootman.conf'), 'w')
            print >> bootman_config, 'BOOTLOADER=grub'
            bootman_config.close()

            bootloader.writeBootmanConfigs(self)
            logCall('chroot "%s" /sbin/bootman' % self.image_root)

        # Workaround for RPL-2423
        if os.path.exists(grub_conf):
            contents = open(grub_conf).read()
            contents = re.compile('^default .*', re.M
                ).sub('default 0', contents)
            open(grub_conf, 'w').write(contents)

        if cfgfile == 'menu.lst' and os.path.exists(grub_conf):
            # workaround for bootloader management tools in SUSE writing
            # menu.lst wrong
            f = open(grub_conf)
            newLines = []
            rootdev_re = re.compile('root=/dev/.*? ')
            grubroot_re = re.compile('root \(.*\)')
            doubleboot_re = re.compile('/boot/boot')
            kernel_re = re.compile('^\s+kernel')
            for line in f:
                line = rootdev_re.sub('root=LABEL=root ', line)
                line = grubroot_re.sub('root (hd0,0)', line)
                line = doubleboot_re.sub('/boot', line)
                if (kernel_re.match(line) and
                    (self.jobData['buildType'] == buildtypes.validBuildTypes['XEN_OVA'])):
                    line = line.replace('\n', ' console=ttyS0 xencons=ttyS\n')
                newLines.append(line)
            contents = ''.join(newLines)
            f = open(grub_conf, 'w')
            f.write(contents)
            f.close()

    def install_mbr(self, root_dir, mbr_device, size):
        """
        Install grub into the MBR.
        """
        if not os.path.exists(util.joinPaths(self.image_root, self.grub_path)):
            log.info("grub not found. skipping setup.")
            return

        #  Assumed:
        # * raw hdd image at mbr_device is bind mounted at root_dir/disk.img
        # * The size requested is an integer multiple of the cylinder size
        bytesPerCylinder = self.geometry.bytesPerCylinder
        assert not (size % bytesPerCylinder), "The size passed in here must be cylinder aligned"
        cylinders = size / bytesPerCylinder
        grubCmds = "device (hd0) /disk.img\n" \
                   "geometry (hd0) %d %d %d\n" \
                   "root (hd0,0)\n" \
                   "setup (hd0)" % (cylinders,
                        self.geometry.heads, self.geometry.sectors)

        logCall('echo -e "%s" | '
                'chroot %s sh -c "%s --no-floppy --batch"'
                % (grubCmds, root_dir, self.grub_path))

    def add_kernels(self):
        bootDirFiles = os.listdir(util.joinPaths(self.image_root, 'boot'))
        kernels = sorted(x[8:] for x in bootDirFiles
                if x.startswith('vmlinuz-2.6'))
        kernels.reverse()
        if kernels:
            log.info("Manually populating grub.conf with installed kernels")
            if is_SUSE(self.image_root):
                self._mkinitrd_suse(kernels)
            else:
                self.writeConf(kernels)
                self._mkinitrd_redhat(kernels)
        else:
            log.error("No kernels found; this image will not be bootable.")

    def _mkinitrd_redhat(self, kernels):
        mkinitrdArgs = [
            '/usr/sbin/chroot', self.image_root, '/sbin/mkinitrd',
            '-f',
            # make sure that whatever variant of the megaraid driver is
            # present is included in the initrd, since it is required
            # for vmware and doesn't hurt anything else
            '--with=megaraid', '--with=mptscsih', '--allow-missing',]
        if is_RH(self.image_root):
            mkinitrdArgs.append('--preload=xenblk')
        for kver in kernels:
            verArgs = mkinitrdArgs + ['/boot/initrd-%s.img' % kver, kver]
            logCall(verArgs)

    def _mkinitrd_suse(self, kernels):
        # Extend mkinitrd config with modules for VM targets
        kconf = self.filePath('etc/sysconfig/kernel')
        out = open(kconf + '.tmp', 'w')
        for line in open(kconf):
            if line[:15] == 'INITRD_MODULES=':
                modules = set(shlex.split(line[15:])[0].split())
                modules.add('piix')
                modules.add('megaraid')
                modules.add('mptscsih')
                modules.add('mptspi')
                out.write('INITRD_MODULES="%s"' % (' '.join(modules)))
            else:
                out.write(line)
        out.close()
        os.rename(kconf + '.tmp', kconf)

        # Order kernels so the desired one is added last and thus the default.
        kernels.sort()
        kernels_xen = [x for x in kernels if x.endswith('-xen')]
        kernels_not_xen = [x for x in kernels if not x.endswith('-xen')]
        if self.force_domU:
            kernels = kernels_not_xen + kernels_xen
        else:
            kernels = kernels_xen + kernels_not_xen

        log.info("Rebuilding initrd(s)")
        kpaths = ['vmlinuz-' + x for x in kernels]
        ipaths = ['initrd-' + x for x in kernels]
        logCall(['/usr/sbin/chroot', self.image_root,
            '/sbin/mkinitrd',
            '-k', ' '.join(kpaths),
            '-i', ' '.join(ipaths),
            ])

        # Build grub config
        log.info("Adding kernel entries")
        self.createFile('boot/grub/menu.lst', contents="""\
# GRUB configuration generated by rBuilder
timeout 8
##YaST - generic_mbr
##YaST - activate

""")
        self.createFile('boot/grub/device.map', '(hd0) /dev/sda\n')
        self._suse_sysconfig_bootloader()
        self._suse_grub_stub()
        for kver, kpath, ipath in zip(kernels, kpaths, ipaths):
            flavor = kpath.split('-')[-1]
            if flavor == 'xen' and self.force_domU:
                flavor = 'default'
            logCall(['/usr/sbin/chroot', self.image_root,
                '/usr/lib/bootloader/bootloader_entry',
                'add', flavor, kver, kpath, ipath])
