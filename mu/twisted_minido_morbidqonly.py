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
from Queue import Queue

# MorbidQ
from stompservice import StompClientFactory
from twisted.internet.task import LoopingCall
from random import random
from orbited import json

# Other imports
import datetime
import time
import traceback

# minido
from db import Db
from exo import Exo,Exodict
from devices import *
# from minido.protocol import MinidoProtocol

MORBIDQ_HOST = 'localhost'
MORBIDQ_PORT = 61613
CHANNEL_MINIDO_NAME  = "/mu/minido"
CHANNEL_DISPLAY_NAME = "/mu/display"
CHANNEL_MINIDO_WRITE = "/mu/write"
CHANNEL_MINIDO_READ  = "/mu/read"
HIST = 5
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

class WebService(xmlrpc.XMLRPC):
    """
    Gather all methods exposed through the XML-RPC web service
    Either for the Exo output directly : 
        self.morbidqFactory.mpd.exodict[exo].get_output(output)
    Or for the Device :
        self.morbidqFactory.mpd.devdict[devid].get_value())
    """
    def xmlrpc_set_output(self, exo, output, value):
        """ change output state """
        try:
            newdata = self.morbidqFactory.mpd.exodict[exo].set_output(int(output), int(value))
        except(KeyError):
            pass
        return(newdata)
        xmlrpc_set_output.signature = [['int', 'int', 'string', 'int', 'string']]

    def xmlrpc_get_output(self, exo, output):
        """ Get the value of an output """
        try:
            return(self.morbidqFactory.mpd.exodict[exo].get_output(output))
        except(KeyError):
            return('No such exo in memory')
        return('Unexpected Error')

        xmlrpc_get_output.signature = [['int', 'int', 'string']]

    def xmlrpc_list_exo(self):
        """ Return the list of EXO currently known by MU """
        exolist = list(iter(self.morbidqFactory.mpd.exodict))
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
        # self.protocol.morbidqFactory.connection.send_packet( self.exilist[0], data )
        return(0)

    def xmlrpc_set_device_value(self, devid, value):
        """ Update the device status """
        print(self.morbidqFactory.mpd.devdict[devid])
        self.morbidqFactory.mpd.devdict[devid].set_value(value)
        return('Ok')

    def xmlrpc_get_device_value(self, devid):
        """ Get devices state """
        return(str(self.morbidqFactory.mpd.devdict[devid].get_value()))

    def xmlrpc_get_device_dict(self):
        """ Get list of devices """
        print("Get list of devices from devdict")
        result = dict()
        for key in self.morbidqFactory.mpd.devdict.keys():
            result[key] = str(self.morbidqFactory.mpd.devdict[key])
        print(result)
        return(result)

    def xmlrpc_get_device_details(self):
        """ List devices from DB """
        print("Get list of devices from DB")
        return(self.morbidqFactory.mpd.mydb.get_device_details())

class MinidoProtocolDecoder(object):
    """ 
    AnB protocol (high level), also used for Minido, D2000 and C2000 
    The constructor builds exodict and devdict from mydb.populate...
    Is it the right place for this mydb.populate... ?
    This class is a Singleton
    """
    chardata = list()
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MinidoProtocolDecoder, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # FixMe
        # Remove the self and the SQLITEDB from the constructor
        self.mydb = Db()
        # self.exodict = self.mydb.populate_exodict()
        print('Creating exodict...')
        self.exodict = Exodict()
        # self.exodict = self.mydb.populate_exodict()
        print('Creating devidct...')
        self.devdict = self.mydb.populate_devdict(self.exodict)
        print('MinidoProtocolDecoder Singleton initialized')

    def recv_message(self, message):
        """
        Called when a new packet is validated by the protocol (low level).
        This methods decode the packet
        """
        print(' '.join(['{0:02x}'.format(x) for x in message]))
        if EXOOFFSET < message[DST] <= EXOOFFSET + 16:
            # This is a packet for an EXO module
            exoid = message[DST] - EXOOFFSET
            exiid = message[SRC] - EXIOFFSET
            if message[COM] == CMD['EXO_UPDATE']:
                try:
                    self.exodict[exoid].update(exiid, message[5:-1])
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
                    # Fixme
                    # Why exiid to create the Exo ?? Certainly a mistake.
                    self.exodict[exoid].update(exiid, message[5:-1])
        elif EXIOFFSET < message[DST] <= EXIOFFSET + 8:
            # This is a packet for EXI module
            print( '{0!s:.23} : SRC-{2:02}->EXI-{1:02} : \
                CMD:{3:2} DATA:{4!s:10}'.format(
                datetime.datetime.now(),
                message[DST] - EXIOFFSET,
                message[SRC],
                message[COM],
                message[5:-1]
                ))
        elif message[DST] == 0x0b:
            # This is a packet for the D2000
            if message[COM] == CMD['EXICENT'] and \
                message[SRC]-EXIOFFSET == message[5:-1][0]:
                # This is an exi packet
                # I don't undestand by the EXI info is twice.
                print( ( '{0!s:.23} : EXI-{1:02}->D-2000 : ' +
                    'Button {2:2} ( EXI from message {3:02} )').format(
                    datetime.datetime.now(),
                    message[SRC]-EXIOFFSET,
                    message[6],
                    message[5]
                    ))
        else:
            print( ( '{0!s:.23} : SRC-{2:02x}->DST-{1:02x} : ' +
                'Unable to decode - ' +
                'CMD:{3:02x} DATA:{4!s:10}' ).format(
                datetime.datetime.now(),
                message[DST],
                message[SRC],
                message[COM],
                ' '.join(['{0:02x}'.format(x) 
                    for x in message[5:-1]])
                ))


class MorbidQClientFactory(StompClientFactory):
    def recv_connected(self, msg):
        self.subscribe(CHANNEL_DISPLAY_NAME)
        self.subscribe(CHANNEL_MINIDO_READ)

    def recv_message(self, msg):
        message = json.decode(msg['body'])
        if msg['headers']['destination'] == CHANNEL_DISPLAY_NAME:
            print(message)
            if 'ButtonClicked' in message and message['ButtonClicked'] == '1':
                self.send_data({'ButtonClicked': '2'})
            if 'ListGroups' in message and message['ListGroups'] == '1':
                self.send_data({'Group1': 'RDC', 'Group2': 'Etage', 'Group3': 'Grenier'})
        elif msg['headers']['destination'] == CHANNEL_MINIDO_READ:
            self.mpd.recv_message(message)
 
    def send_data(self, data):
        print("Debug temporary : " + str(data))
        self.send(CHANNEL_MINIDO_WRITE, json.encode(data))
 
if __name__ == '__main__':
    from twisted.internet import reactor
    morbidqFactory = MorbidQClientFactory()
    morbidqFactory.mpd = MinidoProtocolDecoder()
    # Is there a better way ??
    morbidqFactory.mpd.factory = morbidqFactory
    ws = WebService()
    ws.morbidqFactory = morbidqFactory
    xmlrpc.addIntrospection(ws)
    reactor.listenTCP( 8000, server.Site(ws) )
    reactor.connectTCP(MORBIDQ_HOST, MORBIDQ_PORT, morbidqFactory)
    reactor.run()
