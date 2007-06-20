#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import os
import sys

from jobslave.slave import watchdog

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

    def testWatchdog(self):
        self.dummyPid = 3
        self.commands = []

        def dummySystem(*args, **kwargs):
            print args, kwargs
            sys.stdout.flush()

        system = os.system
        fork = os.fork
        _exit = os._exit
        getppid = os.getppid
        def dummyGetppid():
            self.dummyPid -= 1
            return self.dummyPid

        def dummySystem(command):
            self.commands.append(command)

        try:
            os.system = dummySystem
            os.fork = lambda: 0
            os._exit = lambda x: None
            os.getppid = dummyGetppid
            self.captureAllOutput(watchdog)
            self.failIf(self.commands != ['poweroff -h'],
                        "shutdown command not issued")
        finally:
            os.system = system
            os.fork = fork
            os._exit = _exit
            os.getppid = getppid

if __name__ == "__main__":
    testsuite.main()
