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


import os

from jobslave.generators import bootable_image, constants
from jobslave.util import logCall

from conary.lib import util, log

class RawFsImage(bootable_image.BootableImage):
    def makeBlankFS(self, image, fsType, size, fsLabel = None):
        if os.path.exists(image):
            util.rmtree(image)
        util.mkdirChain(os.path.split(image)[0])
        logCall('dd if=/dev/zero of=%s count=1 seek=%d bs=4096' % \
                      (image, (size / 4096) - 1))

        fs = bootable_image.Filesystem(image, fsType, size, fsLabel = fsLabel)
        fs.format()
        return fs

    def mntPointFileName(self, mountPoint):
        fsType = self.mountDict[mountPoint].fstype
        tag = mountPoint[mountPoint.startswith('/') and 1 or 0:]
        tag = tag.replace("/", "_")
        tag = tag and tag or "root"
        return os.path.join(self.workDir, self.basefilename, "%s-%s.%s" % (self.basefilename, tag, fsType))

    def makeFSImage(self, sizes):
        root = self.workDir + "/root"
        try:
            # create an image file per mount point
            imgFiles = {}
            for mountPoint, req in self.mountDict.items():
                size = sizes[mountPoint]

                tag = mountPoint.replace("/", "")
                tag = tag and tag or "root"
                imgFiles[mountPoint] = path = self.mntPointFileName(mountPoint)
                log.info("Creating mount point %s at %s with size %d bytes",
                        mountPoint, path, size)
                fs = self.makeBlankFS(path, req.fstype, size, fsLabel=req.name)

                self.addFilesystem(mountPoint, fs)

            self.mountAll()

            # Install image contents.
            self.installFileTree(root)
        finally:
            try:
                self.umountAll()
                util.rmtree(root, ignore_errors = True)
            except:
                log.logger.exception("Error unmounting partitions:")

        return imgFiles

    def write(self):
        sizes = self.getImageSize(realign=0)
        finalImage = os.path.join(self.outputDir, self.basefilename + '.fs.tar.gz')

        images = self.makeFSImage(sizes)
        self.status('Compressing filesystem images')
        self.gzip(self.workingDir, finalImage)

        if self.buildOVF10:
            self.diskFilePath = images['/']
            self.diskFileName = os.path.split(self.diskFilePath)[1]

            self.status('Building OVF 1.0 package')
            diskFileGzipPath = self.gzip(self.diskFilePath, 
                os.path.join(self.outputDir, self.diskFileName + '.gz'))
            util.rmtree(self.workingDir)

            self.ovaPath = self.createOvf(
                    imageName=self.basefilename,
                    imageDescription=self.jobData['description'],
                    diskFormat=constants.RAWFS,
                    diskFilePath=diskFileGzipPath,
                    diskCapacity=sizes['/'],
                    diskCompressed=True,
                    workingDir=self.workDir,
                    outputDir=self.outputDir,
                    )
            self.outputFileList.append((self.ovaPath, 
                'Raw Filesystem %s' % constants.OVFIMAGETAG))

        self.outputFileList.append((finalImage, 'Raw Filesystem Image'))
        self.postOutput(self.outputFileList)
