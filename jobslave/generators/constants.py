#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


## Paths
dataDir             = '/usr/share/jobslave'
anacondaImagesPath  = dataDir + '/pixmaps'
entDir              = dataDir + '/entitlements'
fallbackDir         = dataDir + '/fallback'
scriptPath          = dataDir + '/scripts'
skelDir             = dataDir + '/skel'
templateDir         = dataDir + '/templates'
#finishedDir         = dataDir + '/finished-images'

tmpDir              = '/tmp'
anacondaTemplatesPath = tmpDir + '/anaconda-templates'
cachePath           = tmpDir + '/changesets'
finishedDir         = tmpDir + '/finished-images'

implantIsoMd5 = '/usr/bin/implantisomd5'
templatesLabel = 'conary.rpath.com@rpl:1'

# ovf related constants
OVF_EXTENSION = 'ovf'
OVA_EXTENSION = 'ova'
MF_EXTENSION = 'mf'


VMDK, VHD, RAWFS, RAWHD = range(1, 5)
DISKFORMATURLS = {
    VMDK : 'http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized',
    RAWFS : 'http://wiki.rpath.com/wiki/rBuilder_Online:Raw_Filesystem_Image',
    RAWHD : 'http://wiki.rpath.com/wiki/rBuilder_Online:Raw_Hard_Disk_Image',
    VHD  : 'http://www.microsoft.com/technet/virtualserver/downloads/vhdspec.mspx'
}

NETWORKSECTIONINFO = 'List of logical networks used in the package'
DISKSECTIONINFO = 'Describes the set of virtual disks'
VIRTUALHARDWARESECTIONINFO = 'Describes the set of virtual hardware'
FILECOMPRESSION = 'gzip'
OVFIMAGETAG = 'OVF 1.0 Image'
