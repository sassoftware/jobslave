#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import testsuite
testsuite.setup()

import jobslave_helper

from jobslave import buildtypes
from mint import buildtypes as refbuildtypes

class ConstantsTest(jobslave_helper.JobSlaveHelper):
    def testCompareTypes(self):
        if buildtypes.validBuildTypes != refbuildtypes.validBuildTypes:
            types = set(buildtypes.validBuildTypes.iteritems())
            reftypes = set(refbuildtypes.validBuildTypes.iteritems())
            missing = reftypes.difference(types)
            extra = types.difference(reftypes)

            errorStr = ""
            if missing:
                errorStr += ', '.join([x[0] for x in missing]) + \
                    " need%s to be defined" % (len(missing) == 1 and 's' or '')
            if extra:
                if errorStr:
                    errorStr += ' and '
                errorStr += ', '.join([x[0] for x in extra]) + \
                    " need%s to be removed" % (len(extra) == 1 and 's' or '')
            self.failIf(errorStr, errorStr + ". This test can safely be "
                        "disabled if not comparing tip to tip.")


if __name__ == "__main__":
    testsuite.main()
