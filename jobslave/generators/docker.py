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
import datetime
import hashlib
import json
import logging
import os
import shlex
import stat
import tarfile
import tempfile
import sys
import weakref

# jobslave imports
from jobslave import jobstatus
from jobslave.generators import bootable_image, constants
from jobslave.util import logCall

from conary.deps import deps
from conary.lib import util
from conary.trovetup import TroveTuple
from conary.dbstore.sqllib import CaselessDict
from jobslave import buildtypes

log = logging.getLogger(__name__)

class DockerImage(bootable_image.BootableImage):
    fileType = buildtypes.typeNames[buildtypes.DOCKER_IMAGE]
    Repository = 'appeng-test'

    def preInstallScripts(self):
        pass

    def installFilesInExistingTree(self, root, nvf):
        # We need to fork, since rpm doesn't properly set the root in the
        # transaction set object, and subsequent builds will attempt to use
        # previous roots
        pid = os.fork()
        if pid:
            while 1:
                pid, status = os.waitpid(pid, 0)
                if not os.WIFEXITED(status):
                    continue
                if os.WEXITSTATUS(status):
                    raise RuntimeError('Failed to install')
                return
        else:
            self._installFilesInExistingTree(root, nvf)
            os._exit(0)

    def _installFilesInExistingTree(self, root, nvf):
        self.status('Installing image contents')
        self.loadRPM()
        cclient = self._openClient(root)
        cclient.setUpdateCallback(bootable_image.InstallCallback(self.status))
        updJob = cclient.newUpdateJob()
        itemList = [nvf.asJob()]
        cclient.prepareUpdateJob(updJob, itemList)
        cclient.applyUpdateJob(updJob, replaceFiles=True, noRestart=True)

    def write(self):
        self.swapSize = 0
        layersDir = os.path.join(self.workDir, "docker-image/layers")
        util.mkdirChain(layersDir)
        unpackDir = os.path.join(self.workDir, "docker-image/unpacked")
        util.mkdirChain(unpackDir)
        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        imgspec = ImageSpec.deserialize(self.jobData['data']['dockerBuildTree'],
                defaults=dict(repository=self.Repository),
                mainJobData=self.jobData)
        if imgspec.repository is None:
            imgspec.repository = self.Repository
        imgsToBuild = self.findImagesToBuild(imgspec)
        # Base is potentially first; reverse the list so we can use it as a
        # stack
        imgsToBuild.reverse()
        excRaised = None
        while imgsToBuild:
            imgSpec = imgsToBuild.pop()
            if excRaised is not None:
                self.status('Build failed', jobstatus.FAILED,
                    forJobData=imgSpec.jobData)
                continue
            try:
                if imgSpec.parent is None:
                    # Base layer
                    self.writeBase(unpackDir, layersDir, imgSpec)
                else:
                    self.writeChild(unpackDir, layersDir, imgSpec)

                tarball = self._package(outputDir, layersDir, imgSpec)

                self.postOutput(((tarball, 'Tar File'),),
                        attributes={'docker_image_id' : imgSpec.dockerImageId,
                            'installed_size' : imgSpec.computedSize,
                            'manifest' : json.dumps(imgSpec._manifest,
                                sort_keys=True)},
                        forJobData=imgSpec.jobData)
            except:
                excRaised = sys.exc_info()
                self.status('Build failed', jobstatus.FAILED,
                        forJobData=imgSpec.jobData)
            else:
                self.status('Build done', jobstatus.FINISHED,
                        forJobData=imgSpec.jobData)
        if excRaised is not None:
            raise excRaised[0], excRaised[1], excRaised[2]

    def _package(self, outputDir, layersDir, imgSpec):
        reposData = {}
        toArchive = [ 'repositories' ]
        img = imgSpec
        while img:
            toArchive.append(img.dockerImageId)
            for name, tagToId in img.tags.items():
                reposData.setdefault(name, {}).update(tagToId)
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
            stack.extend(reversed(img.children))
            if img.children:
                img.children[-1]._lastChild = True
        return ret

    def isBaseGroup(self, trv):
        for trvtup, byDefault, isStrong in trv.iterTroveListInfo():
            if isStrong and not byDefault and trvtup.name.startswith("group-docker-"):
                return False
        return True

    @classmethod
    def _path(cls, path):
        # Strip out the leading part of a path, since it's not as interesting
        # for debugging
        ret = ['...']
        ret.extend(path.rsplit('/', 2)[-2:])
        return '/'.join(ret)

    @classmethod
    def mountOverlayFs(cls, unpackDir, thisLayerId, prevMount):
        thisLayerDir = os.path.join(unpackDir, thisLayerId)
        ovlfsDir = thisLayerDir + '.ovffs'
        ovlWorkDir = thisLayerDir + '.work'
        util.mkdirChain(ovlfsDir)
        util.mkdirChain(ovlWorkDir)

        log.debug("Mounting layer %s on top of %s", thisLayerId,
                cls._path(prevMount))
        logCall(["mount", "-t", "overlay", os.path.basename(ovlfsDir),
            ovlfsDir, "-olowerdir={0},upperdir={1},workdir={2}".format(
                prevMount, thisLayerDir, ovlWorkDir)])
        return ovlfsDir

    def writeBase(self, unpackDir, layersDir, imgSpec):
        # Copied from tarfile
        dockerImageId = imgSpec.dockerImageId = self.getImageId(imgSpec.nvf)
        log.debug("Building base image %s, layer %s", imgSpec.name,
                dockerImageId)
        basePath = os.path.join(unpackDir, dockerImageId)
        util.mkdirChain(basePath)
        self.installFilesInExistingTree(basePath, imgSpec.nvf)
        self.writeLayer(basePath, layersDir, imgSpec)
        imgSpec._unpackDir = basePath
        return imgSpec

    def writeChild(self, unpackDir, layersDir, imgSpec):
        if imgSpec.parent.url:
            pImageId = imgSpec.parent.dockerImageId
            parentLayerDir = os.path.join(layersDir, pImageId)
            if not os.path.exists(parentLayerDir):
                # First child image in this hierarchy to be built
                self._downloadParentImage(imgSpec.parent, unpackDir, layersDir)
            else:
                imgSpec.parent._unpackDir = os.path.join(unpackDir, pImageId)
                assert os.path.isdir(imgSpec.parent._unpackDir)
                self._setLayerSize(imgSpec.parent, layersDir)
        # At this point, the parent layer should be on the filesystem, and
        # should have been unpacked

        dockerImageId = imgSpec.dockerImageId = self.getImageId(imgSpec.nvf)
        log.debug("Building child image %s, layer %s", imgSpec.name,
                imgSpec.dockerImageId)

        thisLayerContent = os.path.join(unpackDir, dockerImageId)
        util.mkdirChain(thisLayerContent)

        imgHierarchy = [imgSpec]
        img = imgSpec.parent
        while img:
            imgHierarchy.append(img)
            if img._unpackDir is not None:
                break
            img = img.parent
        mountResources = []
        # The base doesn't need to be unioned
        prevMount = imgHierarchy.pop()._unpackDir
        while imgHierarchy:
            thisLayer = imgHierarchy.pop()
            thisLayerId = thisLayer.dockerImageId
            if thisLayerId != imgSpec.dockerImageId:
                # Itermediate image
                layerFile = os.path.join(layersDir, thisLayerId, 'layer.tar')
                if thisLayer._lastChild:
                    # Uncompress this image onto the parent
                    log.debug("Extracting layer %s on %s", thisLayerId,
                            self._path(prevMount))
                    self._extractLayer(prevMount, layerFile)
                    thisLayer._unpackDir = prevMount
                    continue
                # Did we already set up an overlay?
                if mountResources:
                    # Uncompress this layer on top of the overlay
                    prevMount = mountResources[0]
                    log.debug("Extracting layer %s on %s", thisLayerId,
                            self._path(prevMount))
                    self._extractLayer(prevMount, layerFile)
                    continue
            # If no other overlay was set up, or it's the current image, set
            # one up
            ovlfsDir = self.mountOverlayFs(unpackDir, thisLayerId, prevMount)
            mountResources.append(ovlfsDir)
            prevMount = ovlfsDir

        basePath = mountResources[-1]
        log.debug("Installing %s into %s", imgSpec.nvf.asString(),
                self._path(basePath))
        self.installFilesInExistingTree(basePath, imgSpec.nvf)

        while mountResources:
            ovldir = mountResources.pop()
            logCall(["umount", "-f", ovldir])

        thisLayerDir = os.path.join(unpackDir, imgSpec.dockerImageId)
        self.writeLayer(thisLayerDir, layersDir, imgSpec, withDeletions=True)

    def _setLayerSize(self, imgSpec, layersDir):
        img = imgSpec
        while img:
            if img.layerSize is not None:
                break
            layerTarFile = os.path.join(layersDir, img.dockerImageId, "layer.tar")
            img.layerSize = os.stat(layerTarFile).st_size
            img = img.parent

    def _downloadParentImage(self, imgSpec, unpackDir, layersDir):
        log.debug('Downloading parent image %s', imgSpec.dockerImageId)
        self.status('Downloading parent image')
        resp = self.response.getImage(imgSpec.url)
        tmpf = tempfile.TemporaryFile(dir=self.workDir)
        util.copyfileobj(resp, tmpf)
        tmpf.seek(0)

        self.status('Unpacking parent image')
        errcode, stdout, stderr = logCall(["tar", "-C", layersDir,
                "-zxf", "-"], stdin=tmpf)
        tmpf.close()
        parentImageDir = os.path.join(unpackDir,
                imgSpec.dockerImageId)

        log.debug('Unpacking parent image as %s', self._path(parentImageDir))
        layerFilesStack = []
        # Unpack the layers in some temporary directories
        layer = imgSpec
        while layer is not None:
            layerId = layer.dockerImageId
            layer._unpackDir = parentImageDir
            layerFilesStack.append(
                    (layerId, os.path.join(layersDir, layerId, "layer.tar")))
            layer.layerSize = os.stat(layerFilesStack[-1][1]).st_size
            layer._manifest = mf = Manifest(json.load(file(os.path.join(layersDir, layerId, 'json'))))
            mf = json.load(file(os.path.join(layersDir, layerId, 'json')))
            parent = mf.get('parent')
            if parent is not None and not layer.parent:
                layer.parent = ImageSpec(dockerImageId=parent)
                layer.parent.children.append(layer)
            layer = layer.parent
        # We now extract all layers, top-to-bottom, in the same directory.
        while layerFilesStack:
            layerId, layerFile = layerFilesStack.pop()
            log.debug("  Extracting parent layer %s on %s", layerId,
                    self._path(parentImageDir))
            self._extractLayer(parentImageDir, layerFile)
        idToNameTags = {}
        reposFile = os.path.join(layersDir, 'repositories')
        if os.path.isfile(reposFile):
            repos = json.load(file(reposFile))
            for name, tagToId in repos.iteritems():
                for tag, imgid in tagToId.iteritems():
                    idToNameTags.setdefault(imgid, set()).add((name, tag))
        # Walk list again, to compute tags
        layer = imgSpec
        while layer is not None:
            layerId = layer.dockerImageId
            layer.updateNamesAndTags(idToNameTags.get(layerId))
            layer = layer.parent

    def _extractLayer(self, unpackDir, tarFile):
        util.mkdirChain(unpackDir)
        # Walk the files in the tar file, looking for .wh.*
        tf = tarfile.open(tarFile)
        toDeleteAfter = set()
        for tinfo in tf:
            bname = os.path.basename(tinfo.name)
            if bname.startswith('.wh.') and tinfo.mode == 0:
                util.rmtree(util.joinPaths(unpackDir,
                    os.path.dirname(tinfo.name), bname[4:]),
                        ignore_errors=True)
                toDeleteAfter.add(util.joinPaths(unpackDir, tinfo.name))
        logCall(["tar", "-C", unpackDir, "-xf", tarFile])
        for fname in toDeleteAfter:
            util.removeIfExists(fname)

    def writeLayer(self, basePath, layersDir, imgSpec, withDeletions=False):
        layerId = imgSpec.dockerImageId
        if imgSpec.parent:
            parentLayerId = imgSpec.parent.dockerImageId
        else:
            parentLayerId = None
        layerDir = os.path.join(layersDir, layerId)
        util.mkdirChain(layerDir)
        tarball = os.path.join(layerDir, 'layer.tar')
        self.status('Creating layer')
        if withDeletions:
            ovlfs2docker(basePath)
        logCall('tar -C %s -cpPsf %s .' % (basePath, tarball))
        if withDeletions:
            docker2ovlfs(basePath)
        file(os.path.join(layerDir, "VERSION"), "w").write("1.0")
        # XXX for some reason the layer sizes reported by docker are smaller
        # than the tar file
        st = os.stat(tarball)
        imgSpec.layerSize = layerSize = st.st_size
        layerCtime = datetime.datetime.utcfromtimestamp(st.st_ctime).isoformat() + 'Z'
        if imgSpec.nvf.flavor.satisfies(deps.parseFlavor('is: x86_64')):
            arch = 'amd64'
        else:
            arch = '386'
        config = Manifest(
                Env=[ "PATH=/usr/sbin:/usr/bin:/sbin:/bin" ]
                )

        self.status('Creating manifest')
        manifest = imgSpec._manifest = Manifest(id=layerId, Size=layerSize,
                Comment="Created by Conary command: conary update '%s'" % imgSpec.nvf.asString(),
                created=layerCtime,
                config=config,
                os='linux',
                docker_version='1.3.2',
                checksum=TarSum.checksum(tarball, formatted=True),
                Architecture=arch,
                comment="Created by the SAS App Engine",
                container_config=dict(),
                )
        if parentLayerId:
            manifest['parent'] = parentLayerId
        if imgSpec._parsedDockerfile:
            imgSpec._parsedDockerfile.toManifest(manifest)
        if imgSpec.parent:
            manifest.merge(imgSpec.parent._manifest)
        mfile = file(os.path.join(layerDir, "json"), "w")
        manifest.save(mfile)
        return layerId

    def getImageId(self, nvf):
        ctx = hashlib.sha256()
        ctx.update("Version: 0.1\n\n")
        ctx.update(nvf.asString())
        return ctx.hexdigest()

class Manifest(CaselessDict):
    def __init__(self, *args, **kwargs):
        CaselessDict.__init__(self, *args)
        self.update(kwargs)
        if 'config' in self:
            self['config'] = self.__class__(self.get('config', {}))

    def save(self, stream):
        json.dump(self, stream, sort_keys=True)

    @property
    def author(self):
        return self.get('author')

    @property
    def entrypoint(self):
        return self.get('config', {}).get('Entrypoint')

    @property
    def cmd(self):
        return self.get('config', {}).get('Cmd')

    @property
    def exposedPorts(self):
        return self.get('config', {}).get('ExposedPorts')

    def merge(self, other):
        """
        Merge this manifest with a parent. The parent will not be changed.
        """
        if other is None:
            return self
        assert isinstance(other, Manifest)
        # When merging a parent layer with a child layer, we only copy the
        # exposed ports
        thisConfig = self.get('config', self.__class__())
        otherConfig  = other.get('config', {})

        thisPorts = thisConfig.setdefault('ExposedPorts', {})
        otherPorts = dict(otherConfig.get('ExposedPorts', {}))
        for k, v in otherPorts.items():
            thisPorts.setdefault(k, v)

        envs = dict(x.split('=', 1) for x in otherConfig.get('Env', []))
        envs.update(dict(x.split('=', 1) for x in thisConfig.get('Env', [])))
        envs = ["%s=%s" % (x, v) for x, v in envs.items() ]
        thisConfig['Env'] = sorted(envs)

        if other.entrypoint is None:
            entrypoint = self.entrypoint
            if entrypoint:
                cmd = self.cmd
            else:
                cmd = self.cmd or other.cmd
        else:
            # The parent image has defined an entrypoint. If different from the
            # child entrypoint, then invalidate otherCmd
            if self.entrypoint is not None and (self.entrypoint != other.entrypoint):
                cmd = None
                entrypoint = self.entrypoint
            else:
                entrypoint = self.entrypoint or other.entrypoint
                cmd = list(other.cmd or [])
                cmd.extend(self.cmd or [])
        if entrypoint is not None:
            thisConfig['Entrypoint'] = entrypoint
        if cmd:
            thisConfig['Cmd'] = cmd
        return self

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
            'parent', 'repository', 'dockerfile', '_parsedDockerfile',
            'layerSize',
            '_manifest', '_unpackDir', '_lastChild',
            '_nameToTags', '__weakref__', ]
    def __init__(self, **kwargs):
        kwargs.setdefault('_nameToTags', set())
        kwargs.setdefault('children', [])
        for slot in self.__slots__:
            if slot.startswith('__'):
                continue
            setattr(self, slot, kwargs.get(slot, None))

    @classmethod
    def deserialize(cls, dictobj, defaults=None, mainJobData=None, **extraArgs):
        if isinstance(dictobj, basestring):
            params = json.loads(dictobj)
        else:
            params = dict(dictobj)
        if params.get('buildData') is None:
            assert mainJobData is not None
            # This is the top-level build. Insert jobData
            params['buildData'] = mainJobData
        params.update(extraArgs)
        if defaults is None:
            defaults = {}
        # Do not overwrite params with defaults
        for k, v in defaults.iteritems():
            params.setdefault(k, v)
        nvf = params.pop('nvf', None)
        if nvf is not None:
            params['nvf'] = TroveTuple(str(nvf))
        buildData = params.pop('buildData')
        if buildData is not None:
            params['jobData'] = buildData
            params['name'] = buildData['name']
            dockerfile = buildData.get('data', {}).get('dockerfile')
            if dockerfile is not None:
                params['dockerfile'] = dockerfile
                params['_parsedDockerfile'] = D = Dockerfile().parse(dockerfile)
                params['_manifest'] = D.toManifest()
            repository = buildData.get('data', {}).get('dockerRepositoryName',
                    defaults.get('repository'))
            if repository is not None:
                params['repository'] = repository
        children = params.pop('children', None) or []
        obj = cls(**params)
        wobj = weakref.proxy(obj)
        childArgs = dict(defaults=defaults, parent=wobj)
        if obj.url:
            # Need to pass down the main job data
            assert mainJobData is not None
            childArgs.update(mainJobData=mainJobData)
        obj.children = [ cls.deserialize(x, **childArgs) for x in children ]
        return obj

    @property
    def tags(self):
        if self.repository and self.nvf:
            self._nameToTags.add((self.fullName, self.tag))
        ret = {}
        for name, tag in self._nameToTags:
            ret.setdefault(name, {})[tag] = self.dockerImageId
        return ret

    @property
    def fullName(self):
        return "%s/%s" % (self.repository, self.layerName)

    @property
    def layerName(self):
        return self.nvf.name[6:]

    @property
    def tag(self):
        return str(self.nvf.version.trailingRevision())

    def updateNamesAndTags(self, namesToTags):
        self._nameToTags.update(namesToTags or [])

    @property
    def computedSize(self):
        size = self.layerSize
        if self.parent:
            size += self.parent.computedSize
        return size

class QuotedString(str):
    pass

class QuotedList(list):
    pass

class DockerfileParseError(Exception):
    pass

class Dockerfile(object):
    ListArgCommands = ['CMD', 'ENTRYPOINT']
    MultiCommands = ['EXPOSE', ]
    DictCommands = [ 'ENV' ]
    def __init__(self):
        self._directives = {}

    def parse(self, stream):
        if isinstance(stream, unicode):
            stream = stream.encode('utf-8')
        # Convert stream to StringIO if necessary
        stream = shlex.shlex(stream).instream
        # Create lexer, no data by default
        lex = shlex.shlex("", posix=True)
        lex.wordchars += "!$%&()*+-./:x<=>?@:"
        lex.whitespace_split = False
        lex.quotes = '"'

        # Feed one line at the time
        lines = []
        prevline = []
        for raw in stream:
            lex.instream = shlex.StringIO(raw)
            lex.state = ' '
            newline = list(lex)
            withContinuation = (newline[-1] == '\n') if newline else False
            if withContinuation:
                newline.pop()
            if prevline:
                prevline.extend(newline)
                if not withContinuation:
                    prevline = []
                continue
            if withContinuation:
                prevline = newline
            lines.append(newline)
        # Filter out empty lines
        for line in lines:
            if not line:
                continue
            self.parseLine(line)
        return self

    def parseLine(self, line):
        instr, rest = line[0], line[1:]
        instr = instr.upper()
        if rest[0] == '[':
            if rest[-1] != ']':
                raise DockerfileParseError("Error parsing: matching ']' missing")
            rest = rest[1:-1]
            if rest and rest[-1] == ',':
                rest.pop()
            if rest and rest[0] == ',':
                raise DockerfileParseError("Error parsing: leading , in list")
            rest.reverse()
            commaFound = False
            listArgs = QuotedList()
            while rest:
                obj = rest.pop()
                if obj == ',':
                    if commaFound:
                        raise DockerfileParseError("Error parsing: consecutive ,")
                    commaFound = True
                    continue
                if listArgs and not commaFound:
                    raise DockerfileParseError("Error parsing: missing ,")
                commaFound = False
                listArgs.append(obj)
            rest = listArgs
        if instr in self.MultiCommands:
            self._directives.setdefault(instr, []).extend(rest)
        elif instr in self.DictCommands:
            self._directives.setdefault(instr, {}).update(self._parseKV(rest))
        elif instr in self.ListArgCommands:
            if not isinstance(rest, QuotedList):
                rest = " ".join(rest)
            self._directives[instr] = rest
        else:
            self._directives[instr] = " ".join(rest)

    @classmethod
    def _parseKV(cls, values):
        kvdict = {}
        values.reverse()
        while values:
            kv = values.pop()
            k, sep, v = kv.partition('=')
            if sep != '=':
                # Not a "k v"
                if not values:
                    raise DockerfileParseError("Error parsing: expected 'k v'")
                v = values.pop()
            kvdict[k] = v
        return kvdict

    @property
    def environment(self):
        instructions = self._directives.get('ENV', {})
        return [ "%s=%s" % (x, y)
                    for (x, y) in sorted(instructions.items()) ]

    @property
    def exposedPorts(self):
        ret = set()
        vals = self._directives.get('EXPOSE')
        if not vals:
            return ret
        for val in vals:
            if '/' not in val:
                val += '/tcp'
            ret.add(val)
        return sorted(ret)

    @property
    def entrypoint(self):
        return self._getCommand('ENTRYPOINT')

    @property
    def cmd(self):
        return self._getCommand('CMD')

    @property
    def author(self):
        param = self._directives.get('MAINTAINER')
        if param is None:
            return None
        return param

    def _getCommand(self, cmdName):
        params = self._directives.get(cmdName)
        if params is None:
            return None
        if isinstance(params, QuotedList):
            return params
        if isinstance(params, basestring):
            return ['/bin/sh', '-c', params]
        return params

    def toManifest(self, manifest=None):
        if manifest is None:
            manifest = Manifest()
        config = manifest.setdefault('config', Manifest())
        exposedPorts = self.exposedPorts
        if exposedPorts:
            config['ExposedPorts'] = dict((x, {}) for x in exposedPorts)
        entrypoint = self.entrypoint
        if entrypoint:
            config['Entrypoint'] = entrypoint
        cmd = self.cmd
        if cmd:
            config['Cmd'] = cmd
        author = self.author
        if author:
            manifest['author'] = author
        environment = self.environment
        if environment:
            config['Env'] = environment
        return manifest

def docker2ovlfs(dirName):
    for dirPath, dirNames, fileNames in os.walk(dirName):
        for fileName in fileNames:
            if fileName.startswith('.wh.'):
                fPath = os.path.join(dirPath, fileName)
                newName = os.path.join(dirPath, fileName[4:])
                os.unlink(fPath)
                os.mknod(newName, stat.S_IFCHR, os.makedev(0, 0))

def ovlfs2docker(dirName):
    for dirPath, dirNames, fileNames in os.walk(dirName):
        for fileName in fileNames:
            fPath = os.path.join(dirPath, fileName)
            st = os.lstat(fPath)
            if stat.S_ISCHR(st.st_mode) and st.st_rdev == 0:
                newName = os.path.join(dirPath, '.wh.' + fileName)
                log.debug("Renaming %s to %s", fPath, newName)
                os.unlink(fPath)
                fd = os.open(newName, os.O_CREAT | os.O_WRONLY, 0)
                os.close(fd)
