#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved
#

import os


class BootloaderInstaller(object):
    def __init__(self, parent, image_root, geometry):
        self.jobData = parent.jobData
        self.arch = parent.arch
        self.image_root = image_root
        self.geometry = geometry
        self.do_install = True
        self.force_domU = False

    def setup(self):
        '''
        Do any setup necessary before tag scripts are invoked.
        
        Called after troves are installed.
        '''
        pass

    def install(self):
        '''
        Install the bootloader.

        Called after tag scripts are run.
        '''
        raise NotImplemented

    def install_mbr(self, root_dir, mbr_device, size):
        '''
        Install the bootloader's MBR.

        Called after install() for image types with a full hard drive.

        @param root_dir: directory where the root filesystem is mounted
        @param mbr_device: File into which the MBR should be written.
        @param size: Size of the "disk" where the MBR is being written,
            in bytes.
        '''
        pass

    ## Script helpers
    def filePath(self, path):
        while path.startswith('/'):
            path = path[1:]
        return os.path.join(self.image_root, path)

    def fileExists(self, path):
        return os.path.exists(self.filePath(path))

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

    def appendFile(self, path, contents):
        self.createDirectory(os.path.dirname(path))
        open(self.filePath(path), 'ab').write(contents)


class DummyInstaller(BootloaderInstaller):
    '''
    Bootloader installer that does nothing.
    '''

    def install(self):
        pass


def writeBootmanConfigs(installer):
    '''
    Write out bootloader.d entries common to syslinux and grub
    when using bootman.
    '''

    # Tell bootman where / is
    root_conf = open(os.path.join(installer.image_root,
        'etc', 'bootloader.d', 'root.conf'), 'w')
    print >> root_conf, 'timeout 50'
    print >> root_conf, 'add_options ro'
    print >> root_conf, 'root LABEL=root'
    root_conf.close()
