#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#
import httplib
import os
import pwd
import re
import socket
import string
import subprocess
import sys
import tempfile
import time
import urllib
import urlparse

from jobslave.generators import constants
from jobslave import gencslist
from jobslave import splitdistro
from jobslave.splitdistro import call
from jobslave.generators.anaconda_images import AnacondaImages
from jobslave.imagegen import ImageGenerator, MSG_INTERVAL

from jobslave import flavors
from jobslave.helperfuncs import getSlaveRuntimeConfig

from conary import callbacks
from conary import conaryclient
from conary import conarycfg
from conary.deps import deps
from conary import versions
from conary.repository import changeset
from conary.repository import errors
from conary import trove
from conary.build import use
from conary.conarycfg import ConfigFile
from conary.conaryclient.cmdline import parseTroveSpec
from conary.lib import util, sha1helper, openpgpfile

class Callback(callbacks.UpdateCallback):
    def requestingChangeSet(self):
        self._update('Requesting %s from repository')

    def downloadingChangeSet(self, got, need):
        if need != 0:
            self._update('Downloading %%s from repository (%d%%%% of %dk)'
                         %((got * 100) / need, need / 1024))

    def downloadingFileContents(self, got, need):
        if need != 0:
            self._update('Downloading files for %%s from repository '
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

    def _getNVF(self, uJob):
        """returns the n, v, f of an update job, assuming only one job"""
        for job in uJob.getPrimaryJobs():
            trvName, trvVersion, trvFlavor = job[0], str(job[2][0]), str(job[2][1])
            return (trvName, trvVersion, trvFlavor)
    
    def _getMasterIPAddress(self):
        return getSlaveRuntimeConfig().get('MASTER_IP', '')

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
        tmpTar = tempfile.mktemp(dir = constants.tmpDir, suffix = '.tar')
        call('tar', 'cf', tmpTar, '-C', autoGenPath, '.')
        call('tar', 'xf', tmpTar, '-C', os.path.join(tmpPath, 'pixmaps'))
        os.unlink(tmpTar)

        if uJob:
            # copy pixmaps and scripts into cramfs root
            tmpTar = tempfile.mktemp(dir = constants.tmpDir, suffix = '.tar')
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
        util.rmtree(stage2Path, ignore_errors = True)

        # create cramfs
        call('mkcramfs', tmpPath, productPath)

        # clean up
        util.rmtree(tmpPath, ignore_errors = True)
        util.rmtree(tmpRoot, ignore_errors = True)
        util.rmtree(autoGenPath, ignore_errors = True)

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

    def retrieveTemplates(self):
        self.status("Retrieving ISO template")
        print >> sys.stderr, "requesting anaconda-templates for " + self.arch

        masterIPAddress = self._getMasterIPAddress()
        if not masterIPAddress:
            raise RuntimeError, "Failed to get jobmaster's IP address, aborting"

        tmpDir = tempfile.mkdtemp(dir=constants.tmpDir)
        cclient = self.getConaryClient( \
            tmpDir, getArchFlavor(self.baseFlavor).freeze())

        # TODO what about custom templates?
        cclient.cfg.installLabelPath.append(versions.Label(constants.templatesLabel))
        uJob = self._getUpdateJob(cclient, 'anaconda-templates')
        if not uJob:
            raise RuntimeError, "Failed to find anaconda-templates"


        _, v, f = self._getNVF(uJob)

        try:
            try:
                # XXX fix hardcoded port!
                httpconn = httplib.HTTPConnection('%s:%d' % \
                        (masterIPAddress, 8000))
                httpconn.connect()

                # request new template
                params = urllib.urlencode({'v': v, 'f': f})
                headers = {"Content-type": "application/x-www-form-urlencoded",
                           "Content-length": len(params)}
                httpconn.request('POST', '/makeTemplate', params, headers)
                httpresp = httpconn.getresponse()

                # At this point the serve may do one of three things:
                # - Return 202, with trove hash. This indicates that the
                #   template build has been started by this process.
                # - Return 303. This could mean that either
                #   - the build is still in progress (if the URI in location
                #     contains "status" in its path) OR
                #   - the build is complete, and the URI in the location field
                #     is the URL to fetch the finished template via GET
                #
                # Anything else represents a failure mode.
                currentStatus = ''
                nexthop = ''
                while True:
                    print currentStatus
                    contentType = httpresp.getheader('Content-Type')
                    if httpresp.status in (202, 303):
                        nexthop = httpresp.getheader('Location')
                    elif httpresp.status == 200:
                        if contentType == 'text/plain':
                            currentStatus = httpresp.read()
                        elif contentType == 'application/x-tar':
                            break
                        else:
                            raise RuntimeError, "Got an unexpected Content-Type '%s' from the template webservice, aborting" % contentType
                    else:
                        raise RuntimeError, "Failed to request a new template: anaconda-templates=%s[%s]" % (v, f)

                    # Sleep 5 seconds, and ask again
                    # XXX should we bail after a certain number of retries?
                    #     if so, after how many?
                    time.sleep(5)
                    uripath, query = urlparse.urlsplit(nexthop)[2:4]
                    if query:
                        uripath += '?%s' % query
                    httpconn.request('GET', uripath)
                    httpresp = httpconn.getresponse()

                ncpv = httpresp.getheader('x-netclient-protocol-version')
                if ncpv:
                    ncpv = int(ncpv)
                else:
                    print >> sys.stderr, "Missing netclient protocol version," \
                                         "falling back to a safe version (38)"
                    sys.stderr.flush()
                    ncpv = 38

                pTar = subprocess.Popen(['tar', '-xf', '-'],
                    stdin=httpresp.fp, cwd=anacondaTemplateDir)
                rc = pTar.wait()
                if rc != 0:
                    raise RuntimeError, "Failed to expand anaconda-templates (rc=%d)" % rc
            except (IOError, socket.error), e:
                raise "Error occurred when requesting anaconda-templates: %s" % str(e)
        finally:
            httpconn.close()
        return os.path.join(templateDir, 'unified'), ncpv

    def prepareTemplates(self, topdir, templateDir):
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
            util.rmtree(tmpRoot, ignore_errors = True)

    def extractPublicKeys(self, keyDir, topdir, csdir):
        self.status('Extracting Public Keys')
        homeDir = tempfile.mkdtemp(dir = constants.tmpDir)
        tmpRoot = tempfile.mkdtemp(dir = constants.tmpDir)
        try:
            client = self.getConaryClient( \
                tmpRoot, getArchFlavor(self.baseFlavor).freeze())

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
                        fd, fname = tempfile.mkstemp(dir = constants.tmpDir)
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
                raise RuntimeError(errorMessage)
            call('gpg', '--home', homeDir, '--export',
                 '--no-auto-check-trustdb', '-o',
                 os.path.join(topdir, 'public_keys.gpg'))
        finally:
            util.rmtree(homeDir, ignore_errors = True)
            util.rmtree(tmpRoot, ignore_errors = True)

    def extractChangeSets(self, csdir, clientVersion):
        # build a set of the things we already have extracted.
        self.status("Extracting changesets")

        tmpRoot = tempfile.mkdtemp(dir=constants.tmpDir)
        util.mkdirChain(constants.cachePath)
        client = self.getConaryClient(tmpRoot,
                                      getArchFlavor(self.baseFlavor).freeze())
        tg = gencslist.TreeGenerator(client.cfg, client,
            (self.troveName, self.troveVersion, self.troveFlavor),
            cacheDir=constants.cachePath, clientVersion=clientVersion)
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
        try:
            util.mkdirChain(topdir)

            self._setupTrove()

            print >> sys.stderr, "Building ISOs of size: %d Mb" % \
                  (self.maxIsoSize / 1048576)
            sys.stderr.flush()

            # FIXME: hack to ensure we don't trigger overburns.
            # there are probably cleaner ways to do this.
            if self.maxIsoSize > 681574400:
                self.maxIsoSize -= 1024 * 1024

            templateDir, clientVersion = self.retrieveTemplates()
            csdir = self.prepareTemplates(topdir, templateDir)
            tg = self.extractChangeSets(csdir, clientVersion)

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
        finally:
            util.rmtree(os.path.normpath(os.path.join(topdir, "..")),
                        ignore_errors = True)
            util.rmtree(constants.cachePath, ignore_errors = True)
