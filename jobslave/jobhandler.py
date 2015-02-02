from jobslave.generators.installable_iso import InstallableIso
from jobslave.generators.raw_hd_image import RawHdImage
from jobslave.generators.vmware_image import VMwareImage, VMwareESXImage
from jobslave.generators.raw_fs_image import RawFsImage
from jobslave.generators.tarball import Tarball
from jobslave.generators.vpc import VirtualPCImage
from jobslave.generators.xen_ova import XenOVA
from jobslave.generators.virtual_iron import VirtualIronVHD
from jobslave.generators.update_iso import UpdateIso
from jobslave.generators.appliance_iso import ApplianceInstaller
from jobslave.generators.ami import AMIImage
from jobslave.generators.docker import DockerImage

from jobslave import buildtypes

jobHandlers = {
    buildtypes.INSTALLABLE_ISO:   InstallableIso,
    buildtypes.RAW_HD_IMAGE:      RawHdImage,
    buildtypes.VMWARE_IMAGE:      VMwareImage,
    buildtypes.VMWARE_ESX_IMAGE:  VMwareESXImage,
    buildtypes.RAW_FS_IMAGE:      RawFsImage,
    buildtypes.TARBALL:           Tarball,
    buildtypes.VIRTUAL_PC_IMAGE:  VirtualPCImage,
    buildtypes.XEN_OVA:           XenOVA,
    buildtypes.VIRTUAL_IRON:      VirtualIronVHD,
    buildtypes.UPDATE_ISO:        UpdateIso,
    buildtypes.APPLIANCE_ISO:     ApplianceInstaller,
    buildtypes.AMI:               AMIImage,
    buildtypes.DOCKER_IMAGE:      DockerImage,
}


class InvalidBuildType(Exception):
    def __init__(self, buildType):
        self._buildType = buildType

    def __str__(self):
        return "Invalid build type: %d" % self._buildType


def getHandler(cfg, jobData):
    if jobData['type'] == 'build':
        handlerClass = jobHandlers.get(jobData['buildType'])
        if handlerClass:
            return handlerClass(cfg, jobData)

    raise InvalidBuildType(jobData['buildType'])
