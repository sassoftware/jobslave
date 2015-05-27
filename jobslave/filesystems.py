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


from conary import files
from conary.lib import util
from conary.repository.changeset import ChangeSetFromFile

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


def calculatePartitionSizes(uJob, mounts):
    """
    Iterate over every file in a C{changeSet} and return a sum of the
    sizes for each mount in C{mounts}.
    """
    mounts = sortMountPoints(mounts)
    sizes = dict.fromkeys(mounts, 0)

    for csPath in uJob.getJobsChangesetList():
        cs = ChangeSetFromFile(csPath)
        for trvCs in cs.iterNewTroveList():
            _processTrove(cs, trvCs, mounts, sizes)
    return sizes, sum(sizes.values())


def _processTrove(changeSet, trvCs, mounts, sizes):

    for pathId, path, fileId, fVer in trvCs.getNewFileList():
        fStr = changeSet.getFileChange(None, fileId)
        fObj = files.frozenFileContentInfo(fStr)

        if type(fObj) == files.RegularFileStream:
            for mount in mounts:
                if path.startswith(mount):
                    blockSize = 4096
                    realSize = fObj.size()
                    nearestBlock = (realSize / blockSize + 1) * blockSize
                    sizes[mount] += nearestBlock
                    break
