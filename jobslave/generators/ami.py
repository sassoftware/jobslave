#
# Copyright (c) 2005-2007 rPath, Inc.
#
# All Rights Reserved
#

import os
import logging
import tempfile
import urlparse
import urllib

import boto

from conary.lib import util, log as conary_log
from conary.deps import deps
from conary import conaryclient

from jobslave import buildtypes
from jobslave.imagegen import logCall

from jobslave.generators import constants
from jobslave.generators import raw_fs_image

log = logging.getLogger(__name__)


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

        self.productName = buildtypes.typeNamesShort[buildtypes.AMI]
        self.__dict__.update(**self.amiData)

        self._kernelMetadata = {}

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

        self.swapSize = 0

        self.mountDict = dict([(x[0], tuple(x[1:])) for x in self.jobData['filesystems'] if x[0]])

        # get the spot we're going to mount the hyooge disk on (/dev/sda2)
        self.hugeDiskMountpoint = \
                self.getBuildData('amiHugeDiskMountpoint')

        # Work around bad proddef values (RBL-4671)
        if self.hugeDiskMountpoint == 'false':
            log.warning("Ignoring bogus AMI mountpoint %r",
                    self.hugeDiskMountpoint)
            self.hugeDiskMountpoint = None

        # make sure we can actually use this arch
        if self.baseFlavor.satisfies(deps.parseFlavor('is: x86_64')):
            self.amiArch = 'x86_64'
        elif self.baseFlavor.satisfies(deps.parseFlavor('is: x86')):
            self.amiArch = 'i386'
        else:
            arch = deps.getInstructionSetFlavor(self.baseFlavor)
            raise RuntimeError('Unsupported architecture: %s' % str(arch))

    def createAMIBundle(self, inputFSImage, bundlePath):
        # actually call out to create the AMI bundle
        ec2ImagePrefix = "%s_%s.img" % \
                (self.basefilename, self.jobData.get('buildId'))
        try:
            extraArgs = ''

            if ('ec2-ari' in self._kernelMetadata and
                'ec2-aki' in self._kernelMetadata):
                extraArgs += (' --kernel "%(ec2-aki)s" --ramdisk "%(ec2-ari)s"'
                              % self._kernelMetadata)

            productCode = self.amiData.get('ec2ProductCode', None)
            if productCode:
                extraArgs += ' --productcodes "%s"' % productCode

            logCall('ec2-bundle-image'
                + ' -i "%s"' % inputFSImage
                + ' -u "%s"' % self.ec2AccountId
                + ' -c "%s"' % self.ec2CertPath
                + ' -k "%s"' % self.ec2CertKeyPath
                + ' -d "%s"' % bundlePath
                + ' -p "%s"' % ec2ImagePrefix
                + ' -r "%s"' % self.amiArch
                + extraArgs,
                logCmd=False
                )
            bundles = [x for x in os.listdir(bundlePath) if x.endswith('.xml')]
            return bundles and bundles[0] or None
        except RuntimeError:
            # all errors are translated one level higher
            pass

    def uploadAMIBundle(self, pathToManifest):
        try:
            env = None
            proxy = self.jobData.get('proxy')
            if proxy:
                env = {'http_proxy': proxy.get('http', ''),
                       'https_proxy': proxy.get('https', ''),
                      }
            logCall('ec2-upload-bundle -m %s -b %s -a %s -s %s' % \
                    (pathToManifest, self.ec2S3Bucket,
                     self.ec2PublicKey, self.ec2PrivateKey), logCmd=False,
                     env=env)
        except RuntimeError:
            # all errors are translated to upload errors one level higher.
            return False
        return True

    @classmethod
    def splitProxyUrl(self, proxyUrl):
        if proxyUrl:
            scheme, netloc, path, query, fragment = urlparse.urlsplit(proxyUrl)
            userpass, hostport = urllib.splituser(netloc)
            host, port = urllib.splitnport(hostport, None)
            if userpass:
                user, passwd = urllib.splitpasswd(userpass)
            else:
                user, passwd = None, None
            splitUrl = scheme, user, passwd, host, port, path, \
                query or None, fragment or None
        else:
            splitUrl = [ None ] * 7
        kwargs = {}
        kwargs['proxy_user'], kwargs['proxy_pass'], \
            kwargs['proxy'], kwargs['proxy_port'] = splitUrl[1:5]
        return kwargs

    def registerAMI(self, pathToManifest):
        amiId = None
        amiS3ManifestName = '%s/%s' % (self.ec2S3Bucket,
                os.path.basename(pathToManifest))
        try:
            kwargs = self.splitProxyUrl(self.jobData.get('proxy', {}).get('https'))
            c = boto.connect_ec2(self.ec2PublicKey, self.ec2PrivateKey, **kwargs)
            amiId = str(c.register_image(amiS3ManifestName))
            if self.ec2LaunchGroups:
                c.modify_image_attribute(amiId, attribute='launchPermission',
                    operation='add', groups=self.ec2LaunchGroups)
            if self.ec2LaunchUsers:
                c.modify_image_attribute(amiId, attribute='launchPermission',
                    operation='add', user_ids=self.ec2LaunchUsers)
        except:
            # errors will be trapped one level higher
            pass

        return amiId, amiS3ManifestName

    def updateKernelChangeSet(self, cclient):
        # AMIs don't need a kernel
        pass

    def runGrubby(self, dest):
        # AMI's don't have a kernel
        pass

    def _findKernelMetadata(self):
        """
        Figure out if the kernel in the chroot has ec2 related metadata set.
        """

        bootDir = os.path.join(self.conarycfg.root, 'boot')
        kernels = [ os.path.join('/boot', x) for x in os.listdir(bootDir) if x.startswith('vmlinuz') ]

        if len(kernels) == 0:
            log.warn('no kernel found in image')
            return

        if len(kernels) > 1:
            log.warn('found %s kernels in this image' % len(kernels))

        # Still stuck with Conary 1.1.31.z, so no getDatabase()
        # or cclient.close()
        cclient = conaryclient.ConaryClient(self.conarycfg)
        db = cclient.db

        kernelTrvs = [ x for x in db.iterTrovesByPath(kernels[0]) ]

        cclient.db.close()
        cclient.db.commitLock(False)
        if conary_log.syslog.f:
            conary_log.syslog.f.close()
        conary_log.syslog.f = None
        del cclient

        if len(kernelTrvs) == 0:
            log.warn('kernel not owned by a package')
            return

        if len(kernelTrvs) > 1:
            log.warn('file owned by multiple packages')

        kernel = kernelTrvs[0]

        log.info('searching for key/value metadata in %s=%s[%s]'
                 % (kernel.getName(),
                    kernel.getVersion(),
                    kernel.getFlavor()))

        ti = kernel.getTroveInfo()
        md = ti.metadata.get(1)
        if 'keyValue' in md and md['keyValue'] is not None:
            for key in md['keyValue'].keys():
                self._kernelMetadata[key] = md['keyValue'][key]

    def fileSystemOddsNEnds(self, fakeroot):
        raw_fs_image.RawFsImage.fileSystemOddsNEnds(self, fakeroot)

        # Add some useful entries to fstab
        scratchDisk = swapDisk = None
        if self.amiArch == 'i386':
            # 32bit is assumed to be booted as a "small" instance.
            # Disk layout as of 2009-05:
            #  * /dev/sda1 - root
            #  * /dev/sda2 - preformatted ext3 (scratch mount)
            #  * /dev/sda3 - preformatted swap
            scratchDisk = '/dev/sda2'
            swapDisk = '/dev/sda3'
        else:
            # 64bit is assumed to be booted as "large" or better.
            # Disk layout as of 2009-05:
            #  * /dev/sda1 - root
            #  * /dev/sdb  - preformatted ext3 (scratch mount)
            #  * /dev/sdc  - preformatted ext3
            scratchDisk = '/dev/sdb'

        fstab = open(os.path.join(fakeroot, 'etc', 'fstab'), 'a')
        print >> fstab
        if scratchDisk and self.hugeDiskMountpoint:
            # fs_passno (the last field) is 0 to ensure that a change in the
            # way Amazon does scratch disks does not result in boot failures.
            # The disk will never need checking anyway because it was just
            # formatted.
            print >> fstab, "%s %s ext3 defaults 0 0" % (
                    scratchDisk, self.hugeDiskMountpoint)
        if swapDisk:
            print >> fstab, "%s swap swap defaults 0 0" % (swapDisk,)
        fstab.close()

        self._findKernelMetadata()

    def write(self):
        totalSize, sizes = self.getImageSize(realign = 0, partitionOffset = 0)
        images = self.makeFSImage(sizes)

        if self.buildOVF10:
            self.ovaPath = self.createOvf(self.basefilename,
                self.jobData['description'], constants.RAWFS, images['/'],
                sizes['/'], totalSize, True, self.workingDir,
                self.outputDir)
            self.outputFileList.append((self.ovaPath,
                '%s %s' % (self.productName, constants.OVFIMAGETAG)))


        tmpBundlePath = tempfile.mkdtemp(prefix='amibundle',
                dir=constants.tmpDir)
        self.status("Creating the AMI bundle")
        manifestPath = self.createAMIBundle(images['/'], tmpBundlePath)
        if not manifestPath:
            raise AMIBundleError
        self.status("Uploading the AMI bundle to Amazon EC2")
        if not self.uploadAMIBundle(os.path.join(tmpBundlePath, manifestPath)):
            raise AMIUploadError
        self.status("Registering AMI")
        amiId, amiManifestName = self.registerAMI(manifestPath)
        if not (amiId and amiManifestName):
            raise AMIRegistrationError

        self.postAMI(amiId, amiManifestName)
        self.postOutput(self.outputFileList)
