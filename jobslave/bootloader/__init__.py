#
# Copyright (c) 2008 rPath, Inc.
#
# All rights reserved
#


class BootloaderInstaller(object):
    def __init__(self, parent, image_root):
        self.jobData = parent.jobData
        self.arch = parent.arch
        self.image_root = image_root

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

    def install_mbr(self, mbr_device, size):
        '''
        Install the bootloader's MBR.

        Called after install() for image types with a full hard drive.

        @param mbr_device: File into which the MBR should be written.
        @param size: Size of the "disk" where the MBR is being written,
            in bytes.
        '''
        pass
