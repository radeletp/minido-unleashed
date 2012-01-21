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

    Numbering rules for Exi, Exo, channel / output : from 1 ( to 8 or 16 )
    Channel is a tupple to point an output (1-8) on a particular Exo (1-16)

    Improvements since 1.x series :
    - All in memory design (low latency)
    - Twisted Network event based framework (low latency, no unsafe threads to 
          access shared resources.)
    - Correct use of data types, use mutables types when necessary, use integers
          to compute & store exo status. Banned string concatenations. (speed)
    - Full UTF-8 DB
    - Auto Discovery, basic functions on new Minido installations.
    - Centred on a Message Broker using STOMP for agility. Can easily
          remove is performance impact noticed.
    - STP everywhere we can, up to the web browser with Orbited Comet library.
    - Object Oriented design for ease of maintenance.
    - Clean code & readability matters for ease of maintenance.
    - Web service XMLRPC
    - STOMP to communicate asynchronously
"""

###############################################################################
# TODO:                                                                       #
#  * Implement serial adapter (not only tcp/ip)                               #
#  * History for EXI also as with EXO                                         #
#  * Mettre à jour les tables exi_id2output et exi                            #
#  * Implement action testing                                                 #
#                                                                             #
###############################################################################

from __future__ import print_function
from twisted.internet.protocol import Protocol, ReconnectingClientFactory
from twisted.internet import reactor, defer
from twisted.web import xmlrpc, server
from Queue import Queue
import sys

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
from minidodevices import Exo, Exodict, Exi
from devices import *
# from minido.protocol import MinidoProtocol

MORBIDQ_HOST = 'localhost'
MORBIDQ_PORT = 61613
CHANNEL_MINIDO_NAME  = "/mu/minido"
CHANNEL_DISPLAY_NAME = "/mu/display"
CHANNEL_MINIDO_WRITE = "/mu/write"
CHANNEL_MINIDO_READ  = "/mu/read"
CHANNEL_MINIDO_LAYOUT  = "/mu/layout"
HIST = 5
EXIID = 0x17

# Never change the following values, it's only for readability of the code:
EXOOFFSET = 0x3B
EXIOFFSET = 0x13
CMD = {
    'EXO_UPDATE': 0x01,
    'EXICENT'   : 0x31,
    'EXI_ECHO_REQUEST': 0x39,
    'EXI_ECHO_REPLY': 0x38,
    'EXO_ECHO_REQUEST': 0x49,
    'EXO_ECHO_REPLY': 0x05,
    }
DST = 1
SRC = 2
LEN = 3
COM = 4

class WebService(xmlrpc.XMLRPC):
    """
    Gather all methods exposed through the XML-RPC web service
    Either for the Exo output directly : 
        self.morbidq_factory.mpd.exodict[exo].get_output(output)
    Or for the Device :
        self.morbidq_factory.mpd.devdict[devid].get_value())

    pylint option block-disable=W0101
    pylint option block-disable=E0602
    """
    def xmlrpc_set_output(self, exo, output, value):
        """ change output state """
        try:
            newdata = self.morbidq_factory.mpd.exodict[exo].set_output(
                int(output), int(value))
        except(KeyError):
            pass
        return(newdata)
        xmlrpc_set_output.signature = [['int', 'int', 'string', 
            'int', 'string']]

    def xmlrpc_get_output(self, exo, output):
        """ Get the value of an output """
        try:
            return(self.morbidq_factory.mpd.exodict[exo].status(output))
        except(KeyError):
            return('No such exo in memory')
        return('Unexpected Error')

        xmlrpc_get_output.signature = [['int', 'int', 'string']]

    def xmlrpc_list_exo(self):
        """ Return the list of EXO currently known by MU """
        exolist = list(iter(self.morbidq_factory.mpd.exodict))
        return(exolist)
        xmlrpc_list_exo.signature = [['None', 'list']]
        xmlrpc_list_exo.help = "Return the list of EXO currently known by MU"

    def xmlrpc_minido_programming(self, exo, output, mode):
        """ Set an exo output in Learn, Delete or stop Learn/Delete mode."""
        data = list()
        if mode == "add":
            print('Entering learning mode (add) for exo ' + str(exo)
                + ' output ' + str(output))
            #data.append( 0x01 )
            data = [0x01]
        elif mode == "cancel":
            print('Cancelling learn or delete mode for exo ' + str(exo)
                + ' output ' + str(output))
            #data.append( 0x00 )
            data = [0x00]
        elif mode == "remove":
            print('Entering delete mode (remove) for exo ' + str(exo)
                + ' output ' + str(output))
            #data.append( 0x02 )
            data = [0x02]
        data.append( exo )
        data.append( output-1 )
        data.append( 0x00 )
        self.exilist = [0x14, 0x15, 0x16, 0x18]
        for exi in self.exilist:
            self.morbidq_factory.mpd.send_command( exi, 0x31, data )
        return(0)

    def xmlrpc_set_device_on(self, devid):
        """ Update the device status """
        print(self.morbidq_factory.mpd.devdict[devid])
        if self.morbidq_factory.mpd.devdict[devid].type_ == "Light":
            self.morbidq_factory.mpd.devdict[devid].on()
        return('Ok')

    def xmlrpc_set_device_off(self, devid):
        """ Update the device status """
        print(self.morbidq_factory.mpd.devdict[devid])
        if self.morbidq_factory.mpd.devdict[devid].type_ == "Light":
            self.morbidq_factory.mpd.devdict[devid].off()
        return('Ok')

    def xmlrpc_get_device_value(self, devid):
        """ Get devices state """
        return(str(self.morbidq_factory.mpd.devdict[devid].get_value()))

    def xmlrpc_get_device_dict(self):
        """ Get list of devices """
        print("Get list of devices from devdict")
        result = dict()
        for key in self.morbidq_factory.mpd.devdict.keys():
            result[key] = str(self.morbidq_factory.mpd.devdict[key])
        print(result)
        return(result)

    def xmlrpc_get_device_details(self):
        """ List devices from DB """
        print("Get list of devices from DB")
        return(self.morbidq_factory.mpd.mydb.get_device_details())


class MorbidQClientFactory(StompClientFactory):
    def recv_connected(self, msg):
        self.subscribe(CHANNEL_DISPLAY_NAME)
        self.subscribe(CHANNEL_MINIDO_READ)
        self.subscribe(CHANNEL_MINIDO_LAYOUT)
        # mpd is reinitialized at every STOMP server reconnection
        self.mpd = MinidoProtocolDecoder(self.send_data)

    def recv_message(self, msg):
        message = json.decode(msg['body'])
        if msg['headers']['destination'] == CHANNEL_DISPLAY_NAME:
            print(message)
            if 'ButtonClicked' in message and message['ButtonClicked'] == '1':
                self.send_data({'ButtonClicked': '2'})
            if 'ListGroups' in message and message['ListGroups'] == '1':
                self.send_data({'Group1': 'RDC', 
                    'Group2': 'Etage', 'Group3': 'Grenier'})
        elif msg['headers']['destination'] == CHANNEL_MINIDO_READ:
            self.mpd.recv_minido_packet(message)
        elif msg['headers']['destination'] == CHANNEL_MINIDO_LAYOUT:
            if 'query' in message.keys():
                if message['query'] == 'getLayout':
                    self.send(CHANNEL_MINIDO_LAYOUT, 
                        json.encode({'layout': self.mpd.devdict}))
                elif message['query'] == 'getStatus':
                    self.send(CHANNEL_MINIDO_LAYOUT, 
                        json.encode({'status': 'This is a status line'}))
 
    def send_data(self, data):
        print("Sending : " + str(data))
        self.send(CHANNEL_MINIDO_WRITE, json.encode(data))

    def clientConnectionLost(self, connector, reason):
        time.sleep(1.0)
        reactor.connectTCP(MORBIDQ_HOST, MORBIDQ_PORT, self)
 
class MinidoProtocolDecoder():
    """ 
    AnB protocol (high level), also used for Minido, D2000 and C2000 
    The constructor builds exodict and devdict from mydb.populate...
    Is it the right place for this mydb.populate... ?
    This class is a Singleton
    This class :
        - Initialize DB
        - Initialize exodict
        - Initialize exidict
        - Initialize devdict
        - Scan the EXI
    """
    chardata = list()
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(MinidoProtocolDecoder, cls).__new__(cls, 
                *args, **kwargs)
        return cls._instance

    def __init__(self, send_data):
        # FixMe
        # Remove the self and the SQLITEDB from the constructor
        self.mydb = Db()
        print('Creating exodict...')
        self.send_data = send_data
        self.exodict = Exodict(self.send_data)
        print('Creating exidict...')
        self.exidict = dict()
        print('Creating devdict...')
        self.devdict = self.mydb.populate_devdict(self.exodict)
        print('MinidoProtocolDecoder Singleton initialized')
        self.scan_exi()
        # self.scan_exo()

    def recv_minido_packet(self, message):
        """
        Called when a new packet is validated by the protocol (low level).
        This methods decodes the packet
        """
        print(' '.join(['{0:02x}'.format(x) for x in message]))
        if EXOOFFSET < message[DST] <= EXOOFFSET + 16:
            # This is a packet for an EXO module : EXI2EXO
            # No need of additional test as EXO2EXO does not exists.
            exoid = message[DST] - EXOOFFSET
            exiid = message[SRC] - EXIOFFSET
            # EXO_UPDATE :
            # We must call the exo to check if a change occured.
            if message[COM] == CMD['EXO_UPDATE']:
                try:
                    list_of_changes = self.exodict[exoid].update(exiid, 
                        message[5:-1])
                    for change in list_of_changes:
                        print( ('{0!s:.23} : EXI-{1:02}->EXO-{2:02} : ' + \
                            'Output {3:1} = {4:3}  ( was {5:3})').format(
                            datetime.datetime.now(),
                            exiid, exoid,
                            change[0],
                            change[1],
                            change[2]
                            ))
                except(KeyError):
                    print("This should never happen : all EXO are created")
            elif message[COM] == CMD['EXO_ECHO_REQUEST']:
                print( ('{0!s:.23} : EXI-{1:02}->EXO-{2:02} : ' + \
                    'EXI2EXO_ECHO_REQUEST').format(
                    datetime.datetime.now(),
                    exiid, exoid,
                    ))
                # Nothing more to do, as it's probably comming from us.

        elif EXIOFFSET < message[DST] <= EXIOFFSET + 16:
            # This is a packet to an EXI module
            exiid = message[DST] - EXIOFFSET
            if EXOOFFSET < message[SRC] <= EXOOFFSET + 16:
                # From an EXO module : EXO2EXI
                exoid = message[SRC] - EXOOFFSET
                # EXO_ECHO_REPLY
                if message[COM] == CMD['EXO_ECHO_REPLY']:
                    print( ( '{0!s:.23} : EXO-{1:02}->MU ' +
                        'EXO2EXI_ECHO_REPLY').format(
                        datetime.datetime.now(),
                        exoid
                        ))
                    self.exodict[exoid].is_present = True
                else:
                    print('Problem here. AFAIK an EXO never send anything \
                        to EXI except for EXO_ECHO_REPLY')
                    print('{0!s:.23} : EXO-{2:02}->EXI-{1:02} : \
                        CMD:{3:2} DATA:{4!s:10}'.format(
                        datetime.datetime.now(),
                        exiid,exoid,
                        message[COM],
                        message[5:-1]
                        ))
            else:
                # From an EXI module : EXI2EXI
                if message[COM] == CMD['EXI_ECHO_REQUEST']:
                    print( '{0!s:.23} : EXI-{2:02}->EXI-{1:02} : \
                        EXI2EXI_ECHO_REQUEST'.format(
                        datetime.datetime.now(),
                        message[DST] - EXIOFFSET,
                        message[SRC] - EXIOFFSET,
                        ))
                elif message[COM] == CMD['EXI_ECHO_REPLY']:
                    srcexiid = message[SRC] - EXIOFFSET
                    print( '{0!s:.23} : EXI-{2:02}->EXI-{1:02} : \
                        EXI2EXI_ECHO_REPLY'.format(
                        datetime.datetime.now(),
                        message[DST] - EXIOFFSET,
                        srcexiid,
                        ))
                    self.exidict[srcexiid] = Exi(self.send_data)
                else:
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
                # This is packet normally used by D2000
                # The EXI info is twice in the packet, 
                # that's why we make the second check.
                print( ( '{0!s:.23} : EXI-{1:02}->D-2000 : ' +
                    'Button {2:2}').format(
                    datetime.datetime.now(),
                    message[SRC]-EXIOFFSET,
                    message[6],
                    ))
        else:
            print( ( '{0!s:.23} : SRC-{2:02x}->DST-{1:02x} : ' +
                'Unable to decode - ' +
                'CMD (hex):{3:02x} DATA (hex):{4!s:10}' ).format(
                datetime.datetime.now(),
                message[DST],
                message[SRC],
                message[COM],
                ' '.join(['{0:02x}'.format(x) 
                    for x in message[5:-1]])
                ))

    def send_packet(self, data):
        self.send_data(data)

    def send_command(self, dst, cmd, cmd_data = list(), src = EXIID):
        """
        This is a helper to build packet.
        """
        packet = [ 35, dst, src, len(cmd_data) + 2, cmd ] + cmd_data
        self.send_data(packet)

    def scan_exo(self):
        self.d = defer.Deferred()
        self.exo = 1
        def scanNext():
            if self.exo >= 16:
                self.loop.stop()
                self.d.callback(None)
            self.send_command(self.exo + EXOOFFSET, CMD['EXO_ECHO_REQUEST'])
            self.exo += 1
        self.loop = LoopingCall(scanNext)
        self.loop.start(0.1)

    def scan_exi(self):
        """
        First scan the EXI
        Check answers to make sure we do not use an EXIID
        that is already used by a real EXI
        """
        self.exid = defer.Deferred()
        self.exi = 1
        def scanNext():
            if self.exi >= 16:
                self.exiloop.stop()
                self.exid.callback(None)
            packet = [35, 00, 11, 2, CMD['EXI_ECHO_REQUEST']]
            packet[1] = self.exi + EXIOFFSET
            self.send_command(self.exi + EXIOFFSET, CMD['EXI_ECHO_REQUEST'])
            self.exi += 1
        self.exiloop = LoopingCall(scanNext)
        self.exiloop.start(0.1)

if __name__ == '__main__':
    from twisted.internet import reactor
    morbidq_factory = MorbidQClientFactory()
    ws = WebService()
    ws.morbidq_factory = morbidq_factory
    xmlrpc.addIntrospection(ws)
    reactor.listenTCP( 8000, server.Site(ws) )
    reactor.connectTCP(MORBIDQ_HOST, MORBIDQ_PORT, morbidq_factory)
    reactor.run()
