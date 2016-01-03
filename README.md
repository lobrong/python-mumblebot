# python-mumblebot-server
Python bot server for mumble, you can write custom bots depending on your needs!

Currently use CTRL + C to kill the server.

Dependancies:
Google protobuf
(https://github.com/google/protobuf)

Original code from: https://code.google.com/p/mumblebot/ (Stuart McMurray, 2013)

Current bots available:
* Trivia bot
  - Can ask for random bits of trivia
  - Can start a 'question round', trivia bot asks a question, users can attempt to answer

Future bot ideas:
* Echo bot
  - Echos messages back to you 

* Youtube bot
  - Give a youtube link, this bot will play the audio to you

* Soundboard bot
  - Similar vein to the youtubebot, but with small audio clips instead.

To-dos
  - mute/deafen upon entry to reduce incoming packets (depending on application)
  - handle 'CTRL+C' / 'kill <pid>' signals to quit gracefully
  - MORE ROBUSTNESS
