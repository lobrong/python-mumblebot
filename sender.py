# Imported modules
import argparse
import datetime
import Mumble_pb2
import os
import platform
#import queue #2TO3 Change this
import Queue
import re
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time

import data
config = data.config
msgtype = data.msgtype
msgnum = data.msgnum
#Version of mumble to send to the server: (major, minor, revision).
#This gets packed in a goofy manner
version = (1,2,0)

logmsg = lambda x: x
errmsg = logmsg
debugmsg = logmsg

#Thread to send messages to server
class Sender(threading.Thread):
    socket = None
    txqueue = None
    _running = False
    sendlock = None
    pingdata = None
    pingthread = None
    current_channel = None

    def __init__(self, socket):
        threading.Thread.__init__(self)
        self.socket = socket
        self.txqueue = Queue.Queue()
        self.sendlock = threading.Lock()
        self.pingdata = Mumble_pb2.Ping()
        self.pingdata.resync = 0
    #Wait for messages, send them to the server, expects messages to be
    #ready to put on the wire
    def run(self):
        self.update_logging()
        debugmsg("Sender starting")

        #Send back our version info
        clientversion = Mumble_pb2.Version()
        clientversion.version = struct.unpack(">I", struct.pack(">HBB", *version))[0]
        #TODO: work on a better way to receive error messages from scripts

        clientversion.release = ""#mumblebot-0.0.1"
        clientversion.os = ""#platform.system()
        clientversion.os_version = ""#platform.release()
        self.send(clientversion)
        debugmsg("Sent version info")
        #Send auth info
        authinfo = Mumble_pb2.Authenticate()
        authinfo.username = config["username"]
        if config["password"]:
            authinfo.password = config["password"]
        else:
            authinfo.password = ""
        self.send(authinfo)
        debugmsg("Authenticated as %s with password %s"%(authinfo.username,authinfo.password))

        #TODO: Implement tokens
        #TODO: Timeout on rx of auth message if !mumble server
        #Start the pinger
        self.pingthread = threading.Thread(target=self.send_pings)
        self.pingthread.daemon = True
        self.pingthread.start()

        #Flag to keep running.
        self._running = True
        while self._running:
            #Make sure we're still in business
            msg = self.txqueue.get()
            #Die if we're meant to
            #if msg is None and not self._running:
            #    return
            #Number of bytes sent
            count = 0
            #Keep sending 'till we're done
            res = msg
            while len(res) > 0:
                #Lop of the bits we don't need to send
                count = self.socket.send(res)
                res = res[count:]

    #Special case to send a chat message
    def send_chat_message(self, msg):
        textmessage = Mumble_pb2.TextMessage()
        textmessage.message = msg
        textmessage.channel_id.append(self.current_channel)
        self.send(textmessage)
        return
        
    #Send keepalive pings
    def send_pings(self):
        debugmsg("Pinger starting")
        while True:
            self.send(self.pingdata)
            time.sleep(5)

    #Send a message to the series of tubes.  msg is a protobuf object
    def send(self, msg):
        #Type code
        type = msgnum[msg.__class__.__name__]
        #Format as a series of bytes
        msg = msg.SerializeToString()
        #Size of messages
        size = len(msg)
        #Pack the header
        hdr = struct.pack(">HL", type, size)
        #Send it out
        self.sendlock.acquire()
        self.txqueue.put(hdr+msg)
        self.sendlock.release()
        
    #Stop thread
    def stop(self):
        debugmsg("Stopping Sender")
        self._running = False
        self.txqueue.put(None)


    #------------Logging functions------------
    def update_logging(self):
        errmsg = self._err_to_stderr
        logmsg = self._log_to_stdout
        debugmsg = self._debug_to_stdout

    def _err_to_stderr(self,msg):
        msg = "<E-R>"+str(datetime.datetime.now())+": "+msg
        print >>sys.stderr, msg.encode('utf-8')

    def _log_to_stdout(self,msg):
        msg = "<I-R>"+str(datetime.datetime.now())+": "+msg
        print(msg.encode('utf-8'))

    def _debug_to_stdout(self,msg):
        msg = "<D-R>"+str(datetime.datetime.now())+": "+msg
        print(msg.encode('utf-8'))

#TODO: Set list of entities to which to send: sender.add_id/chan