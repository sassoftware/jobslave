#
# Copyright (c) rPath, Inc.
#

import base64
import ConfigParser
import cPickle
import logging
import os
import subprocess
import tempfile
import time
import urllib2

from jobslave.generators import constants
from jobslave import gencslist
from jobslave import imagegen
from jobslave import splitdistro
from jobslave.splitdistro import call
from jobslave.generators.anaconda_images import AnacondaImages
from jobslave.imagegen import ImageGenerator, MSG_INTERVAL
from jobslave.generators import ovf_image
from jobslave.util import logCall

from jobslave import flavors

from conary import callbacks
from conary import conaryclient
from conary.deps import deps
from conary import versions
from conary.repository import changeset
from conary import trove
from conary.conaryclient.cmdline import parseTroveSpec
from conary.lib import util, openpgpfile


log = logging.getLogger('')


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
        if trvSpec and trvSpec.upper() != 'NONE':
            n, v, f = parseTroveSpec(trvSpec.encode('utf8'))
            try:
                v = versions.ThawVersion(v)
            except:
                try:
                    v = versions.VersionFromString(v)
                except:
                    log.error("Bad version string %r in custom trove field %r"
                            " -- using it anyway.", v, troveName)
            itemList = [(n, (None, None), (v, f), True)]
            uJob, suggMap = cclient.updateChangeSet(itemList,
                resolveDeps = False)
            return uJob

    def _getNVF(self, uJob):
        """returns the n, v, f of an update job, assuming only one job"""
        for job in uJob.getPrimaryJobs():
            return job[0], job[2][0], job[2][1]
    
    def getConaryClient(self, tmpRoot, arch):
        arch = deps.ThawFlavor(arch)
        cfg = self.conarycfg

        cfg.root = tmpRoot
        cfg.dbPath = tmpRoot + "/var/lib/conarydb"
        cfg.installLabelPath = [self.baseVersion.branch().label()]
        cfg.buildFlavor = flavors.getStockFlavor(arch)
        cfg.flavor = flavors.getStockFlavorPath(arch)
        cfg.initializeFlavors()

        return conaryclient.ConaryClient(cfg)

    def convertSplash(self, topdir, tmpPath):
        # convert syslinux-splash.png to splash.lss, if exists
        if os.path.exists(tmpPath + '/pixmaps/syslinux-splash.png'):
            log.info("found syslinux-splash.png, converting to splash.lss")

            splash = file(tmpPath + '/pixmaps/splash.lss', 'w')
            palette = [] # '#000000=0', '#cdcfd5=7', '#c90000=2', '#ffffff=15', '#5b6c93=9']
            pngtopnm = subprocess.Popen(['pngtopnm', tmpPath + '/pixmaps/syslinux-splash.png'], stdout = subprocess.PIPE)
            ppmtolss16 = subprocess.Popen(['ppmtolss16'] + palette, stdin = pngtopnm.stdout, stdout = splash)
            ppmtolss16.communicate()

        # copy the splash.lss files to the appropriate place
        if os.path.exists(tmpPath + '/pixmaps/splash.lss'):
            log.info("found splash.lss; moving to isolinux directory")
            splashTarget = os.path.join(topdir, 'isolinux')
            call('cp', '--remove-destination', tmpPath + '/pixmaps/splash.lss', splashTarget)
            # FIXME: regenerate boot.iso here

        # Locate splash for isolinux vesamenu background.
        for name in ('vesamenu-splash.jpg', 'vesamenu-splash.png'):
            sourcePath = os.path.join(tmpPath, 'pixmaps', name)
            if os.path.exists(sourcePath):
                ext = name.split('.')[-1]
                name = 'splash.%s' % ext
                util.copyfile(sourcePath,
                        os.path.join(topdir, 'isolinux', name))

                # Rewrite isolinux.cfg to point to the background image.
                isolinux = os.path.join(topdir, 'isolinux', 'isolinux.cfg')
                lines = open(isolinux).readlines()
                for n, line in enumerate(lines):
                    if line.startswith('menu background '):
                        lines[n] = 'menu background %s\n' % name
                open(isolinux, 'w').write(''.join(lines))

                break

    def changeIsolinuxMenuTitle(self, topdir):
        title = self.jobData['name']
        isolinux = os.path.join(topdir, 'isolinux', 'isolinux.cfg')
        lines = open(isolinux).readlines()
        for n, line in enumerate(lines):
            if line.startswith('menu title '):
                lines[n] = 'menu title %s\n' % title
        open(isolinux, 'w').write(''.join(lines))

    def writeBuildStamp(self, tmpPath):
        isDep = deps.InstructionSetDependency
        archFlv = getArchFlavor(self.baseFlavor)

        arch = ''
        if archFlv is not None:
            arches = [ x.name for x in archFlv.iterDepsByClass(isDep) ]
            if len(arches) > 0:
                arch = arches[0]

        stamp = '%s.%s' % (int(time.time()), arch)

        bsFile = open(os.path.join(tmpPath, ".buildstamp"), "w")
        print >> bsFile, stamp
        print >> bsFile, self.jobData['name']
        print >> bsFile, upstream(self.baseVersion)
        print >> bsFile, self.productDir
        print >> bsFile, self.getBuildData("bugsUrl")
        print >> bsFile, "%s %s %s" % (self.baseTrove,
                self.baseVersion.freeze(), self.baseFlavor.freeze())
        bsFile.close()

    def writeProductImage(self, topdir, arch):
        """write the product.img cramfs"""
        baseDir = os.path.join(topdir, self.productDir, 'base')
        tmpPath = tempfile.mkdtemp(dir=constants.tmpDir)
        self.writeBuildStamp(tmpPath)

        # RHEL 6 anaconda looks for product.img in a different location than
        # rPL 1 or rPL 2. To aid in detection, the path to product.img is
        # stashed in .treeinfo.
        treeInfo = os.path.join(topdir, '.treeinfo')
        productPath = os.path.join(baseDir, "product.img")
        stage2 = None
        if os.path.exists(treeInfo):
            try:
                parser = ConfigParser.SafeConfigParser()
                parser.read(treeInfo)
                # Look for an images-ARCH section, which may include a
                # path to product.img
                for section in parser.sections():
                    if not section.startswith('images-'):
                        continue
                    if parser.has_option(section, 'product.img'):
                        productPath = os.path.normpath(os.path.join(topdir,
                            parser.get(section, 'product.img')))
                # There may also be a pointer to the stage2
                if parser.has_option('stage2', 'mainimage'):
                    stage2 = parser.get('stage2', 'mainimage')
            except:
                log.exception("Failed to parse .treeinfo; "
                        "using default paths.")
        log.info("Target path for product.img is %s", productPath)

        # extract anaconda-images from repository, if exists
        tmpRoot = tempfile.mkdtemp(dir=constants.tmpDir)
        util.mkdirChain(os.path.join(tmpRoot, 'usr', 'share', 'anaconda',
                                     'pixmaps'))
        cclient = self.getConaryClient(tmpRoot, arch)
        cclient.setUpdateCallback(self.callback)

        log.info("generating anaconda artwork.")
        autoGenPath = tempfile.mkdtemp(dir=constants.tmpDir)
        ai = AnacondaImages( \
            self.jobData['name'],
            indir = constants.anacondaImagesPath,
            outdir = autoGenPath,
            fontfile = '/usr/share/fonts/bitstream-vera/Vera.ttf')
        ai.processImages()

        uJob = None
        log.info("checking for artwork from anaconda-custom=%s" % cclient.cfg.installLabelPath[0].asString())
        uJob = self._getUpdateJob(cclient, "anaconda-custom")
        if uJob:
            log.info("custom artwork found. applying on top of generated artwork")
            cclient.applyUpdate(uJob, callback = self.callback,
                                replaceFiles = True)
            log.info("success.")

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
        self.changeIsolinuxMenuTitle(topdir)
        self.writeConaryRc(os.path.join(tmpPath, 'conaryrc'), cclient)

        # extract constants.py from the stage2.img template and override the BETANAG flag
        # this would be better if constants.py could load a secondary constants.py
        for path in (stage2, 'images/stage2.img', 'rPath/base/stage2.img'):
            if not path:
                # stage2 is None if .treeinfo was not found
                continue
            fullpath = os.path.join(topdir, path)
            if not os.path.exists(fullpath):
                continue
            betaNag = int(self.getBuildData('betaNag'))
            log.info('Copying constants.py from %s and setting beta nag to %s',
                    path, betaNag)

            stage2Path = tempfile.mkdtemp(dir=constants.tmpDir)
            logCall(['/bin/mount', '-o', 'loop,ro', fullpath, stage2Path])
            out = open(tmpPath + '/constants.py', 'w')
            for line in open(os.path.join(stage2Path
                    + '/usr/lib/anaconda/constants.py')):
                if line.startswith('BETANAG ='):
                    line = 'BETANAG = %d\n' % betaNag
                out.write(line)
            out.close()
            logCall(['/bin/umount', '-d', stage2Path])
            os.rmdir(stage2Path)
            break
        else:
            log.info('Could not find stage2.img; not changing beta nag')

        # create cramfs
        logCall(['/usr/bin/mkcramfs', tmpPath, productPath])

        # clean up
        util.rmtree(tmpPath, ignore_errors = True)
        util.rmtree(tmpRoot, ignore_errors = True)
        util.rmtree(autoGenPath, ignore_errors = True)

    def buildIsos(self, topdir):
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        self.outputDir = outputDir
        util.mkdirChain(outputDir)
        # add the group writeable bit
        os.chmod(outputDir, os.stat(outputDir)[0] & 0777 | 0020)

        isoList = []

        if self.basefilename:
            isoNameTemplate = self.basefilename + '-'
        else:
            isoNameTemplate = "%s-%s-%s-" % \
                (self.jobData['project']['hostname'],
                 upstream(self.baseVersion),
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

            # mkisofs will happily ignore out of space conditions and produce a
            # truncated ISO file, so assume that if there's less than 1MB of
            # free space afterwards that it failed.
            fst = os.statvfs(outputDir)
            if fst.f_bsize * fst.f_bfree < 1000000:
                raise RuntimeError(
                        "Not enough scratch space while running mkisofs")

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
            log.info("adding kickstart arguments")
            cfg = open(os.path.join(topdir, 'isolinux', 'isolinux.cfg'), "r+")
            contents = self.addKsBootLabel(cfg.readlines())
            cfg.seek(0)
            cfg.writelines(contents)
            cfg.close()

    def addKsBootLabel(self, isoLinuxCfg):
        '''
        Input initial isolinux.cfg contents, add new entry
        and make it the default
        '''

        contents = []
        for line in isoLinuxCfg:
            if line.startswith('default'):
                line = 'default kscdrom\n' 
            contents.append(line)
        contents.extend(('label kscdrom\n', '  kernel vmlinuz\n',
                '  append initrd=initrd.img ramdisk_size=8192 ks=cdrom\n'))
        return contents

    def retrieveTemplates(self):
        self.status("Retrieving ISO template")
        log.info("requesting anaconda-templates for " + self.arch)

        tmpDir = tempfile.mkdtemp(dir=constants.tmpDir)
        cclient = self.getConaryClient( \
            tmpDir, getArchFlavor(self.baseFlavor).freeze())

        cclient.cfg.installLabelPath.append(
                versions.Label(constants.templatesLabel))
        uJob = self._getUpdateJob(cclient, 'anaconda-templates')
        if not uJob:
            raise RuntimeError, "Failed to find anaconda-templates"

        kernels = self.findImageSubtrove('kernel')
        kernelTup = kernels and sorted(kernels)[0] or None
        params = {
                'templateTup': self._getNVF(uJob),
                'kernelTup': kernelTup,
                }
        params = base64.urlsafe_b64encode(cPickle.dumps(params, 2))

        url = '%stemplates/getTemplate?p=%s' % (self.cfg.masterUrl, params)
        noStart = False
        path = None
        while True:
            conn = urllib2.urlopen(url)
            response = conn.read()
            conn.close()

            status, path = response.split()[:2]
            if status == 'DONE':
                break
            elif status == 'NOT_FOUND':
                raise RuntimeError("Failed to request templates. "
                        "Check the jobmaster logfile.")

            if not noStart:
                noStart = True
                url += '&nostart=1'
            time.sleep(5)

        templatePath = os.path.join(self.cfg.templateCache, path)
        templateDir = tempfile.mkdtemp('templates-')
        logCall(['/bin/tar', '-xf', templatePath, '-C', templateDir])

        metadata = cPickle.load(open(templatePath + '.metadata', 'rb'))
        ncpv = metadata['netclient_protocol_version']

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

            log.info("extracting ad-hoc content from " \
                  "media-template=%s" % client.cfg.installLabelPath[0].asString())
            uJob = self._getUpdateJob(client, "media-template")
            if uJob:
                client.applyUpdate(uJob, callback = self.callback)
                log.info("success: copying media template data to unified tree")

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
                        util.mkdirChain(destDir)
                        call('cp', '-R', '--no-dereference', srcDir, destDir)
            else:
                log.info("media-template not found on repository")
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
            (self.baseTrove, self.baseVersion, self.baseFlavor),
            cacheDir=constants.cachePath, clientVersion=clientVersion)
        tg.parsePackageData()
        tg.extractChangeSets(csdir, callback=self.callback)

        log.info("done extracting changesets")
        return tg

    def write(self):
        self.callback = Callback(self.status)

        # set up the topdir
        topdir = os.path.join(self.workDir, "unified")
        util.mkdirChain(topdir)

        log.info("Building ISOs of size: %d Mb" % (self.maxIsoSize / 1048576))

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
        splitdistro.splitDistro(topdir, self.baseTrove, self.maxIsoSize)
        outputFileList = self.buildIsos(topdir)

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

            outputFileList.append((self.ovaPath, 'Installable ISO OVF 1.0'))

        # notify client that images are ready
        self.postOutput(outputFileList)
