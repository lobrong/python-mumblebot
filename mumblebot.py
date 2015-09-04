    #!/usr/bin/env python
# Copyright (c) 2013, Stuart McMurray
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the <organization> nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#mumblebot
#by MagisterQuis

#TODO: Generate certificate for auth
# Imported modules
import argparse
import datetime
import Mumble_pb2
import os
import platform
import time

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

from receiver import Receiver
from sender import Sender
from trivia import Trivia

import data

config = data.config
msgtype = data.msgtype
msgnum = data.msgnum


#Logging functions
logmsg = lambda x: x
errmsg = logmsg
debugmsg = logmsg

#Config file locations
config_locations = (
    ".",
    os.environ["HOME"],
    "/etc",
    "/usr/local/etc",
)

#Start here
def main():
    #Set the log functions
    update_logging()
    #Parse command-line arguments
    #TODO: config special word for pwd
    changed = parse_arguments()

    #Parse config file
    #parse_config(changed)
    print "parsed args"

    #Enqueued messages will be sent back to the server
    #txqueue = Queue.Queue()
    #txqueue = queue.Queue() #2TO3
    #Connect to server
    try:
        socket = connect_to_server()
    except ssl.SSLError as e:
        print "Unable to connect.  Are you banned?: " + str(e)
        return -1
    #TODO: debug message for adding user
    #TODO: Handle non-ascii characters
    #Make thread for sending, give it a pipe
    sender = Sender(socket)
    sender.start()
    print "Starting Sender"

    #Make thread for listening, spawn subprocesses for each module
    receiver = Receiver(socket, sender)
    receiver.start()
    #print "Starting Receiver"

    try:
        import time
        while(sender.current_channel==None):
            time.sleep(1)

        trivia = Trivia(receiver)
        receiver.addService(trivia)
        trivia.start()

        #TODO: multiple tokens
        while sender.is_alive() and receiver.is_alive():
            time.sleep(5)

    except KeyboardInterrupt:
        pass

    #close everything down!
    #receiver.stop()
    sender.join()
    receiver.join()
    socket.close()
    exit(0)



#Parse the arguments on the command line
def parse_arguments():
    global config
    #Argparser
    parser = argparse.ArgumentParser(description="Extensible bot for Mumble")
    #Command-line options
    parser.add_argument("-c", "--config", metavar="CONFIGFILE", help="Specifies the config file.  Arguments given on the command line take precedence over the config file.  If this is not specified, the config file will be looked for in the following locations: %s.  Every long option which may specified on the command line may be specified in the config file, separated by its value by whitespace."%", ".join([str(p) for p in config_locations]))
    parser.add_argument("-s", "--server", help="The mumble server to which to connect.")
    parser.add_argument("-p", "--port", type=int, help="The port to which to connect on the mumble server.")
    parser.add_argument("--srcip", help="The IP address from which to connect.  The default is usually fine.")
    parser.add_argument("--srcport", help="The port from which to connect.  The default is usually fine.")
    parser.add_argument("--timeout", help="The amout of time to wait for a connection to be established.  The default (10s) is usually fine.")
    parser.add_argument("--syslog", action="store_true", help="Log to syslog instead of standard out/error.")
    parser.add_argument("-d", "--debug", action="store_true", help="Log messages useful for debugging.")
    parser.add_argument("-u", "--username", help="The username to use on the server.")
    parser.add_argument("--password", help="An optional password to send to the server.")
    parser.add_argument("--certfile", help="An optional ssl certificate to send to the server.  If this includes the key as well, KEYFILE need not be specified.")
    parser.add_argument("--keyfile", help="An optional ssl key that matches the CERTFILE.  If the key is included in the CERTFILE, this need not be specified.")
    parser.add_argument("--printusers", metavar="TIMEOUT", nargs='?', const=1, type=float, help="Print a list of users on the server.  An optional time may be specified to limit how long to wait for new users to appear.  The default (1s) is usually fine.")
    parser.add_argument("--printchannels", metavar="TIMEOUT", nargs='?', const=1, type=float, help="Print a list of channels on the server.  An optional time may be specified to limit how long to wait for new channel data to become available.  The default (1s) is usually fine.")
    parser.add_argument("--trigger", help="If a message starts with this character, it'll send the message to the script named the first word in the message (or silently ignore it if there's no script).  The default (an exclamation mark) is usually fine.")
    parser.add_argument("--scriptwd", help="The working directory for the scripts.  The default (/) is usually fine.")
    parser.add_argument("--scriptdir", help="The directory containing the scripts to run.  The default (/etc/mumblebot.d) is usually fine.  This is relative to SCRIPTWD if not absolute.")
    parser.add_argument("--channel", help="The channel to join.  This may either be given as a Unix-style path (/rootchannel/channel/subchannel) or a channel ID number (which may be retrieved with printchannels).  The default is the root channel.")
    #Get the options from the command line
    options = vars(parser.parse_args())
    #Save the options
    changed = [] #List of changed options
    for o in options:
        #TODO: Add numbers (or something) to username when username is already in use
        if options[o] is not None:
            config[o] = options[o]
            changed.append(o)
    #Update logging functions
    update_logging()
    return changed

#Try to find the config file.  If it exists, open it and parse it
def parse_config(changed):
    global config
    #Open the config file
    f = open_config()
    #If it's not found, log and exit
    if f is None:
        debugmsg("Unable to open config file ({}).".format(config["config"]))
        return None
    #Read each line of the file
    for line in f:
        #Remove whitespace
        line = line.strip()
        #Ignore comments
        if len(line) == 0 or line[0] == '#': continue
        #Split the line into keys and values
        key, value = line.split(None, 1)
        #Ignore it if set by the command line
        if key in changed: continue
        #Add it to the config if it's not set already
        config[key] = value
    #Update logging functions
    update_logging()
    #Log it
    logmsg("Read config from {}".format(f.name))
    #Print out options, if debugging
    for o in config:
        debugmsg("Option {}: {}".format(o, config[o]))


def open_config():
    f = None
    #If the config files starts with a /, assume it's an absolute path
    if config["config"][0] == "/":
        try:
            f = open(config["config"], "r")
            return f
        except IOError as e:
            f = None
    #Cycle through the default locations
    for l in config_locations:
        try:
            f = open(os.path.join(l, config["config"]))
            return f
        except IOError as e:
            f = None
        try:
            f = open(os.path.join(l, "."+config["config"]))
            return f
        except:
            f = None
    #If we're here, we couldn't find a file to open
    return f


#Makes a socket to the server and handshakes
def connect_to_server():
    #Make sure we have a server and port
    if "server" not in config:
        errmsg("No hostname or IP address given.  Unable to proceed.")
        print "wah"
        sys.exit(1)
    #Connect to the server
    try:
        s = socket.create_connection((config["server"], int(config["port"])),
                                     float(config["timeout"]), (config["srcip"],
                                                         int(config["srcport"])))
    except socket.error as msg:
        errmsg("Unable to connect to {}:{} - {}.".format(config["server"],config["port"], msg))
        print "wah1"
        exit(1)

    sslsocket = ssl.wrap_socket(s, keyfile=config["keyfile"],
                                certfile=config["certfile"],
                                ssl_version=ssl.PROTOCOL_TLSv1,
                                ciphers="AES256-SHA", )
#TODO: add support for keyfile
    logmsg("Connected to {}:{}".format(config["server"], config["port"]))
    #Set the socket back to blocking
    sslsocket.setblocking(1)
    return sslsocket

#------------Logging functions------------
def update_logging():
    errmsg = _err_to_stderr
    logmsg = _log_to_stdout
    debugmsg = _debug_to_stdout

def _err_to_stderr(msg):
    msg = "<E-M>"+str(datetime.datetime.now())+": "+msg
    print >>sys.stderr, msg.encode('utf-8')
def _log_to_stdout(msg):
    msg = "<I-M>"+str(datetime.datetime.now())+": "+msg
    print(msg.encode('utf-8'))
def _debug_to_stdout(msg):
    msg = "<D-M>"+str(datetime.datetime.now())+": "+msg
    print(msg.encode('utf-8'))


#TODO: Install script
#TODO: standard -h for script, help script: find scriptdir -type x -type f, !help foo -> script -h


if __name__ == "__main__":
    main()
