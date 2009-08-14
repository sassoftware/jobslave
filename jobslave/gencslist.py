#!/usr/bin/python
# -*- python -*-
#
# Copyright (c) 2004-2006 rPath, Inc.
# All rights reserved
#

import os
import errno
import shutil
import tempfile

from jobslave.generators import constants
from jobslave.trovebucket import TroveBucket, Node, log

from conary.deps import deps
from conary.lib import sha1helper
from conary.repository import changeset

def _linkOrCopyFile(src, dest):
    while 1:
        try:
            os.link(src, dest)
        except OSError, msg:
            if msg.errno == errno.EEXIST:
                # if the file already exists, unlink and try again
                os.unlink(dest)
                continue
            # if we're attempting to make a cross-device link,
            # fall back to copy.
            if msg.errno != errno.EXDEV:
                # otherwise re-raise the unhandled exception, something
                # else went wrong.
                raise
            fd, fn = tempfile.mkstemp(dir=os.path.dirname(dest))
            destf = os.fdopen(fd, 'w')
            srcf = open(src, 'r')
            shutil.copyfileobj(srcf, destf)
            destf.close()
            srcf.close()
            os.rename(fn, dest)
            os.chmod(dest, 0644)
        break


class CsCache(TroveBucket):
    __slots__ = ('client', 'cacheDir', 'changesetVersion')

    def __init__(self, client, groupcs, cacheDir=None, changesetVersion=None):
        self.client = client
        self.cacheDir = cacheDir or ''
        self.groupcs = groupcs
        self.changesetVersion = changesetVersion

    def _getCacheFilename(self, name, version, flavor, compNames):
        # hash the version and flavor to give a unique filename
        versionFlavor = '%s %s' % (version.asString(), flavor.freeze())
        if compNames:
            # we could be generating a different set of troves,
            # say, :runtime only instead of :runtime + :devel, so add
            # in the components we're creating
            versionFlavor += ' %s' % ' '.join(compNames)
        h = sha1helper.md5ToString(sha1helper.md5String(versionFlavor))
        return '%s-%s.ccs' %(name, h)

    def _validateTrove(self, cachedCs, name, version, flavor):
        try:
            cachedTrove = self._getTrove(cachedCs, name, version, flavor)
        except KeyError:
            # the cached cs doesn't know anything about the trove we
            # want, it's definitely not the trove we're looking for.
            # move along.
            return False
        newTrove = self._getTrove(self.groupcs, name, version, flavor)
        cachedTrove.idMap.clear()
        if cachedTrove.freeze() != newTrove.freeze():
            return False
        return True

    def _validateChangeSet(self, path, name, version, flavor, compNames):
        # check to make sure that a cached change set matches the version
        # from the repository
        cachedCs = changeset.ChangeSetFromFile(path)

        # first check the top level trove
        if not self._validateTrove(cachedCs, name, version, flavor):
            return False

        if name.startswith('group-'):
            # groups are extracted with recurse=False, so we are done with
            # validataion
            return True

        # then iterate over any included troves (if any)
        topTrove = self._getTrove(self.groupcs, name, version, flavor)
        for name, version, flavor in topTrove.iterTroveList(strongRefs = True):
            if name not in compNames:
                if cachedCs.hasNewTrove(name, version, flavor):
                    return False
                continue
            if not self._validateTrove(cachedCs, name, version, flavor):
                return False

        return True

    def _downloadChangeSet(self, name, version, flavor, compNames,
                           callback=None, num=0, total=0):
        csRequest = [(name, (None, None), (version, flavor), True)]
        csRequest += ((x, (None, None), (version, flavor), True)
                      for x in compNames)

        # create the cs to a temp file
        fd, fn = tempfile.mkstemp(dir=self.cacheDir)
        os.close(fd)

        if callback:
            callback.setChangeSet(name)
            callback.setPrefix('changeset %d of %d: ' % (num, total))

        self.client.getRepos().createChangeSetFile(
            csRequest, fn,
            recurse = False,
            primaryTroveList = [(name, version, flavor)],
            changesetVersion = self.changesetVersion,
            callback = callback
        )

        return fn

    def getCs(self, trv, callback=None, num=0, total=0):
        if not trv.isGroup() and not trv.isComponent():
            compNames = [ x.name for x in trv.getChildren() ]
        else:
            compNames = []

        cacheName = self._getCacheFilename(trv.name, trv.version,
                                            trv.flavor, compNames)
        cachePath = os.path.join(self.cacheDir, cacheName)

        if (os.path.exists(cachePath) and 
            self._validateChangeSet(cachePath, trv.name, trv.version,
                                    trv.flavor, compNames)):
            return cachePath

        # Invalidate changeset
        if os.path.exists(cachePath):
            os.unlink(cachePath)

        # Populate cache with fresh changeset.
        fn = self._downloadChangeSet(trv.name, trv.version, trv.flavor,
                                     compNames, callback=callback, num=num,
                                     total=total)

        if not self.cacheDir:
            return fn

        os.rename(fn, cachePath)
        os.chmod(cachePath, 0644)

        return cachePath


class TreeGenerator(TroveBucket):
    __slots__ = ('client', 'cacheDir', 'cscache', 'cslist', 'pkgorder',
                 'changesetVersion', '_cslist')

    def __init__(self, cfg, client, topGroup, cacheDir=None, 
                 clientVersion=None):
        TroveBucket.__init__(self, cfg)
        self.client = client
        self.topGroup = topGroup
        self.cacheDir = cacheDir

        self.cscache = None
        self.pkgorder = None
        self.cslist = None
        self.changesetVersion = None

        self._cslist = None

        if clientVersion:
            self.changesetVersion = changeset.getNativeChangesetVersion(
                clientVersion)


    def _getGroupChangeSet(self):
        name, version, flavor = self.topGroup
        cl = [ (name, (None, None), (version, flavor), False) ]
        log.info('requesting changeset %s=%s[%s]' % (name, version, flavor))
        self.groupcs = self.client.createChangeSet(cl, withFiles=False,
                                                   withFileContents=False,
                                                   skipNotByDefault = False)

        # Get a cscache as soon as possible.
        self.cscache = CsCache(self.client, self.groupcs,
                               cacheDir=self.cacheDir,
                               changesetVersion=self.changesetVersion)

    def _orderValidTroves(self, jobs):
        trvList = []
        handled = set()

        for job in jobs:
            for csInfo in job:
                (name, (oldVersion, oldFlavor),
                       (newVersion, newFlavor), absolute) = csInfo

                assert(oldVersion == None)
                assert(oldFlavor == None)

                trv = self.getTrove(name, newVersion, newFlavor)

                if trv.isComponent():
                    ptrv = self.getTrove(trv.pkgName(), newVersion, newFlavor)
                    if ptrv not in handled:
                        trvList.append(ptrv)
                        # mark the package as handled so we don't do it
                        # again later.
                        handled.add(ptrv)
                    # already (or just) handled, carry on
                    continue

                if trv not in handled:
                    trvList.append(trv)
                    handled.add(trv)

        return trvList

    def _verifyPackageList(self):
        selected = [ x for x in self.troves.itervalues() if x.isSelected() ]

        pkgorder = set()
        for trv in self.pkgorder:
            pkgorder.add(trv)

            if not trv.isGroup() and not trv.isComponent():
                for t in trv.getChildren():
                    pkgorder.add(t)

        diff = pkgorder.difference(set(selected))

        if len(diff) > 0:
            log.critical('The following packages were different between what '
                         'conary put in the update job and what is '
                         'byDefault=True in the group: %s' % diff)
            return False
        return True

    def parsePackageData(self):
        # Get the group changeset.
        log.info('getting group changeset')
        self._getGroupChangeSet()

        # Parse the group into a node tree.
        log.info('calculating group hierarchy')
        self._calcGroupHierarchy(*self.topGroup)

        # Make sure that all kernels get on the disc.
        log.info('selecting kernels')
        self.selectTroveByName('kernel:runtime')

        # Check deps and get package install order.
        log.info('checking deps')
        updJob, suggMap = self._checkDeps()

        assert not suggMap

        # Get an ordered list of troves from the job set.
        log.info('calculating package order')
        self.pkgorder = self._orderValidTroves(updJob.getJobs())

        # Verify that all selected troves are in the pkgorder.
        log.info('verifying package list')
        assert self._verifyPackageList()

    def _getCsFilename(self, trv):
        if deps.DEP_CLASS_IS in trv.flavor.members:
            pkgarch = trv.flavor.members[deps.DEP_CLASS_IS].members.keys()[0]
        else:
            pkgarch = 'none';

        csfile = '%s-%s-%s-%s' % (trv.name, trv.revision.getVersion(),
                                  trv.release, pkgarch)

        if '%s.ccs' % csfile in self._cslist:
            i = 0
            while '%s-%s.ccs' % (csfile, i) in self._cslist:
                i += 1
            return '%s-%s.ccs' % (csfile, i)

        return '%s.ccs' % csfile

    def _getCsListEntry(self, trv, csfile):
        version = trv.version.asString()
        flavor = trv.flavor.freeze() or 'none'
        entry = '%s %s %s %s %s' % (csfile, trv.name, version, flavor, 1)
        return entry

    def extractChangeSets(self, csdir, callback=None):
        self.cslist = []
        self._cslist = []
        total = len(self.pkgorder)
        for num, trv in enumerate(self.pkgorder):
            log.info('extracting %s' % trv.name)

            csfile = self._getCsFilename(trv)
            self._cslist.append(csfile)
            self.cslist.append(self._getCsListEntry(trv, csfile))

            csPath = os.path.join(csdir, csfile)

            cachefn = self.cscache.getCs(trv, callback=callback, num=num,
                                         total=total)

            _linkOrCopyFile(cachefn, csPath)

            if not self.cacheDir:
                os.unlink(cachefn)

    def writeCsList(self, path):
        csListFile = os.path.join(path, 'cslist')
        if not os.path.exists(csListFile):
            log.info('writing cslist')
            fd = open(csListFile, 'w')
            fd.write('\n'.join(self.cslist))
            fd.close()

    def writeGroupCs(self, path):
        groupCsFile = os.path.join(path, 'group.ccs')
        if not os.path.exists(groupCsFile):
            log.info('writing group changeset')
            self.groupcs.writeToFile(groupCsFile, 
                                     versionOverride=self.changesetVersion)


if __name__ == '__main__':
    import sys
    from conary import conarycfg
    from conary import conaryclient
    from conary import updatecmd
    from conary.lib import util

    def usage():
        print ('usage: %s group /path/to/product '
               '</path/to/cscache>' % sys.argv[0])
        sys.exit(1)

    sys.excepthook = util.genExcepthook()

    if len(sys.argv) < 3 or len(sys.argv) > 4:
        usage()

    topGroup = sys.argv[1]
    prodDir = sys.argv[2]
    cacheDir = '/tmp/cscache'

    csdir = os.path.join(prodDir, 'changesets')
    baseDir = os.path.join(prodDir, 'base')

    if len(sys.argv) == 4:
        cacheDir = sys.argv[3]

    util.mkdirChain(csdir)
    util.mkdirChain(baseDir)
    util.mkdirChain(cacheDir)

    cfg = conarycfg.ConaryConfiguration(True)
    cfg.setContext(cfg.context)
    cfg.dbPath = ':memory:'
    cfg.root = ':memory:'
    cfg.initializeFlavors()
    client = conaryclient.ConaryClient(cfg)

    name, ver, flv = updatecmd.parseTroveSpec(topGroup)
    trvList = client.repos.findTrove(cfg.installLabelPath[0],
                                     (name, ver, flv),
                                     defaultFlavor = cfg.flavor)

    # Set flavor to match what anaconda uses.
    cfg.flavor = deps.parseFlavor('')

    if not trvList:
        print >> sys.stderr, "no match for", groupName
        raise RuntimeException
    elif len(trvList) > 1:
        print >> sys.stderr, "multiple matches for", groupName
        raise RuntimeException

    tg = TreeGenerator(cfg, client, trvList[0], cacheDir=cacheDir)
    tg.parsePackageData()
    tg.extractChangeSets(csdir)
    tg.writeCsList(baseDir)
    tg.writeGroupCs(baseDir)
