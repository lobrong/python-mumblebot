# -*- coding: utf-8 -*-
import Queue
import threading
import time
import logging
from bot import Bot
from random import randint

import data
config = data.config

# Length before answers accepted is over (in seconds)
QUESTION_LENGTH = 10


class Trivia(Bot):
    process = None
    conn = None
    _running = False
    name = ""
    queue = None

    # Special 'not space but looks like a space' char that mumble doesnt auto-remove
    # Used to get extend past the the default text-to-speech message limit of 250 chars
    padding_char = " "
    users = None
    questionTimer = None
    questionAnswered = True
    question = None
    answer = None
    introduction = None

    def __init__(self, conn):
        threading.Thread.__init__(self)
        self.conn = conn
        self.name = "tb"
        self.queue = Queue.Queue()

    # A loop to read output from the process and send it to the tubes
    def run(self):
        self._running = True
        intro = "Welcome to triviabot!"
        intro += "<p> To give a command, type '!tb' followed by: </p>"
        intro += "<p> - 'gimme' for trivia </p>"
        intro += "<p> - 'question' for a question round</p>"
        intro += "<p> - 'score' to view the scoreboard!</p>"
        intro += "<p> - 'info' for some information</p>"
        intro += "<p> - 'help' to print this again</p>"
        intro += "<p> - 'quit' to close mumblebot :(</p>"
        self.introduction = intro
        self.send(self.introduction)
        command = None
        while self._running:
            # Check to see new messages!
            try:
                command = self.queue.get(block=False)
            except Queue.Empty:
                time.sleep(1)
                continue

            msg = command[0]
            name = command[1]
            logging.debug("TB: got {}".format(msg))
            # Parse command
            # Commands are of the following:
            # "!tb <command>"
            messageSplit = msg.split(" ", 1)  # Only split once. (Into two pieces.)
            firstWord = None
            if len(messageSplit) == 2:
                firstWord = messageSplit[0]

            if firstWord is not None and firstWord == "!tb":
                self.parseCommand(messageSplit[1])
            else:
                self.checkAnswer(msg, name)

        # If we're done, send the last words to the chat
        self.conn.send_chat_message("Triviabot hears your pleas for mercy, but triviabot is a hard mistress.")

    def parseCommand(self, command):
        if command == "gimme":
            self.trivia()

        elif command == "question":
            self.questionStart()

        elif command == "quit":
            self._running = False

        elif command == "info":
            self.send("All trivia was found on the back of cereal boxes")

        elif command == "help":
            self.send(self.introduction)

    # Send a random bit of trivia to the server.
    def trivia(self):
        searchfile = open("random.txt", "r")
        number = randint(1, 159)
        str_num = str(number) + "."
        to_send = None
        for line in searchfile:
            if str_num in line:
                to_send = line
                break
        to_send = to_send.split(".", 1)[1]
        self.send(to_send)
        searchfile.close()
        return

    def questionStart(self):
        # Start a new question
        if self.questionAnswered:
            self.send("Question time!")
            self.users = {}
            self.answer = "T"
            self.question = "hello moto"
            self.questionAnswered = False
            self.questionTimer = threading.Timer(QUESTION_LENGTH, self.timeUp)
            self.questionTimer.start()
        else:
            self.send("Question in progress!")

    def checkAnswer(self, answer, name):
        if not self.questionAnswered:

            if answer == self.answer:
                self.questionTimer.cancel()
                self.questionAnswered = True
                self.question = None
                self.answer = None
                self.send("You got it {}!".format(name))

    def timeUp(self):
        to_send = "<p> Time up! </p>"
        to_send += "<p> No one got it! </p>"
        to_send += "<p> Q: " + self.question + "</p>"
        to_send += "<p> A: " + self.answer + "</p>"
        self.question = None
        self.answer = None
        self.questionAnswered = True
        self.conn.send_chat_message(to_send)
        return

    # Used to receive data from the receiver regarding a message that relates to us
    def recv(self, message, name):
        self.queue.put([message,name])

    # Send 'message' to the server
    def send(self, message):
        self.conn.send_chat_message(message)

    # Stop running.
    def stop(self):
        self._running = False
