#
# Copyright (c) 2010-2012 rPath, Inc.
#
# All Rights Reserved
#

import logging
log = logging.getLogger(__name__)

from jobslave import buildtypes
from jobslave.generators import tarball


class AMIImage(tarball.Tarball):
    fileType = buildtypes.typeNames[buildtypes.AMI]
