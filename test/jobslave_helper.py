#!/usr/bin/python2.4
#
# Copyright (c) 2006-2007 rPath, Inc.
#
# All rights reserved
#

import os, sys
import testhelp
from jobslave import jobhandler

class DummyConnection(object):
    def __init__(self, *args, **kwargs):
        self.sent = []
        self.listeners = []
        self.subscriptions = []
        self.unsubscriptions = []
        self.acks = []

    def send(self, dest, message):
        self.sent.insert(0, (dest, message))

    def receive(self, message):
        for listener in self.listeners:
            listener.receive(message)

    def subscribe(self, dest, ack = 'auto'):
        assert ack == 'client', 'Queue will not be able to refuse a message'
        self.subscriptions.insert(0, dest)

    def unsubscribe(self, dest):
        self.unsubscriptions.insert(0, dest)

    def addlistener(self, listener):
        if listener not in self.listeners:
            self.listeners.append(listener)

    def dellistener(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def start(self):
        pass

    def ack(self, messageId):
        self.acks.append(messageId)

    def insertMessage(self, message):
        message = 'message-id: dummy-message\n\n\n' + message
        self.receive(message)

    def disconnect(self):
        pass

class DummyResponse(object):
    response = DummyConnection()

class JobSlaveHelper(testhelp.TestCase):
    def getHandler(self, buildType):
        return jobhandler.getHandler( \
            {'serialVersion': 1,
             'type' : 'build',
             'project' : {'name': 'Foo',
                          'hostname' : 'foo',
                          'label': 'foo.rpath.local@rpl:devel',
                          'conaryCfg': ''},
             'name' : 'Foo',
             'UUID' : 'mint.rpath.local-build-25',
             'troveName' : 'group-core',
             'troveVersion' : '/conary.rpath.com@rpl:1/0:1.0.1-1-1',
             'troveFlavor': '1#x86',
             'data' : {'jsversion': '3.0.0'},
             'outputQueue': 'test',
             'buildType' : buildType},
            DummyResponse())

    def supressOutput(self, func, *args, **kwargs):
        oldErr = os.dup(sys.stderr.fileno())
        oldOut = os.dup(sys.stdout.fileno())
        fd = os.open(os.devnull, os.W_OK)
        os.dup2(fd, sys.stderr.fileno())
        os.dup2(fd, sys.stdout.fileno())
        os.close(fd)
        try:
            return func(*args, **kwargs)
        finally:
            os.dup2(oldErr, sys.stderr.fileno())
            os.dup2(oldOut, sys.stdout.fileno())
