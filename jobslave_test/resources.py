#
# Copyright (c) SAS Institute Inc.
#


import os


def get_path(*subpath):
    return os.path.join(_test_root, *subpath)


def get_archive(*subpath):
    return get_path('jobslave_test', 'archive', *subpath)


def _get_test_root():
    modname = __name__.split('.')
    modroot = os.path.abspath(__file__)
    while modname:
        modroot = os.path.dirname(modroot)
        modname.pop()
    return modroot
_test_root = _get_test_root()
