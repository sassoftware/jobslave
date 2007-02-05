import os
import SocketServer
import BaseHTTPServer
import SimpleHTTPServer
import threading
import posixpath
import urllib
import socket

TIMEOUT = 3

class ServerStopped(Exception):
    pass

class ImageHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    basePath = None

    def translate_path(self, path):
        """Code copied from base class. altered os.getcwd() so that images
        could be served without altering cwd"""
        path = posixpath.normpath(urllib.unquote(path))
        words = path.split('/')
        words = filter(None, words)
        path = self.basePath
        for word in words:
            drive, word = os.path.splitdrive(word)
            head, word = os.path.split(word)
            if word in (os.curdir, os.pardir): continue
            path = os.path.join(path, word)
        return path

    def list_directory(self, path):
        # Returning None indicates an error occured.
        # We don't want to allow directory listing.
        self.send_error(404, "File not found")


class ImageServer(threading.Thread, SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self)
        BaseHTTPServer.HTTPServer.__init__(self, *args, **kwargs)
        self.running = True
        self.lock = threading.RLock()
        self.socket.settimeout(TIMEOUT)

    def get_request(self):
        #conn, addr = self.socket.accept()
        #return conn, addr
        running = True
        while running:
            # Using exceptions like this is tacky. if there were a better method
            # we'd be using it. that's why the socket timeout is in seconds.
            try:
                return self.socket.accept()
            except socket.timeout:
                self.lock.acquire()
                running = self.running
                self.lock.release()
        # we implement a custom defined exception so that we're guaranteed to
        # skip the entire call stack and safely abort in the thread's run method
        raise ServerStopped

    def run(self):
        try:
            while True:
                self.handle_request()
        except ServerStopped:
            pass

    def stop(self):
        self.lock.acquire()
        self.running = False
        self.lock.release()
        self.join()

def getServer(basePath):
    # due to the roundabout mechanisms here we need to modify the actual class
    # definition. This means only one imgserver instance can exist at a time.
    # unless all imgservers can agree on what the base path is.
    ImageHandler.basePath = basePath

    started = False
    for port in range(8000, 8100):
        try:
            server = ImageServer(('', port), ImageHandler)
        except socket.error, e:
            if e.args[0] != 98:
                raise
        else:
            break
    server.start()

    return server
