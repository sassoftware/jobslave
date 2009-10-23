#
# Copyright (c) 2009 rPath, Inc.
#
# All rights reserved.
#

import logging
import os
import select
import stat
import subprocess
import sys
import tempfile


def _getLogger(levels=2):
    """
    Get a logger for the function two stack frames up, e.g. the caller of the
    function calling this one.
    """
    caller = sys._getframe(levels)
    name = caller.f_globals['__name__']
    return logging.getLogger(name)


class CommandError(RuntimeError):
    def __init__(self, cmd, rv, stdout, stderr):
        self.cmd = cmd
        self.rv = rv
        self.stdout = stdout
        self.stderr = stderr
        self.args = (cmd, rv, stdout, stderr)

    def __str__(self):
        return "Error executing command: %s (return code %d)" % (
                self.cmd, self.rv)


def divCeil(num, div):
    """
    Divide C{num} by C{div} and round up.
    """
    div = long(div)
    return (long(num) + (div - 1)) / div


def null():
    return open('/dev/null', 'w+')


def call(cmd, ignoreErrors=False, logCmd=False, logLevel=logging.DEBUG,
        captureOutput=True, **kw):
    """
    Run command C{cmd}, optionally logging the invocation and output.

    If C{cmd} is a string, it will be interpreted as a shell command.
    Otherwise, it should be a list where the first item is the program name and
    subsequent items are arguments to the program.

    @param cmd: Program or shell command to run.
    @type  cmd: C{basestring or list}
    @param ignoreErrors: If C{False}, a L{CommandError} will be raised if the
            program exits with a non-zero return code.
    @type  ignoreErrors: C{bool}
    @param logCmd: If C{True}, log the invocation and its output.
    @type  logCmd: C{bool}
    @param captureOutput: If C{True}, standard output and standard error are
            captured as strings and returned.
    @type  captureOutput: C{bool}
    @param kw: All other keyword arguments are passed to L{subprocess.Popen}
    @type  kw: C{dict}
    """
    logger = _getLogger(kw.pop('_levels', 2))

    if logCmd:
        if isinstance(cmd, basestring):
            niceString = cmd
        else:
            niceString = ' '.join(repr(x) for x in cmd)
        env = kw.get('env', {})
        env = ''.join(['%s="%s" ' % (k,v) for k,v in env.iteritems()])
        logger.log(logLevel, "+ %s%s", env, niceString)

    kw.setdefault('close_fds', True)
    kw.setdefault('shell', isinstance(cmd, basestring))
    if 'stdin' not in kw:
        kw['stdin'] = open('/dev/null')
    elif isinstance(kw['stdin'], basestring):
        stdinFile = tempfile.TemporaryFile()
        stdinFile.write(kw.pop('stdin'))
        stdinFile.seek(0)
        kw['stdin'] = stdinFile

    pipe = captureOutput and subprocess.PIPE or None
    kw.setdefault('stdout', pipe)
    kw.setdefault('stderr', pipe)
    p = subprocess.Popen(cmd, **kw)

    stdout = stderr = ''
    if captureOutput:
        while p.poll() is None:
            rList = [x for x in (p.stdout, p.stderr) if x]
            rList, _, _ = select.select(rList, [], [])
            for rdPipe in rList:
                line = rdPipe.readline()
                if rdPipe is p.stdout:
                    which = 'stdout'
                    stdout += line
                else:
                    which = 'stderr'
                    stderr += line
                if logCmd and line.strip():
                    logger.log(logLevel, "++ (%s) %s", which, line.rstrip())

        # pylint: disable-msg=E1103
        stdout_, stderr_ = p.communicate()
        if stderr_ is not None:
            stderr += stderr_
            if logCmd:
                for x in stderr_.splitlines():
                    logger.log(logLevel, "++ (stderr) %s", x)
        if stdout_ is not None:
            stdout += stdout_
            if logCmd:
                for x in stdout_.splitlines():
                    logger.log(logLevel, "++ (stdout) %s", x)
    else:
        p.wait()

    if p.returncode and not ignoreErrors:
        raise CommandError(cmd, p.returncode, stdout, stderr)
    else:
        return p.returncode, stdout, stderr


def logCall(cmd, **kw):
    # This function logs by default.
    kw.setdefault('logCmd', True)

    # _getLogger() will need to go out an extra frame to get the original
    # caller's module name.
    kw['_levels'] = 3

    return call(cmd, **kw)


def getFileSize(filePath):
    return os.stat(filePath)[stat.ST_SIZE]


def setupLogging(logLevel=logging.INFO, toStderr=True, toFile=None):
    """
    Set up a root logger with default options and possibly a file to
    log to.
    """
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s')

    if isinstance(logLevel, basestring):
        logLevel = logging.getLevelName(logLevel.upper())

    rootLogger = logging.getLogger()
    rootLogger.setLevel(logLevel)
    rootLogger.handlers = []

    if toStderr:
        streamHandler = logging.StreamHandler()
        streamHandler.setFormatter(formatter)
        rootLogger.addHandler(streamHandler)

    if toFile:
        fileHandler = logging.FileHandler(toFile)
        fileHandler.setFormatter(formatter)
        rootLogger.addHandler(fileHandler)
