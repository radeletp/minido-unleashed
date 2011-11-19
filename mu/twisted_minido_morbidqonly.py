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
"""

###############################################################################
# TODO:                                                                       #
#  * Implement serial adapter (not only tcp/ip)                               #
#  * History for EXI also as with EXO                                         #
#  * Mettre à jour les tables exi_id2output et exi                            #
#                                                                             #
#                                                                             #
###############################################################################

from __future__ import print_function
from twisted.internet.protocol import Protocol, ReconnectingClientFactory
from twisted.web import xmlrpc, server
from sys import stdout
from SimpleXMLRPCServer import SimpleXMLRPCServer
from Queue import Queue
from minido.db import Db
from minido.exo import Exo
from minido.devices import *

# MorbidQ
from stompservice import StompClientFactory
from twisted.internet.task import LoopingCall
from random import random
from orbited import json

# Other imports
import datetime
import time
import traceback

MORBIDQ_HOST = 'localhost'
MORBIDQ_PORT = 61613
CHANNEL_MINIDO_NAME = "/mu/minido"
CHANNEL_DISPLAY_NAME = "/mu/display"
CHANNEL_MINIDO_WRITE = "/mu/write"
CHANNEL_MINIDO_READ  = "/mu/read"
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



class WebService(xmlrpc.XMLRPC):
    """ Gather all methods exposed through the SOAP web service """
    def xmlrpc_set_output(self, exo, output, value):
        """ change output state """
        try:
            newdata = self.factory.minidoprotocol.exodict[exo].set_output(int(output), int(value))
        except(KeyError):
            pass
        return(newdata)
        xmlrpc_set_output.signature = [['int', 'int', 'string', 'int', 'string']]

    def xmlrpc_get_output(self, exo, output):
        """ Get the value of an output """
        try:
            return(self.factory.minidoprotocol.exodict[exo].get_output(output))
        except(KeyError):
            return('No such exo in memory')
        return('Unexpected Error')

        xmlrpc_get_output.signature = [['int', 'int', 'string']]

    def xmlrpc_list_exo(self):
        """ Return the list of EXO currently known by MU """
        exolist = list(iter(self.factory.minidoprotocol.exodict))
        return(exolist)
        xmlrpc_list_exo.signature = [['None', 'list']]
        xmlrpc_list_exo.help = "Return the list of EXO currently known by MU"

    def xmlrpc_minido_programming(self, exo, output, mode):
        """ Set an exo output in Learn, Delete or stop Learn/Delete mode."""
        data = [0x31]
        if mode == "add":
            print('Entering learning mode (add) for exo ' + str(exo)
                + ' output ' + str(output))
            data.append( 0x01 )
        elif mode == "cancel":
            print('Cancelling learn or delete mode for exo ' + str(exo)
                + ' output ' + str(output))
            data.append( 0x00 )
        elif mode == "remove":
            print('Entering delete mode (remove) for exo ' + str(exo)
                + ' output ' + str(output))
            data.append( 0x02 )
        data.append( exo )
        data.append( output-1 )
        data.append( 0x00 )
        self.exilist = [0x14, 0x15, 0x16, 0x18]
        # Todo : Add a loop, once sure of the code.
        self.protocol.factory.connection.send_packet( self.exilist[0], data )
        return(0)

    def xmlrpc_set_device_value(self, devid, value):
        """ Update the device status """
        print(self.factory.minidoprotocol.devdict[int(devid)])
        self.factory.minidoprotocol.devdict[devid].set_value(value)
        return('Ok')

    def xmlrpc_get_device_value(self, devid):
        """ Get devices state """
        return(str(self.factory.minidoprotocol.devdict[devid].get_value()))

    def xmlrpc_get_device_dict(self):
        """ Get list of devices """
        print("Get list of devices from devdict")
        return(self.factory.minidoprotocol.devdict)

    def xmlrpc_get_device_details(self):
        """ List devices from DB """
        print("Get list of devices from DB")
        return(self.factory.minidoprotocol.mydb.get_device_details())

class MinidoProtocol():
    ''' Bus protocol, also used for Minido, D2000 and C2000 '''
    chardata = list()
    def __init__(self):
        self.mydb = Db(self, SQLITEDB)
        self.exodict = self.mydb.populate_exodict()
        self.devdict = self.mydb.populate_devdict()
        print('MinidoProtocol initialized')
        print(self.exodict)

    def newpacket(self, data):
        """ Called when a new packet is validated """
        print(' '.join(['{0:02x}'.format(x) for x in data]))
        if EXOOFFSET < data[DST] <= EXOOFFSET + 16:
            # This is a packet for an EXO module
            exoid = data[DST] - EXOOFFSET
            exiid = data[SRC] - EXIOFFSET
            if data[COM] == CMD['EXO_UPDATE']:
                try:
                    self.exodict[exoid].update(exiid, data[5:-1])
                    commit_delay = 5
                except(KeyError):
                    print(
                        '{0!s:.23} : The EXO {1:2} does not exist. \
                        Creating it.'.format(
                        datetime.datetime.now(),
                        exiid)
                        )
                    print('Warning : The exo ' + str(exoid) +
                        ' do not exist. Creating it.')
                    self.exodict[exoid] = Exo(exiid, 
                        exoid, self.mydb, self, HIST)
                    self.exodict[exoid].update(exiid, data[5:-1])
        elif EXIOFFSET < data[DST] <= EXIOFFSET + 8:
            # This is a packet for EXI module
            print( '{0!s:.23} : SRC-{2:02}->EXI-{1:02} : \
                CMD:{3:2} DATA:{4!s:10}'.format(
                datetime.datetime.now(),
                data[DST] - EXIOFFSET,
                data[SRC],
                data[COM],
                data[5:-1]
                ))
        elif data[DST] == 0x0b:
            # This is a packet for the D2000
            if data[COM] == CMD['EXICENT'] and \
                data[SRC]-EXIOFFSET == data[5:-1][0]:
                # This is an exi packet
                # I don't undestand by the EXI info is twice.
                print( ( '{0!s:.23} : EXI-{1:02}->D-2000 : ' +
                    'Button {2:2} ( EXI from data {3:02} )').format(
                    datetime.datetime.now(),
                    data[SRC]-EXIOFFSET,
                    data[6],
                    data[5]
                    ))
        else:
            print( ( '{0!s:.23} : SRC-{2:02x}->DST-{1:02x} : ' +
                'Unable to decode - ' +
                'CMD:{3:02x} DATA:{4!s:10}' ).format(
                datetime.datetime.now(),
                data[DST],
                data[SRC],
                data[COM],
                ' '.join(['{0:02x}'.format(x) 
                    for x in data[5:-1]])
                ))

    def send_packet(self, dst, data):
        valuelist = [0x23, dst, EXIID, len(data) + 1] + data
        valuelist.append(checksum( data ))
        print('Debug : sending packet : ', ' '.join(
            [ '%0.2x' % c for c in valuelist ]))
        packet = ''.join([chr(x) for x in valuelist])
        self.transport.write(packet)

class MorbidQClientFactory(StompClientFactory):
 
    def recv_connected(self, msg):
        self.subscribe(CHANNEL_DISPLAY_NAME)
        self.subscribe(CHANNEL_MINIDO_READ)

    def recv_message(self, msg):
        message = json.decode(msg['body'])
        if msg['headers']['destination'] == CHANNEL_DISPLAY_NAME:
            print(message)
            # self.handlers[message['id']].setattr(message['trait'], message['value'])
            if 'ButtonClicked' in message and message['ButtonClicked'] == '1':
                self.send_data({'ButtonClicked': '2'})
            if 'ListGroups' in message and message['ListGroups'] == '1':
                self.send_data({'Group1': 'RDC', 'Group2': 'Etage', 'Group3': 'Grenier'})
        elif msg['headers']['destination'] == CHANNEL_MINIDO_READ:
            self.minidoprotocol.newpacket(message)
 
    def send_data(self, data):
        self.send(CHANNEL_MINIDO_WRITE, json.encode(data))
 
if __name__ == '__main__':
    from twisted.internet import reactor
    morbidqFactory = MorbidQClientFactory()
    minidoprotocol = MinidoProtocol()
    morbidqFactory.minidoprotocol = minidoprotocol
    ws = WebService()
    ws.morbidqFactory = morbidqFactory
    xmlrpc.addIntrospection(ws)
    reactor.listenTCP( 8000, server.Site(ws) )
    reactor.connectTCP(MORBIDQ_HOST, MORBIDQ_PORT, morbidqFactory)
    reactor.run()