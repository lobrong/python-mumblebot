import abc
import threading


class Bot(threading.Thread):
    __metaclass__ = abc.ABCMeta

    def run(self):
        return

    @abc.abstractmethod
    def recv(self, message, name):
        ''' Used to receive a message from the current channel '''
        return

    @abc.abstractmethod
    def send(self,message):
        ''' Send a message to the current channel'''
        return

    @abc.abstractmethod
    def stop(self):
        ''' Stop the bot '''
        return