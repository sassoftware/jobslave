#
# Copyright (c) 2007 rPath, Inc.
#
# All Rights Reserved
#

from conary.conaryclient import ConaryClient
from conary import trove, files
from conary import conarycfg
from conary.lib import util
import conary

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
                seen[(name, version, flavor)] = True
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
                        mountDict[mount] += fObj.size()
                        break
        seen[(n, v, f)] = True
    return mountDict, sum(mountDict.values())
