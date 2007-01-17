#
# Copyright (c) 2007 rPath, Inc.
#
# All rights reserved
#

# manifest is a list of relative paths to include in teh data tarball
manifest = ['templates', 'skel', 'pixmaps']

import os
from jobslave import constants

# do standard setuptools inclusion
from setuptools import setup, find_packages
setup(
    name = "jobslave",
    version = constants.version,
    packages = find_packages(),
)

# include data separately to avoid complicated setuptools rules
os.system('tar -czvO %s > "dist/jobslave-data-%s.tar.gz"' % \
              ('"' + '" "'.join(manifest) + '"', constants.version))
