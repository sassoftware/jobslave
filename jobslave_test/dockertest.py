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


import json
import os
from testutils import mock

from jobslave.generators import docker
from jobslave_test.jobslave_helper import JobSlaveHelper
import logging


class DockerTest(JobSlaveHelper):
    def setUp(self):
        super(DockerTest, self).setUp()
        self.origLogHandlers = logging.root.handlers
        logging.root.handlers = []
        self.logFile = os.path.join(self.workDir, "build.log")
        logging.basicConfig(filename=self.logFile, filemode="w",
                format="%(filename)s/%(funcName)s: %(message)s", level=logging.DEBUG)

    def tearDown(self):
        for handler in logging.root.handlers:
            handler.close()
        logging.root.handlers = self.origLogHandlers
        super(DockerTest, self).tearDown()

    def _mock(self, img, dockerBuildTree, withURLOpener=False):
        self.data['data'].update(dockerBuildTree=json.dumps(dockerBuildTree))
        self.slaveCfg.conaryProxy = "http://[fe80::250:56ff:fec0:1]/conary"
        origLogCall = docker.logCall
        self.logCallArgs = logCallArgs = []
        def mockLogCall(cmd, **kw):
            logCallArgs.append((cmd, kw))
            if cmd[0].startswith('mount') or cmd[0].startswith('umount'):
                return
            return origLogCall(cmd, **kw)
        self.mock(docker, 'logCall', mockLogCall)
        mock.mockMethod(img.downloadChangesets)
        mock.mockMethod(img.postOutput)
        mock.mockMethod(img.status)
        mock.mockMethod(img.installFilesInExistingTree)

        imgNames = []
        stack = [ dockerBuildTree ]
        while stack:
            top = stack.pop()
            if top.get('url') is None:
                imgNames.append(img.sanitizeBaseFileName(top['buildData']['name']))
            stack.extend(top.get('children', []))
        imgNames.sort()
        tarballs = [ os.path.join(docker.constants.finishedDir, img.UUID,
                x + '.tar.gz') for x in imgNames ]
        if withURLOpener:
            self._mockURLOpener(img, dockerBuildTree)
        return tarballs

    def _mockURLOpener(self, img, dockerBuildTree):
        extractedLayerDir = os.path.join(self.workDir, "tests", "uncompressed-layer")
        layersDir = os.path.join(self.workDir, 'tests', 'layers')
        docker.util.mkdirChain(extractedLayerDir)
        file(os.path.join(extractedLayerDir, "dummy"), "w").write("dummy")
        dockerImageIds = [ dockerBuildTree['dockerImageId'] ]
        fakeParents = [(x['id'], x) for x in
                dockerBuildTree.get('_fakeParents', [])]
        dockerImageIds.extend(x[0] for x in fakeParents)

        fakeParents = dict(fakeParents)
        fakeParents[dockerBuildTree['dockerImageId']] = dict(
                manifest=dockerBuildTree.pop('manifest', {}))

        dockerImageIds.reverse()

        parent = None
        repos = {}
        for i, dockerImageId in enumerate(dockerImageIds):
            layerDir = os.path.join(layersDir, dockerImageId)
            docker.util.mkdirChain(layerDir)
            docker.logCall(["tar", "-C", extractedLayerDir, "-cf",
                    os.path.join(layerDir, "layer.tar"), "."])
            # If a manifest is present in the "fake" parents, use it
            meta = fakeParents.get(dockerImageId, {}).get('manifest', {})
            if parent is not None:
                meta['parent'] = parent
            json.dump(meta, file(os.path.join(layerDir, 'json'), "w"))
            repos['my-super-repo/img-%d' % i] = { 'latest' : dockerImageId }
            repos['my-lame-repo/img-%d' % (100+i)] =  { "tag-%02d" % i : dockerImageId }
            # Same name with different tags for different images
            repos.setdefault('my-release-repo/conflict', {})['image-%02d' % i] = dockerImageId
            parent = dockerImageId
        json.dump(repos, file(os.path.join(layersDir, 'repositories'), "w"))
        parentImage = os.path.join(self.workDir, "tests", "parent.tar.gz")
        docker.logCall(["tar", "-C", layersDir,
                "-zcf", parentImage, 'repositories', ] + dockerImageIds)

        def getImage(url):
            f = file(parentImage)
            # Make sure we don't download it again
            os.unlink(parentImage)
            return f
        img.response.getImage = getImage

    def testBaseImage(self):
        dockerBuildTree = dict(
                nvf="group-foo=/my.example.com@ns:1/12345.67:1-1-1[is: x86_64]",
                buildData=self.Data,
                )
        img = docker.DockerImage(self.slaveCfg, self.data)
        tarballs = self._mock(img, dockerBuildTree)

        img.write()
        self.assertEquals(
                [x[0][0] for x in img.installFilesInExistingTree._mock.calls],
                [img.workDir + '/docker-image/unpacked/131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800'])
        self.assertEquals([ sorted(x.name for x in docker.tarfile.open(t)) for t in
            tarballs ],
                [[
                    '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800',
                    '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/VERSION',
                    '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/json',
                    '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/layer.tar',
                    'repositories',
                    ]])

    def testChildImage(self):
        dockerBuildTree = dict(
                nvf="group-foo=/my.example.com@ns:1/12345.67:1-1-1[is: x86_64]",
                url="http://example.com/downloadFile?id=123",
                dockerImageId="131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800",
                buildData=self.Data,
                children=[
                    dict(
                        nvf="group-bar=/my.example.com@ns:1/12345.67:2-1-1[is: x86_64]",
                        buildData=dict(
                            buildId=1001,
                            name='bar-64bit',
                            outputToken='OUTPUT-TOKEN-bar',
                            ),
                        ),
                    ],
                )
        img = docker.DockerImage(self.slaveCfg, self.data)
        tarballs = self._mock(img, dockerBuildTree, withURLOpener=True)

        img.write()

        self.assertEquals(
                [x[0][0] for x in img.installFilesInExistingTree._mock.calls],
                [
                    img.workDir + '/docker-image/unpacked/5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972.ovffs',
                    ])

        self.assertEquals([sorted(x.name for x in docker.tarfile.open(t)) for t in
            tarballs ],
                [[
                    '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800',
                    '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/json',
                    '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/layer.tar',
                    '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972',
                    '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/VERSION',
                    '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/json',
                    '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/layer.tar',
                    'repositories',
                    ]])

        # Call again, just to make sure we don't re-download
        img.write()

    def testDeepChildHierarchy(self):
        dockerBuildTree = dict(
                nvf="group-foo=/my.example.com@ns:1/12345.67:1-1-1[is: x86_64]",
                url="http://example.com/downloadFile?id=123",
                _fakeParents = [
                    dict(
                        id="dockerImageIdFakeParent-1",
                        manifest=dict(
                          config=dict(
                            Env=["FP1=1"], ExposedPorts={"21/ssh":{}}),
                            ),
                          ),
                    dict(
                        id="dockerImageIdFakeParent-0",
                            ),
                    ],
                manifest=dict(config=dict(Entrypoint=["/bin/bash"], Cmd="-x",
                    Env=["FP1=1"], ExposedPorts={"22/ssh":{}})),
                dockerImageId="131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800",
                buildData=self.Data,
                children=[
                    dict(
                        nvf="group-bar=/my.example.com@ns:1/12345.67:2-1-1[is: x86_64]",
                        buildData=dict(
                            buildId=1001,
                            name='bar-64bit',
                            outputToken='OUTPUT-TOKEN-bar',
                            ),
                        children=[
                            dict(
                                nvf="group-baz=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                buildData=dict(
                                    buildId=1002,
                                    name='baz-64bit',
                                    outputToken='OUTPUT-TOKEN-baz',
                                    ),
                                ),
                            ],
                        ),
                    ],
                )
        img = docker.DockerImage(self.slaveCfg, self.data)
        tarballs = self._mock(img, dockerBuildTree, withURLOpener=True)

        img.write()

        self.assertEquals(
                [x[0][0] for x in img.installFilesInExistingTree._mock.calls],
                    [ os.path.join(img.workDir, x) for x in [
                    'docker-image/unpacked/5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972.ovffs',
                    'docker-image/unpacked/18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313.ovffs',
                    ]])

        self.assertEquals([sorted(x.name for x in docker.tarfile.open(t)) for t in tarballs ],
                [
                    [
                        '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800',
                        '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/json',
                        '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/layer.tar',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/VERSION',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/json',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/layer.tar',
                        'dockerImageIdFakeParent-0',
                        'dockerImageIdFakeParent-0/json',
                        'dockerImageIdFakeParent-0/layer.tar',
                        'dockerImageIdFakeParent-1',
                        'dockerImageIdFakeParent-1/json',
                        'dockerImageIdFakeParent-1/layer.tar',
                        'repositories',
                        ],
                    [
                        '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800',
                        '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/json',
                        '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/layer.tar',
                        '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313',
                        '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313/VERSION',
                        '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313/json',
                        '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313/layer.tar',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/VERSION',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/json',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/layer.tar',
                        'dockerImageIdFakeParent-0',
                        'dockerImageIdFakeParent-0/json',
                        'dockerImageIdFakeParent-0/layer.tar',
                        'dockerImageIdFakeParent-1',
                        'dockerImageIdFakeParent-1/json',
                        'dockerImageIdFakeParent-1/layer.tar',
                        'repositories',
                        ],
                    ],
                )


        self.assertEquals(
                [x[0] for x in img.postOutput._mock.calls],
                [
                    ((('%s/%s/bar-64bit.tar.gz' % (docker.constants.finishedDir, img.UUID), 'Tar File'),),),
                    ((('%s/%s/baz-64bit.tar.gz' % (docker.constants.finishedDir, img.UUID), 'Tar File'),),),
                    ]
                )
        calls = img.postOutput._mock.calls
        # Remove created time, since that breaks our comparisons
        for call in calls:
            manif = json.loads(call[1][0][1]['manifest'])
            del manif['created']
            # File ownership makes this unpredictable too
            del manif['checksum']
            call[1][0][1]['manifest'] = json.dumps(manif, sort_keys=True)
        self.assertEquals(
                [x[1] for x in img.postOutput._mock.calls],
                [
                    (
                        ('attributes', {'docker_image_id': '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972', 'installed_size': 40960,
                            'manifest' : '{"Architecture": "amd64", "Comment": "Created by Conary command: conary update \'group-bar=/my.example.com@ns:1/2-1-1[is: x86_64]\'", "Size": 10240, "config": {"Cmd": ["-", "x"], "Entrypoint": ["/bin/bash"], "Env": ["FP1=1", "PATH=/usr/sbin:/usr/bin:/sbin:/bin"], "ExposedPorts": {"22/ssh": {}}}, "container_config": {}, "docker_version": "1.3.2", "id": "5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972", "os": "linux", "parent": "131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800"}'}),
                        ('forJobData', dockerBuildTree['children'][0]['buildData']),
                        ),
                    (
                        ('attributes', {'docker_image_id': '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313', 'installed_size': 51200,
                        'manifest' : '{"Architecture": "amd64", "Comment": "Created by Conary command: conary update \'group-baz=/my.example.com@ns:1/3-1-1[is: x86_64]\'", "Size": 10240, "config": {"Cmd": ["-", "x"], "Entrypoint": ["/bin/bash"], "Env": ["FP1=1", "PATH=/usr/sbin:/usr/bin:/sbin:/bin"], "ExposedPorts": {"22/ssh": {}}}, "container_config": {}, "docker_version": "1.3.2", "id": "18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313", "os": "linux", "parent": "5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972"}'}),
                        ('forJobData', dockerBuildTree['children'][0]['children'][0]['buildData']),
                        ),
                    ])
        self.assertEquals(
                [x[0] for x in img.status._mock.calls],
                [
                    ('Downloading parent image',),
                    ('Unpacking parent image',),
                    ('Creating layer',),
                    ('Creating manifest',),
                    ('Packaging layers',),
                    ('Build done', 300),
                    ('Creating layer',),
                    ('Creating manifest',),
                    ('Packaging layers',),
                    ('Build done', 300),
                    ])
        self.assertEquals(
                [x[1] for x in img.status._mock.calls],
                [
                    (), (), (), (), (),
                    (('forJobData', dockerBuildTree['children'][0]['buildData']),),
                    (), (), (),
                    (('forJobData', dockerBuildTree['children'][0]['children'][0]['buildData']),),
                ])

        repos = json.load(file(img.workDir + '/docker-image/layers/repositories'))
        self.assertEquals(repos, {
            'my-super-repo/img-0': {'latest': 'dockerImageIdFakeParent-0'},
            'appeng/foo': {'1-1-1': '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800'},
            'my-super-repo/img-1': {'latest': 'dockerImageIdFakeParent-1'},
            'appeng/baz': {'3-1-1': '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313'},
            'my-super-repo/img-2': {'latest': '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800'},
            'appeng/bar': {'2-1-1': '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972'},
            'my-lame-repo/img-102': {'tag-02': '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800'},
            'my-lame-repo/img-101': {'tag-01': 'dockerImageIdFakeParent-1'},
            'my-lame-repo/img-100': {'tag-00': 'dockerImageIdFakeParent-0'},
            'my-release-repo/conflict' : {
                'image-00' : 'dockerImageIdFakeParent-0',
                'image-01' : 'dockerImageIdFakeParent-1',
                'image-02' : '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800',
                }
            })

        manif = json.load(file(img.workDir + '/docker-image/layers/5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/json'))
        self.assertEquals(manif['config']['Entrypoint'],
                ['/bin/bash'])
        self.assertEquals(manif['config']['Env'],
                ['FP1=1', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin'])
        self.assertEquals(manif['config']['ExposedPorts'],
                {'22/ssh': {}})

        manif = json.load(file(img.workDir + '/docker-image/layers/18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313/json'))
        self.assertEquals(manif['config']['Env'],
                ['FP1=1', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin'])
        self.assertEquals(manif['config']['ExposedPorts'],
                {'22/ssh': {}})

    def testOverlayfsLimits(self):
        # APPENG-3414
        dockerBuildTree = dict(
                nvf="group-foo=/my.example.com@ns:1/12345.67:1-1-1[is: x86_64]",
                url="http://example.com/downloadFile?id=123",
                _fakeParents = [dict(id="dockerImageIdFakeParent-2"),
                    dict(id="dockerImageIdFakeParent-1")],
                dockerImageId="DockerImageIdFakeParent-0",
                buildData=self.Data,
                children=[
                    dict(
                        nvf="group-A=/my.example.com@ns:1/12345.67:2-1-1[is: x86_64]",
                        buildData=dict(
                            buildId=10,
                            name='A-64bit',
                            outputToken='OUTPUT-TOKEN-A',
                            ),
                        children=[
                            dict(
                                nvf="group-AA=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                buildData=dict(
                                    buildId=100,
                                    name='AA-64bit',
                                    outputToken='OUTPUT-TOKEN-AA',
                                    ),
                                children = [
                                    dict(
                                        nvf="group-AAA=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                        buildData=dict(
                                            buildId=1000,
                                            name='AAA-64bit',
                                            outputToken='OUTPUT-TOKEN-AAA',
                                            ),
                                        children = [
                                            dict(
                                                nvf="group-AAAA=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                                buildData=dict(
                                                    buildId=10000,
                                                    name='AAAA-64bit',
                                                    outputToken='OUTPUT-TOKEN-AAAA',
                                                    ),
                                                ),
                                            dict(
                                                nvf="group-AAAB=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                                buildData=dict(
                                                    buildId=10001,
                                                    name='AAAB-64bit',
                                                    outputToken='OUTPUT-TOKEN-AAAB',
                                                    ),
                                                ),
                                            ],
                                        ),
                                    dict(
                                        nvf="group-AAB=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                        buildData=dict(
                                            buildId=1001,
                                            name='AAB-64bit',
                                            outputToken='OUTPUT-TOKEN-AAB',
                                            ),
                                        ),
                                    ],
                                ),
                            dict(
                                nvf="group-AB=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                buildData=dict(
                                    buildId=101,
                                    name='AB-64bit',
                                    outputToken='OUTPUT-TOKEN-AB',
                                    ),
                                children = [
                                    dict(
                                        nvf="group-ABA=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                        buildData=dict(
                                            buildId=1010,
                                            name='ABA-64bit',
                                            outputToken='OUTPUT-TOKEN-ABA',
                                            ),
                                        children = [
                                            dict(
                                                nvf="group-ABAA=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                                buildData=dict(
                                                    buildId=10100,
                                                    name='ABAA-64bit',
                                                    outputToken='OUTPUT-TOKEN-ABAA',
                                                    ),
                                                ),
                                            dict(
                                                nvf="group-ABAB=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                                buildData=dict(
                                                    buildId=10101,
                                                    name='ABAB-64bit',
                                                    outputToken='OUTPUT-TOKEN-ABAB',
                                                    ),
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ],
                        ),
                    ],
                )
        img = docker.DockerImage(self.slaveCfg, self.data)
        tarballs = self._mock(img, dockerBuildTree, withURLOpener=True)

        img.write()
        lines = [ x for x in file(self.logFile) if x.startswith('docker.py/') ]
        self.assertEquals(''.join(lines), """\
docker.py/_downloadParentImage: Downloading parent image DockerImageIdFakeParent-0
docker.py/_downloadParentImage: Unpacking parent image as .../unpacked/DockerImageIdFakeParent-0
docker.py/_downloadParentImage:   Extracting parent layer dockerImageIdFakeParent-1 on .../unpacked/DockerImageIdFakeParent-0
docker.py/_downloadParentImage:   Extracting parent layer dockerImageIdFakeParent-2 on .../unpacked/DockerImageIdFakeParent-0
docker.py/_downloadParentImage:   Extracting parent layer DockerImageIdFakeParent-0 on .../unpacked/DockerImageIdFakeParent-0
docker.py/writeChild: Building child image A-64bit, layer c6026eee80a1779cf07c46d57e628cf324bbc59f30f01b2c5828a7f7cc80a957
docker.py/mountOverlayFs: Mounting layer c6026eee80a1779cf07c46d57e628cf324bbc59f30f01b2c5828a7f7cc80a957 on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/writeChild: Installing group-A=/my.example.com@ns:1/2-1-1[is: x86_64] into .../unpacked/c6026eee80a1779cf07c46d57e628cf324bbc59f30f01b2c5828a7f7cc80a957.ovffs
docker.py/writeChild: Building child image AA-64bit, layer d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c
docker.py/writeChild: Extracting layer c6026eee80a1779cf07c46d57e628cf324bbc59f30f01b2c5828a7f7cc80a957 on .../unpacked/DockerImageIdFakeParent-0
docker.py/mountOverlayFs: Mounting layer d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/writeChild: Installing group-AA=/my.example.com@ns:1/3-1-1[is: x86_64] into .../unpacked/d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c.ovffs
docker.py/writeChild: Building child image AAA-64bit, layer ba3eb7b677b067cc3e9d96b9ae4cd7a26147bfcafd279216920ac93140a7c8b3
docker.py/mountOverlayFs: Mounting layer d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/mountOverlayFs: Mounting layer ba3eb7b677b067cc3e9d96b9ae4cd7a26147bfcafd279216920ac93140a7c8b3 on top of .../unpacked/d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c.ovffs
docker.py/writeChild: Installing group-AAA=/my.example.com@ns:1/3-1-1[is: x86_64] into .../unpacked/ba3eb7b677b067cc3e9d96b9ae4cd7a26147bfcafd279216920ac93140a7c8b3.ovffs
docker.py/writeChild: Building child image AAAA-64bit, layer 4d23ee7e0cf3673936bae6e79573d66ee5c8b6eda70bf2cb8d4660b6c446d5d9
docker.py/mountOverlayFs: Mounting layer d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/writeChild: Extracting layer ba3eb7b677b067cc3e9d96b9ae4cd7a26147bfcafd279216920ac93140a7c8b3 on .../unpacked/d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c.ovffs
docker.py/mountOverlayFs: Mounting layer 4d23ee7e0cf3673936bae6e79573d66ee5c8b6eda70bf2cb8d4660b6c446d5d9 on top of .../unpacked/d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c.ovffs
docker.py/writeChild: Installing group-AAAA=/my.example.com@ns:1/3-1-1[is: x86_64] into .../unpacked/4d23ee7e0cf3673936bae6e79573d66ee5c8b6eda70bf2cb8d4660b6c446d5d9.ovffs
docker.py/writeChild: Building child image AAAB-64bit, layer 50923db68d510024b722c3f35508636d5bbafe66ff937a530846b1c1e185d4c9
docker.py/mountOverlayFs: Mounting layer d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/writeChild: Extracting layer ba3eb7b677b067cc3e9d96b9ae4cd7a26147bfcafd279216920ac93140a7c8b3 on .../unpacked/d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c.ovffs
docker.py/mountOverlayFs: Mounting layer 50923db68d510024b722c3f35508636d5bbafe66ff937a530846b1c1e185d4c9 on top of .../unpacked/d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c.ovffs
docker.py/writeChild: Installing group-AAAB=/my.example.com@ns:1/3-1-1[is: x86_64] into .../unpacked/50923db68d510024b722c3f35508636d5bbafe66ff937a530846b1c1e185d4c9.ovffs
docker.py/writeChild: Building child image AAB-64bit, layer 48c4efe6960fa63f9b180dfaa9c07f1022da209358dd346958a6d35f6ad51b3b
docker.py/mountOverlayFs: Mounting layer d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/mountOverlayFs: Mounting layer 48c4efe6960fa63f9b180dfaa9c07f1022da209358dd346958a6d35f6ad51b3b on top of .../unpacked/d42a05e6082c032fe6f3316848be3e6bb4918147860f3c2da0f9b0957048bc8c.ovffs
docker.py/writeChild: Installing group-AAB=/my.example.com@ns:1/3-1-1[is: x86_64] into .../unpacked/48c4efe6960fa63f9b180dfaa9c07f1022da209358dd346958a6d35f6ad51b3b.ovffs
docker.py/writeChild: Building child image AB-64bit, layer de97564729559f69824a96665ddb4698982408dd13db98f4616c2fb5ffec0a99
docker.py/mountOverlayFs: Mounting layer de97564729559f69824a96665ddb4698982408dd13db98f4616c2fb5ffec0a99 on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/writeChild: Installing group-AB=/my.example.com@ns:1/3-1-1[is: x86_64] into .../unpacked/de97564729559f69824a96665ddb4698982408dd13db98f4616c2fb5ffec0a99.ovffs
docker.py/writeChild: Building child image ABA-64bit, layer 89e7b6f17c593889b68757edd7bdd8efdf373f337c1d275f68faaa38d6133601
docker.py/writeChild: Extracting layer de97564729559f69824a96665ddb4698982408dd13db98f4616c2fb5ffec0a99 on .../unpacked/DockerImageIdFakeParent-0
docker.py/mountOverlayFs: Mounting layer 89e7b6f17c593889b68757edd7bdd8efdf373f337c1d275f68faaa38d6133601 on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/writeChild: Installing group-ABA=/my.example.com@ns:1/3-1-1[is: x86_64] into .../unpacked/89e7b6f17c593889b68757edd7bdd8efdf373f337c1d275f68faaa38d6133601.ovffs
docker.py/writeChild: Building child image ABAA-64bit, layer 8089ffec4b48c8ac03e31974edfd3df6886920fbce323130debf15f23095bd80
docker.py/writeChild: Extracting layer 89e7b6f17c593889b68757edd7bdd8efdf373f337c1d275f68faaa38d6133601 on .../unpacked/DockerImageIdFakeParent-0
docker.py/mountOverlayFs: Mounting layer 8089ffec4b48c8ac03e31974edfd3df6886920fbce323130debf15f23095bd80 on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/writeChild: Installing group-ABAA=/my.example.com@ns:1/3-1-1[is: x86_64] into .../unpacked/8089ffec4b48c8ac03e31974edfd3df6886920fbce323130debf15f23095bd80.ovffs
docker.py/writeChild: Building child image ABAB-64bit, layer 380be0952033bb90c7f7924f1461fc746fea8461f09866e272d9874439cee697
docker.py/mountOverlayFs: Mounting layer 380be0952033bb90c7f7924f1461fc746fea8461f09866e272d9874439cee697 on top of .../unpacked/DockerImageIdFakeParent-0
docker.py/writeChild: Installing group-ABAB=/my.example.com@ns:1/3-1-1[is: x86_64] into .../unpacked/380be0952033bb90c7f7924f1461fc746fea8461f09866e272d9874439cee697.ovffs
""")

    def testDeepHierarchy(self):
        dockerBuildTree = dict(
                nvf="group-foo=/my.example.com@ns:1/12345.67:1-1-1[is: x86_64]",
                dockerImageId="131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800",
                buildData=self.Data,
                children=[
                    dict(
                        nvf="group-bar=/my.example.com@ns:1/12345.67:2-1-1[is: x86_64]",
                        buildData=dict(
                            buildId=1001,
                            name='bar-64bit',
                            outputToken='OUTPUT-TOKEN-bar',
                            data=dict(
                                dockerRepositoryName='repository-for-bar',
                                dockerfile="""
MAINTAINER jean.valjean@paris.fr
EXPOSE 80
ENTRYPOINT [ "/usr/bin/a" ]
CMD [ "-d" ]""",
                                )
                            ),
                        children=[
                            dict(
                                nvf="group-baz=/my.example.com@ns:1/12345.67:3-1-1[is: x86_64]",
                                buildData=dict(
                                    buildId=1002,
                                    name='baz-64bit',
                                    outputToken='OUTPUT-TOKEN-baz',
                                    data = dict(
                                        dockerRepositoryName='repository-for-baz',
                                        dockerfile="""
EXPOSE 443
ENTRYPOINT [ "/usr/bin/b" ]
CMD [ "-d" ]""",)
                                    ),
                                ),
                            ],
                        ),
                    ],
                )
        img = docker.DockerImage(self.slaveCfg, self.data)
        tarballs = self._mock(img, dockerBuildTree, withURLOpener=True)

        img.write()

        self.assertEquals(
                [x[0][0] for x in img.installFilesInExistingTree._mock.calls],
                [ os.path.join(img.workDir, x) for x in [
                    'docker-image/unpacked/131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800',
                    'docker-image/unpacked/5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972.ovffs',
                    'docker-image/unpacked/18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313.ovffs',
                    ]])

        # Look at the json files
        manifest = json.load(file(img.workDir + '/docker-image/layers/18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313/json'))
        self.assertEquals(manifest.get('author'), None)
        self.assertEquals(manifest['config']['ExposedPorts'],
                {'443/tcp' : {}, '80/tcp' : {}})
        self.assertEquals(manifest['Comment'],
                "Created by Conary command: conary update 'group-baz=/my.example.com@ns:1/3-1-1[is: x86_64]'")

        manifest = json.load(file(img.workDir + '/docker-image/layers/5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/json'))
        self.assertEquals(manifest.get('author'), 'jean.valjean@paris.fr')
        self.assertEquals(manifest['config']['ExposedPorts'],
                {'80/tcp': {}})
        self.assertEquals(manifest['Comment'],
                "Created by Conary command: conary update 'group-bar=/my.example.com@ns:1/2-1-1[is: x86_64]'")
        repos = json.load(file(img.workDir + '/docker-image/layers/repositories'))
        self.assertEquals(repos, {
            'repository-for-bar/bar': {
                '2-1-1': '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972',
                },
            'appeng/foo': {
                '1-1-1': '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800',
                },
            'repository-for-baz/baz': {
                '3-1-1': '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313',
                },
            })

    def testWriteLayerWithDeletions(self):
        img = docker.DockerImage(self.slaveCfg, self.data)
        mock.mockMethod(img.status)
        layersDir = os.path.join(img.workDir, "docker-image/layers")
        unpackDir = os.path.join(img.workDir, "docker-image/unpacked")
        explodedDir = os.path.join(self.workDir, "exploded")
        docker.util.mkdirChain(explodedDir)
        regularFilePath = os.path.join(explodedDir, 'regular-file')
        deletedFilePath = os.path.join(explodedDir, 'deleted-file')
        symlinkFile = os.path.join(explodedDir, 'symlink-file')
        file(regularFilePath, "w").write('a')
        file(deletedFilePath, "w")
        os.symlink("regular-file", symlinkFile)

        unpackDir2 = os.path.join(self.workDir, 'unpacked')
        docker.util.mkdirChain(os.path.join(unpackDir2, 'deleted-file'))

        origStat = os.lstat
        def mockStat(fname):
            if fname.endswith('deleted-file'):
                obj = mock.MockObject(st_mode=docker.stat.S_IFCHR,
                        st_rdev=0)
                return obj
            return origStat(fname)
        self.mock(os, 'lstat', mockStat)
        origOpen = os.open
        def mockOpen(fname, mode, perms=0644):
            if fname.endswith('deleted-file'):
                perms = 0755
            return origOpen(fname, mode, perms)
        self.mock(os, 'open', mockOpen)
        def mockMknod(fname, mode, dev):
            file(fname, "w").write("Mocked")
        self.mock(os, 'mknod', mockMknod)

        imgSpec = docker.ImageSpec(name='foo', dockerImageId='aaaa-bb-cc',
                nvf=docker.TroveTuple('group-foo=/cny.tv@ns:1/123.45:1-2-3[is: x86_64]'))

        img.writeLayer(explodedDir, layersDir, imgSpec, withDeletions=True)
        # Make sure we've reverted back to the ovf-marked deleted file
        self.assertEqual(file(deletedFilePath).read(), "Mocked")
        # Make sure the tarball has a .wh.deleted-file
        tarfilePath = os.path.join(layersDir, imgSpec.dockerImageId, 'layer.tar')
        tf = docker.tarfile.open(tarfilePath)
        deleted = [ x for x in tf if x.name == './.wh.deleted-file' ]
        self.assertEqual([ x.mode for x in deleted ], [ 0755 ])

        # Now try to extract the layer
        self.unmock()
        mockTF = mock.MockObject()
        mockTF._mock._dict[0] = mock.MockObject(name='./regular-file')
        mockTF._mock._dict[1] = mock.MockObject(name='./.wh.deleted-file',
                mode=0)
        def mockOpen(fpath):
            return mockTF
        self.mock(docker.tarfile, 'open', mockOpen)
        img._extractLayer(unpackDir2, tarfilePath)
        # We should have only the regular file
        self.assertEqual(sorted(os.listdir(unpackDir2)),
                [ 'regular-file', 'symlink-file', ])

class DockerfileTest(JobSlaveHelper):
    def testParseDockerFile(self):
        txt = """
# THIS is a comment
 FROM aaa
MAINTAINER jean.valjean@paris.fr
CMD /usr/sbin/httpd -X
EXPOSE 80
EXPOSE "443/tcp"
EXPOSE 53/udp 211/tcp
"""
        df = docker.Dockerfile()
        df.parse(txt)
        manif = docker.Manifest()
        df.toManifest(manif)
        self.assertEquals(manif,
            docker.Manifest(
                config=docker.Manifest(
                    Cmd=['/bin/sh', '-c', '/usr/sbin/httpd -X'],
                    ExposedPorts={'211/tcp': {}, '443/tcp': {}, '80/tcp': {},
                        '53/udp': {}},
                    ),
                author="jean.valjean@paris.fr",
            ))

    def testParseDockerFile2(self):
        txt = """
# THIS is a comment
 FROM aaa
MAINTAINER <jean.valjean@paris.fr>
ENTRYPOINT ["/usr/sbin/httpd", "-D", "a b", ]
CMD -X
EXPOSE 80
EXPOSE "443/tcp"
EXPOSE 53/udp 211/tcp
ENV a=1 b=2 \\
        c=3
ENV d=4 # With a comment
ENV e 5
ENV f=6 c 33 g=two\ words h=localhost:80
"""
        df = docker.Dockerfile()
        df.parse(txt)
        self.assertEquals(df.environment,
                ['a=1', 'b=2', 'c=33', 'd=4', 'e=5', 'f=6', 'g=two words',
                    'h=localhost:80'])
        self.assertEquals(df.exposedPorts,
                ['211/tcp', '443/tcp', '53/udp', '80/tcp'])
        self.assertEquals(df.entrypoint, ["/usr/sbin/httpd", "-D", "a b",])

    def testCmdAndEntrypoint(self):
        txt = """
ENTRYPOINT [ "/usr/sbin/httpd" , ]
CMD ["-X"]
"""
        df = docker.Dockerfile().parse(txt)
        self.assertEquals(df.entrypoint, [ "/usr/sbin/httpd" ])
        self.assertEquals(df.cmd, ['-X'])

    def testCmdAndEntrypointInvalid(self):
        txt = """
ENTRYPOINT [ "/usr/sbin/httpd" , ]
CMD "-X"
"""
        df = docker.Dockerfile().parse(txt)
        self.assertEquals(df.entrypoint, [ "/usr/sbin/httpd" ])
        self.assertEquals(df.cmd, ['/bin/sh', '-c', '-X'])

    def testDockerFileMerge(self):
        txt = """
MAINTAINER jean.valjean@paris.fr
ENTRYPOINT [ "/usr/sbin/httpd" ]
CMD [ "-X" ]
EXPOSE 80
EXPOSE "443/tcp"
ENV a=1 b=2
"""
        df1 = docker.Dockerfile()
        df1.parse(txt)

        txt = """
MAINTAINER insp.javert@paris.fr
CMD /usr/sbin/a
EXPOSE "443/tcp"
EXPOSE 211
ENV b=3 c=4
"""
        df2 = docker.Dockerfile()
        df2.parse(txt)

        child = df1.toManifest()
        child.merge(df2.toManifest())
        self.assertEquals(child.exposedPorts,
                {'211/tcp':{},  '443/tcp':{}, '80/tcp':{}, })
        self.assertEquals(child.author, 'jean.valjean@paris.fr')

        self.assertEqual(child, docker.Manifest(
            config = docker.Manifest({
                'Cmd': ['-X'],
                'Entrypoint': ['/usr/sbin/httpd'],
                'ExposedPorts': { '211/tcp' : {}, '443/tcp' : {}, '80/tcp' : {}},
                'Env' : [ "a=1", "b=2", "c=4" ],
                }),
            author = 'jean.valjean@paris.fr',
            ))

    def testDockerFileMerge_Entrypoint_CMD(self):
        # Parent dockerfile, child dockerfile, expected entrypoint, expected cmd
        combinations = [
                ('ENTRYPOINT [ "/bin/echo", "foo" ]', 'CMD [ "/bin/bash" ]',
                    [ "/bin/echo", "foo" ], [ "/bin/bash" ]),
                ('CMD [ "/bin/bash" ]', 'ENTRYPOINT [ "/bin/echo", "foo" ]',
                    [ "/bin/echo", "foo" ], None),
                ('ENTRYPOINT [ "/bin/echo" ]\nCMD ["foo"]', 'CMD [ "/bin/bash" ]',
                    [ "/bin/echo" ], [ "foo", "/bin/bash" ]),
                ('ENTRYPOINT [ "/bin/echo" ]\nCMD ["foo"]',
                    'ENTRYPOINT [ "/bin/echo" ]\nCMD [ "/bin/bash" ]',
                    [ "/bin/echo" ], [ "foo", "/bin/bash" ]),
                ('ENTRYPOINT [ "/bin/echo" ]\nCMD ["foo"]',
                    'ENTRYPOINT [ "/bin/bash" ]\nCMD [ "-x" ]',
                    [ "/bin/bash" ], [ "-x" ]),
                ]
        for parentDF, childDF, expEntrypoint, expCmd in combinations:
            parent = docker.Dockerfile()
            parent.parse(parentDF)
            pManif = parent.toManifest()
            child = docker.Dockerfile()
            child.parse(childDF)
            cManif = child.toManifest()
            cManif.merge(pManif)
            self.assertEquals(cManif.entrypoint, expEntrypoint)
            self.assertEquals(cManif.cmd, expCmd)

        txt = """
CMD [ "/bin/bash" ]
"""
        df1 = docker.Dockerfile()
        df1.parse(txt)

        txt = """
ENTRYPOINT [ "/bin/echo", "foo" ]
"""
        df2 = docker.Dockerfile()
        df2.parse(txt)

        self.assertEquals(df1.cmd, ['/bin/bash', ])
        self.assertEquals(df1.entrypoint, None)

        child = df1.toManifest()
        child.merge(df2.toManifest())
        self.assertEquals(child.cmd, ['/bin/bash', ])
        self.assertEquals(child.entrypoint, [ "/bin/echo", "foo", ])
