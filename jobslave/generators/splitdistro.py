#!/usr/bin/env python2.4
# -*- python -*-
#
# Copyright (c) 2004-2006 rPath, Inc.
# All rights reserved
#

import os, sys
import tempfile
import subprocess

from jobslave.generators.gencslist import _linkOrCopyFile
from jobslave.generators import constants

import conary
from conary.lib import util
import conary.trove
import conary.repository.changeset

commonfiles = ('README', 'LICENSE')
basicminimal = ('group-core', 'group-base')

def call(*cmds):
    print >> sys.stderr, " ".join(cmds)
    sys.stderr.flush()
    subprocess.call(cmds)

def join(*args):
    return os.sep.join(args)

def lndir(src, dest, excludes=[]):
    for dirpath, dirnames, filenames in os.walk(src):
        curdir = dirpath[len(src) + 1:]
        # skipping the directory by itself is not enough, we need to ensure
        # that sub directories get excluded as well (since we can't know them
        # ahead of time)
        if [x for x in excludes if curdir.startswith(x)]:
            continue
        for p in (filenames + dirnames):
            if curdir:
                curpath = join(curdir, p)
            else:
                curpath = p
            if curpath in excludes:
                continue
            if not os.path.exists(join(dest, curpath)):
                # this is perfectly fine since the exact same path can't appear
                # in both the directory list and the file list.
                if p in filenames:
                    _linkOrCopyFile(join(dirpath, p), join(dest, curpath))
                else:
                    os.mkdir(join(dest, curpath))

def spaceused(path, isoblocksize):
    if not os.path.isdir(path):
        sb = os.stat(path)
        return sb.st_size + (isoblocksize - sb.st_size % isoblocksize)

    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            filepath = join(dirpath, filename)
            sb = os.stat(filepath)
            # round up to an ISO9660 block
            total += sb.st_size + (isoblocksize - sb.st_size % isoblocksize)

    return total

def preparedir(unified, path, csdir):
    if os.path.isdir(path):
        print >> sys.stderr, 'removing stale', path
        util.rmtree(path)

    print >> sys.stderr, 'creating', path
    os.mkdir(path)
    base = path
    for d in csdir.split(os.sep):
        os.mkdir(join(base, d))
        base = join(base, d)
    for f in commonfiles:
        src = join(unified, f)
        if os.access(src, os.R_OK):
            os.link(src, join(path, f))
    if 'media-template' in os.listdir(unified) and \
       'all' in os.listdir(os.path.join(unified, 'media-template')):
        lndir(os.path.join(unified, 'media-template', 'all'), path)
    # copy over new media-template using overwrite rules
    srcDir = os.path.join(unified, 'media-template2', 'all')
    if os.path.exists(srcDir):
        for src in os.listdir(srcDir):
            call('cp', '-R', '--no-dereference', os.path.join(srcDir, src),
                 path)

def writediscinfo(path, discnum, discinfo):
    newinfo = discinfo[:]
    newinfo[3] = str(discnum)
    f = open(join(path, '.discinfo'), 'w')
    f.write('\n'.join(newinfo))
    f.write('\n')
    f.close()

def reorderChangesets(f, csPath, initialSizes, maxisosize, isoblocksize,
                      baseTrove):
    reservedTroves = []
    sizedList = []
    infoTroves = []
    baseTroves = []
    for line in f:
        csFile = line.split()[0]
        trvName = line.split()[1]
        if trvName in basicminimal:
            reservedTroves.append(line)
        spaceUsed = spaceused(join(csPath, csFile), isoblocksize)
        if trvName.startswith('info-'):
            infoTroves.append((spaceUsed, line))
        elif trvName == baseTrove:
            baseTroves.append((spaceUsed, line))
        else:
            sizedList.append((spaceUsed, line))
    sizedList = [x for x in reversed(sorted(sizedList))]

    reservedList = []
    if reservedTroves:
        trvNames = set()
        for trvLine in reservedTroves:
            trvNames.add(trvLine.split()[1])
            cs = conary.repository.changeset.ChangeSetFromFile( \
                join(csPath, trvLine.split()[0]))
            trv = conary.trove.Trove([x for x in cs.iterNewTroveList()][0])
            for includedTrv in [x[0].split(':')[0] for x in \
                                trv.iterTroveList(strongRefs = True,
                                                  weakRefs = True)]:
                trvNames.add(includedTrv)

        for size, line in sizedList[:]:
            if line.split()[1] in trvNames:
                reservedList.append((size, line))
                sizedList.remove((size, line))

    sizedList = infoTroves + reservedList + baseTroves + sizedList

    reOrdList = [[[], maxisosize - initialSizes[0]]]

    for size, line in sizedList:
        match = False
        for i, (changesets, limit) in enumerate(reOrdList):
            if maxisosize and (size <= limit):
                reOrdList[i][0].append(line)
                reOrdList[i][1] -= size
                match = True
                break
        if not match:
            reOrdList.append([[line], maxisosize - size - initialSizes[1]])

    csList = []
    for disc in [x[0] for x in reOrdList]:
        csList.extend(disc)
    return csList

def splitDistro(unified, baseTrove, maxisosize = 650 * 1024 * 1024,
                isoblocksize = 2048):
    if not os.path.isdir(unified):
        # FIXME: move ParameterError into mint_errors and use that.
        raise AssertionError("path is not a directory")

    f = open(join(unified, '.discinfo'))
    discinfo = [ line.strip() for line in f ]
    f.close()

    cslist = join(discinfo[4], 'cslist')
    csdir = discinfo[5]

    # create disc1, it needs to contain all the disc1 files
    current = join(os.path.dirname(unified), 'disc1')
    discnum = 1
    if os.path.isdir(current):
        print >> sys.stderr, 'removing stale', current
        util.rmtree(current)
    print >> sys.stderr, 'creating', current
    os.mkdir(current)
    lndir(unified, current, excludes=(csdir, cslist, '.discinfo',
                                      'media-template'))
    writediscinfo(current, discnum, discinfo)
    # clone custom media content in before calculating size.
    # lay 'disc1' before 'all' to ensure collisions are handled correctly
    for cDir in ('disc1', 'all'):
        if 'media-template' in os.listdir(unified) and \
               cDir in os.listdir(os.path.join(unified, 'media-template')):
            lndir(os.path.join(unified, 'media-template', cDir), current)

    for cDir in ('all', 'disc1'):
        srcDir = os.path.join(unified, 'media-template2', cDir)
        if os.path.exists(srcDir):
            for src in os.listdir(srcDir):
                call('cp', '-R', '--no-dereference', os.path.join(srcDir, src),
                     current)

    used = spaceused(current, isoblocksize)

    # prepare a dummy disc ahead of time to precalc the initial size correctly
    # the fact that media-template is completely custom has the unlimited
    # power to make this extremely messy through other calculation methods.
    tmpDisc = tempfile.mkdtemp(dir=constants.tmpDir)
    preparedir(unified, tmpDisc, csdir)
    allContentSize = spaceused(tmpDisc, isoblocksize)
    util.rmtree(tmpDisc, ignore_errors = True)

    # iterate through the cslist, copying all the changesets that
    # will fit
    f = open(join(unified, cslist))
    outcs = open(join(current, cslist), 'w')
    reOrd = reorderChangesets(f, join(unified, csdir), (used, allContentSize),
                              maxisosize, isoblocksize, baseTrove)
    f.close()
    for line in reOrd:
        csfile = line.split()[0]
        src = join(unified, csdir, csfile)
        used += spaceused(src, isoblocksize)
        if maxisosize and (used > maxisosize):
            # oops, ran out of space.  set up a new disc
            discnum += 1
            current = join(os.path.dirname(unified), 'disc%d' %discnum)
            preparedir(unified, current, csdir)
            writediscinfo(current, discnum, discinfo)
            used = spaceused(current, isoblocksize) + \
                   spaceused(src, isoblocksize)
        dest = join(current, csdir, csfile)
        util.mkdirChain(os.path.dirname(dest))
        os.link(src, dest)
        # cut off disc number, record the disc location
        newline = " ".join(line.split()[:-1])
        outcs.write("%s %d\n" %(newline, discnum))
    outcs.close()
