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

from twisted.internet.protocol import Protocol
from twisted.internet import task
import datetime

def checksum(datalist):
    """ Calculate an XOR checksum """
    checksum_ = 0
    for item in datalist:
        checksum_ ^= item
    return checksum_

class MinidoProtocol(Protocol):
    """
    Bus protocol (low level), also used for Minido, D2000 and C2000
    This class only assemble and validate the packet, but does not decode is.
    This class can also check the checksum of incoming packets, 
    or add the missing checksum before sending packets.
    The decoding is left to the MinidoProtocolDecoder class when receiving
    new packet.
    """
    chardata = list()
    def __init__(self, factory, kalive=0.0):
        self.factory = factory
        print('MinidoProtocol initialized')
        self.factory.connections = list()
        self.kalive = kalive

    def connectionMade(self):
        print(str(datetime.datetime.now()) + " :" +
            "New connection :" + str(self.transport.getPeer()))
        self.factory.connections.append(self)
        if self.kalive > 0.0:
            print('Starting the keepalive loop every ' + str(self.kalive) + ' seconds.')
            self.loopingcall = task.LoopingCall(self.keepalive)
            self.loopingcall.start(self.kalive)
        else:
            print('Keepalive disabled for this connection')

    def connectionLost(self, reason):
        self.factory.connections.remove(self)
        print("Lost connection : " + str(self.transport.getPeer()))
        print("Reason : " + str(reason))
        if self.kalive > 0.0:
            self.loopingcall.stop()


    def newpacket(self, data):
        """ Called when a new packet is validated """
        self.factory.recv_message(data)

    def send_data(self, data):
        if data[len(data)-1] == checksum( data[4:(len(data)-1)]):
            # print(str(datetime.datetime.now()) + " : ",
            #     ' '.join([ '%0.2x' % c for c in data ]))
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

#    def send_packet(self, dst, data):
#        valuelist = [0x23, dst, EXIID, len(data) + 1] + data
#        valuelist.append(checksum( data ))
#        print('Debug : sending packet : ', ' '.join(
#            [ '%0.2x' % c for c in valuelist ]))
#        packet = ''.join([chr(x) for x in valuelist])
#        self.transport.write(packet)

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
                    self.newpacket(data)
                else:
                    #print("Debug packet : " + str(map(lambda x: ord(x), self.chardata)))
                    #print("Debug ord(self.chardata[3]) : " + str(datalength))
                    break

    def keepalive(self):
         self.send_data([0x31, 0x00, 0x00, 0x01, 0x00])
#        Looks like the following code is now useless.
#        try:
#            print("Keepalive")
#            self.send_data([0x31, 0x00, 0x00, 0x01, 0x00])
#        except:
#            # Not nice, but we must evate all errors, as it's just a keepalive and
#            # might fail for many reasons, including during initialization.
#            pass
 
