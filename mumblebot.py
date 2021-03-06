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
# mumblebot
# by MagisterQuis

# TODO: Generate certificate for auth
# Imported modules
import argparse
import os
import socket
import ssl
import sys
import time
import logging

from connection import Connection
from trivia import Trivia

import data

config = data.config
msgtype = data.msgtype
msgnum = data.msgnum

# Config file locations
config_locations = (
    ".",
    os.environ["HOME"],
    "/etc",
    "/usr/local/etc",
)

logger = None


# Parse the arguments on the command line
def parse_arguments():
    global config
    # Argparser
    parser = argparse.ArgumentParser(description="Extensible bot for Mumble")
    # Command-line options
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
    # Get the options from the command line
    options = vars(parser.parse_args())
    # Save the options
    changed = []  # List of changed options
    for o in options:
        # TODO: Add numbers (or something) to username when username is already in use
        if options[o] is not None:
            config[o] = options[o]
            changed.append(o)

    return changed


# Try to find the config file.  If it exists, open it and parse it
def parse_config(changed):
    global config
    f = open_config()
    # If it's not found, log and exit
    if f is None:
        logging.debug("Unable to open config file ({}).".format(config["config"]))
        return None

    for line in f:
        line = line.strip()
        # Ignore comments
        if len(line) == 0 or line[0] == '#':
            continue

        key, value = line.split(None, 1)
        # Ignore it if set by the command line
        if key in changed:
            continue
        # Add it to the config if it's not set already
        config[key] = value

    logging.info("Read config from {}".format(f.name))
    # Print out options, if debugging
    for o in config:
        logging.debug("Option {}: {}".format(o, config[o]))


def open_config():
    f = None
    # If the config files starts with a /, assume it's an absolute path
    if config["config"][0] == "/":
        try:
            f = open(config["config"], "r")
            return f
        except IOError as e:
            f = None
    # Cycle through the default locations
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
    # If we're here, we couldn't find a file to open
    return f


# Makes a socket to the server and handshakes
def connect_to_server():
    #Make sure we have a server and port
    if "server" not in config:
        logging.error("No hostname or IP address given.  Unable to proceed.")
        sys.exit(1)

    # Connect to the server
    try:
        s = socket.create_connection((config["server"],
                                      int(config["port"])),
                                      float(config["timeout"]),
                                      (config["srcip"], int(config["srcport"])))

    except socket.error as msg:
        logging.error("Unable to connect to {}:{} - {}.".format(config["server"],config["port"], msg))
        sys.exit(1)

    sslsocket = ssl.wrap_socket(s, keyfile=config["keyfile"],
                                certfile=config["certfile"],
                                ssl_version=ssl.PROTOCOL_TLSv1,
                                ciphers="AES256-SHA", )
# TODO: add support for keyfile
    logging.info("Connected to {}:{}".format(config["server"], config["port"]))
    # Set the socket back to blocking
    sslsocket.setblocking(1)
    return sslsocket


# Start here
def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s - %(message)s', datefmt='%Y-%m-%d %I:%M:%S', level=logging.DEBUG)
    # TODO: config special word for pwd
    changed = parse_arguments()

    # Parse config file
    parse_config(changed)
    logging.info("Parsed Arguments")

    # Connect to server
    try:
        socket = connect_to_server()
        logging.info("Connected")
    except ssl.SSLError as e:
        logging.info("Unable to connect.  Are you banned?: {}".format(e))
        return sys.exit(1)

    # TODO: debug message for adding user
    # TODO: Handle non-ascii characters
    conn = Connection(socket)
    conn.start()

    try:
        while conn.current_channel is None:
            time.sleep(1)

        # Add services here
        trivia = Trivia(conn)
        conn.addService(trivia)
        trivia.start()

        # TODO: multiple tokens
        while conn.is_alive():
            time.sleep(5)

    except KeyboardInterrupt:
        pass

    logging.info("Closing down")
    # close everything down!
    conn.stop()
    socket.close()
    sys.exit(0)

if __name__ == "__main__":
    main()
