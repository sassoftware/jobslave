#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

class JobSlaveError(Exception):
    pass

class ProtocolError(JobSlaveError):
    def __init__(self, msg = "Protocol Error"):
        self.msg = msg
    def __str__(self):
        return self.msg

