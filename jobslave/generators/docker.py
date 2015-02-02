#
# Copyright (c) SAS Institute Inc.
#

# python standard library imports
import io
import logging
import os
import tempfile

# jobslave imports
from jobslave.generators import bootable_image, constants
from jobslave.util import logCall, CommandError

from conary.lib import util
from conary.lib.http import opener
from jobslave import buildtypes
from jobslave import imagegen

log = logging.getLogger(__name__)


class DockerImage(bootable_image.BootableImage):
    fileType = buildtypes.typeNames[buildtypes.DOCKER_IMAGE]

    def write(self):
        self.status('Creating tarball')
        cclient = self._openClient(self.tempRoot)

        trvtup = cclient.repos.findTrove(None, (self.baseTrove,
            self.baseVersion, self.baseFlavor))[0]
        trv = cclient.repos.getTrove(*trvtup)

        imageName = "test/%s:%s" % (self.baseTrove[6:],
            self.baseVersion.trailingRevision())

        outputDir = os.path.join(constants.finishedDir, self.UUID)
        util.mkdirChain(outputDir)
        tarball = os.path.join(outputDir, self.basefilename + '.tar')
        try:
            if self.isBaseGroup(trv):
                imgId = self.writeBaseGroup(outputDir, imageName)
            else:
                imgId = self.writeChildGroup(outputDir, imageName)
            self.status('Saving image from docker')
            try:
                self.runDockerCommand("save", "-o", tarball, imgId)
            finally:
                try:
                    self.runDockerCommand("rmi", imgId)
                except CommandError, e:
                    # XXX
                    pass

            self.status('Compressing image')
            logCall(["gzip", tarball])
            tarball += '.gz'

            self.postOutput(((tarball, 'Tar File'),),
                    attributes={'dockerImageId' : imgId})
        finally:
            pass

    def isBaseGroup(self, trv):
        for trvtup, byDefault, isStrong in trv.iterTroveListInfo():
            if isStrong and not byDefault and trvtup.name.startswith("group-docker-"):
                return False
        return True

    def writeBaseGroup(self, outputDir, imageName):
        # Copied from tarfile
        self.swapSize = 0
        basePath = os.path.join(self.workDir, self.basefilename)
        util.mkdirChain(basePath)
        tarball = os.path.join(outputDir, self.basefilename + '.tar')
        self.installFileTree(basePath, no_mbr=True)

        self.status('Creating tarball')
        logCall('tar -C %s -cpPsf %s .' % (basePath, tarball))

        self.status('Importing tarball into docker')
        errcode, stdout, stderr = self.runDockerCommand("import", "-",
                imageName, stdin=file(tarball))
        if errcode != 0:
            log.error("Error importing into docker: %s", stderr)
            raise Exception(stderr)
        return stdout.strip()

        self.status('Saving image from docker')
        try:
            self.runDockerCommand("save", "-o", tarball, imgId)
        finally:
            self.runDockerCommand("rmi", imgId)

        self.status('Compressing image')
        logCall(["gzip", tarball])
        tarball += '.gz'

        self.postOutput(((tarball, 'Tar File'),),
                attributes={'installed_size': installedSize,
                    'dockerImageId' : imgId})

    def writeChildGroup(self, outputDir, imageName):
        conaryProxyHost = util.urlSplit(self.cfg.conaryProxy)[3]
        self.status('Downloading parent image')
        url = "http://[%s]/downloadImage?fileId=31" % util.urlSplit(self.cfg.conaryProxy)[3]
        parentImageId = '397031ff5fcdf04874d02a1c4c3e5e89dc1283173125de075dc400335c75f746'
        op = URLOpener(connectAttempts=2)
        resp = op.open(url)
        tmpf = tempfile.TemporaryFile(dir=outputDir)
        util.copyfileobj(resp, tmpf)
        tmpf.seek(0)

        self.status('Importing parent image')
        errcode, stdout, stderr = self.runDockerCommand("load",
                stdin=tmpf)
        tmpf.close()
        dockerFileTmpl = """\
FROM {imageId}
RUN ["conary", "--config", "proxyMap []", "--config", "proxyMap * conarys://[{host}]", "update", "{group}"]
"""
        self.status('Building new image')
        dockerContext = os.path.join(self.workDir, "docker-context")
        util.mkdirChain(dockerContext)
        dockerFileContents = dockerFileTmpl.format(
            imageId=parentImageId, host='miiban-rce-feldspar.na.sas.com',
            group="%s=%s[%s]" % (self.baseTrove, self.baseVersion, self.baseFlavor))
        dockerFilePath = os.path.join(dockerContext, "Dockerfile")
        file(dockerFilePath, "w").write(dockerFileContents)
        errcode, stdout, stderr = self.runDockerCommand("build",
            "--rm=true", "-t", imageName, dockerContext)
        imageId = self._idFromOutput(stdout)
        if errcode != 0 or not imageId:
            raise Exception(stderr)
        return imageId

    @classmethod
    def _idFromOutput(cls, stderr):
        prefix = "Successfully built "
        stream = io.StringIO(stderr)
        for line in stream:
            line = line.strip()
            if not line.startswith(prefix):
                continue
            return line[len(prefix):].strip()
        return None

    def runDockerCommand(self, *args, **kwargs):
        cmd = ['/usr/bin/docker', ]
        cmd.extend(args)
        return logCall(cmd,
                env=dict(DOCKER_HOST="unix:///tmp/.docker/docker.sock"),
                **kwargs)

class URLOpener(opener.URLOpener):
    def _handleError(self, req, response):
        if response.status != 301:
            return opener.URLOpener._handleError(self, req, response)
        newUrl = response.getheader('Location')
        return self.open(newUrl)
