#
# Copyright (c) 2007 rPath, Inc.
#
# All Rights Reserved
#

from conary import trove, files
from conary.lib import util

import sys
import os


def sortMountPoints(mounts):
    """Sorts mount points by specificity by counting os.path.sep instances."""
    mounts = [util.normpath(x) for x in mounts]

    # sort mounts by specificity, more specific mountpoints first.
    mounts = sorted(mounts, key = lambda x: x.count(os.path.sep), reverse = True)

    # / is special, put it at the end
    if os.path.sep in mounts:
        mounts.remove(os.path.sep)
        mounts.append(os.path.sep)

    return mounts


def calculatePartitionSizes(cs, mounts):
    """Iterate over every file in a changeset and returns a sum of files inside
       each directory specified by "mounts"."""
    mounts = sortMountPoints(mounts)
    mountDict = dict.fromkeys(mounts, 0)

    seen = {}
    q = util.IterableQueue()
    for n, v, f in cs.getPrimaryTroveList():
        q.add((n, v, f))
    for n, v, f in q:
        trv = trove.Trove(cs.getNewTroveVersion(n, v, f))

        for (name, version, flavor), byDefault, strongRef in trv.iterTroveListInfo():
            if not byDefault:
                continue
            q.add((name, version, flavor))

        if (n, v, f) in seen:
            continue

        for pathId, path, fileId, fVer in trv.iterFileList():
            fStr = cs.getFileChange(None, fileId)
            fObj = files.frozenFileContentInfo(fStr)

            if type(fObj) == files.RegularFileStream:
                for mount in mounts:
                    if path.startswith(mount):
                        blockSize = 4096
                        realSize = fObj.size()
                        nearestBlock = (realSize / blockSize + 1) * blockSize
                        mountDict[mount] += nearestBlock
                        break
        seen[(n, v, f)] = True
    return mountDict, sum(mountDict.values())


def test(args):
    import time
    from conary.repository.changeset import ChangeSetFromFile

    def prettySize(bytes):
        if bytes > 1073741824:
            pretty = '%.2fGiB' % (bytes / 1073741824.0)
        elif bytes > 1048576:
            pretty = '%.2fMiB' % (bytes / 1048576.0)
        elif bytes > 1024:
            pretty = '%.2fKiB' % (bytes / 1024.0)
        else:
            pretty = '%dB' % bytes
        return '%s (%d)' % (pretty, bytes)

    if len(args) < 2:
        sys.exit('Usage: %s <changeset> <mount point>+' % sys.argv[0])

    changeSetPath, mountPoints = args[0], args[1:]

    _start = time.time()
    changeSet = ChangeSetFromFile(changeSetPath)
    _stop = time.time()

    csTotal = 0
    print 'From changeset: (loaded in %.03fs)' % (_stop - _start)
    for primaryTup in sorted(changeSet.getPrimaryTroveList()):
        trvCs = changeSet.getNewTroveVersion(*primaryTup)
        trv = trove.Trove(trvCs)
        trvSize = trv.getTroveInfo().size()
        csTotal += trvSize
        trvSpec = '%s=%s[%s]' % primaryTup
        print '%s=%s[%s] %s' % (primaryTup + (prettySize(trvSize),))
    print 'Total: %s' % prettySize(csTotal)
    print

    _start = time.time()
    sizeDict, totalSize = calculatePartitionSizes(changeSet, mountPoints)
    _stop = time.time()
    print 'From calculatePartitionSizes: (runtime %.03fs)' % (_stop - _start)
    for mountPoint in sortMountPoints(mountPoints):
        print '%-32s: %s' % (mountPoint, prettySize(sizeDict[mountPoint]))
    print 'Total: %s' % prettySize(totalSize)

    factor = float(csTotal) / float(totalSize)
    print 'Info delta: %12d  Factor: %.03f (%+.1f%%)' % (csTotal - totalSize,
        factor, (1 - factor) * -100.0)


if __name__ == '__main__':
    sys.exit(test(sys.argv[1:]))
