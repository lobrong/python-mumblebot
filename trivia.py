# -*- coding: utf-8 -*-
import argparse
import datetime
import Mumble_pb2
import os
import platform

import Queue
import re
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time

from random import randint
import data
config = data.config

#Length before answers accepted is over (in seconds)
QUESTION_LENGTH = 10

#A thread representing a connection to a script
class Trivia(threading.Thread):
	process = None
	conn = None
	_running = False
	name = ""
	queue = None
	questionTime = None
	questionLock = None
	# Special 'not space but looks like a space' char that mumble doesnt auto-remove
	# Used to get extend past the the default text-to-speech message limit of 250 chars
	padding_char = " "	
	users = None

	def __init__(self, conn):
		threading.Thread.__init__(self)
		self.conn = conn
		self.name = "tb"
		self.queue = Queue.Queue()
		self.questionTimeStart = None

	#A loop to read output from the process and send it to the tubes
	def run(self):
		self._running = True
		intro = "Welcome to triviabot."
		intro += "<p> To give a command, type '!tb' followed by: </p>"
		intro += "<p> - 'gimme' for trivia </p>"
		intro += "<p> - 'question' for a question round</p>"
		intro += "<p> (to answer, you still need to type '!tb' before your guess)</p>"
		intro += "<p> - 'score' to view the scoreboard!</p>"
		intro += "<p> - 'info' for some information</p>"
		intro += "<p> - 'help' to print this again</p>"
		intro += "<p> - 'quit' to close mumblebot :(</p>"
		self.send(intro)
		#a = "a                                                                                                              "
		#a = a+ "                                                                                                              "
		#a = a+ "                             "
		#print len(a)
		#self.send(str(a))
		#a = "                                                                                                              "
		#a = a+ "                                                                                                              "
		#a = a+ "                                                                                                              "
		#a = a+ "a"
		#self.send(str(a))
		
		while self._running:
			#Check to see new messages!
			try:
				command = self.queue.get(False)[0]
			except Queue.Empty:
				command = None

			#Parse command
			if(command!=None):
				if(command=="gimme"):
					self.trivia()

				elif(command=="question"):
					self.question()

				elif (command=="quit"):
					_running = False

				elif(command=="info"):
					self.send("All trivia was found from the back of cereal boxes")

				elif(command=="harry"):
					self.send("Harry 'Suakweuy' Simpson is not the best.")

				elif(command=="help"):
					self.send(intro)

				else:
					self.checkAnswer(command)
			time.sleep(1)

		#If we're done, send the last words to the chat
		self.conn.send_chat_message("Triviabot hears your pleas for mercy, but triviabot is a hard mistress.")

	#Send a random bit of trivia to the server.
	def trivia(self):
		searchfile = open("random.txt", "r")
		number = randint(1,159)
		str_num = str(number) + "."
		for line in searchfile:
			if str_num in line: 
				break
		line = line.split(".")[1]
		self.send(line)
		searchfile.close()
		return

	def question(self):
		# Start a new question
		if(self.questionTimeStart == None):
			self.send("Question time!")
			self.users = {}
			self.questionTimeStart = time.clock()


	def checkAnswer(self,input):
		if(self.questionTimeStart != None):
			currentTime = time.clock()

			if(currentTime < (self.questionTime + QUESTION_LENGTH)):
				answer = input[0]
				name = input[1]

			if(answer != None and name != None):
				self.send(name + " " + answer)

	#Used to receive data from the receiver regarding a message that relates to us
	def recv(self,message,id,name):
		firstWord = message.split(" ")[1]
		if(firstWord!=None):
			self.queue.put([firstWord,name])

	#Send 'message' to the server
	def send(self,message):
		self.conn.send_chat_message(message)
		return

	#Stop running.
	def stop(self):
		self._running = False


