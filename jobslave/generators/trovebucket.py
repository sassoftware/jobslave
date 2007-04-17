#
# Copyright (c) 2006-2007 rPath, Inc.
# All rights reserved.
#

import copy

from conary.deps import deps
from conary.errors import TroveNotFound
from conary.repository import changeset
from conary.repository.resolvemethod import DepResolutionByLabelPath
from conary import trove, versions, conaryclient

import sys
class Logger(object):
    def info(self, msg):
        self.log('info', msg)
    def warn(self, msg):
        self.log('warning', msg)
    def critical(self, msg):
        self.log('critical', msg)
    def debug(self, msg):
        self.log('debug', msg)
    def log(self, level, msg):
        print >>sys.stderr, '%s: %s' % (level.upper(), msg)

log = Logger()


class Node(object):
    def isComponent(self):
        return ':' in self.name

    def isGroup(self):
        return self.name.startswith('group-')

    def pkgName(self):
        if self.isComponent():
            return self.name.split(':')[0]
        else:
            return self.name

    def setParent(self, p):
        if not self.__parents:
            self.__parents = []
        if p not in self.__parents:
            self.__parents.append(p)

    def setChild(self, c, pkgselection=True):
        if not self.__children:
            self.__children = []
        if c not in self.__children:
            self.__children.append(c)

        if not self.children:
            self.children = []
        if pkgselection and c not in self.children:
            self.children.append(c)

    def _getParents(self):
        if not self.__parents:
            self.__parents = []

        return self.__parents

    def _getChildren(self, select=False, unselect=False):
        assert(select or unselect)
        assert(not (select and unselect))

        if not self.__children:
            self.__children = []

        if self.isGroup():
            if unselect:
                # This is very dependent on the state of the selection tree
                # and can not be cached.
                c = [ x for x in self.__children
                      if x.groups[self] and
                         not [ y for y in x.groups.iterkeys()
                               if y != self and x.groups[y] and y.isSelected() ]
                    ]
                return c

        return self.__children

    def getChildren(self):
        if not self.children:
            self.children = []

        if not self._children:
            self._children = [ x for x in self.children if x.isDefault() ]
            self._children.sort(_pkgSort)

        return self._children

    def isSelected(self):
        return self.selected

    # direction: True == Up, False == down
    def select(self, dep=False, implicit=False, direction=False, group=None,
               cache=None):
        if not cache:
            cache = []

        if self.nvf in cache:
            return

        if self.selected:
            return

        log.debug('selecting %s' % self)

        self.selected = True
        self.dep = dep
        cache.append(self.nvf)

        if not implicit:
            for trv in self._getParents():
                trv.select(implicit=True, direction=True, cache=cache)
            for trv in self._getChildren(select=True):
                if trv.isDefault() or trv.isDefault(group=(self.isGroup() and self or None)):
                    trv.select(implicit=True, direction=False, cache=cache)
        else:
            if direction:
                for grp in self._getParents():
                    grp.select(implicit=implicit, direction=direction, cache=cache)
            else:
                for trv in self._getChildren(select=True):
                    if trv.isDefault() or trv.isDefault(group=(self.isGroup() and self or None)):
                        trv.select(implicit=implicit, direction=direction, cache=cache)

    def unselect(self, implicit=False, direction=False, cache=None):
        if not cache:
            cache = []

        if self.nvf in cache:
            return

        if not self.selected:
            return

        def hasSelectedChildren(trv):
            found = False
            for x in trv._getChildren(unselect=True):
                if x.isSelected():
                    found = True
                    break
            return found

        log.debug('unselecting %s' % self)

        if self.dep:
            log.warn('%s has been enabled through dep resolution, disabling'
                     ' this package may break your install' % self.name)

        self.selected = False
        self.dep = False
        cache.append(self.nvf)

        if not implicit:
            for trv in self._getChildren(unselect=True):
                trv.unselect(implicit=True, direction=False, cache=cache)
            for trv in self._getParents():
                if not hasSelectedChildren(trv):
                    trv.unselect(implicit=True, direction=True, cache=cache)
        else:
            if not direction:
                for trv in self._getChildren(unselect=True):
                    if trv.isSelected():
                        trv.unselect(implicit=implicit, direction=direction, cache=cache)
            else:
                for trv in self._getParents():
                    if not hasSelectedChildren(trv):
                        trv.unselect(implicit=implicit, direction=direction, cache=cache)

    def isDep(self):
        return self.dep

    def isDefault(self, group=None):
        # group is a node object
        if group in self.groups:
            return self.groups[group]

        return self.byDefault

        # If this trove is set as byDefault for any group then the
        # byDefault setting is true.
        return bool([ x for x in self.groups.iteritems() if x[1] ])

    __slots__ = ('name', 'version', 'flavor', 'nvf', 'order', 'disc', 'size',
                 'selected', 'dep', 'csfile', 'arch', 'revision', 'release',
                 '__parents', '__children', '_children', 'children', 'troves',
                 'groups', 'byDefault')

    def __init__(self, name, version, flavor):
        self.name = name
        self.version = version
        self.flavor = flavor
        self.nvf = (name, version, flavor)
        self.order = 0
        self.disc = 1
        self.size = 0
        self.selected = False
        self.dep = False
        self.csfile = None
        self.arch = self.__getArch()
        self.revision = self.__getRevision()
        self.release = self.__getRelease()

        self.__parents = None
        self.__children = None
        self._children = None
        self.children = None

        # reference back to the tree
        self.troves = None

        # byDefault settings are stored on a group by group basis
        self.groups = {}
        self.byDefault = False

    def __cmp__(self, n):
        if self.order < n.order:
            return -1
        elif self.order > n.order:
            return 1
        elif self.disc < n.disc:
            return -1
        elif self.disc > n.disc:
            return 1
        elif self.name.lower() < n.name.lower():
            return -1
        elif self.name.lower() > n.name.lower():
            return 1
        elif self.version < n.version:
            return -1
        elif self.version > n.version:
            return 1
        elif self.flavor < n.flavor:
            return -1
        elif self.flavor > n.flavor:
            return 1
        else:
            return 0

    def __repr__(self):
        return "('%s', '%s')" % (self.name, self.csfile)

    def __str__(self):
        return "%s=%s[%s]" % (self.name, self.version, self.flavor)
        #return "%s=%s" % (self.name, self.version)

    def __hash__(self):
        return hash(self.nvf)

    def __getArch(self):
        isdep = deps.InstructionSetDependency
        arches = [ x.name for x in self.flavor.iterDepsByClass(isdep) ]
        if not arches:
            arches = [ 'noarch' ]
        return ','.join(arches)

    def __getRevision(self):
        return [ x for x in self.version.iterRevisions() ][0]

    def __getRelease(self):
        return '-'.join([str(self.revision.getSourceCount()),
                         str(self.revision.getBuildCount())])


class TroveBucket(object):
    nodeClass = Node

    __slots__ = ('cfg', 'discs', 'grpList', 'groups', 'troves', 'topGroup',
                 'groupcs', 'groupTrv', 'nodeClass')

    def __init__(self, cfg):
        self.cfg = cfg
        self.discs = []
        self.grpList = []
        self.groups = {}
        self.troves = {}
        self.topGroup = None
        self.groupcs = None
        self.groupTrv = None

    def _getTrove(self, cs, name, version, flavor):
        troveCs = cs.getNewTroveVersion(name, version, flavor)
        t = trove.Trove(troveCs, skipIntegrityChecks=True)
        return t

    def _getNode(self, trv, name, version, flavor):
        if not (name, version, flavor) in self.troves:
            node = apply(self.nodeClass, (name, version, flavor))
            node.troves = self.troves
            self.troves[node.nvf] = node

        node = self.troves[(name, version, flavor)]
        grpSpec = (trv.getName(), trv.getVersion(), trv.getFlavor())
        grpNode = self.troves[grpSpec]

        if not self.groupTrv:
            self.groupTrv = self._getTrove(self.groupcs, self.topGroup[0],
                                           self.topGroup[1], self.topGroup[2])

        if node.nvf != grpSpec:
            if name == self.topGroup[0]:
                byDefault = True
            else:
                byDefault = trv.includeTroveByDefault(name, version, flavor)

            topByDefault = self.groupTrv.includeTroveByDefault(name, version,
                                                               flavor)

            if grpNode not in node.groups:
                node.groups[grpNode] = byDefault

            if topByDefault:
                node.selected = True
                node.byDefault = True
        elif node.nvf == self.topGroup:
            node.groups[grpNode] = True
            node.selected = True
            node.byDefault = True

        return node

    def _calcGroupHierarchy(self, grpName, grpVer, grpFlavor):
        log.info('processing group hierarchy: %s' % grpName)
        # instantiate all the trove objects in the group, make a set
        # of the changesets we should extract
        trv = self._getTrove(self.groupcs, grpName, grpVer, grpFlavor)
        grpNode = self._getNode(trv, grpName, grpVer, grpFlavor)
        self.grpList.append(grpNode.nvf)
        if grpName not in self.groups:
            self.groups[grpName] = []
        self.groups[grpName].append(grpNode.nvf)

        groups = []
        for name, version, flavor in trv.iterTroveList(strongRefs=True):
            node = self._getNode(trv, name, version, flavor)

            grpNode.setChild(node)
            node.setParent(grpNode)

            if node.isGroup():
                groups.append(node)
                continue

            if not node.isComponent():
                pkgTrv = self._getTrove(self.groupcs, name, version, flavor)
                for n, v, f in pkgTrv.iterTroveList(strongRefs=True):
                    cNode = self._getNode(trv, n, v, f)

                    t = self._getTrove(self.groupcs, n, v, f)
                    cNode.size = t.getSize() or 0

                    grpNode.setChild(cNode, pkgselection=False)
                    node.setChild(cNode)
                    cNode.setParent(node)

        for groupNode in groups:
            self._calcGroupHierarchy(*groupNode.nvf)

    def iterTroves(self):
        return self.troves.itervalues()

    def getTrove(self, name, version, flavor):
        trvSpec = (name, version, flavor)
        if trvSpec in self.troves:
            return self.troves[trvSpec]
        else:
            log.warn('requested trove not found %s=%s[%s]' % trvSpec)
            return None

    def getTroveByName(self, name, withComponents=False):
        return [ trv for trv in self.troves.itervalues() 
                     if trv.name == name or 
                        (withComponents and 
                         not trv.isGroup() and
                         trv.name.startswith(name) and 
                         trv.isDefault()) ]

    def selectTroveByName(self, name, dep=False, withComponents=False):
        for trv in self.getTroveByName(name, withComponents):
            trv.select(dep=dep)

    def unselectTroveByName(self, name, withComponents=False):
        for trv in self.getTroveByName(name, withComponents):
            trv.unselect()

    def isSelected(self, name, version, flavor):
        return self.troves[(name, version, flavor)].isSelected()

    def select(self, name, version, flavor, dep=False):
        self.troves[(name, version, flavor)].select(dep=dep)

    def unselect(self, name, version, flavor):
        self.troves[(name, version, flavor)].unselect()

    def hasTroveByName(self, name):
        if [ x for x in self.troves.itervalues() if x.name == name ]:
            return True
        else:
            return False

    def hasTrove(self, name, version, flavor):
        return (name, version, flavor) in self.troves

    def _checkDeps(self):
        log.info('resolving dependencies')

        l = []
        t = []
        for p in self.troves.itervalues():
            if p.isSelected():
                l.append((p.name, (None, None), (p.version, p.flavor), False))
            if p.isDefault() or p.name in ('kernel', 'kernel:runtime'):
                t.append(p.nvf)

        cfg = copy.copy(self.cfg)
        cfg.root = ':memory:'
        cfg.dbPath = ':memory:'
        cfg.autoResolve = True

        client = conaryclient.ConaryClient(cfg)
        client.repos = None

        csList = [ self.groupcs ]

        resolveSource = ResolveByLabelPathWithTroveFilter(t, cfg, None, cfg.installLabelPath)

        try:
            (updJob, suggMap) = client.updateChangeSet(l, resolveDeps = True,
                                                       recurse = False,
                                                       resolveRepos = False,
                                                       fromChangesets=csList,
                                                       resolveSource = resolveSource)
        except conaryclient.DepResolutionFailure, e:
            log.critical(str(e))
            raise

        return updJob, suggMap

    def _selectDeps(self, suggMap):
        # Invert the suggestion map so that each trove only gets selected once.
        d = {}
        for what, need in suggMap.iteritems():
            for item in need:
                if item not in d:
                    d[item] = []
                d[item].append(what)

        for item, what in d.iteritems():
            trv = self.getTrove(item[0], item[1], item[2])
            if not trv.isDefault():
                raise TroveNotFound, 'Trove not on disc %s' % trv
            self.select(item[0], item[1], item[2], dep=True)
            log.info('using %s to satisfy %s', str(item), str(what))

    # Check to make sure no byDefault False troves are selected. This is only 
    # used by the test suite and for debugging purposes.
    def _verifySelection(self):
        broken = []
        for trv in self.troves.itervalues():
            if trv.isSelected() and not trv.isDefault():
                broken.append(trv)
        if len(broken) > 0:
            raise TroveNotFound, ('The following troves are selected, but are '
                                  'not going to be on the disc: %s'
                                   % ', '.join(broken))


# Dep solver that can take a list of troves (name, version, flavor) to resolve
# against.
class ResolveByLabelPathWithTroveFilter(DepResolutionByLabelPath):
    def __init__(self, troveList, *args, **kw):
        self.filterList = troveList
        DepResolutionByLabelPath.__init__(self, *args, **kw)

    def selectResolutionTrove(self, requiredBy, dep, depClass,
                              troveTups, installFlavor, affFlavorDict):
        troveTups = [ x for x in troveTups if x in self.filterList ]
        return DepResolutionByLabelPath.selectResolutionTrove(self, requiredBy,
            dep, depClass, troveTups, installFlavor, affFlavorDict)


# Used by the package selection interface for display order.
def _pkgSort(a, b):
    if a.name.startswith('group-') and not b.name.startswith('group-'):
        return 1
    elif not a.name.startswith('group-') and b.name.startswith('group-'):
        return -1
    elif a.name.lower() > b.name.lower():
        return 1
    elif a.name.lower() < b.name.lower():
        return -1
    elif a.version > b.version:
        return 1
    elif a.version < b.version:
        return -1
    elif a.flavor > b.flavor:
        return 1
    elif a.flavor < b.flavor:
        return -1
    else:
        return 0
