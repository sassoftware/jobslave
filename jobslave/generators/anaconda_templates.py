#
# Copyright (c) 2004-2006 rPath, Inc.
#
# All Rights Reserved
#
import os
import subprocess
import sys

from conary.lib import util


def call(cmds, env = None):
    print >> sys.stderr, "+ " + " ".join(cmds)
    sys.stderr.flush()
    kwargs = {'env': env}
    subprocess.call(cmds, **kwargs)


class Image(object):
    def run(self, cmd, *args):
        args = list(args)
        try:
            func = self.__getattribute__(cmd)
        except AttributeError:
            raise RuntimeError, "Invalid anaconda templates manifest image command: %s" % (cmd)

        if len(args) == 3:
            mode = int(args.pop(-1), 8)
        else:
            mode = 0644

        input = os.path.join(self.tmpDir, args[0])
        output = os.path.join(self.templateDir, args[1])

        util.mkdirChain(os.path.dirname(output))
        retcode = func(input, output)
        os.chmod(output, mode)

        # copy the resulting file back to the source area in
        # case it is used elsewhere in the manifest
        util.copyfile(output, os.path.join(self.tmpDir, args[1]))
        return retcode

    def cpiogz(self, inputDir, output):
        oldCwd = os.getcwd()
        os.chdir(inputDir)
        try:
            os.system("find . | cpio --quiet -c -o | gzip -9 > %s" % output)
        finally:
            try:
                os.chdir(oldCwd)
            except:
                pass

    def mkisofs(self, inputDir, output):
        cmd = ['mkisofs', '-quiet', '-o', output,
            '-b', 'isolinux/isolinux.bin',
            '-c', 'isolinux/boot.cat',
            '-no-emul-boot',
            '-boot-load-size', '4',
            '-boot-info-table',
            '-R', '-J', '-T',
            '-V', 'rPath Linux',
            inputDir]
        call(cmd)

    def mkcramfs(self, inputDir, output):
        cmd = ['mkcramfs', inputDir, output]
        call(cmd)

    def mkdosfs(self, inputDir, output):
        call(['dd', 'if=/dev/zero', 'of=%s' % output, 'bs=1M', 'count=8'])
        call(['/sbin/mkdosfs', output])

        files = [os.path.join(inputDir, x) for x in os.listdir(inputDir)]
        cmds = ['mcopy', '-i', output] + files + ['::']
        call(cmds)
        call(['syslinux', output])

    def mksquashfs(self, inputDir, output):
        cmd = ['mksquashfs', inputDir, output, '-all-root']
        call(cmd)

    def __init__(self, templateDir, tmpDir):
        self.templateDir = templateDir
        self.tmpDir = tmpDir
