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

from __future__ import print_function
from twisted.application import internet, service
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.internet import reactor

# MorbidQ
from stompservice import StompClientFactory
from orbited import json

# Other imports
import time
import textwrap

# Minido
from protocol import MinidoProtocol

MINIDO_ADAPTER_HOST  = 'minidoadt'
MINIDO_ADAPTER_PORT  = 23
MORBIDQ_HOST         = 'localhost'
MORBIDQ_PORT         = 61613
CHANNEL_MINIDO_WRITE = '/mu/write'
CHANNEL_MINIDO_READ  = '/mu/read'
KASEC                = 15.0

class MinidoClientFactory(ReconnectingClientFactory):
    def startedConnecting(self, connector):
        print('Started to connect.')

    def buildProtocol(self, addr):
        print('Connected.')
        # self.resetDelay()
        return MinidoProtocol(self, KASEC)

    # exceptions.TypeError: str() takes at most 1 argument (2 given)
    def clientConnectionLost(self, connector, reason):
        # print('Lost connection.  Reason:', reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        print('Connection failed. Reason:', reason)
        ReconnectingClientFactory.clientConnectionFailed(self, connector,
                                                         reason)

    def recv_message(self, msg):
        self.morbidq_factory.send_data(msg)

 
class MorbidQClientFactory(StompClientFactory):
    def recv_connected(self, msg):
        print('Subscribing to channel ' + CHANNEL_MINIDO_WRITE)
        self.subscribe(CHANNEL_MINIDO_WRITE)

    def recv_message(self, msg):
        message = json.decode(msg['body'])
        if msg['headers']['destination'] == CHANNEL_MINIDO_WRITE:
            if type(message) is list:
                print("STOMP to RS485 : %s" % (
                    ' '.join(map(lambda i: '{0:02X}'.format(i),message))))
                for conn in self.minido_factory.connections:
                    conn.send_data(message)
                # Also copy it for other listeners.
                self.send(CHANNEL_MINIDO_READ, json.encode(message))
 
    def send_data(self, message):
        print("RS485 to STOMP : %s" % (
            ' '.join(map(lambda i: '{0:02X}'.format(i),message))))
        self.send(CHANNEL_MINIDO_READ, json.encode(message))
    
    def clientConnectionLost(self, connector, reason):
        time.sleep(1.0)
        reactor.connectTCP(MORBIDQ_HOST, MORBIDQ_PORT, self)


morbidq_factory = MorbidQClientFactory()
minido_factory = MinidoClientFactory()

# Cross references
morbidq_factory.minido_factory =  minido_factory
minido_factory.morbidq_factory = morbidq_factory

minidoclient = internet.TCPClient(MINIDO_ADAPTER_HOST, 
    MINIDO_ADAPTER_PORT, minido_factory)
morbidqclient = internet.TCPClient(MORBIDQ_HOST, MORBIDQ_PORT, morbidq_factory)
application = service.Application("RS485 to STOMP connector application")
minidoclient.setServiceParent(application)
morbidqclient.setServiceParent(application)

def mu_main():
    reactor.connectTCP(MINIDO_ADAPTER_HOST, MINIDO_ADAPTER_PORT, minido_factory)
    reactor.connectTCP(MORBIDQ_HOST, MORBIDQ_PORT, morbidq_factory)
    reactor.run()

if __name__ == '__main__':
    print('Please use twistd -noy to start this script')
    mu_main()

