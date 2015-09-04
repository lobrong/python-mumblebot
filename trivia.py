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
    sender = None
    receiver = None
    _running = False
    name = ""
    queue = None
    questionTime = None

    def __init__(self, receiver):
        threading.Thread.__init__(self)
        self.sender = receiver.sender
        self.receiver = receiver
        self.name = "tb"
        self.queue = Queue.Queue()

    #A loop to read output from the process and send it to the tubes
    def run(self):
        _running = True
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
        
        while _running:
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
                    self.questionTime = time.clock()
                    self.question()

                elif (command=="quit"):
                    _running = False

                elif(command=="info"):
                    self.send("All trivia was found from the back of Jaimi's Libra pads")

                elif(command=="harry"):
                    self.send("Harry 'Suakweuy' Simpson is not the best. a.k.a bronze")

                elif(command=="help"):
                    self.send(intro)

                else:
                    self.send("unknown command")
            time.sleep(1)

        #If we're done, send the last words to the chat
        self.sender.send_chat_message("Triviabot hears your pleas for mercy, but triviabot is a hard mistress.")

    #Send a random bit of trivia to the server.
    def trivia(self):
        searchfile = open("random.txt", "r")
        number = randint(1,159)
        str_num = str(number) + "."
        for line in searchfile:
            if str_num in line: 
                self.send(line)
        searchfile.close()
        return

    def question(self):
        self.send("Question time!")
        users = {}

        newtime = time.clock()
        while(newtime <(self.questionTime + QUESTION_LENGTH)):
            try:
                entry = self.queue.get(False)
                answer = entry[0]
                name = entry[1]
            except Queue.Empty:
                answer = None
                name = None

            if(answer!=None and name!=None):
                self.send(name + " " + answer)
            newtime = time.clock()
        self.questionTime = None
        self.send("Question time over!")
    #Used to receive data from the receiver regarding a message that relates to us
    def recv(self,message,id,name):
        firstWord = message.split(" ")[1]
        if(firstWord!=None):
            self.queue.put([firstWord,name])

    #Send 'message' to the server
    def send(self,message):
        self.sender.send_chat_message(message)
        return

    #Stop running.
    def stop(self):
        self._running = False


