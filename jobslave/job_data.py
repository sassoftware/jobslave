#
# Copyright (c) 2011 rPath, Inc.
#


BUILD_DEFAULTS = {
        'autoResolve': False,
        'maxIsoSize': '681574400',
        'bugsUrl': 'http://issues.rpath.com/',
        'natNetworking': False,
        'vhdDiskType': 'dynamic',
        'anacondaCustomTrove': '',
        'stringArg': '',
        'mediaTemplateTrove': '',
        'baseFileName': '',
        'vmSnapshots': False,
        'swapSize': 128,
        'betaNag': False,
        'anacondaTemplatesTrove': '',
        'enumArg': '2',
        'vmMemory': 256,
        'installLabelPath': '',
        'intArg': 0,
        'freespace': 250,
        'boolArg': False,
        'mirrorUrl': '',
        'zisofs': True,
        'diskAdapter': 'lsilogic',
        'unionfs': False,
        'showMediaCheck': False,
        'amiHugeDiskMountpoint': '',
        'platformName': '',
        'vmCPUs': 1,
        }


class JobData(dict):

    def getBuildData(self, key):
        value = self.get('data', {}).get(key)
        if value is None:
            value = BUILD_DEFAULTS.get(key)
        return value
