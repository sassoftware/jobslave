#
# Copyright (c) 2005-2007 rPath, Inc.
#
# All Rights Reserved
#

import sys

validBuildTypes = {
    'BOOTABLE_IMAGE'   : 0,
    'INSTALLABLE_ISO'  : 1,
    'STUB_IMAGE'       : 2,
    'RAW_FS_IMAGE'     : 3,
    'NETBOOT_IMAGE'    : 4,
    'TARBALL'          : 5,
    'LIVE_ISO'         : 6,
    'RAW_HD_IMAGE'     : 7,
    'VMWARE_IMAGE'     : 8,
    'VMWARE_ESX_IMAGE' : 9,
    'VIRTUAL_PC_IMAGE' : 10,
    'XEN_OVA'          : 11,
    'VIRTUAL_IRON'     : 12,
    'PARALLELS'        : 13,
    'AMI'              : 14,
    'UPDATE_ISO'       : 15,
    'APPLIANCE_ISO'    : 16,
    'IMAGELESS'        : 17,
    }

TYPES = validBuildTypes.values()

# add all the defined image types directly to the module so that the standard
# approach of "buildtypes.IMAGE_TYPE" will result in the expected enum
sys.modules[__name__].__dict__.update(validBuildTypes)

deprecatedBuildTypes = {
    'QEMU_IMAGE' : RAW_HD_IMAGE
    }


#BOOTABLE_IMAGE Should never get stored in the DB and therefore doesn't need a name

# NOTA BENE: Using Latin-1 here is harmful to XML-RPC which expects UTF-8
# Until we figure out the root cause, use "(R)" for registered trademark here.

typeNames = {
    NETBOOT_IMAGE:      "Netboot Image",
    INSTALLABLE_ISO:    "Installable CD/DVD",
    RAW_FS_IMAGE:       "Raw Filesystem Image",
    STUB_IMAGE:         "Stub Image",
    RAW_HD_IMAGE:       "Raw Hard Disk Image",
    VMWARE_IMAGE:       "VMware (R) Virtual Appliance",
    VMWARE_ESX_IMAGE:   "VMware (R) ESX Server Virtual Appliance",
    LIVE_ISO:           "Demo CD/DVD (Live CD/DVD)",
    TARBALL:            "Compressed Tar File",
    VIRTUAL_PC_IMAGE:   "Microsoft (R) VHD Virtual Appliance",
    XEN_OVA:            "Citrix XenServer (TM) Appliance",
    VIRTUAL_IRON:       "Virtual Iron Virtual Appliance",
    PARALLELS:          "Parallels Virtual Appliance",
    AMI:                "Amazon Machine Image (EC2)",
    UPDATE_ISO:         "Update CD/DVD",
    APPLIANCE_ISO:      "Appliance Installable ISO",
    IMAGELESS:          "Online Update",
}

typeNamesShort = {
    NETBOOT_IMAGE:      "Netboot",
    INSTALLABLE_ISO:    "Inst CD/DVD",
    RAW_FS_IMAGE:       "Raw FS",
    STUB_IMAGE:         "Stub",
    RAW_HD_IMAGE:       "HDD",
    VMWARE_IMAGE:       "VMware (R)",
    VMWARE_ESX_IMAGE:   "VMware (R) ESX",
    LIVE_ISO:           "Demo CD/DVD",
    TARBALL:            "Tar",
    VIRTUAL_PC_IMAGE:   "Microsoft (R) VHD",
    XEN_OVA:            "Citrix XenServer (TM)",
    VIRTUAL_IRON:       "Virtual Iron",
    PARALLELS:          "Parallels",
    AMI:                "AMI",
    UPDATE_ISO:         "Update CD/DVD",
    APPLIANCE_ISO:      "Appliance Inst",
    IMAGELESS:          "Online Update",
}

typeNamesMarketing = {
    NETBOOT_IMAGE:      "Netboot Image",
    INSTALLABLE_ISO:    "Installable CD/DVD",
    RAW_FS_IMAGE:       "Mountable Filesystem",
    STUB_IMAGE:         "Stub Image",
    RAW_HD_IMAGE:       "Parallels, QEMU (Raw Hard Disk)",
    VMWARE_IMAGE:       "VMware (R) Virtual Appliance",
    VMWARE_ESX_IMAGE:   "VMware (R) ESX Server Virtual Appliance",
    LIVE_ISO:           "Demo CD/DVD (Live CD/DVD)",
    TARBALL:            "TAR File",
    VIRTUAL_PC_IMAGE:   "Microsoft (R) VHD",
    XEN_OVA:            "Citrix XenServer (TM) Appliance",
    VIRTUAL_IRON:       "Virtual Iron Virtual Appliance",
    PARALLELS:          "Parallels Virtual Appliance",
    AMI:                "Amazon Machine Image (EC2)",
    UPDATE_ISO:         "Update CD/DVD",
    APPLIANCE_ISO:      "Appliance Installable ISO",
    IMAGELESS:          "Online Update",
}
