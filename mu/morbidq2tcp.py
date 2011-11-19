#!/usr/bin/env python
# **- encoding: utf-8 -**
"""
    Minido-Unleashed is a set of programs to control a home automation
    system based on minido from AnB S.A.

    Please check http://kenai.com/projects/minido-unleashed/

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.


    This program connects to a STOMP server, and allow dual way communication
    with the minido bus, checking the validity of the packet before sending.
"""

###############################################################################
# TODO:                                                                       #
#                                                                             #
###############################################################################

from __future__ import print_function
from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor
from twisted.web import xmlrpc, server
from sys import stdout
from threading import Thread, Timer
from SimpleXMLRPCServer import SimpleXMLRPCServer
from collections import deque
from Queue import Queue

# MorbidQ
from stompservice import StompClientFactory
from twisted.internet.task import LoopingCall
from random import random
from orbited import json

# Other imports
import datetime
import time
import textwrap
import traceback

MINIDO_ADAPTER_HOST = 'localhost'
MINIDO_ADAPTER_PORT = 2323
MORBIDQ_HOST = 'localhost'
MORBIDQ_PORT = 61613
CHANNEL_MINIDO_WRITE= "/mu/write"
CHANNEL_MINIDO_READ= "/mu/read"
HIST = 5
SQLITEDB = "minido_unleashed.db"
EXIID = 0x17

# Never change the following values, it's only for clarity :
EXOOFFSET = 0x3B
EXIOFFSET = 0x13
CMD = {
    'EXO_UPDATE': 0x01,
    'ECHO_REPLY': 0x05,
    'EXICENT'   : 0x31,
    'ECHO REQUEST': 0x49,
    }
DST = 1
SRC = 2
LEN = 3
COM = 4


def checksum(datalist):
    """ Calculate an XOR checksum """
    checksum_ = 0
    for item in datalist:
        checksum_ ^= item
    return checksum_

class MinidoProtocol(Protocol):
    ''' Bus protocol, also used for Minido, D2000 and C2000 '''
    chardata = list()
    def __init__(self, factory):
        self.factory = factory

    def connectionMade(self):
        print(str(datetime.datetime.now()) + " :",
            "New connection from :", self.transport.getPeer())
        self.factory.connections.append(self)

    def connectionLost(self, reason):
        self.factory.connections.remove(self)
        print(str(datetime.datetime.now()) + " :",
            "Lost connection from : ", self.transport.getPeer(), reason)

    def newpacket(self, data):
        """ Called when a new packet is validated """
        self.factory.morbidqFactory.send_data(data)

    def send_data(self, data):
        if data[len(data)-1] == checksum( data[4:(len(data)-1)]):
            packet = ''.join([chr(x) for x in data])
            self.transport.write(packet)
        else:
            # First check if the packet is complete, 
            # and build the missing checksum.
            if len(data) == data[3] + 3:
                print(str(datetime.datetime.now()) + " :",
                    "Adding the missing checksum")
                data.append(checksum ( data[4:(len(data))] ))
                packet = ''.join([chr(x) for x in data])
                self.transport.write(packet)

            else:
                print(str(datetime.datetime.now()) + " : " + 
                    'Bad checksum for packet : ' + str(' '.join(
                    [ '%0.2x' % c for c in data ])))

    def dataReceived(self, chardata):
        """ This method is called by Twisted  """
        self.chardata.extend(chardata)
            
        while len(self.chardata) >= 6:
            if ord(self.chardata[0]) != 0x23:
                startidx = 0
                try:
                    startidx = self.chardata.index(chr(0x23))
                except(LookupError, ValueError):
                    # We did not find 0x23
                    # We are not interested in data not starting by 0x23.
                    print(str(datetime.datetime.now()) +
                        " Error : none is 0x23. Dropping everything.")
                    print(str([ord(x) for x in self.chardata]))
                    self.chardata = list()
                    continue

                if startidx != 0:
                    print('Deleting first characters : StartIDX : ', startidx)
                    self.chardata = self.chardata[startidx:]
                    continue
            else:
                """ We have a valid begining """
                datalength = ord(self.chardata[3])
                if len(self.chardata) >= datalength + 4:
                    """ We have at least a complete packet"""
                    #print("Debug " + str(len(self.chardata)) + " datalength : " + str(datalength))
                    if checksum(
                        [ord(x) for x in self.chardata[4:datalength + 3]]
                        ) != ord(self.chardata[datalength + 3]):
                        print("Warning : Invalid checksum for packet : "
                            + str( [ord(x) for x in self.chardata] ))
                        validpacket = self.chardata[0:datalength + 4]
                        self.chardata = self.chardata[datalength + 4:]
                        continue
                    else:
                        validpacket = self.chardata[0:datalength + 4]
                        self.chardata = self.chardata[datalength + 4:]
                    # OK, I have now a nice, beautiful, valid packet
                    data = [ord(x) for x in validpacket]
                    # print(str(datetime.datetime.now()) + " : " + str(data))
                    self.newpacket(data)
                else:
                    #print("Debug packet : " + str(map(lambda x: ord(x), self.chardata)))
                    #print("Debug ord(self.chardata[3]) : " + str(datalength))
                    break


class MinidoServerFactory(Factory):
    def __init__(self):
        self.connections = []

    def startedConnecting(self, connector):
        print('Started to connect.')

    def buildProtocol(self, addr):
        return MinidoProtocol(self)

    def clientConnectionLost(self, connector, reason):
        print('Lost connection.  Reason:', reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        print('Connection failed. Reason:', reason)
        ReconnectingClientFactory.clientConnectionFailed(self, connector,
                                                         reason)
 
class MorbidQClientFactory(StompClientFactory):
    def recv_connected(self, msg):
        self.subscribe(CHANNEL_MINIDO_READ)

    def recv_message(self, msg):
        message = json.decode(msg['body'])
        if msg['headers']['destination'] == CHANNEL_MINIDO_READ:
            if type(message) is list:
                print(str(datetime.datetime.now()), ": Sending to",
                    len(self.minidoFactory.connections),"tcp client(s) :", message)
                for conn in self.minidoFactory.connections:
                    conn.send_data(message)
 
    def send_data(self, data):
        self.send(CHANNEL_MINIDO_WRITE, json.encode(data))

def mu_main():
    morbidqFactory = MorbidQClientFactory()
    minidoFactory = MinidoServerFactory()
    morbidqFactory.minidoFactory =  minidoFactory
    minidoFactory.morbidqFactory = morbidqFactory
    reactor.listenTCP(MINIDO_ADAPTER_PORT, minidoFactory)
    reactor.connectTCP(MORBIDQ_HOST, MORBIDQ_PORT, morbidqFactory)
    reactor.run()

if __name__ == '__main__':
    mu_main()

