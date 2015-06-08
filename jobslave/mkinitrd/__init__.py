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
import shlex


class InitrdGenerator(object):

    def __init__(self, image_root):
        self.image_root = image_root

    def generate(self, kernels):
        for kver, rdpath in kernels:
            self.generateOne(kver, rdpath)

    def generateOne(self, kver, rdpath):
        raise NotImplementedError

    def generateFromBootman(self):
        kernels = []
        bootconfig = os.path.join(self.image_root, 'etc/bootloader.conf')
        for line in open(bootconfig):
            if not line.startswith('linux '):
                continue
            args = shlex.split(line)
            if len(args) < 5:
                continue
            kver = args[1]
            rdpath = args[4]
            kernels.append((kver, rdpath))
        self.generate(kernels)

    def generateFromGrub(self, confName):
        paths = []
        path = os.path.join(self.image_root, 'boot/grub', confName)
        kernel = initrd = None
        for line in open(path):
            line = line.strip()
            if line.startswith('kernel '):
                if kernel:
                    paths.append((kernel, initrd))
                    kernel = initrd = None
                kernel = line.split()[1]
            elif line.startswith('initrd '):
                if initrd:
                    paths.append((kernel, initrd))
                    kernel = initrd = None
                initrd = line.split()[1]
            elif line.startswith('title '):
                if kernel or initrd:
                    paths.append((kernel, initrd))
                    kernel = initrd = None
        if kernel or initrd:
            paths.append((kernel, initrd))

        kernels = []
        for kpath, ipath in paths:
            # /boot/vmlinuz-1.2.3 -> 1.2.3
            kver = os.path.basename(kpath)[8:]
            if kver == 'template':
                continue
            kernels.append((kver, ipath))
        self.generate(kernels)
