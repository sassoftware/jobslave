#
# Copyright (c) 2011 rPath, Inc.
#


class InitrdGenerator(object):

    def __init__(self, image_root):
        self.image_root = image_root

    def generate(self, kernels):
        for kver, rdpath in kernels:
            self.generateOne(kver, rdpath)

    def generateOne(self, kver, rdpath):
        raise NotImplementedError
