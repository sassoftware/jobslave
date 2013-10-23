#
# Copyright (c) SAS Institute Inc.
#

import os
import random
import time
from jobslave import lvm
from jobslave_test import resources
from jobslave_test.jobslave_helper import JobSlaveHelper


class LVMTest(JobSlaveHelper):

    def testNames(self):
        image = os.path.join(self.workDir, 'test.img')
        container = lvm.LVMContainer(totalSize=20*1024*1024, image=image)
        self.assertEqual(container.lvname('', 'swap'), 'swap')
        self.assertEqual(container.lvname('', 'swap'), 'swap2')
        self.assertEqual(container.lvname('/', 'ext4'), 'root')
        self.assertEqual(container.lvname('/srv', 'ext4'), 'srv')
        self.assertEqual(container.lvname('/srv/foo', 'ext4'), 'srvfoo')
        self.assertEqual(container.lvname('/sr/vfoo', 'ext4'), 'srvfoo2')

    def testLVMContainer(self):
        self.mock(time, 'time', lambda: 0)
        self.mock(random, 'choice', lambda items: items[0])
        image = os.path.join(self.workDir, 'test.img')
        container = lvm.LVMContainer(totalSize=20*1024*1024, image=image)

        container.addFilesystem('/', 'ext3', 10*1024*1024)
        container.addFilesystem('swap1', 'swap', 9*1024*1024)
        self.assertRaises(lvm.LVMOverflowError,
                container.addFilesystem, 'swap2', 'swap', 1)
        self.assertEqualWithDiff(container.getMetadata(), """\
vg00 {
id = "000000-0000-0000-0000-0000-0000-000000"
seqno = 1
format = "lvm2" # informational
status = ["RESIZEABLE", "READ", "WRITE"]
flags = []
extent_size = 2048
max_lv = 0
max_pv = 0
metadata_copies = 0

physical_volumes {

pv0 {
id = "000000-0000-0000-0000-0000-0000-000000"
device = "/dev/sda2"

status = ["ALLOCATABLE"]
flags = []
dev_size = 20971520
pe_start = 2048
pe_count = 19
}
}

logical_volumes {

root {
id = "000000-0000-0000-0000-0000-0000-000000"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_host = "localhost.localdomain"
creation_time = 0
segment_count = 1

segment1 {
start_extent = 0
extent_count = 10

type = "striped"
stripe_count = 1\t# linear

stripes = [
"pv0", 0
]
}
}

swap1 {
id = "000000-0000-0000-0000-0000-0000-000000"
status = ["READ", "WRITE", "VISIBLE"]
flags = []
creation_host = "localhost.localdomain"
creation_time = 0
segment_count = 1

segment1 {
start_extent = 0
extent_count = 9

type = "striped"
stripe_count = 1\t# linear

stripes = [
"pv0", 10
]
}
}


}
}
contents = "Text Format Volume Group"
version = 1
description = ""
creation_host = "localhost.localdomain"
creation_time = 0
# Created by SAS App Engine
""")

        container.unmount()

        expected = os.popen("xxd " + resources.get_archive('lvm.dsk')).read()
        actual = os.popen("xxd " + image).read()
        self.assertEqualWithDiff(actual, expected)
