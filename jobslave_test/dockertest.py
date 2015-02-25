#
# Copyright (c) SAS Institute Inc.
#

import json
import os
from testutils import mock

from jobslave.job_data import JobData
from jobslave.generators import docker
from jobslave_test.jobslave_helper import JobSlaveHelper
from conary.deps import deps

class DockerTest(JobSlaveHelper):
    def _mock(self, img, dockerBuildTree, withURLOpener=False):
        self.data['data'].update(dockerBuildTree=json.dumps(dockerBuildTree))
        self.slaveCfg.conaryProxy = "http://[fe80::250:56ff:fec0:1]/conary"
        origLogCall = docker.logCall
        logCallArgs = []
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
        docker.util.mkdirChain(extractedLayerDir)
        file(os.path.join(extractedLayerDir, "dummy"), "w").write("dummy")
        layerDir = os.path.join(self.workDir, "tests", dockerBuildTree['dockerImageId'])
        docker.util.mkdirChain(layerDir)
        docker.logCall(["tar", "-C", extractedLayerDir, "-cf",
                os.path.join(layerDir, "layer.tar"), "."])
        parentImage = os.path.join(self.workDir, "tests", "parent.tar.gz")
        docker.logCall(["tar", "-C", os.path.join(self.workDir, "tests"),
                "-zcf", parentImage, dockerBuildTree['dockerImageId']])

        class URLOpener(object):
            def __init__(slf, *args, **kwargs):
                pass
            def open(slf, url):
                f = file(parentImage)
                # Make sure we don't download it again
                os.unlink(parentImage)
                return f

        self.mock(docker, 'URLOpener', URLOpener)


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
                        '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/layer.tar',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/VERSION',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/json',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/layer.tar',
                        'repositories',
                        ],
                    [
                        '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800',
                        '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800/layer.tar',
                        '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313',
                        '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313/VERSION',
                        '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313/json',
                        '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313/layer.tar',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/VERSION',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/json',
                        '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/layer.tar',
                        'repositories',
                        ],
                    ],
                )


        self.assertEquals(
                [x[0] for x in img.postOutput._mock.calls],
                [
                    ((('%s/mint.rpath.local-build-25/bar-64bit.tar.gz' % docker.constants.finishedDir, 'Tar File'),),),
                    ((('%s/mint.rpath.local-build-25/baz-64bit.tar.gz' % docker.constants.finishedDir, 'Tar File'),),),
                    ]
                )
        self.assertEquals(
                [x[1] for x in img.postOutput._mock.calls],
                [
                    (
                        ('attributes', {'docker_image_id': '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972'}),
                        ('forJobData', dockerBuildTree['children'][0]['buildData']),
                        ),
                    (
                        ('attributes', {'docker_image_id': '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313'}),
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
        manifest = json.load(file('/tmp/mint.rpath.local-build-25/docker-image/layers/18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313/json'))
        self.assertEquals(manifest.get('author'), None)
        self.assertEquals(manifest['config']['ExposedPorts'],
                {'443/tcp' : {}, '80/tcp' : {}})
        self.assertEquals(manifest['Comment'],
                "Created by Conary command: conary update 'group-baz=/my.example.com@ns:1/3-1-1[is: x86_64]'")

        manifest = json.load(file('/tmp/mint.rpath.local-build-25/docker-image/layers/5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972/json'))
        self.assertEquals(manifest.get('author'), 'jean.valjean@paris.fr')
        self.assertEquals(manifest['config']['ExposedPorts'],
                {'80/tcp': {}})
        self.assertEquals(manifest['Comment'],
                "Created by Conary command: conary update 'group-bar=/my.example.com@ns:1/2-1-1[is: x86_64]'")
        repos = json.load(file('/tmp/mint.rpath.local-build-25/docker-image/layers/repositories'))
        self.assertEquals(repos, {
            'repository-for-bar/bar': {
                '2-1-1': '5414b567e26c01f2032e41e62a449fd2781f26011721b2b7cb947434c080c972',
                },
            'appeng-test/foo': {
                '1-1-1': '131ae464fe41edbb2cea58d9b67245482b7ac5d06fd72e44a9d62f6e49bac800',
                },
            'repository-for-baz/baz': {
                '3-1-1': '18723084021be3ea9dd7cc38b91714d34fb9faa464ea19c77294adc8f8453313',
                },
            })

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
        I = docker.DockerfileInstruction
        df = docker.Dockerfile()
        df.parse(txt)
        items = df._directives.items()
        self.assertEquals(sorted(items),
                [
                    ('CMD', I('CMD', '/usr/sbin/httpd -X')),
                    ('EXPOSE', [ I('EXPOSE', ['80']),
                        I('EXPOSE', '443/tcp'),
                        I('EXPOSE', ['53/udp', '211/tcp']),
                        ]),
                    ('FROM', I('FROM', 'aaa')),
                    ('MAINTAINER', I('MAINTAINER', 'jean.valjean@paris.fr')),
                    ])
        self.assertEquals(df.exposedPorts, ['211/tcp', '443/tcp', '53/udp', '80/tcp', ])
        self.assertEquals(df.entrypoint, None)
        self.assertEquals(df.cmd, ['/bin/sh', '-c', '/usr/sbin/httpd -X'])

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
"""
        df1 = docker.Dockerfile()
        df1.parse(txt)

        txt = """
MAINTAINER insp.javert@paris.fr
CMD /usr/sbin/a
EXPOSE "443/tcp"
EXPOSE 211
"""
        df2 = docker.Dockerfile()
        df2.parse(txt)
        df1.merge(df2)
        self.assertEquals(df1.exposedPorts, ['211/tcp', '443/tcp', '80/tcp', ])
        self.assertEquals(df1.author, 'jean.valjean@paris.fr')

        manifest = {}
        df1.toManifest(manifest)
        self.assertEqual(manifest, {
            'config': {
                'Cmd': ['-X'],
                'Entrypoint': ['/usr/sbin/httpd'],
                'ExposedPorts': { '211/tcp' : {}, '443/tcp' : {}, '80/tcp' : {}},
                },
            'author': 'jean.valjean@paris.fr'
            })
