#
# Copyright (c) 2005-2007 rPath, Inc.
#
# All Rights Reserved
#

import os
import tempfile

import boto

from conary.conarycfg import ConfigFile
from conary.lib import cfgtypes
from conary.lib import util

from jobslave.generators import constants
from jobslave.generators import raw_fs_image

class AMIBundleError(Exception):
    def __str__(self):
        return "Failed to create the AMI bundle"

class AMIUploadError(Exception):
    def __str__(self):
        return "Failed to upload the image to the Amazon EC2 Service"

class AMIRegistrationError(Exception):
    def __str__(self):
        return "Failed to register the image with the Amazon EC2 Service"

class AMIImage(raw_fs_image.RawFsImage):

    def __init__(self, *args, **kwargs):

        raw_fs_image.RawFsImage.__init__(self, *args, **kwargs)

        self.amiData = self.jobData.get('amiData')
        if not self.amiData:
            raise RuntimeError, 'Cannot build Amazon Machine Image without ' \
                                'configuration information!'

        self.__dict__.update(**self.amiData)

        # write out X.509 certificate data
        fd, self.ec2CertPath = tempfile.mkstemp(dir=constants.tmpDir)
        os.write(fd, self.ec2Certificate)
        os.close(fd)

        fd, self.ec2CertKeyPath = tempfile.mkstemp(dir=constants.tmpDir)
        os.write(fd, self.ec2CertificateKey)
        os.close(fd)

        # we want one single filesystem with the freespace allocated
        # no swap is necessary, because EC2 provides us with all we 
        # need on /dev/sda3
        freespace = self.getBuildData("freespace") * 1048576
        self.jobData['filesystems'] = [ ('/', 0, freespace, 'ext3'), ]

        self.mountDict = dict([(x[0], tuple(x[1:])) for x in self.jobData['filesystems'] if x[0]])

        # get the spot we're going to mount the hyooge disk on (/dev/sda2)
        self.hugeDiskMountpoint = \
                self.getBuildData('amiHugeDiskMountpoint')


    def createAMIBundle(self, inputFSImage, bundlePath):
        # actually call out to create the AMI bundle
        ec2ImagePrefix = "%s_%s.img" % \
                (self.basefilename, self.jobData.get('buildId'))
        try:
            os.system('ec2-bundle-image -i %s -u %s -c %s -k %s -d %s -p %s' % \
                    (inputFSImage, self.ec2AccountId,
                        self.ec2CertPath, self.ec2CertKeyPath,
                        bundlePath, ec2ImagePrefix))
            for f in os.listdir(bundlePath):
                if f.endswith('.xml'):
                    return f
        except OSError:
            # just let the thing return None
            pass

        return None

    def uploadAMIBundle(self, pathToManifest):
        try:
            os.system('ec2-upload-bundle -m %s -b %s -a %s -s %s' % \
                    (pathToManifest, self.ec2S3Bucket,
                     self.ec2PublicKey, self.ec2PrivateKey))
            return True
        except OSError:
            return False

    def registerAMI(self, pathToManifest):
        amiId = None
        amiS3ManifestName = '%s/%s' % (self.ec2Bucket,
                os.path.basename(pathToManifest))
        c = boto.connect_ec2(self.ec2PublicKey, self.ec2PrivateKey)
        amiId = str(c.register_image(amiS3ManifestName))
        if self.amiConfig.ec2LaunchGroups:
            c.modify_image_attribute(amiId, attribute='launchPermission',
                operation='add', groups=self.amiConfig.launchGroups)
        if self.amiConfig.ec2LaunchUsers:
            c.modify_image_attribute(amiId, attribute='launchPermission',
                operation='add', user_ids=self.amiConfig.launchUsers)

        return amiId, amiS3ManifestName

    def updateKernelChangeSet(self, cclient):
        # AMIs don't need a kernel
        pass

    def fileSystemOddsNEnds(self, fakeroot):
        raw_fs_image.RawFsImage.fileSystemOddsNEnds(self, fakeroot)

        # append some useful things to /etc/fstab for AMIs
        fstabFile = file(os.path.join(fakeroot, 'etc', 'fstab'), 'a+')
        if self.hugeDiskMountpoint:
            fstabFile.write("/dev/sda2\t%s\t\text3\tdefaults 1 2" % \
                    self.hugeDiskMountpoint)
        fstabFile.write("/dev/sda3\tswap\t\tswap\tdefaults 0 0")
        fstabFile.close()

    def write(self):
        totalSize, sizes = self.getImageSize(realign = 0, partitionOffset = 0)
        images = self.makeFSImage(sizes)

        tmpBundlePath = tempfile.mkdtemp(prefix='amibundle',
                dir=constants.tmpDir)
        self.status("Creating the AMI bundle")
        manifestPath = self.createAMIBundle(images[0], tmpBundlePath)
        if not manifestPath:
            raise AMIBundleError
        self.status("Uploading the AMI bundle to Amazon EC2")
        if not self.uploadAMIBundle(os.path.join(tmpBundlePath, manifestPath)):
            raise AMIUploadError
        self.status("Registering AMI")
        amiId, amiManifestName = self.registerAMI(manifestPath)
        if not (amiId and amiManifestName):
            raise AMIRegistrationError

        # return empty list because files aren't stored here, they're on
        # Amazon's EC2 service
        # TODO vet this with the experts -- will this do the appropriate thing?
        # TODO figure out how to set build metadata
        self.postOutput(())

