#
# Copyright (c) 2008 rPath, Inc.
#
# All rights reserved
#

import os
import re
import stat

from conary.lib import log
from conary.lib import util

from jobslave import bootloader
from jobslave import buildtypes
from jobslave.generators import constants
from jobslave.imagegen import logCall

def getGrubConf(name, hasInitrd = True, xen = False, dom0 = False, clock = ""):
    xen = xen or dom0
    macros = {'name': name,
              'kversion'  : 'template',
              'initrdCmd' : '',
              'moduleCmd' : '',
              'timeOut'   : '5',
              'bootDev'   : 'hda',
              'kernelCmd' : 'kernel /boot/vmlinuz-%%(kversion)s ro root=LABEL=/ %s' % clock}
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
                   'hiddenmenu',
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

class GrubInstaller(bootloader.BootloaderInstaller):
    def setup(self):
        if not os.path.exists(os.path.join(self.image_root, 'sbin', 'grub')):
            log.info("grub not found. skipping setup.")
            return

        util.mkdirChain(os.path.join(self.image_root, 'boot', 'grub'))
        # path to grub stage1/stage2 files in rPL/rLS
        util.copytree(
            os.path.join(self.image_root, 'usr', 'share', 'grub', '*', '*'),
            os.path.join(self.image_root, 'boot', 'grub'))
        # path to grub files in SLES
        util.copytree(
            os.path.join(self.image_root, 'usr', 'lib', 'grub', '*'),
            os.path.join(self.image_root, 'boot', 'grub'))
        util.mkdirChain(os.path.join(self.image_root, 'etc'))

        # Create a stub grub.conf
        if os.path.exists(os.path.join(self.image_root, 'etc', 'issue')):
            f = open(os.path.join(self.image_root, 'etc', 'issue'))
            name = f.readline().strip()
            if not name:
                name = self.jobData['project']['name']
            f.close()
        else:
            name = self.jobData['project']['name']
        bootDirFiles = os.listdir(os.path.join(self.image_root, 'boot'))
        xen = bool([x for x in bootDirFiles
            if re.match('vmlinuz-.*xen.*', x)])
        dom0 = bool([x for x in bootDirFiles
            if re.match('xen.gz-.*', x)])
        hasInitrd = bool([x for x in bootDirFiles
            if re.match('initrd-.*.img', x)])

        clock = ""
        if self.jobData['buildType'] == buildtypes.VMWARE_IMAGE:
            if self.arch == 'x86':
                clock = "clock=pit"
            elif self.arch == 'x86_64':
                clock = "notsc"

        conf = getGrubConf(name, hasInitrd, xen, dom0, clock)

        f = open(
            os.path.join(self.image_root, 'boot', 'grub', 'grub.conf'), 'w')
        f.write(conf)
        f.close()

        # write /etc/sysconfig/bootloader for SUSE systems
        if os.path.exists(
            os.path.join(self.image_root, 'etc', 'SuSE-release')):
            f = open(
                os.path.join(self.image_root, 'etc', 'sysconfig', 'bootloader'), 'w')
            f.write('CYCLE_DETECTION="no"\n')
            f.write('CYCLE_NEXT_ENTRY="1"\n')
            f.write('LOADER_LOCATION=""\n')
            f.write('LOADER_TYPE="grub"\n')
            f.close()

        os.chmod(os.path.join(self.image_root, 'boot/grub/grub.conf'), 0600)
        # Create the appropriate links
        os.symlink('grub.conf',
            os.path.join(self.image_root, 'boot', 'grub', 'menu.lst'))
        os.symlink('../boot/grub/grub.conf',
            os.path.join(self.image_root, 'etc', 'grub.conf'))

    def install(self):
        # Now that grubby has had a chance to add the new kernel,
        # remove the template entry added in setup()
        if os.path.exists(os.path.join(self.image_root, 'sbin', 'grubby')):
            logCall('chroot %s /sbin/grubby '
                    '--remove-kernel=/boot/vmlinuz-template' % self.image_root,
                    ignoreErrors=True)

        # If bootman is present, configure it for grub and run it
        if os.path.exists(os.path.join(self.image_root, 'sbin', 'bootman')):
            bootman_config = open(os.path.join(self.image_root, 'etc',
                'bootman.conf'), 'w')
            print >>bootman_config, 'BOOTLOADER=grub'
            bootman_config.close()
            logCall('chroot "%s" /sbin/bootman' % self.image_root)

    def install_mbr(self, mbr_device, size):
        # Install grub into the MBR
        cylinders = size / constants.cylindersize
        grubCmds = "device (hd0) %s\n" \
                   "geometry (hd0) %d %d %d\n" \
                   "root (hd0,0)\n" \
                   "setup (hd0)" % (mbr_device, cylinders,
                        constants.heads, constants.sectors)

        logCall('echo -e "%s" | '
                '/sbin/grub --no-floppy --batch' % (grubCmds))
