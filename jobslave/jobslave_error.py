#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

class JobSlaveError(Exception):
    pass

class KernelTroveRequired(JobSlaveError):
    def __str__(self):
        return "Your group must include a kernel for proper operation."
