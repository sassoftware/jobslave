#
# Copyright (c) 2004-2007 rPath, Inc.
#
# All Rights Reserved
#

# python standard library imports
import os
import sys
import time

# jobslave imports
from jobslave.generators import bootable_image, constants, installable_iso
from jobslave import buildtypes
from jobslave import splitdistro

from conary import versions
from conary.lib import util

class TarSplit(object):
    def __init__(self, file):
        self.file = file
        self.tarfh = open(file)
        self.count = 0
        self.prefix = 'tar-chunk.'
        self.files = []
        self.tblist = []
        self.chunkSize = 50*1024*1024

        self.tarfh.seek(0, 2)
        self.tarEnd = self.tarfh.tell()
        self.tarfh.seek(0)

    def _formatFileName(self):
        return '%s%s' % (self.prefix, self.count)

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

            self.files.append(self._formatFileName())
            self.tblist.append('%s %s %s' % (self._formatFileName(), size, 1))

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

        if 'filesystems' not in self.jobData:
            # support for legacy requests
            freeSpace = self.getBuildData("freespace") * 1048576
            swapSize = 0

            self.jobData['filesystems'] = [
                ('/', 0, freeSpace, 'ext3'),
                ('swap', 0, swapSize, 'swap'),
            ]

        self.mountDict = dict([(x[0], tuple(x[1:])) for x in self.jobData['filesystems'] if x[0]])

        basefilename = self.getBuildData('baseFileName') or ''
        basefilename = ''.join([(x.isalnum() or x in ('-', '.')) and x or '_' \
                                for x in basefilename])
        ver = versions.ThawVersion(self.jobData['troveVersion'])
        basefilename = basefilename or \
                       "%(name)s-%(version)s-%(arch)s" % {
                           'name': self.jobData['project']['hostname'],
                           'version': ver.trailingRevision().asString().split('-')[0],
                           'arch': self.arch}

        self.basefilename = basefilename
    
    def writeBuildStamp(self, tmpPath):
        installable_iso.InstallableIso.writeBuildStamp(self, tmpPath)
        bsFile = open(os.path.join(tmpPath, ".buildstamp"), "a")
        print >> bsFile, 'rPath/tarballs'
        bsFile.close()

    def write(self):
        topDir = os.path.join(constants.tmpDir, self.jobId, 'unified')
        tbdir = os.path.join(topDir, self.productDir, 'tarballs')
        baseDir = os.path.join(topDir, self.productDir, 'base')
        util.mkdirChain(tbdir)
        util.mkdirChain(baseDir)

        basePath = os.path.join(constants.tmpDir, self.jobId, self.basefilename)
        if os.path.exists(basePath):
            util.rmtree(basePath)
        util.mkdirChain(basePath)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        tarball = os.path.join(constants.tmpDir, self.jobId,
                               self.basefilename + '.tgz')
        cwd = os.getcwd()
        try:
            self.installFileTree(basePath)
            os.chdir(basePath)
            util.execute('tar -C %s -cpPs --to-stdout ./ | gzip > %s' % \
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

	    self._setupTrove()
	    self.callback = installable_iso.Callback(self.status)

            print >> sys.stderr, "Building ISOs of size: %d Mb" % \
              (self.maxIsoSize / 1048576)
            sys.stderr.flush()
    
            # FIXME: hack to ensure we don't trigger overburns.
            # there are probably cleaner ways to do this.
            if self.maxIsoSize > 681574400:
                self.maxIsoSize -= 1024 * 1024
    
            csdir = self.prepareTemplates(topDir)
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
            current = os.path.join(constants.tmpDir, self.jobId, 'disc1')
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
                        call('cp', '-R', '--no-dereference', os.path.join(srcDir, src),
                             current)

	    
            isoList = self.buildIsos(topDir)
    
            # notify client that images are ready
            self.postOutput(isoList)
        finally:
            util.rmtree(os.path.normpath(os.path.join(topDir, "..")),
                        ignore_errors = True)
            util.rmtree(constants.cachePath, ignore_errors = True)
