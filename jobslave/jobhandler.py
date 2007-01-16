from jobslave.generators.installable_iso import InstallableIso
from jobslave.generators.live_iso import LiveIso
from jobslave.generators.raw_hd_image import RawHdImage
from jobslave.generators.vmware_image import VMwareImage, VMwareESXImage
from jobslave.generators.stub_image import StubImage
from jobslave.generators.netboot_image import NetbootImage
#from jobslave.generators.group_trove import GroupTroveCook
from jobslave.generators.raw_fs_image import RawFsImage
from jobslave.generators.tarball import Tarball
from jobslave.generators.vpc import VirtualPCImage
from jobslave.generators.xen_ova import XenOVA

from jobslave import buildtypes

jobHandlers = {
    buildtypes.INSTALLABLE_ISO:   InstallableIso,
#    buildtypes.STUB_IMAGE:        StubImage,
#    buildtypes.LIVE_ISO:          LiveIso,
    buildtypes.RAW_HD_IMAGE:      RawHdImage,
#    buildtypes.VMWARE_IMAGE:      VMwareImage,
#    buildtypes.VMWARE_ESX_IMAGE:  VMwareESXImage,
#    buildtypes.RAW_FS_IMAGE:      RawFsImage,
#    buildtypes.TARBALL:           Tarball,
#    buildtypes.NETBOOT_IMAGE:     NetbootImage,
#    buildtypes.VIRTUAL_PC_IMAGE:  VirtualPCImage,
}

import threading
import weakref

def getHandler(jobData, response):
    # FIXME: this probably only works for builds
    handlerClass = jobHandlers.get(jobData['buildType'])
    if handlerClass:
        return handlerClass(jobData, response)
    else:
        return None

class JobHandler(threading.Thread):
    def __init__(self, jobData, response):
        self.jobData = jobData
        self.jobId = jobData['UUID']
        self.response = weakref.ref(response)
        threading.Thread.__init__(self)

    def status(self, statusMessage, status = 'running'):
        self.response().jobStatus(self.jobId, status, statusMessage)

    def run(self):
        try:
            self.status('starting')
            self.doWork()
        except Exception, e:
            self.status(str(e), status = 'failed')
            # FIXME: log all exceptions.
        else:
            self.status('Finished', status = 'finished')

    def doWork(self):
        raise NotImplementedError
