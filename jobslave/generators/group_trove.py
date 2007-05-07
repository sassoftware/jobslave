#
# Copyright (c) 2005-2006 rPath, Inc.
#
# All Rights Reserved
#
import os.path
import sys
import string
import tempfile
import time

from jobslave.generators import constants
from jobslave.flavors import getStockFlavor
from jobslave.generators.imagegen import Generator

from conary import checkin
from conary import conarycfg
from conary import versions
from conary.build import cook
from conary import build
from conary.deps import deps
from conary import conaryclient
from conary.repository import changeset
from conary.lib import util

def troveInGroup(self, trvItems, name, version, flavor):
        trvDicts = [x for x in trvItems if x['trvName'] == name]
        for trvDict in trvDicts:
            flav = deps.ThawFlavor(flavor)
            if not (trvDict['useLock'] or trvDict['instSetLock']):
                flavor = ''
            elif (trvDict['useLock'] and trvDict['instSetLock']):
                flavor = str(flav)
            elif trvDict['useLock']:
                depSet = deps.Flavor()
                depSet.addDeps(deps.UseDependency,
                               flav.iterDepsByClass(deps.UseDependency))
                flavor = str(depSet)
            else:
                depSet = deps.Flavor()
                depSet.addDeps(deps.InstructionSetDependency,
                               flav.iterDepsByClass(deps.InstructionSetDependency))
                flavor = str(depSet)
            if flavor:
                flavorMatch = trvDict['trvFlavor'] == flavor
            else:
                # short circuit degenerate flavors
                flavorMatch = True
            if version == '':
                # short circuit degenerate versions
                return flavorMatch
            parsedVer = versions.VersionFromString(version)
            label = str(parsedVer.branch().label())
            if trvDict['trvFlavor'] == flavor and \
               (trvDict['versionLock'] and  \
               version == trvDict['trvVersion'] or \
                (not trvDict['versionLock'] and
                    trvDict['trvLabel'] == label)):
                return True
        return False

def getRecipe(jobData):
        recipe = ""
        name = ''.join((string.capwords(
            ' '.join(jobData['recipeName'].split('-')))).split(' '))
        indent = 4 * " "

        recipe += "class " + name + "(GroupRecipe):\n"
        recipe += indent + "name = '%s'\n" % str(jobData['recipeName'])
        recipe += indent + "version = '%s'\n\n" % str(jobData['upstreamVersion'])
        recipe += indent + "autoResolve = %s\n\n" % \
                  str(jobData['autoResolve'])
        recipe += indent + 'def setup(r):\n'

        indent = 8 * " "
        recipeLabels = [str(x) for x in jobData['labelPath']]
        recipe += indent + "r.setLabelPath(%s)\n" % \
                  str(recipeLabels).split('[')[1].split(']')[0]

        removedComponents = jobData['removedComponents']
        if removedComponents:
            recipe += indent + "r.removeComponents(('" + \
                      "', '".join(removedComponents) + "'))\n"

        for trv in jobData['troveItems']:
            ver = trv['versionLock'] and trv['trvVersion'] or trv['trvLabel']

            d = {}
            d['name'] = str(trv['trvName'])
            d['flavor'] = str(trv['trvFlavor'])
            d['groupName'] = str(trv['subGroup'])
            d['ver'] = str(ver)

            # XXX HACK to use the "fancy-flavored" group troves from
            # conary.rpath.com
            if trv['trvName'].startswith('group-') and \
                   trv['trvLabel'].startswith('conary.rpath.com@'):

                branch = trv['trvLabel'].split("@")[1]
                addonsLabel = "addons.rpath.com@" + branch

                d['fancyFlavor'] = 'is:x86(i486,i586,i686) x86_64'
                d['searchPath'] = str([str(addonsLabel)] + recipeLabels)

                recipe += indent + "if Arch.x86_64:\n"
                recipe += (12 * " ") + "r.add('%(name)s', flavor = '%(fancyFlavor)s', groupName = '%(groupName)s', searchPath = %(searchPath)s)\n" % d
                recipe += indent + "else:\n" + (4 * " ")
                recipe += indent + "r.add('%(name)s', flavor = '%(flavor)s', groupName = '%(groupName)s', searchPath = %(searchPath)s)\n" % d
            else:
                recipe += indent + "r.add('%(name)s', '%(ver)s', '%(flavor)s', groupName = '%(groupName)s')\n" % d

        return recipe

class GroupTroveCook(Generator):
    def write(self):
        self.status("Cooking group")
        curDir = os.getcwd()

        recipeName = self.jobData['recipeName']

        ret = None
        e = None
        try:
            path = tempfile.mkdtemp(dir=constants.tmpDir)
            recipe = getRecipe(self.jobData)
            sourceName = recipeName + ":source"
            flavor = deps.ThawFlavor(str(self.getCookData("arch")))

            cfg = self.conarycfg
            cfg.configLine('user * mintauth mintpass')
            cfg.name = "rBuilder Online"
            cfg.contact = "http://www.rpath.org"
            cfg.quiet = True
            cfg.buildLabel = versions.Label(self.jobData['project']['label'])
            cfg.buildFlavor = getStockFlavor(flavor)
            cfg.initializeFlavors()
            self.readConaryRc(cfg)

            repos = conaryclient.ConaryClient(cfg).getRepos()
            trvLeaves = repos.getTroveLeavesByLabel(\
                {sourceName : {cfg.buildLabel : None} }).get(sourceName, [])

            os.chdir(path)
            if trvLeaves:
                checkin.checkout(repos, cfg, path, [recipeName])
                added = True
            else:
                checkin.newTrove(repos, cfg, recipeName, path)
                added = False

            tries = 0
            while tries < 2:
                recipeFile = open(recipeName + '.recipe', 'w')
                recipeFile.write(recipe)
                recipeFile.flush()
                recipeFile.close()

                if not trvLeaves and not added:
                    checkin.addFiles([recipeName + '.recipe'])
                    added = True

                # commit recipe as changeset
                message = "Auto generated commit from %s.\n%s" % \
                          (cfg.name, self.jobData['description'])
                checkin.commit(repos, cfg, message.encode('ascii', 'replace'))

                troveSpec = "%s[%s]" % (recipeName, str(flavor))
                removeTroves = []
                try:
                    ret = cook.cookItem(repos, cfg, troveSpec)
                except build.errors.GroupPathConflicts, e:
                    if tries:
                        import itertools
                        conflicts = [y for y in itertools.chain( \
                            *[x[1] for x in e.conflicts.items()])]
                        break
                    labelPath = self.jobData['labelPath']
                    for group, conflicts in e.conflicts.items():
                        for conflict in conflicts:
                            expMatches = [x for x in conflict[0] \
                                      if troveInGroup( \
                                    self.jobData['troveItems'],
                                    x[0].split(':')[0], str(x[1]),
                                    x[2].freeze())]

                            for l in labelPath:
                                # if expMatches is not empty, we must honor it.
                                # otherwise fallback to all conflicts.
                                matches = [x for x in \
                                          (expMatches or conflict[0]) \
                                          if x[1].branch().label().asString() == l]
                                if matches:
                                    con = list(conflict[0])
                                    # very rare corner case: 2 matches on same
                                    # branch: largest version number is best.
                                    con.remove(max(matches))
                                    con = [(x[0].split(':')[0], x[1], x[2], group) \
                                         for x in con]
                                    for trvCon in con:
                                        if trvCon not in removeTroves:
                                            removeTroves.append(trvCon)
                                    break
                else:
                    break
                for rm in removeTroves:
                    recipe += "        r.remove('%s', '%s', '%s', groupName='%s')\n" % (rm[0], rm[1].asString(), str(rm[2]), rm[3])
                recipe += "\n"
                tries += 1

            sys.stderr.flush()
            sys.stdout.flush()

            if not ret:
                raise RuntimeError("Conflicts which couldn't be automatically "
                                   "corrected have occured:\n%s " % \
                                   '\n'.join(\
                    ['\n'.join([z[0] + "=" + str(z[1]) + "[" + str(z[2]) + "]"\
                               for z in y]) for y in [x[0] \
                                                      for x in conflicts]]))

            ret = ret[0][0]
        finally:
            try:
                os.chdir(curDir)
            except:
                pass
            util.rmtree(path)

        if ret:
            return ret[0], ret[1], ret[2].freeze()
        else:
            return None
