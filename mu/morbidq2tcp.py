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
from twisted.internet.protocol import Factory
from twisted.internet import reactor

# MorbidQ
from stompservice import StompClientFactory
from random import random
from orbited import json

# Other imports
import datetime
import time

# minido
from minido.protocol import *

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

