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

CONNTYPE = 'Socket'
MINIDO_ADAPTER_HOST = 'minidoadt'
MINIDO_ADAPTER_PORT = 23
MORBIDQ_HOST = 'localhost'
MORBIDQ_PORT = 61613
CHANNEL_MINIDO_NAME = "/mu/minido"
CHANNEL_DISPLAY_NAME = "/mu/display"
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

class GenericDevice(object):
    """ Light states & methods """
    def __init__(self, 
        channels, type_ = 'Light, DimLight or RCS (Remote controlled socket)',
        name = 'Generic Device'):
        self.channels = channels
        self.type_ = type_
        self.name = name
    def __str__(self):
        return "Device : type {0} name {1} channels {2!s}".format(
            self.type_, self.name, self.channels)
    def set_value(self, cmd):
        """ Set device status """
        exo = self.channels['power']['exo']
        channel = self.channels['power']['channel']
        if str(cmd) == 'on':
            exo.set_output(channel, 255)
        elif str(cmd) == 'off':
            exo.set_output(channel, 0)
        else:
            exo.set_output(channel, int(cmd))
    def get_value(self):
        """ Get device status """
        exo = self.channels['power']['exo']
        return(exo.get_output(self.channels['power']['channel']))

class StoreDevice(GenericDevice):
    """ Store """
    def __init__(self, channels, type_ = 'StoreNoType',
        name = 'Generic Device'):
        GenericDevice.__init__(self, channels)
        self.name = name
        self.type_ = type_
        self.exoup = channels['up']['exo']
        self.channelup = channels['up']['channel']
        self.exodown = channels['down']['exo']
        self.channeldown = channels['down']['channel']
        self.tmr = Timer( 1, self.exoup.set_output,
                [self.channelup, 0])
        self.openratio = None

    def set_value(self, cmd):
        """ Set device status """
        if ( cmd == 'up' and 
                self.exoup.get_output(self.channelup) == 0):
            if self.tmr.is_alive():
                self.tmr.cancel()
            if self.exodown.get_output(self.channeldown) != 0 :
                self.exodown.set_output(self.channeldown, 0)
                time.sleep(0.3)
            self.exoup.set_output(self.channelup, 255)
            self.tmr = Timer(30, 
                self.exoup.set_output, [self.channelup, 0])
            self.tmr.start()

        if ( cmd == 'down' and 
                self.exodown.get_output(self.channeldown) == 0):
            if self.tmr.is_alive():
                self.tmr.cancel()
            if ( self.exoup.get_output(self.channelup) != 0 ):
                self.exoup.set_output(self.channelup, 0)
                time.sleep(0.3)
            self.exodown.set_output(self.channeldown, 255)
            self.tmr = Timer(30,
                self.exodown.set_output, [self.channeldown, 0])
            self.tmr.start()

        if ( cmd == 'stop' ):
            if ( self.tmr.is_alive() ):
                self.tmr.cancel()
            if ( self.exoup.get_output(self.channelup) !=0 ):
                self.exoup.set_output(self.channelup, 0)
            elif ( self.exodown.get_output(self.channeldown) != 0 ):
                self.exodown.set_output(self.channeldown, 0)

    def get_value(self):
        """ Get store status """
        if ( self.exoup.get_output(self.channelup) != 0 ):
            return('up')
        elif ( self.exodown.get_output(self.channeldown) !=0 ):
            return('down')
        else:
            return('stop')

class VentilationDevice(GenericDevice):
    """ Ventilation Mecanique Constolee """
    pass

class Exo(object):
    """ One instanciation for each physical EXO module """
    # self.history is a tuple of 8 deque containing (date, value) tuples.
    def __init__(self, src, exoid, mydb, protocol):
        self.src = src
        self.exoid = exoid
        self.mydb = mydb
        self.protocol = protocol
        self.oldstatus = list()
        self.history = tuple([deque(maxlen=HIST) for i in range(8)])
        # Not necessary, but ensure queues are not empty.
        for i in range(8):
            self.history[i].append( ( datetime.datetime.now(), None ) )

    def update(self, src, statuslist):
        """Update the Exo status"""
        self.src = src
        self.oldstatus = [self.history[i][-1][1] for i in range(8)]
        for i in range(8):
            if self.history[i][-1][1] != statuslist[i]:
                now = datetime.datetime.now()
                self.history[i].append( ( now, statuslist[i] ) )
                self.mydb.history( now, 'EXO', self.exoid, i+1, statuslist[i] )
                print( ('{0!s:.23} : EXI-{1:02}->EXO-{2:02} : ' + \
                    'Channel {3:1} = {4:3}').format(
                    now,
                    self.src,
                    self.exoid,
                    i+1,
                    statuslist[i]
                    ))

    def update_history(self, dtime, output, status):
        """ Used to update from DB history """
        data = (dtime, status)
        self.history[output - 1].append( data )

    def set_output(self, channel, value):
        """Change the status of an EXO channel"""
        idx = channel - 1
        now = datetime.datetime.now()
        # These 2 lines might seem touchy, and should be explained.
        self.mydb.history( now, 'EXO', self.exoid, idx+1, value )
        self.history[ idx ].append( ( now, value ) )
        newdata = [self.history[i][-1][1] for i in range(8)]
        self.protocol.factory.connection.send_packet( self.exoid + EXOOFFSET, [01] + newdata )
        # return [self.history[i][-1][1] for i in range(8)]
        return 'Ok'

    def get_output(self, channel):
        """Get status of an EXO output"""
        return self.history[ channel -1 ][-1][1]


class Db(object):
    """ Every access to DB from here """
    def __init__(self, protocol):
        self.exodict = dict()
        self.protocol = protocol
        try:
            self.conn = sqlite3.connect(SQLITEDB,
                detect_types=sqlite3.PARSE_DECLTYPES|\
                sqlite3.PARSE_COLNAMES, check_same_thread = False)
        except:
            print("I am unable to connect to the SQLITE database ( " + SQLITEDB
                + ") , exiting.")
            raise
        self.cur = self.conn.cursor()
        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS output (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exo INTEGER NOT NULL  DEFAULT NULL,
        channel INTEGER NOT NULL  DEFAULT NULL,
        type TEXT DEFAULT NULL
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS button (
        id INTEGER NOT NULL  DEFAULT NULL PRIMARY KEY AUTOINCREMENT,
        id_exi_id INTEGER DEFAULT NULL REFERENCES exi (id),
        floor TEXT DEFAULT NULL,
        room TEXT DEFAULT NULL,
        posx INTEGER DEFAULT NULL,
        posy INTEGER DEFAULT NULL,
        name TEXT DEFAULT NULL
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS exi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exi INTEGER NOT NULL  DEFAULT NULL,
        number INTEGER NOT NULL  DEFAULT NULL
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS exi_id2output (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_exi_id INTEGER DEFAULT NULL REFERENCES exi (id),
        id_output INTEGER DEFAULT NULL REFERENCES output (id)
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS output2device (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_output INTEGER NOT NULL REFERENCES output (id),
        id_device INTEGER NOT NULL REFERENCES device (id),
        cmdtype TEXT DEFAULT NULL
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS device (
        id INTEGER NOT NULL  DEFAULT NULL PRIMARY KEY AUTOINCREMENT,
        devtype TEXT DEFAULT NULL,
        name INTEGER DEFAULT NULL REFERENCES translation (id),
        floor INTEGER DEFAULT NULL REFERENCES translation (id),
        room INTEGER DEFAULT NULL REFERENCES translation (id),
        posx INTEGER DEFAULT NULL,
        posy INTEGER DEFAULT NULL,
        description TEXT DEFAULT NULL
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS trigger (
        id INTEGER NOT NULL  DEFAULT NULL PRIMARY KEY AUTOINCREMENT,
        name TEXT DEFAULT NULL,
        on_status TEXT DEFAULT NULL,
        from_time TEXT DEFAULT NULL,
        to_time TEXT DEFAULT NULL,
        weekdays TEXT DEFAULT NULL,
        src_type TEXT DEFAULT NULL,
        src_busid INTEGER DEFAULT NULL,
        src_channel INTEGER DEFAULT NULL,
        id_program INTEGER DEFAULT NULL
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS actions (
        function TEXT NOT NULL  DEFAULT 'deviceaction',
        parameter1 TEXT DEFAULT NULL,
        parameter2 TEXT DEFAULT NULL,
        parameter3 TEXT DEFAULT NULL,
        id_program INTEGER DEFAULT NULL REFERENCES trigger (id)
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS translation (
        id INTEGER NOT NULL  DEFAULT NULL PRIMARY KEY AUTOINCREMENT,
        language TEXT NOT NULL  DEFAULT 'NULL',
        text TEXT NOT NULL  DEFAULT 'NULL'
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS log (
        id INTEGER NOT NULL  DEFAULT NULL PRIMARY KEY AUTOINCREMENT,
        logtime NONE NOT NULL  DEFAULT NULL,
        logsource TEXT DEFAULT NULL,
        logtext TEXT DEFAULT NULL
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS scheduler (
        id INTEGER DEFAULT NULL PRIMARY KEY AUTOINCREMENT,
        year TEXT DEFAULT NULL,
        month TEXT DEFAULT NULL,
        day TEXT DEFAULT NULL,
        week TEXT DEFAULT NULL,
        day_of_week TEXT DEFAULT NULL,
        hour TEXT DEFAULT NULL,
        minute TEXT DEFAULT NULL,
        second TEXT DEFAULT NULL
        );
        '''))

        self.cur.execute(textwrap.dedent('''
        CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dtime DATETIME,
        type TEXT NOT NULL,
        busid NUMERIC NOT NULL,
        channel NUMERIC NOT NULL,
        status TEXT NOT NULL
        );
        '''))

        self.mdev = dict()

    def history(self, now, type_, exoid, output, status):
        """ history( now, self.exoid, self.status[i] )"""
        self.cur.execute("INSERT INTO history \
            ( dtime, type, busid, channel, status ) \
            VALUES ( ?, ?, ?, ?, ?)", [now, type_, exoid, output, status])

    def get_device_details(self):
        self.cur.execute(textwrap.dedent('''
        SELECT output.id, output2device.id, device.id,exo,channel,type,
        cmdtype, devtype, name, floor, room 
        FROM output2device 
        LEFT JOIN device ON id_device=device.id 
        LEFT JOIN output ON id_output=output.id 
        ORDER BY floor,room;
        '''))
        result = dict()
        for row in self.cur:
            result[row[8]]= row
        return(result)

    def populate_exodict(self):
        """ Retrieve exodict object from the history """
        self.cur.execute("SELECT dtime, busid, channel, status \
            FROM history WHERE type = 'EXO'")
        for row in self.cur:
            exoid = int(row[1])
            output = int(row[2])
            status = int(row[3])
            if row[1] in self.exodict:
                self.exodict[exoid].update_history(row[0], output, status)
                # print('Updating from DB : ', exoid, output, status)
            else:
                print('Exo does not exists, creating it.')
                statuslist = 8 * [None]
                statuslist[output - 1] = status
                self.exodict[exoid] = Exo( 255, exoid, self, self.protocol)
                self.exodict[exoid].update_history(row[0], output, status)
                print('Updating from DB : ', exoid, output, status)

        print(datetime.datetime.now(), 'self.exodict restored')
        return(self.exodict)

    def populate_devdict(self):
        """ Retrieve known devices from DB """
        print(('{0!s:.23} : Initialisation : ' +
            'Importing known devices...').format(
            datetime.datetime.now()))
        self.cur.execute("SELECT id, devtype, name, floor, room, \
            posx, posy, description FROM device")
        devdict = dict()
        # Sample devdict structure :
        # devdict = {'CentreBureau': GenericDevice(
        #   {'power': {'exo':3, 'channel':1}}, type_ = 'Light', ...), ... }
        cur2 = self.conn.cursor()
        print('exodict : ', self.exodict)
        for row in self.cur:
            devid = str(row[0])
            devtype = row[1]
            name = row[2]
        #            devdetails[devid] = dict(
        #                name = row[2],
        #                floor = str(row[3]),
        #                room = str(row[4]),
        #                posx = row[5],
        #                posy = row[6],
        #                description = row[7]
        #            )
            # Fetch the exo/channels for the device.
            channels = dict()
            print('devid : ', row[0], ' devtype : ', row[1], ' name ', row[2])
            cur2.execute(
                "SELECT cmdtype, exo, channel FROM output2device \
                LEFT JOIN output ON id_output = output.id WHERE \
                id_device = '{0}'".format(devid))
            for row2 in cur2:
                print(row2)
                try:
                    channels[ str(row2[0]) ] = {
                        'exo': self.exodict[int(row2[1])],
                        'channel': int(row2[2]) 
                        }
                except(KeyError):
                    print('KeyError creating devdict : ', row2[1])
            # End fetch the exo/channels for the device.
            if devtype == 'Light':
                devdict[ devid ] = GenericDevice( channels, 'Light', name)
            elif devtype == 'RCS':
                devdict[ devid ] = GenericDevice( channels, 'RCS', name)
            elif devtype == 'Store':
                devdict[ devid ] = StoreDevice( channels, 'Store', name)
                print('Debug', devdict[ devid ] , "StoreDevice : ", channels)
        print(('{0!s:.23} : Initialisation : ' +
            'Known devices imported.').format(
            datetime.datetime.now()))
        return( devdict )

    def get_dev_details(self, filter_=None, sort=None):
        devdetails = dict()
        self.cur.execute("SELECT id, devtype, name, floor, room, \
            posx, posy, description FROM device")
        cur = self.conn.cursor()
        print('exodict : ', self.exodict)
        for row in self.cur:
            devid = str(row[0])
            devdetails[devid] = dict(
                name = row[2],
                floor = str(row[3]),
                room = str(row[4]),
                posx = row[5],
                posy = row[6],
                description = row[7]
            )

    def commit(self):
        """ Commit (used when we have time to do it) """
        self.conn.commit()

    def closedb(self):
        """ Cleanly close the DB """
        self.conn.commit()
        self.cur.close()
        self.conn.close()

class WebService(xmlrpc.XMLRPC):
    """ Gather all methods exposed through the SOAP web service """
    allowNone = 0
    def __init__(self, factory):
        self.factory = factory
        self.exilist = [0x14, 0x15, 0x16, 0x18]

    def xmlrpc_set_output(self, exo, output, value):
        """ change output state """
        try:
            newdata = self.factory.connection.exodict[exo].set_output(int(output), int(value))
        except(KeyError):
            pass
        return(newdata)

    def xmlrpc_get_output(self, exo, output):
        """ Get the value of an output """
        try:
            return(self.factory.connection.exodict[exo].get_output(output))
        except(KeyError):
            return('No such exo in memory')
        return('Unexpected Error')

    def xmlrpc_list_exo(self):
        """ Return the list of EXO currently known by MU """
        exolist = list(iter(self.factory.connection.exodict))
        return(exolist)

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
        exi = self.exilist[0]
        self.protocol.factory.connection.send_packet( exi, data )
        return(0)

    def xmlrpc_set_device_value(self, devid, value):
        """ Update the device status """
        print(self.factory.connection.devdict[int(devid)])
        self.factory.connection.devdict[devid].set_value(value)
        return('Ok')

    def xmlrpc_get_device_value(self, devid):
        """ List devices """
        return(str(self.factory.connection.devdict[devid].get_value()))

    def xmlrpc_get_device_dict(self):
        """ Get list of devices """
        return(self.factory.connection.devdict)

    def xmlrpc_get_device_details(self):
        """ List devices from DB """
        return(self.factory.connection.mydb.get_device_details())

    def xmlrpc_get_nextevent(self):
        return(self.factory.connection.xmlrpclongpollqueue.get())

class MinidoProtocol(Protocol):
    ''' Bus protocol, also used for Minido, D2000 and C2000 '''
    chardata = list()
    def __init__(self):
        # self.factory = factory
        self.mydb = Db(self)
        self.exodict = self.mydb.populate_exodict()
        self.devdict = self.mydb.populate_devdict()
        self.xmlrpclongpollqueue = Queue(5)
        print('MinidoProtocol initialized')
        print(self.exodict)

    def connectionMade(self):
        self.factory.connection = self

    def newpacket(self, data):
        """ Called when a new packet is validated """
        # Just for fun
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
                        exoid, self.mydb, self)
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
        #self.send_packet(0x3e, [01, 00, 00, 00, 00, 00, 00, 00, 00])
        # This is buggy code, I just leave it to ensure I think to remove any reference to it
        #self.xmlrpclongpollqueue.put(data)

    def send_packet(self, dst, data):
        valuelist = [0x23, dst, EXIID, len(data) + 1] + data
        valuelist.append(checksum( data ))
        print('Debug : sending packet : ', ' '.join(
            [ '%0.2x' % c for c in valuelist ]))
        packet = ''.join([chr(x) for x in valuelist])
        self.transport.write(packet)

    def dataReceived(self, chardata):
        """ This method is called by Twisted  """
        self.chardata.extend(chardata)
        # if len(self.chardata) >= 6:
            
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
                    print("Debug " + str(len(self.chardata)) + " datalength : " + str(datalength))
                    if checksum(
                        [ord(x) for x in self.chardata[4:datalength + 3]]
                        ) != ord(self.chardata[datalength + 3]):
                        print("Warning : Invalid checksum for packet : "
                            + str( self.chardata ))
                        validpacket = self.chardata[0:datalength + 4]
                        self.chardata = self.chardata[datalength + 4:]
                        continue
                    else:
                        validpacket = self.chardata[0:datalength + 4]
                        self.chardata = self.chardata[datalength + 4:]
                    # OK, I have now a nice, beautiful, valid packet
                    data = [ord(x) for x in validpacket]
                    self.newpacket(data)
                else:
                    print("Debug packet : " + str(map(lambda x: ord(x), self.chardata)))
                    print("Debug ord(self.chardata[3]) : " + str(datalength))
                    break


class MinidoClientFactory(ReconnectingClientFactory):
    protocol = MinidoProtocol
    def startedConnecting(self, connector):
        print('Started to connect.')

#    def buildProtocol(self, addr):
#        print 'Connected.'
#        print 'Resetting reconnection delay'
#        self.resetDelay()
#        return self.protocol()
#
#    def clientConnectionLost(self, connector, reason):
#        print 'Lost connection.  Reason:', reason
#        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
#
#    def clientConnectionFailed(self, connector, reason):
#        print 'Connection failed. Reason:', reason
#        ReconnectingClientFactory.clientConnectionFailed(self, connector,
#                                                         reason)
 
class MorbidQClientFactory(StompClientFactory):
 
    def recv_connected(self, msg):
        self.subscribe(CHANNEL_DISPLAY_NAME)

    def recv_message(self, msg):
        message = json.decode(msg['body'])
        if msg['headers']['destination'] == CHANNEL_DISPLAY_NAME:
            print(message)
            # self.handlers[message['id']].setattr(message['trait'], message['value'])
            if 'ButtonClicked' in message and message['ButtonClicked'] == '1':
                self.send_data({'ButtonClicked': '2'})
            if 'ListGroups' in message and message['ListGroups'] == '1':
                self.send_data({'Group1': 'RDC', 'Group2': 'Etage', 'Group3': 'Grenier'})
        elif msg['headers']['destination'] == CHANNEL_CONTROL_NAME:
            pass
 
    def send_data(self, data):
        self.send(CHANNEL_DISPLAY_NAME, json.encode(data))
 

def mu_main():
    morbidqFactory = MorbidQClientFactory()
    minidoFactory = MinidoClientFactory()
    ws = WebService(minidoFactory)
    reactor.listenTCP( 8000, server.Site(ws) )
    reactor.connectTCP(MINIDO_ADAPTER_HOST, MINIDO_ADAPTER_PORT, minidoFactory)
    reactor.connectTCP(MORBIDQ_HOST, MORBIDQ_PORT, morbidqFactory)
    reactor.run()

if __name__ == '__main__':
    mu_main()

