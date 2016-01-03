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
import thread 

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

class Connection(threading.Thread):
	socket = None
	pingthread = None
	sendmsgthread = None
	recvmsgthread = None
	next_ping_time = None
	_running = False

	rxbytes = None #DEBUG

	#Keep ahold of the channels and users on the server
	channels = {}
	orphans = {} #Orphaned channels, same format as above
	users = {}
	services = [] # Keep track of running services, like trivia-bots!

	channellock = None
	current_channel = None
	channelwait = None
	userwait = None
	channeltimer = None
	usertimer = None
	userevent = None

	txqueue = None
	sendlock = None
	pingdata = None

	def __init__(self, socket):
		print "Initialising Connection"
		threading.Thread.__init__(self)
		self.socket = socket
		self.daemon = True
		self.channellock = threading.Lock()

		self.txqueue = Queue.Queue()
		self.sendlock = threading.Lock()
		self.pingdata = Mumble_pb2.Ping()
		self.pingdata.resync = 0


	#Wait for messages, act on them as appropriate
	def run(self):
		self.update_logging()
		print "Running conn"

		#Send back our version info
		clientversion = Mumble_pb2.Version()
		clientversion.version = struct.unpack(">I", struct.pack(">HBB", *version))[0]
		#TODO: work on a better way to receive error messages from scripts

		clientversion.release = ""#mumblebot-0.0.1"
		clientversion.os = ""#platform.system()
		clientversion.os_version = ""#platform.release()
		self.send(clientversion)
		print "Sent version info"
		#Send auth info
		authinfo = Mumble_pb2.Authenticate()
		authinfo.username = config["username"]
		if config["password"]:
			authinfo.password = config["password"]
		else:
			authinfo.password = ""
		self.send(authinfo)
		print("Authenticated as %s with password %s"%(authinfo.username,authinfo.password))

		#TODO: Implement tokens
		#TODO: Timeout on rx of auth message if !mumble server
		#Start the pinger
		#thread.start_new_thread(self._pingLoop, ()) 
		self._running = True
		self.pingthread = threading.Thread(target=self.send_pings)
		self.pingthread.daemon = True
		self.pingthread.start()

		self.sendmsgthread = threading.Thread(target=self.send_msgs)
		self.sendmsgthread.start()

		
		while self._running:
			#Get the six header bytes
			header = self.recvsize(6)
			if header != None:
				#Unpack the header
				(type, size) = struct.unpack(">HL", header)
				data = self.recvsize(size)
				typename = msgtype[type].__name__
				#Handle each message, this is going to get inefficient.
				print "Got {}-byte {} message".format(size, typename)
				try:
					{"Version":         self.onVersion,
					 "ChannelState":    self.onChannelState,
					 "UserState":       self.onUserState,
					 "TextMessage":     self.onTextMessage,
					 "Reject":          self.onReject,
					}[typename](data)

					
				except KeyError as ke:
					#print("{} message unhandled".format(typename)) #DEBUG
					pass

			#print "end loop, status: " + str(self._running)

	def send_msgs(self):
		while self._running:
			msg = self.txqueue.get()	# Block until msg
			if msg != None:
				totalsent = 0
				while totalsent < len(msg):
					#Lop of the bits we don't need to send
					sent = self.socket.send(msg[totalsent:])
					if sent == 0:
						raise RuntimeError("socket brokens")
					totalsent += sent
			else:
				return

	def send_pings(self):
		print "Pinger Thread Starting"
		while self._running:
			self.send(self.pingdata)
			time.sleep(5)
		print "Pinger Thread Ending"


#---------------------------------------------------------------------------------------
# 									SENDER STUFF
#---------------------------------------------------------------------------------------

	#Special case to send a chat message
	def send_chat_message(self, msg):
		textmessage = Mumble_pb2.TextMessage()
		textmessage.message = msg
		textmessage.channel_id.append(self.current_channel)
		self.send(textmessage)
		return

	#Send a message to the series of tubes.  msg is a protobuf object
	def send(self, msg):
		#Type code
		type = msgnum[msg.__class__.__name__]
		#Format as a series of bytes
		msg = msg.SerializeToString()
		size = len(msg)
		#Pack the header
		hdr = struct.pack(">HL", type, size)
		self.sendlock.acquire()
		self.txqueue.put(hdr+msg)
		self.sendlock.release()

#---------------------------------------------------------------------------------------
# 									RECEIVER STUFF
#---------------------------------------------------------------------------------------

	#Receive a specified number of bytes
	def recvsize(self, size):
		try:
			buf = ""
			while len(buf) < size:
				recv = self.socket.recv(size - len(buf))
				if recv == '':
					raise RuntimeError("socket broken :(")
				buf += recv
					
			return buf
		except:
			return None

	def onVersion(self, data):
		serverversion = Mumble_pb2.Version()
		#CamelCase, ReaLly?
		serverversion.ParseFromString(data)
		(major, minor, revision) = struct.unpack('>HBB',struct.pack('>I', serverversion.version))
		print("Server {}.{}.{} {} ({}: {})".format(major, minor, revision,
													serverversion.release,
													serverversion.os,
													serverversion.os_version))
		return

	def onChannelState(self, data):
		#If we're still collecting channels, reset the timeout
		if self.channelwait is not None and self.channeltimer is not None:
			self.channeltimer.cancel()
			self.channeltimer = None
		#If we're just printing channels, start the timer
		if self.channelwait is not None and self.channeltimer is None:
			self.channeltimer = threading.Timer(self.channelwait,self.printchannels)
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
			self.addChannel(channelstate)

		#If we have the channel, update it
		else:
			self.updateChannel(channelstate)

		#Join the right channel when we learn about it
		to_join = None
		#If we're meant to be in root, join it
		if config["channel"] == "/" and 0 in self.channels:
			to_join = 0

		#If we're given a channel number, join it when we get it
		elif config["channel"].isdigit() and int(config["channel"]) in self.channels:
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
			self.send(userstate)
			self.current_channel = to_join
			print("Joined [c%i] %s"%(to_join, self.channels[to_join].name))
		self.channellock.release()

	# Add channel to list of stored channels
	def addChannel(self,channelstate):
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
		debugmsg("Added new channel %s [%i:%i]"%(t.name, t.parent, channelstate.channel_id))

	def updateChannel(self,channelstate):
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

	#We've been rejected for some reason
	def onReject(self, data):
		reject = Mumble_pb2.Reject()
		reject.ParseFromString(data)
		errmsg("Unable to join server (%i): %s"%(reject.type,reject.reason))
		#TODO: Auth with certificate
		self.stop()

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
		self.users[userstate.session] = (userstate.channel_id, userstate.name, userstate.session)

	#Handle messages
	def onTextMessage(self, data):
		textmessage = Mumble_pb2.TextMessage()
		textmessage.ParseFromString(data)
		print "Message: %s from [%i] %s"%(textmessage.message,textmessage.actor,self.users[textmessage.actor][1])

		# If the message doesn't start with the trigger, we don't care about it.
		# if not textmessage.message.startswith(config["trigger"]):
		# return
		
		#message is of format <trigger><service> <message>
		#triggerLength = len(config["trigger"])
		#specific = textmessage.message.split(" ")
		#nameToSend = specific[0][triggerLength:]
		#print nameToSend
		for t in self.services:
			t.recv(textmessage.message,textmessage.actor,self.users[textmessage.actor][1])


	#Print channel list
	def printchannels(self):
		#Get a lock on the channel list
		self.channellock.acquire()
		#Depth-first traversal
		self._printchannel(0, "")

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

	#Stop this thread and all subthreads
	def stop(self):
		for t in self.services:
			t.stop()
		self._running = False
		self.txqueue.put(None)


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
