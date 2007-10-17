#
# Copyright (c) 2007 rPath, Inc.
#
# All Rights Reserved
#
import sys
from conary import versions

class GeneratorStub(object):
    UUID = "abcd"
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

class ImageGeneratorStub(GeneratorStub):
    arch = 'x86'
    jobId = '1234'

    def __init__(self, jobData, parent, *args, **kwargs):
        self.jobData = jobData
        self.jobData.setdefault('troveVersion',
                '/test.rpath.local@rpl:1/0.000:1-1-1')
        self.troveVersion = versions.ThawVersion(self.jobData['troveVersion'])

    def writeConaryRc(self, path, client):
        pass

class BootableImageStub(ImageGeneratorStub):
    jobId = "jobid"
    def __init__(self, jobData, parent, *args, **kwargs):
        self.filesystems = {}
        self.workDir = '/tmp/workdir'
        self.outputDir = '/tmp/outputdir'
        self.basefilename = 'image'
        self.mountDict = {'/': (0, 100, 'ext3'), 'swap': (0, 100, 'swap')}
        self.jobData = jobData

    def addFilesystem(self, mountPoint, fs):
        self.filesystems[mountPoint] = fs

    def mountAll(self):
        pass

    def umountAll(self):
        pass

    def makeImage(self):
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

    def getKernelFlavor(self):
        flavor = ''
        return flavor

    def addScsiModules(self, dest):
        pass

    def updateGroupChangeSet(self, cclient):
        pass

    def updateKernelChangeSet(self, cclient):
        pass

    def installFileTree(self, dest):
        pass

    def installGrub(self, fakeRoot, image, size):
        pass

    def gzip(self, source, dest = None):
        return dest

class InstallableIsoStub(ImageGeneratorStub):
    jobId = "jobid"
    UUID = "abcd"
    productDir = 'rPath'

    def retrieveTemplates(self):
        return None, None

    def prepareTemplates(self, topdir, templateDir):
        return None
