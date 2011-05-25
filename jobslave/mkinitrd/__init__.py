#
# Copyright (c) 2011 rPath, Inc.
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
