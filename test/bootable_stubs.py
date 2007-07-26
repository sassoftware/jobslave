#
# Copyright (c) 2007 rPath, Inc.
#
# All Rights Reserved
#
import sys

class GeneratorStub(object):
    def postOutput(self, fileList):
        pass

class ImageGeneratorStub(GeneratorStub):
    pass

class BootableImageStub(ImageGeneratorStub):
    def __init__(self, *args, **kwargs):
        self.filesystems = {}
        self.workDir = '/tmp/workdir'
        self.outputDir = '/tmp/outputdir'
        self.basefilename = 'image'
        self.mountDict = {'/': (0, 100, 'ext3'), 'swap': (0, 100, 'swap')}

        self.parentPipe = sys.stderr.fileno()

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
