#
# Copyright (c) 2010 rPath, Inc.
#
# All Rights Reserved
#
import os
from conary import versions
from conary.deps import deps
from conary.lib import util

from jobslave import bootloader


class GeneratorStub(object):
    UUID = "abcd"  
    ovfClass = None
    def __init__(self, jobData, parent, *args, **kwargs):
        self.jobData = jobData

    def postOutput(self, fileList):
        self.posted_output = fileList

    def getBuildData(self, key):
        return 0

    def getCookData(self, key):
        return 0

    def readConaryRc(self, cfg):
        pass

    def status(self, status, statusMessage = None):
        pass

    def createOvf(self, imageName, imageDescription, diskFormat,
                  diskFilePath, diskCapacity, diskCompressed,
                  workingDir, outputDir):
        from jobslave.generators import ovf_image
        diskFileSize = '1234567890'

        if self.ovfClass is None:
            self.ovfClass = ovf_image.OvfImage

        self.ovfImage = self.ovfClass(
            imageName, imageDescription, diskFormat,
            diskFilePath, diskFileSize, diskCapacity, diskCompressed,
            256, workingDir, outputDir)

        self.ovfImage.createOvf()
        self.ovfImage.writeOvf()

        def createManifest(*args):
            self.ovfImage.manifestFileName = '%s.mf' % self.basefilename

        self.ovfImage.createManifest = createManifest
        self.ovfImage.createManifest()

        rval = self.ovfImage.createOva()

        self.ovfXml = self.ovfImage.ovfXml
        self.ovfPath = self.ovfImage.ovfPath
        self.ovfFileName = self.ovfImage.ovfFileName

        return rval

class ImageGeneratorStub(GeneratorStub):
    arch = 'x86'
    jobId = 'test.rpath.local-build-1-2'

    def __init__(self, jobData, parent, *args, **kwargs):
        self.jobData = jobData
        self.jobData.setdefault('troveVersion',
                '/test.rpath.local@rpl:1/0.000:1-1-1')
        self.troveVersion = versions.ThawVersion(self.jobData['troveVersion'])

    def writeConaryRc(self, path, client):
        pass

class BootableImageStub(ImageGeneratorStub):
    jobId = "test.rpath.local-build-2-4"

    def __init__(self, jobData, parent, *args, **kwargs):
        self.filesystems = {}
        self.workDir = '/tmp/workdir'
        self.outputDir = '/tmp/outputdir'
        self.basefilename = 'image'
        self.workingDir = os.path.join(self.workDir, self.basefilename)
        self.mountDict = {'/': (0, 100, 'ext3'), 'swap': (0, 100, 'swap')}
        self.jobData = jobData
        self.buildOVF10 = jobData.get('buildOvf', False)
        self.outputFileList = []

        if jobData.has_key('troveVersion'):
            versionStr = self.jobData['troveVersion']
            ver = versions.ThawVersion(versionStr)
            self.baseVersion = ver.asString()
        if jobData.has_key('troveFlavor'):
            flavorStr = self.jobData['troveFlavor']
            self.baseFlavor = deps.ThawFlavor(str(flavorStr))

    def addFilesystem(self, mountPoint, fs):
        self.filesystems[mountPoint] = fs

    def mountAll(self):
        pass

    def umountAll(self):
        pass

    def setupGrub(self, fakeRoot):
        pass

    def findFile(self, baseDir, fileName):
        pass

    def createTemporaryRoot(self, fakeRoot):
        pass

    def fileSystemOddsNEnds(self, fakeRoot):
        pass

    def getImageSize(self, realign = 0, partitionOffset = 0):
        return 100, {'/': 100, 'swap': 100}

    def addScsiModules(self, dest):
        pass

    def updateGroupChangeSet(self, cclient):
        pass

    def installFileTree(self, dest):
        util.mkdirChain(dest)
        return bootloader.DummyInstaller(self, None, None, None)

    def installGrub(self, fakeRoot, image, size):
        pass

    def gzip(self, source, dest = None):
        return dest

class InstallableIsoStub(ImageGeneratorStub):
    jobId = "test.rpath.local-build-4-3"
    UUID = "abcd"
    productDir = 'rPath'

    def __init__(self, jobData, parent, *args, **kwargs):
        ImageGeneratorStub.__init__(self, jobData, parent, *args, **kwargs)

    def retrieveTemplates(self):
        return None, None

    def prepareTemplates(self, topdir, templateDir):
        return None

class ApplianceInstallerStub(ImageGeneratorStub):
    jobId = "test.rpath.local-build-4-3"
    UUID = "abcd"
    productDir = 'rPath'

    def retrieveTemplates(self):
        return None, None

    def prepareTemplates(self, topdir, templateDir):
        return None
