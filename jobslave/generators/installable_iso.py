#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#
import os
import pwd
import re
import string
import subprocess
import sys
import tempfile
import time

from jobslave.generators import constants
from jobslave.generators import gencslist
from jobslave.generators import splitdistro
from jobslave.generators.splitdistro import call
from jobslave.generators import anaconda_templates
from jobslave.generators.anaconda_images import AnacondaImages
from jobslave.generators.imagegen import ImageGenerator, MSG_INTERVAL

#from mint.client import upstream

from jobslave import flavors

from conary import callbacks
from conary import conaryclient
from conary import conarycfg
from conary.deps import deps
from conary import versions
from conary.repository import errors
from conary.build import use
from conary.conarycfg import ConfigFile
from conary.conaryclient.cmdline import parseTroveSpec
from conary.lib import util, sha1helper


class AnacondaTemplateMissing(Exception):
    def __init__(self, arch = "arch"):
        self._arch = arch

    def __str__(self):
        return "Anaconda template missing for architecture: %s" % self._arch


class Callback(callbacks.UpdateCallback):
    def requestingChangeSet(self):
        self._update('requesting %s from repository')

    def downloadingChangeSet(self, got, need):
        if need != 0:
            self._update('downloading %%s from repository (%d%%%% of %dk)'
                         %((got * 100) / need, need / 1024))

    def downloadingFileContents(self, got, need):
        if need != 0:
            self._update('downloading files for %%s from repository '
                         '(%d%%%% of %dk)' %((got * 100) / need, need / 1024))

    def _update(self, msg):
        # only push an update into the database if it differs from the
        # current message, and a given timeout period has elapsed.
        curTime = time.time()
        if self.msg != msg and (curTime - self.timeStamp) > MSG_INTERVAL:
            self.msg = msg
            self.status(self.prefix + msg % self.changeset)
            self.timeStamp = curTime

    def setChangeSet(self, name):
        self.changeset = name

    def setPrefix(self, prefix):
        self.prefix = prefix

    def __init__(self, status):

        self.exceptions = []
        self.abortEvent = None
        self.status = status
        self.restored = 0
        self.msg = ''
        self.changeset = ''
        self.prefix = ''
        self.timeStamp = 0

        callbacks.UpdateCallback.__init__(self)


def _linkRecurse(fromDir, toDir):
    for root, dirs, files in os.walk(fromDir):
        for dir in dirs:
            newRoot = toDir + root[len(fromDir):]
            util.mkdirChain(os.path.join(newRoot, dir))
        for file in files:
            newRoot = toDir + root[len(fromDir):]
            src = os.path.join(root, file)
            dest = os.path.join(newRoot, file)
            gencslist._linkOrCopyFile(src, dest)

def getArchFlavor(flv):
    if flv.members and deps.DEP_CLASS_IS in flv.members:
        # search through our pathSearchOrder and find the
        # best single architecture flavor for this build
        for x in [deps.ThawFlavor(y) for y in flavors.pathSearchOrder]:
            if flv.satisfies(x):
                return x
        return deps.Flavor()

upstream = lambda ver: ver.trailingRevision().asString().split('-')[0]

class InstallableIso(ImageGenerator):
    productDir = 'rPath'

    def __init__(self, *args, **kwargs):
        ImageGenerator.__init__(self, *args, **kwargs)
        self.showMediaCheck = self.getBuildData('showMediaCheck')
        self.maxIsoSize = int(self.getBuildData('maxIsoSize'))

    def _getUpdateJob(self, cclient, troveName):
        self.callback.setChangeSet(troveName)
        trvSpec = self.getBuildData(troveName)
        if trvSpec:
            spec = parseTroveSpec(trvSpec)
            itemList = [(troveName, (None, None), (spec[1], spec[2]), True)]
            uJob, suggMap = cclient.updateChangeSet(itemList,
                resolveDeps = False)
            return uJob

    def _getTroveSpec(self, uJob):
        """returns the specstring of an update job"""
        for job in uJob.getPrimaryJobs():
            trvName, trvVersion, trvFlavor = job[0], str(job[2][0]), str(job[2][1])
            return "%s=%s[%s]" % (trvName, trvVersion, trvFlavor)

    def getConaryClient(self, tmpRoot, arch):
        arch = deps.ThawFlavor(arch)
        cfg = self.conarycfg
        self.readConaryRc(cfg)

        cfg.root = tmpRoot
        cfg.dbPath = tmpRoot + "/var/lib/conarydb"
        cfg.installLabelPath = [self.troveVersion.branch().label()]
        cfg.buildFlavor = flavors.getStockFlavor(arch)
        cfg.flavor = flavors.getStockFlavorPath(arch)
        cfg.initializeFlavors()

        return conaryclient.ConaryClient(cfg)

    def convertSplash(self, topdir, tmpPath):
        # convert syslinux-splash.png to splash.lss, if exists
        if os.path.exists(tmpPath + '/pixmaps/syslinux-splash.png'):
            print >> sys.stderr, "found syslinux-splash.png, converting to splash.lss"

            splash = file(tmpPath + '/pixmaps/splash.lss', 'w')
            palette = [] # '#000000=0', '#cdcfd5=7', '#c90000=2', '#ffffff=15', '#5b6c93=9']
            pngtopnm = subprocess.Popen(['pngtopnm', tmpPath + '/pixmaps/syslinux-splash.png'], stdout = subprocess.PIPE)
            ppmtolss16 = subprocess.Popen(['ppmtolss16'] + palette, stdin = pngtopnm.stdout, stdout = splash)
            ppmtolss16.communicate()

        # copy the splash.lss files to the appropriate place
        if os.path.exists(tmpPath + '/pixmaps/splash.lss'):
            print >> sys.stderr, "found splash.lss; moving to isolinux directory"
            splashTarget = os.path.join(topdir, 'isolinux')
            call('cp', '--remove-destination', tmpPath + '/pixmaps/splash.lss', splashTarget)
            # FIXME: regenerate boot.iso here

    def writeBuildStamp(self, tmpPath):
        ver = versions.ThawVersion(self.jobData['troveVersion'])

        bsFile = open(os.path.join(tmpPath, ".buildstamp"), "w")
        print >> bsFile, time.time()
        print >> bsFile, self.jobData['name']
        print >> bsFile, upstream(ver)
        print >> bsFile, self.productDir
        print >> bsFile, self.getBuildData("bugsUrl")
        print >> bsFile, "%s %s %s" % (self.baseTrove,
                                       self.jobData['troveVersion'],
                                       self.baseFlavor.freeze())
        bsFile.close()

    def writeProductImage(self, topdir, arch):
        # write the product.img cramfs
        baseDir = os.path.join(topdir, self.productDir, 'base')
        productPath = os.path.join(baseDir, "product.img")
        tmpPath = tempfile.mkdtemp(dir=constants.tmpDir)

        self.writeBuildStamp(tmpPath)

        # extract anaconda-images from repository, if exists
        tmpRoot = tempfile.mkdtemp(dir=constants.tmpDir)
        util.mkdirChain(os.path.join(tmpRoot, 'usr', 'share', 'anaconda',
                                     'pixmaps'))
        cclient = self.getConaryClient(tmpRoot, arch)
        cclient.setUpdateCallback(self.callback)

        print >> sys.stderr, "generating anaconda artwork."
        autoGenPath = tempfile.mkdtemp(dir=constants.tmpDir)
        ai = AnacondaImages( \
            self.jobData['name'],
            indir = constants.anacondaImagesPath,
            outdir = autoGenPath,
            fontfile = '/usr/share/fonts/bitstream-vera/Vera.ttf')
        ai.processImages()

        uJob = None
        print >> sys.stderr, "checking for artwork from anaconda-custom=%s" % cclient.cfg.installLabelPath[0].asString()
        uJob = self._getUpdateJob(cclient, "anaconda-custom")
        if not uJob:
            print >> sys.stderr, "anaconda-custom not found, falling back to legacy anaconda-images trove"
            uJob = self._getUpdateJob(cclient, "anaconda-images")
        if uJob:
            print >> sys.stderr, "custom artwork found. applying on top of generated artwork"
            cclient.applyUpdate(uJob, callback = self.callback,
                                replaceFiles = True)
            print >> sys.stderr, "success."
            sys.stderr.flush()

        # if syslinux-splash.png does not exist in the anaconda-custom trove, change the
        # syslinux messages to fit our autogenerated palette.
        if not os.path.exists(os.path.join(tmpRoot, 'usr', 'share', 'anaconda', 'pixmaps', 'syslinux-splash.png')) and \
            os.path.isdir(os.path.join(topdir, 'isolinux')):
            # do this here because we know we don't have custom artwork.
            # modify isolinux message colors to match default splash palette.
            for msgFile in [x for x in os.listdir( \
                os.path.join(topdir, 'isolinux')) if x.endswith('.msg')]:

                call('sed', '-i', 's/07/0a/g;s/02/0e/g',
                     os.path.join(topdir, 'isolinux', msgFile))

        # copy autogenerated pixmaps into cramfs root
        util.mkdirChain(os.path.join(tmpPath, 'pixmaps'))
        tmpTar = tempfile.mktemp(suffix = '.tar')
        call('tar', 'cf', tmpTar, '-C', autoGenPath, '.')
        call('tar', 'xf', tmpTar, '-C', os.path.join(tmpPath, 'pixmaps'))
        os.unlink(tmpTar)

        if uJob:
            # copy pixmaps and scripts into cramfs root
            tmpTar = tempfile.mktemp(suffix = '.tar')
            call('tar', 'cf', tmpTar, '-C',
                 os.path.join(tmpRoot, 'usr', 'share', 'anaconda'), '.')
            call('tar', 'xf', tmpTar, '-C', tmpPath)
            os.unlink(tmpTar)

        self.convertSplash(topdir, tmpPath)
        self.writeConaryRc(os.path.join(tmpPath, 'conaryrc'), cclient)

        # extract constants.py from the stage2.img template and override the BETANAG flag
        # this would be better if constants.py could load a secondary constants.py
        stage2Path = tempfile.mkdtemp(dir=constants.tmpDir)
        call('/sbin/fsck.cramfs', topdir + '/rPath/base/stage2.img', '-x', stage2Path)
        call('cp', stage2Path + '/usr/lib/anaconda/constants.py', tmpPath)

        betaNag = self.getBuildData('betaNag')
        call('sed', '-i', 's/BETANAG = 1/BETANAG = %d/' % int(betaNag), tmpPath + '/constants.py')
        util.rmtree(stage2Path)

        # create cramfs
        call('mkcramfs', tmpPath, productPath)

        # clean up
        util.rmtree(tmpPath)
        util.rmtree(tmpRoot)
        util.rmtree(autoGenPath)

    def buildIsos(self, topdir):
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        # add the group writeable bit
        os.chmod(outputDir, os.stat(outputDir)[0] & 0777 | 0020)

        isoList = []

        if self.basefilename:
            isoNameTemplate = self.basefilename + '-'
        else:
            isoNameTemplate = "%s-%s-%s-" % \
                (self.jobData['project']['hostname'],
                 upstream(self.troveVersion),
                 self.arch)
        sourceDir = os.path.normpath(topdir + "/../")

        for d in sorted(os.listdir(sourceDir)):
            if not d.startswith('disc'):
                continue

            discNum = d.split("disc")[-1]
            discNumStr = "Disc %d" % int(discNum)
            truncatedName = self.jobData['name'][:31-len(discNumStr)]
            volumeId = "%s %s" % (truncatedName, discNumStr)
            outputIsoName = isoNameTemplate + d + ".iso"
            if os.access(os.path.join(sourceDir, d, "isolinux/isolinux.bin"), os.R_OK):
                os.chdir(os.path.join(sourceDir, d))
                call("mkisofs", "-o", outputDir + "/" + outputIsoName,
                                "-b", "isolinux/isolinux.bin",
                                "-c", "isolinux/boot.cat",
                                "-no-emul-boot",
                                "-boot-load-size", "4",
                                "-boot-info-table", "-R", "-J",
                                "-V", volumeId,
                                "-T", ".")
            else:
                os.chdir(os.path.join(sourceDir, d))
                call("mkisofs", "-o", outputDir + "/" + outputIsoName,
                     "-R", "-J", "-V", volumeId, "-T", ".")

            isoList.append((outputIsoName, "%s Disc %s" % (self.jobData['project']['name'], discNum)))

        isoList = [ (os.path.join(outputDir, iso[0]), iso[1]) for iso in isoList ]
        # this for loop re-identifies any iso greater than 700MB as a DVD
        for index, (iso, name) in zip(range(len(isoList)), isoList[:]):
            szPipe = os.popen('isosize %s' % iso, 'r')
            isoSize = int(szPipe.read())
            szPipe.close()
            if isoSize > 734003200: # 700 MB in bytes
                newIso = iso.replace('disc', 'dvd')
                newName = name.replace('Disc', 'DVD')
                os.rename(iso, newIso)
                isoList[index] = (newIso, newName)

        for iso, name in isoList:
            if not os.access(iso, os.R_OK):
                raise RuntimeError, "ISO generation failed"
            else:
                cmd = [constants.implantIsoMd5]
                if not self.showMediaCheck:
                    cmd.append('--supported-iso')
                cmd.append(iso)
                call(*cmd)

        # add the netboot images
        for f in ('boot.iso', 'diskboot.img'):
            inF = os.path.join(topdir, 'images', f)
            outF = os.path.join(outputDir, f)
            if os.path.exists(inF):
                gencslist._linkOrCopyFile(inF, outF)
                isoList += ( (outF, f), )
        return isoList

    def setupKickstart(self, topdir):
        if os.path.exists(os.path.join(topdir, 'media-template',
                                       'disc1', 'ks.cfg')):
            print >> sys.stderr, "Adding kickstart arguments"
            os.system("sed -i '0,/append/s/append.*$/& ks=cdrom/' %s" % \
                      os.path.join(topdir, 'isolinux', 'isolinux.cfg'))

    def _makeTemplate(self, templateDir, tmpDir, uJob, cclient):
        # templateData is something that the template commands can
        # modify so that we can use the information later on down the
        # road.
        self.templateData = {}
        self.status("Preparing and caching new anaconda template...")

        def setInfo(key, data):
            self.templateData[key] = data

        def syslinux(self, input):
            return call(['syslinux', input])

        image = anaconda_templates.Image(templateDir, tmpDir)

        cmdMap = {
            'image':    image.run,
            'set':      setInfo,
            'syslinux': syslinux,
        }

        if uJob:
            cclient.applyUpdate(uJob)
            util.copytree(os.path.join(tmpDir, 'unified'), templateDir + os.path.sep)

        manifest = open(os.path.join(tmpDir, "MANIFEST"))
        for l in manifest.xreadlines():
            cmds = [x.strip() for x in l.split(',')]

            cmd = cmds.pop(0)
            if cmd not in cmdMap:
                raise RuntimeError, "Invalid command in anaconda-templates MANIFEST: %s" % (cmd)

            func = cmdMap[cmd]
            ret = func(*cmds)

    def _getTemplatePath(self):
        tmpDir = tempfile.mkdtemp(dir=constants.tmpDir)
        try:
            print >> sys.stderr, "finding anaconda-templates for " + self.arch
            cclient = self.getConaryClient( \
                tmpDir, getArchFlavor(self.baseFlavor).freeze())

            cclient.cfg.installLabelPath.append(versions.Label(constants.templatesLabel))

            uJob = self._getUpdateJob(cclient, 'anaconda-templates')
            if not uJob:
                raise RuntimeError, "anaconda-templates package not found!"
            troveSpec = self._getTroveSpec(uJob)
            hash = sha1helper.md5ToString(sha1helper.md5String(troveSpec))
            templateDir = os.path.join(constants.anacondaTemplatesPath, hash)
            templateDirTemp = templateDir + "-temp"

            # check to see if someone else is already creating the cache
            tries = 0
            while os.path.exists(templateDirTemp):
                time.sleep(10)
                print >> sys.stderr, "someone else is creating templates in %s -- sleeping 10 seconds" % templateDirTemp
                tries += 1

                if tries > 360:
                    raise RuntimeError, "Waited 1 hour for anaconda templates from another job to appear: giving up."

            if not os.path.exists(templateDir):
                try:
                    print >> sys.stderr, "template package not cached, creating"
                    util.mkdirChain(templateDirTemp)
                    self._makeTemplate(templateDirTemp, tmpDir, uJob, cclient)
                    os.rename(templateDirTemp, templateDir)
                finally:
                    if os.path.exists(templateDirTemp):
                        util.rmtree(templateDirTemp)
            print >> sys.stderr, "templates found:", templateDir

            return templateDir
        finally:
            util.rmtree(tmpDir, ignore_errors = True)

    def prepareTemplates(self, topdir):
        templateDir = self._getTemplatePath() + "/unified"

        self.status("Preparing ISO template")
        _linkRecurse(templateDir, topdir)
        productDir = os.path.join(topdir, self.productDir)

        # replace isolinux.bin with a real copy, since it's modified
        call('cp', '--remove-destination', '-a',
            templateDir + '/isolinux/isolinux.bin', topdir + '/isolinux/isolinux.bin')
        if os.path.exists(os.path.join(templateDir, 'isolinux')):
            for msgFile in [x for x in os.listdir(os.path.join(templateDir, 'isolinux')) if x.endswith('.msg')]:
                call('cp', '--remove-destination', '-a',
                     os.path.join(templateDir, 'isolinux', msgFile),
                     os.path.join(topdir, 'isolinux', msgFile))

        csdir = os.path.join(topdir, self.productDir, 'changesets')
        util.mkdirChain(csdir)
        return csdir

    def extractMediaTemplate(self, topdir):
        tmpRoot = tempfile.mkdtemp(dir=constants.tmpDir)
        try:
            client = self.getConaryClient(\
                tmpRoot, getArchFlavor(self.baseFlavor).freeze())

            print >> sys.stderr, "extracting ad-hoc content from " \
                  "media-template=%s" % client.cfg.installLabelPath[0].asString()
            uJob = self._getUpdateJob(client, "media-template")
            if uJob:
                client.applyUpdate(uJob, callback = self.callback)
                print >> sys.stderr, "success: copying media template data to unified tree"
                sys.stderr.flush()

                # copy content into unified tree root. add recurse and no-deref
                # flags to command. following symlinks is really bad in this case.
                oldTemplateDir = os.path.join(tmpRoot,
                                              'usr', 'lib', 'media-template')
                if os.path.exists(oldTemplateDir):
                    call('cp', '-R', '--no-dereference', oldTemplateDir, topdir)
                for tDir in ('all', 'disc1'):
                    srcDir = os.path.join(tmpRoot, tDir)
                    destDir = os.path.join(topdir, 'media-template2')
                    if os.path.exists(srcDir):
                        util.mkdirchain(destDir)
                        call('cp', '-R', '--no-dereference', srcDir, destDir)
            else:
                print >> sys.stderr, "media-template not found on repository"
        finally:
            util.rmtree(tmpRoot)

    def extractPublicKeys(self, keyDir, topdir, csdir):
        self.status('Extracting Public Keys')
        homeDir = tempfile.mkdtemp()
        tmpRoot = tempfile.mkdtemp()
        try:
            client = self.getConaryClient(tmpRoot,
                                          self.build.getArchFlavor().freeze())

            fingerprints = {}
            fpTrovespecs = {}
            for filename in [x for x in os.listdir(csdir) if x.endswith('.ccs')]:
                cs = changeset.ChangeSetFromFile(os.path.join(csdir, filename))
                troves = [trove.Trove(x) for x in cs.iterNewTroveList()]
                for trv in troves:
                    label = trv.version.v.trailingLabel()
                    for sig in trv.troveInfo.sigs.digitalSigs.iter():
                        tspecList = fpTrovespecs.get(sig[0], set())
                        tspecList.add('%s=%s[%s]' % (trv.getName(),
                                                 str(trv.getVersion()),
                                                 str(trv.getFlavor())))
                        fpTrovespecs[sig[0]] = tspecList
                        if fingerprints.has_key(label):
                            if sig[0] not in fingerprints[label]:
                                fingerprints[label].append(sig[0])
                        else:
                            fingerprints.update({label:[sig[0]]})

            missingKeys = []
            for label, fingerprints in fingerprints.items():
                for fp in fingerprints:
                    try:
                        key = client.repos.getAsciiOpenPGPKey(label, fp)
                        fd, fname = tempfile.mkstemp()
                        os.close(fd)
                        fd = open(fname, 'w')
                        fd.write(key)
                        fd.close()
                        call('gpg', '--home', homeDir,
                             '--trust-model', 'always',
                             '--import', fname)
                        os.unlink(fname)
                    except openpgpfile.KeyNotFound:
                        missingKeys.append(fp)

            if missingKeys:
                errorMessage = 'The following troves do not have keys in ' \
                    'their associated repositories:\n'
                for fingerprint in missingKeys:
                    errorMessage += '%s requires %s\n' %  \
                        (', '.join(fpTrovespecs[fingerprint]), fingerprint)
                if self.isocfg.failOnKeyError:
                    raise RuntimeError(errorMessage)
                else:
                    print >> sys.stderr, errorMessage
            call('gpg', '--home', homeDir, '--export',
                 '--no-auto-check-trustdb', '-o',
                 os.path.join(topdir, 'public_keys.gpg'))
        finally:
            util.rmtree(homeDir)
            util.rmtree(tmpRoot)

    def extractChangeSets(self, csdir):
        # build a set of the things we already have extracted.
        self.status("Extracting changesets")

        tmpRoot = tempfile.mkdtemp(dir=constants.tmpDir)
        client = self.getConaryClient(tmpRoot,
                                      getArchFlavor(self.baseFlavor).freeze())
        tg = gencslist.TreeGenerator(client.cfg, client,
            (self.troveName, self.troveVersion, self.troveFlavor),
            cacheDir=constants.cachePath)
        tg.parsePackageData()
        tg.extractChangeSets(csdir, callback=self.callback)

        print >> sys.stderr, "done extracting changesets"
        sys.stderr.flush()
        return tg

    def _setupTrove(self):
        self.troveName = self.baseTrove
        self.troveVersion = versions.ThawVersion(self.jobData['troveVersion'])
        self.troveFlavor = self.baseFlavor

    def write(self):
        self.callback = Callback(self.status)

        # set up the topdir
        topdir = os.path.join(constants.tmpDir, self.jobId, "unified")
        util.mkdirChain(topdir)

        self._setupTrove()

        print >> sys.stderr, "Building ISOs of size: %d Mb" % \
              (self.maxIsoSize / 1048576)
        sys.stderr.flush()

        # FIXME: hack to ensure we don't trigger overburns.
        # there are probably cleaner ways to do this.
        if self.maxIsoSize > 681574400:
            self.maxIsoSize -= 1024 * 1024

        csdir = self.prepareTemplates(topdir)
        tg = self.extractChangeSets(csdir)

        if self.arch == 'x86':
            anacondaArch = 'i386'
        else:
            anacondaArch = self.arch

        baseDir = os.path.join(topdir, self.productDir, 'base')

        # write the cslist
        tg.writeCsList(baseDir)

        # write the group.ccs
        tg.writeGroupCs(baseDir)

        # write .discinfo
        discInfoPath = os.path.join(topdir, ".discinfo")
        if os.path.exists(discInfoPath):
            os.unlink(discInfoPath)
        discInfoFile = open(discInfoPath, "w")
        print >> discInfoFile, time.time()
        print >> discInfoFile, self.jobData['name']
        print >> discInfoFile, anacondaArch
        print >> discInfoFile, "1"
        for x in ["base", "changesets", "pixmaps"]:
            print >> discInfoFile, "%s/%s" % (self.productDir, x)
        discInfoFile.close()

        self.extractMediaTemplate(topdir)
        self.extractPublicKeys('public_keys', topdir, csdir)
        self.setupKickstart(topdir)
        self.writeProductImage(topdir, getArchFlavor(self.baseFlavor).freeze())

        self.status("Building ISOs")
        splitdistro.splitDistro(topdir, self.troveName, self.maxIsoSize)
        isoList = self.buildIsos(topdir)

        # notify client that images are ready
        self.postOutput(isoList)

        # clean up
        self.status("Cleaning up...")
        util.rmtree(os.path.normpath(os.path.join(topdir, "..")))
