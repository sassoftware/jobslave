#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


# python standard library imports
import os
import sys
import time

# jobslave imports
from jobslave.generators import bootable_image, constants, \
    installable_iso, ovf_image
from jobslave import imagegen
from jobslave import splitdistro
from jobslave.util import call

from conary.lib import util
from conary.lib.sha1helper import sha1String, sha1ToString

class TarSplit(object):
    def __init__(self, file):
        self.file = file
        self.tarfh = open(file)
        self.count = 0
        self.prefix = 'tar-chunk.'
        self.files = []
        self.tblist = []
        self.chunkSize = 10*1024*1024

        self.tarfh.seek(0, 2)
        self.tarEnd = self.tarfh.tell()
        self.tarfh.seek(0)

    def _formatFileName(self):
        return '%s%03d' % (self.prefix, self.count)

    def _getChunk(self):
        pos = self.tarfh.tell()
        if pos + self.chunkSize > self.tarEnd:
            size = self.tarEnd - pos
        else:
            size = self.chunkSize
        return size, self.tarfh.read(size)

    def splitFile(self, dir):
        while self.tarfh.tell() < self.tarEnd:
            size, chunk = self._getChunk()
            chunkfh = open(os.path.join(dir, self._formatFileName()), 'w')
            chunkfh.write(chunk)
            chunkfh.close()

            fileName = self._formatFileName()
            sha1sum = sha1ToString(sha1String(chunk))

            self.files.append(fileName)

            # Add both lines to the tblist for backwards compatibility with
            # older versions of Anaconda.
            self.tblist.append('%s %s %s' % (fileName, size, 1))
            self.tblist.append('%s %s %s %s' % (fileName, size, 1, sha1sum))

            self.count += 1

    def writeTbList(self, file):
        fh = open(file, 'w')
        fh.write('\n'.join(self.tblist))
        fh.write('\n')
        fh.close()

class ApplianceInstaller(bootable_image.BootableImage, 
                         installable_iso.InstallableIso):
    def __init__(self, *args, **kwargs):
        bootable_image.BootableImage.__init__(self, *args, **kwargs)
        self.showMediaCheck = self.getBuildData('showMediaCheck')
        #self.maxIsoSize = int(self.getBuildData('maxIsoSize'))
        self.maxIsoSize = 0
        self.swapSize = 0

    def writeBuildStamp(self, tmpPath):
        installable_iso.InstallableIso.writeBuildStamp(self, tmpPath)
        bsFile = open(os.path.join(tmpPath, ".buildstamp"), "a")
        print >> bsFile, '%s/tarballs' % self.productDir
        bsFile.close()

    def write(self):
        topDir = os.path.join(self.workDir, 'unified')
        tbdir = os.path.join(topDir, self.productDir, 'tarballs')
        baseDir = os.path.join(topDir, self.productDir, 'base')
        util.mkdirChain(tbdir)
        util.mkdirChain(baseDir)

        basePath = os.path.join(self.workDir, self.basefilename)
        if os.path.exists(basePath):
            util.rmtree(basePath)
        util.mkdirChain(basePath)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        tarball = os.path.join(self.workDir, self.basefilename + '.tar.gz')
        cwd = os.getcwd()
        try:
            self.installFileTree(basePath, no_mbr=True)

            self.status('Preparing to build ISOs')

            os.chdir(basePath)
            util.execute('tar -C %s -cpPsS --to-stdout ./ | gzip > %s' % \
                             (basePath, tarball))
            ts = TarSplit(tarball)
            ts.splitFile(tbdir)
            ts.writeTbList(os.path.join(baseDir, 'tblist'))
            util.rmtree(basePath, ignore_errors = True)
            util.rmtree(tarball, ignore_errors = True)
            try:
                os.chdir(cwd)
            except:
                # block all errors so that real ones can get through
                pass

            self.callback = installable_iso.Callback(self.status)

            print >> sys.stderr, "Building ISOs of size: %d Mb" % \
              (self.maxIsoSize / 1048576)
            sys.stderr.flush()

            # FIXME: hack to ensure we don't trigger overburns.
            # there are probably cleaner ways to do this.
            if self.maxIsoSize > 681574400:
                self.maxIsoSize -= 1024 * 1024

            templateDir, clientVersion = self.retrieveTemplates()
            csdir = self.prepareTemplates(topDir, templateDir)

            util.rmtree(csdir, ignore_errors=True)

            if self.arch == 'x86':
                anacondaArch = 'i386'
            else:
                anacondaArch = self.arch

            # write .discinfo
            discInfoPath = os.path.join(topDir, ".discinfo")
            if os.path.exists(discInfoPath):
                os.unlink(discInfoPath)
            discInfoFile = open(discInfoPath, "w")
            print >> discInfoFile, time.time()
            print >> discInfoFile, self.jobData['name']
            print >> discInfoFile, anacondaArch
            print >> discInfoFile, "1"
            for x in ["base", "tarballs", 'pixmaps']:
                print >> discInfoFile, "%s/%s" % (self.productDir, x)
            discInfoFile.close()

            self.extractMediaTemplate(topDir)
            self.setupKickstart(topDir)
            self.writeProductImage(topDir, installable_iso.getArchFlavor(self.baseFlavor).freeze())

            self.status("Building ISOs")

            # Mostly copied from splitdistro
            current = os.path.join(self.workDir, 'disc1')
            discnum = 1
            if os.path.isdir(current):
                print >> sys.stderr, 'removing stale', current
                util.rmtree(current)
            print >> sys.stderr, 'creating', current
            os.mkdir(current)
            splitdistro.lndir(topDir, current, excludes=('media-template',))
            # lay 'disc1' before 'all' to ensure collisions are handled correctly
            for cDir in ('disc1', 'all'):
                if 'media-template' in os.listdir(topDir) and \
                       cDir in os.listdir(os.path.join(topDir, 'media-template')):
                    splitdistro.lndir(os.path.join(topDir, 'media-template', cDir), current)

            for cDir in ('all', 'disc1'):
                srcDir = os.path.join(topDir, 'media-template2', cDir)
                if os.path.exists(srcDir):
                    for src in os.listdir(srcDir):
                        call('cp', '-R', '--no-dereference',
                                os.path.join(srcDir, src), current)

            outputFileList = self.buildIsos(topDir)

            if self.buildOVF10:
                self.workingDir = os.path.join(self.workDir, self.basefilename)
                util.mkdirChain(self.workingDir)

                diskFileSize = imagegen.getFileSize(outputFileList[0][0])
                self.ovfImage = ovf_image.ISOOvfImage(self.basefilename,
                    self.jobData['description'], None, outputFileList[0][0],
                    diskFileSize, self.maxIsoSize, False,
                    self.getBuildData('vmMemory'), self.workingDir, 
                    self.outputDir)

                self.ovfObj = self.ovfImage.createOvf()
                self.ovfXml = self.ovfImage.writeOvf()
                self.ovfImage.createManifest()
                self.ovaPath = self.ovfImage.createOva()

                outputFileList.append((self.ovaPath, 'Appliance ISO OVF 1.0'))

            # notify client that images are ready
            self.postOutput(outputFileList)
        finally:
            util.rmtree(os.path.normpath(os.path.join(topDir, "..")),
                        ignore_errors = True)
            util.rmtree(constants.cachePath, ignore_errors = True)
