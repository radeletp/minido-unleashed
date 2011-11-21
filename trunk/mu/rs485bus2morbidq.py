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
from twisted.internet.protocol import ReconnectingClientFactory
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
import sqlite3
import time
import textwrap
import traceback

# Minido
from minido.protocol import MinidoProtocol

MINIDO_ADAPTER_HOST = 'minidoadt'
MINIDO_ADAPTER_PORT = 23
MORBIDQ_HOST = 'localhost'
MORBIDQ_PORT = 61613
CHANNEL_MINIDO_WRITE= "/mu/write"
CHANNEL_MINIDO_READ= "/mu/read"

class MinidoClientFactory(ReconnectingClientFactory):
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
        print('Subscribing to channel ' + CHANNEL_MINIDO_WRITE)
        self.subscribe(CHANNEL_MINIDO_WRITE)

    def recv_message(self, msg):
        message = json.decode(msg['body'])
        if msg['headers']['destination'] == CHANNEL_MINIDO_WRITE:
            if type(message) is list:
                print(str(datetime.datetime.now()), ": STOMP to RS485 :", message)
                for conn in self.minidoFactory.connections:
                    conn.send_data(message)
                # Also copy it for other listeners.
                self.send(CHANNEL_MINIDO_READ, json.encode(message))
 
    def send_data(self, data):
        print(str(datetime.datetime.now()) + " : RS485 to STOMP : " + str(data))
        self.send(CHANNEL_MINIDO_READ, json.encode(data))
 

def mu_main():
    morbidqFactory = MorbidQClientFactory()
    minidoFactory = MinidoClientFactory()
    morbidqFactory.minidoFactory =  minidoFactory
    minidoFactory.morbidqFactory = morbidqFactory
    reactor.connectTCP(MINIDO_ADAPTER_HOST, MINIDO_ADAPTER_PORT, minidoFactory)
    reactor.connectTCP(MORBIDQ_HOST, MORBIDQ_PORT, morbidqFactory)
    reactor.run()

if __name__ == '__main__':
    mu_main()

