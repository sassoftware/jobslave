#!/usr/bin/python
#
# Copyright (c) 2010 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import os
import sys

from jobslave import helperfuncs


class HelperFunctionsTest(testsuite.TestCase):
    def captureAllOutput(self, func, *args, **kwargs):
        oldErr = os.dup(sys.stderr.fileno())
        oldOut = os.dup(sys.stdout.fileno())
        fd = os.open(os.devnull, os.W_OK)
        os.dup2(fd, sys.stderr.fileno())
        os.dup2(fd, sys.stdout.fileno())
        os.close(fd)
        try:
            return func(*args, **kwargs)
        finally:
            os.dup2(oldErr, sys.stderr.fileno())
            os.dup2(oldOut, sys.stdout.fileno())
            os.close(oldErr)
            os.close(oldOut)

    def testGetMountedFiles(self):
        class mock_popen:
            def read(xself):
                return ' 1234 5678'
        class mock_os:
            def __init__(xself, listdir_hits, readlink_hits):
                xself.listdir_hits = listdir_hits
                xself.readlink_hits = readlink_hits
                xself.path = os.path
            def listdir(xself, path):
                xself.listdir_hits.add(path)
                if path == '/proc/1234/fd':
                    return ['1', '2']
                elif path == '/proc/5678/fd':
                    return ['3']
            def readlink(xself, path):
                xself.readlink_hits.add(path)
                return paths[path.split('/')[-1]]
            def popen(xself, path, mode):
                self.failUnlessEqual(path, 'fuser -m /mnt/null 2>/dev/null')
                self.failUnlessEqual(mode, 'r')
                return mock_popen()

        listdir_hits = set()
        listdir_want = set(['/proc/1234/fd', '/proc/5678/fd'])
        readlink_hits = set()
        readlink_want = set(['/proc/1234/fd/1', '/proc/1234/fd/2',
            '/proc/5678/fd/3'])
        paths = { '1': '/irrelevant', '2': '/mnt/null/foo',
            '3': '/mnt/null/bar'}

        _os = helperfuncs.os
        try:
            helperfuncs.os = mock_os(listdir_hits, readlink_hits)

            paths = helperfuncs.getMountedFiles('/mnt/null')
            self.failUnlessEqual(paths,
                set(['/mnt/null/foo', '/mnt/null/bar']))

            self.failUnlessEqual(listdir_hits, listdir_want)
            self.failUnlessEqual(readlink_hits, readlink_want)
        finally:
            helperfuncs.os = _os

if __name__ == "__main__":
    testsuite.main()
