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

logmsg = lambda x: x
errmsg = logmsg
debugmsg = logmsg

#Thread that handles receiving messages
class Receiver(threading.Thread):
    socket = None
    sender = None
    _running = False
    rxbytes = None #DEBUG

    #Keep ahold of the channels and users on the server
    channels = {}
    orphans = {} #Orphaned channels, same format as above
    users = {}
    services = [] # Keep track of running services, like trivia-bots!
    channellock = None
    current_channel = None

    #Variables relevant to printing channels/users
    channelwait = None
    userwait = None
    channeltimer = None
    usertimer = None
    userevent = None
    

    def __init__(self, socket, sender):
        threading.Thread.__init__(self)
        self.sender = sender
        self.socket = socket
        self.daemon = True
        self.channellock = threading.Lock()


    #Wait for messages, act on them as appropriate
    def run(self):
        self.update_logging()
        debugmsg("Receiver starting")

        _running = True
        while _running:
            #Get the six header bytes
            header = self.recvsize(6)
            #Unpack the header
            (type, size) = struct.unpack(">HL", header)
            data = self.recvsize(size)
            typename = msgtype[type].__name__
            print("Got {}-byte {} message".format(size, typename))
            #Handle each message, this is going to get inefficient.
            try:
                {"Version":         self.onVersion,
                 "ChannelState":    self.onChannelState,
                 "UserState":       self.onUserState,
                 "TextMessage":     self.onTextMessage,
                 "Reject":          self.onReject,
                }[typename](data)
            except KeyError as ke:
                #debugmsg("{} message unhandled".format(typename)) #DEBUG
                pass
            if(self.current_channel != None):
                self.sender.current_channel = self.current_channel

    def onVersion(self, data):
        serverversion = Mumble_pb2.Version()
        #CamelCase, ReaLly?
        serverversion.ParseFromString(data)
        (major, minor, revision) = struct.unpack('>HBB',
            struct.pack('>I', serverversion.version))
        logmsg("Server {}.{}.{} {} ({}: {})".format(major, minor, revision,
                                                    serverversion.release,
                                                    serverversion.os,
                                                    serverversion.os_version))

    def onChannelState(self, data):
        #If we're still collecting channels, reset the timeout
        if self.channelwait is not None and self.channeltimer is not None:
            self.channeltimer.cancel()
            self.channeltimer = None
        #If we're just printing channels, start the timer
        if self.channelwait is not None and self.channeltimer is None:
            self.channeltimer = threading.Timer(self.channelwait,
                                                self.printchannels)
            self.channeltimer.start()

        #Unroll the data
        channelstate = Mumble_pb2.ChannelState()
        channelstate.ParseFromString(data)
        #Lock the channel tree
        self.channellock.acquire()
        #Root channel
        if channelstate.channel_id == 0:
            #If it's the first time we've seen it
            if 0 not in self.channels:
                self.channels[0] = Channel()
                self.channels[0].name = channelstate.name
            #If not, update the name
            else:
                self.channels[0].name = channelstate.name
        #Regular channels, new channel
        elif channelstate.channel_id not in self.channels:
            t = Channel()
            t.name = channelstate.name
            t.parent = channelstate.parent
            #Check for a list of orphans for which this is the parent
            if channelstate.channel_id in self.orphans:
                for c in self.orphans[channelstate.channel_id]:
                    if c not in t.children:
                        t.children.add(c)
            #If the parent is there, add it to the parent's children
            if channelstate.parent in self.channels:
                self.channels[channelstate.parent].children.add(channelstate.channel_id)
            #If not, add it to the list of orphans for that child
            else:
                if t.channel_id not in self.orphans:
                    self.orphans[t.parent] = []
                self.orphans[t.parent].add(self.channel_id)
            #Add the channel to the list
            self.channels[channelstate.channel_id] = t
            debugmsg("Added new channel %s [%i:%i]"%(t.name, t.parent,
                                                     channelstate.channel_id))
        #If we have the channel, update it
        else:
            #Update the name
            if channelstate.name and (self.channels[channelstate.channel_id] != channelstate.name):
                oldname = self.channels[channelstate.channel_id].name
                self.channels[channelstate.channel_id].name = channelstate.name
                debugmsg("Changed channel %i's name from %s to %s"%(
                    channelstate.channel_id, oldname, channelstate.name))
            #Update the parent
            if self.channels[channelstate.channel_id].parent != channelstate.parent:
                #Remove the channel from the old parent's list of children
                oldpid = self.channels[channelstate.channel_id].parent
                self.channels[oldpid].children.remove(channelstate.channel_id)
                #Add it to the new parent's list of children, if we can
                if channelstate.parent in self.channels:
                    self.channels[channelstate.parent].children.add(channelstate.channel_id)
                #Failing that, it's an orphan
                else:
                    self.orphans.add(channelstate.channel_id)
                debugmsg("Changed channel %i's (%s) parent from %i to %i"
                         %(channelstate.channel_id,
                           self.channels[channelstate.channel_id].name,
                           oldpid, channelstate.parent))
        #Join the right channel when we learn about it
        to_join = None
        #If we're meant to be in root, join it
        if config["channel"] == "/" and 0 in self.channels:
            to_join = 0
        #If we're given a channel number, join it when we get it
        elif config["channel"].isdigit() and \
                int(config["channel"]) in self.channels:
            to_join = int(config["channel"])
        #If we're given a path, join it
        elif config["channel"][0] == "/" and len(config["channel"]) > 1 and 0 in self.channels:
            #Get a list of channel bits.
            #Sucks if there's a / in the channel name
            channel_path = filter(None, config["channel"].split("/")[1:])
            #If the first part is the name of the root channel, remove it
            if channel_path[0] == self.channels[0].name:
                channel_path = channel_path[1:]
            #We're at where in the tree.  If there's no more path to descend,
            #return the name of the channel we're in.  Else, descend deeper.
            #Failing that, return None
            def _traverse_tree(self, channel_path, where):
                #We've found the last element
                if len(channel_path) == 0:
                    return where
                #If not, see if the next element is a known child
                else:
                    for p in self.channels[where].children:
                        #When we've found the child, recurse
                        if self.channels[p].name == channel_path[0]:
                            return _traverse_tree(self, channel_path[1:], p)
            #Find the id of the channel to join
            to_join = _traverse_tree(self, channel_path, 0)
        #If we're not already there, join the channel
        if to_join is not None and to_join != self.current_channel:
            userstate = Mumble_pb2.UserState()
            userstate.channel_id = to_join
            self.sender.send(userstate)
            self.current_channel = to_join
            self.sender.current_channel = to_join
            logmsg("Joined [c%i] %s"%(to_join, self.channels[to_join].name))
        self.channellock.release()

    def onUserState(self, data):
        #If we're still collecting users, reset the timeout
        if self.userwait is not None and self.usertimer is not None:
            self.usertimer.cancel()
            self.usertimer = None
        #If we're just printing users, start the timer
        if self.userwait is not None and self.usertimer is None:
            self.usertimer = threading.Timer(self.userwait, self.printusers)
            self.usertimer.start()
        #Unroll the data
        userstate = Mumble_pb2.UserState()
        userstate.ParseFromString(data)
        #Make sure the user is in the list
        self.users[userstate.session] = (userstate.channel_id, userstate.name,
                                        userstate.session)
        wah = userstate.user_id
        if(wah!=None):
            print "User ID:" + str(wah) + " Name:" + str(userstate.name)
    #Handle messages
    def onTextMessage(self, data):
        textmessage = Mumble_pb2.TextMessage()
        textmessage.ParseFromString(data)
        print "Message: %s from [%i] %s"%(textmessage.message,textmessage.actor,self.users[textmessage.actor][1])

        #If the message doesn't start with the trigger, we don't care about it.
        if not textmessage.message.startswith(config["trigger"]):
            return
        
        #message is of format <trigger><service> <message>
        triggerLength = len(config["trigger"])
        specific = textmessage.message.split(" ")
        nameToSend = specific[0][triggerLength:]
        print nameToSend
        for t in self.services:
            if(t.name == nameToSend):
                t.recv(textmessage.message,textmessage.actor,self.users[textmessage.actor][1])

    #Receive a specified number of bytes
    def recvsize(self, size):
        buf = ""
        while len(buf) < size:
            tmp = ""
            tmp = self.socket.recv(size - len(buf))
            buf += tmp
        return buf

    #Print channel list
    def printchannels(self):
        #Get a lock on the channel list
        self.channellock.acquire()
        #Depth-first traversal
        self._printchannel(0, "")
        #Release the list
        self.channellock.release()

    #Print a channel's children, recursively, depth-first.  Pass in a channel
    #number and the name of the previous channel path
    def _printchannel(self, channel, parentname):
        name = parentname + "/" + self.channels[channel].name
        logmsg("[c%s]\t%s"%(channel, name))
        for c in self.channels[channel].children:
            self._printchannel(c, name)

    #Print a list of the known users
    def printusers(self):
        #Print the userlist
        for u in self.users:
            logmsg("[u%i:c%i]\t%s"%(u, self.users[u][0], self.users[u][1]))

    #We've been rejected for some reason
    def onReject(self, data):
        reject = Mumble_pb2.Reject()
        reject.ParseFromString(data)
        errmsg("Unable to join server (%i): %s"%(reject.type,reject.reason))
        #TODO: Auth with certificate
        self.stop()


    #Stop this thread and all subthreads
    def stop(self):
        self.sender.stop()
        for t in self.services:
            t.stop()
        self._running = False


    #------------Service functions------------
    # Add a service for the receiver to talk to if needed.
    def addService(self, t):
        self.services.append(t);

    #Remove a service.
    def removeService(self,t):
        self.services.remove(t);

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

#Channel tree
class Channel:
    parent = None
    children = None
    name = ""
    def __init__(self):
        self.children = set()