#
# Copyright (c) SAS Institute Inc.
#

# python standard library imports
import datetime
import hashlib
import json
import logging
import os
import tarfile
import tempfile
import weakref

# jobslave imports
from jobslave import jobstatus
from jobslave.generators import bootable_image, constants
from jobslave.util import logCall

from conary.deps import deps
from conary.lib import util
from conary.lib.http import opener
from conary.trovetup import TroveTuple
from jobslave import buildtypes

log = logging.getLogger(__name__)

class DockerImage(bootable_image.BootableImage):
    fileType = buildtypes.typeNames[buildtypes.DOCKER_IMAGE]
    Repository = 'appeng-test'

    def preInstallScripts(self):
        pass

    def installFilesInExistingTree(self, root, nvf):
        self.status('Installing image contents')
        self.loadRPM()
        cclient = self._openClient(root)
        cclient.setUpdateCallback(bootable_image.InstallCallback(self.status))
        updJob = cclient.newUpdateJob()
        itemList = [nvf.asJob()]
        cclient.prepareUpdateJob(updJob, itemList)
        cclient.applyUpdateJob(updJob, replaceFiles=True, noRestart=True)

    def write(self):
        layersDir = os.path.join(self.workDir, "docker-image/layers")
        util.mkdirChain(layersDir)
        unpackDir = os.path.join(self.workDir, "docker-image/unpacked")
        util.mkdirChain(unpackDir)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        #from conary.lib import epdb; epdb.st()
        imgspec = ImageSpec.deserialize(self.jobData['data']['dockerBuildTree'],
                mainJobData=self.jobData)
        # XXX This should come from the proddef, probably
        imgspec.repository = self.Repository
        imgsToBuild = self.findImagesToBuild(imgspec)
        # Base is potentially first; reverse the list so we can use it as a
        # stack
        imgsToBuild.reverse()
        while imgsToBuild:
            imgSpec = imgsToBuild.pop()
            if imgSpec.parent is None:
                # Base layer
                self.writeBase(unpackDir, layersDir, imgSpec)
            else:
                self.writeChild(unpackDir, layersDir, imgSpec)
            imgsToBuild.extend(imgSpec.children)

            tarball = self._package(outputDir, layersDir, imgSpec)

            self.postOutput(((tarball, 'Tar File'),),
                    attributes={'docker_image_id' : imgSpec.dockerImageId},
                    forJobData=imgSpec.jobData)
            self.status('Build done', jobstatus.FINISHED,
                    forJobData=imgSpec.jobData)

    def _package(self, outputDir, layersDir, imgSpec):
        reposData = {}
        toArchive = [ 'repositories' ]
        img = imgSpec
        while img:
            toArchive.append(img.dockerImageId)
            reposData[img.fullName] = { img.tag : img.dockerImageId }
            img = img.parent

        json.dump(reposData, file(os.path.join(layersDir, 'repositories'), "w"))
        self.status('Packaging layers')
        tarball = os.path.join(outputDir, self.sanitizeBaseFileName(imgSpec.name + '.tar.gz'))
        logCall('tar -C %s -cpPsS --to-stdout %s | gzip > %s' %
                (layersDir, ' '.join(toArchive), tarball))
        return tarball

    def findImagesToBuild(self, imgSpec):
        stack = [imgSpec]
        ret = []
        while stack:
            img = stack.pop()
            if img.url is None:
                # We need to build this (and all its children)
                ret.append(img)
                continue
            stack.extend(img.children)
        return ret

    def isBaseGroup(self, trv):
        for trvtup, byDefault, isStrong in trv.iterTroveListInfo():
            if isStrong and not byDefault and trvtup.name.startswith("group-docker-"):
                return False
        return True

    def writeBase(self, unpackDir, layersDir, imgSpec):
        # Copied from tarfile
        dockerImageId = imgSpec.dockerImageId = self.getImageId(imgSpec.nvf)
        basePath = os.path.join(unpackDir, dockerImageId)
        util.mkdirChain(basePath)
        self.installFilesInExistingTree(basePath, imgSpec.nvf)
        self.writeLayer(basePath, layersDir, imgSpec)
        return imgSpec

    def writeChild(self, unpackDir, layersDir, imgSpec):
        if imgSpec.parent.url:
            parentLayerDir = os.path.join(layersDir, imgSpec.parent.dockerImageId)
            if not os.path.exists(parentLayerDir):
                # First child image in this hierarchy to be built
                self._downloadParentImage(imgSpec.parent, unpackDir, layersDir)
        # At this point, the parent layer should be on the filesystem

        dockerImageId = imgSpec.dockerImageId = self.getImageId(imgSpec.nvf)

        thisLayerContent = os.path.join(unpackDir, dockerImageId)
        util.mkdirChain(thisLayerContent)

        imgHierarchy = [dockerImageId]
        img = imgSpec.parent
        while img:
            imgHierarchy.append(img.dockerImageId)
            img = img.parent
        # Mount overlay dirs
        mountResources = []
        # The base doesn't need to be unioned
        prevMount = os.path.join(unpackDir, imgHierarchy.pop())
        while imgHierarchy:
            thisLayerId = imgHierarchy.pop()
            thisLayerDir = os.path.join(unpackDir, thisLayerId)
            ovlfsDir = thisLayerDir + '.ovffs'
            ovlWorkDir = thisLayerDir + '.work'
            util.mkdirChain(ovlfsDir)
            util.mkdirChain(ovlWorkDir)

            logCall(["mount", "-t", "overlay", os.path.basename(ovlfsDir),
                ovlfsDir, "-olowerdir={0},upperdir={1},workdir={2}".format(
                    prevMount, thisLayerDir, ovlWorkDir)])

            mountResources.append(ovlfsDir)

        basePath = mountResources[-1]
        self.installFilesInExistingTree(basePath, imgSpec.nvf)

        while mountResources:
            ovldir = mountResources.pop()
            logCall(["umount", "-f", ovldir])

        self.writeLayer(basePath, layersDir, imgSpec)

    def _downloadParentImage(self, imgSpec, unpackDir, layersDir):
        self.status('Downloading parent image')
        conaryProxyHost = util.urlSplit(self.cfg.conaryProxy)[3]
        urlPieces = list(util.urlSplit(imgSpec.url))
        urlPieces[3] = conaryProxyHost
        url = util.urlUnsplit(urlPieces)
        op = URLOpener(connectAttempts=2)
        resp = op.open(url)
        tmpf = tempfile.TemporaryFile(dir=self.workDir)
        util.copyfileobj(resp, tmpf)
        tmpf.seek(0)

        self.status('Unpacking parent image')
        errcode, stdout, stderr = logCall(["tar", "-C", layersDir,
                "-zxf", "-"], stdin=tmpf)
        tmpf.close()
        # Unpack the layers in some temporary directories
        layer = imgSpec
        while layer is not None:
            layerId = layer.dockerImageId
            dest = os.path.join(unpackDir, layerId)
            util.mkdirChain(dest)
            logCall(["tar", "-C", dest, "-xf",
                os.path.join(layersDir, layerId, "layer.tar")])
            layer = layer.parent

    def writeLayer(self, basePath, layersDir, imgSpec):
        layerId = imgSpec.dockerImageId
        if imgSpec.parent:
            parentLayerId = imgSpec.parent.dockerImageId
        else:
            parentLayerId = None
        layerDir = os.path.join(layersDir, layerId)
        util.mkdirChain(layerDir)
        tarball = os.path.join(layerDir, 'layer.tar')
        self.status('Creating layer')
        logCall('tar -C %s -cpPsf %s .' % (basePath, tarball))
        file(os.path.join(layerDir, "VERSION"), "w").write("1.0")
        # XXX for some reason the layer sizes reported by docker are smaller
        # than the tar file
        st = os.stat(tarball)
        layerSize = st.st_size
        layerCtime = datetime.datetime.utcfromtimestamp(st.st_ctime).isoformat() + 'Z'
        if imgSpec.nvf.flavor.satisfies(deps.parseFlavor('is: x86_64')):
            arch = 'amd64'
        else:
            arch = '386'
        config = dict(
                Cmd=["conary", "update", imgSpec.nvf.asString()],
                )

        self.status('Creating manifest')
        manifest = Manifest(id=layerId, Size=layerSize,
                created=layerCtime,
                Config=config,
                os='linux',
                docker_version='1.3.2',
                checksum=TarSum.checksum(tarball, formatted=True),
                Architecture=arch,
                comment="Created by the SAS App Engine",
                container_config=dict(Cmd=config['Cmd'],)
                )
        if parentLayerId:
            manifest.update(parent=parentLayerId)
        mfile = file(os.path.join(layerDir, "json"), "w")
        manifest.save(mfile)
        return layerId

    def getImageId(self, nvf):
        ctx = hashlib.sha256()
        ctx.update("Version: 0.1\n\n")
        ctx.update(nvf.asString())
        return ctx.hexdigest()

class Manifest(dict):
    def save(self, stream):
        json.dump(self, stream, sort_keys=True)

class URLOpener(opener.URLOpener):
    def _handleError(self, req, response):
        if response.status != 301:
            return opener.URLOpener._handleError(self, req, response)
        newUrl = response.getheader('Location')
        return self.open(newUrl)

class TarSum(object):
    Version = "v1"
    Template = '%s%s'
    Fields = [
            'name', 'mode', 'uid', 'gid', 'size', 'typeflag', 'linkname',
            'uname', 'gname', 'devmajor', 'devminor',
            ]
    FieldsMap = dict(typeflag='type')

    @classmethod
    def checksum(cls, tarFile, formatted=False):
        if isinstance(tarFile, basestring):
            tarFile = file(tarFile, "rb")
        tf = tarfile.open(fileobj=tarFile)
        checksums = []
        for entry in tf:
            ctx = hashlib.sha256()
            for f in cls.Fields:
                val = getattr(entry, cls.FieldsMap.get(f, f))
                if f == 'name' and entry.isdir() and not val.endswith('/'):
                    val += '/'
                ctx.update(cls.Template % (f, val))
            if entry.size > 0:
                src = tf.extractfile(entry)
                while 1:
                    buf = src.read(16384)
                    if not buf:
                        break
                    ctx.update(buf)
            checksums.append(ctx.hexdigest())
        checksums.sort()
        ctx = hashlib.sha256()
        for csum in checksums:
            ctx.update(csum)
        csum = ctx.hexdigest()
        if formatted:
            csum = "tarsum.{0}+sha256:{1}".format(cls.Version, csum)
        return csum

class ImageSpec(object):
    __slots__ = [ 'name', 'nvf', 'url', 'dockerImageId', 'jobData', 'children',
            'parent', 'repository', '__weakref__', ]
    def __init__(self, **kwargs):
        for slot in self.__slots__:
            if slot.startswith('__'):
                continue
            setattr(self, slot, kwargs.get(slot, None))

    @classmethod
    def deserialize(cls, dictobj, **extraArgs):
        if isinstance(dictobj, basestring):
            params = json.loads(dictobj)
        else:
            params = dict(dictobj)
        mainJobData = extraArgs.pop('mainJobData', None)
        if params.get('url') is None and extraArgs.get('parent') is None:
            assert mainJobData is not None
            # This is the top-level build. Insert jobData
            params['buildData'] = mainJobData
        params.update(extraArgs)
        nvf = params.pop('nvf', None)
        if nvf is not None:
            params['nvf'] = TroveTuple(str(nvf))
        buildData = params.pop('buildData')
        params['jobData'] = buildData
        params['name'] = buildData['name']
        children = params.pop('children', None) or []
        obj = cls(**params)
        wobj = weakref.proxy(obj)
        obj.children = [ cls.deserialize(x, parent=wobj) for x in children ]
        return obj

    @property
    def fullName(self):
        return "%s/%s" % (self.repository, self.layerName)

    @property
    def layerName(self):
        return self.nvf.name[6:]

    @property
    def tag(self):
        return str(self.nvf.version.trailingRevision())
