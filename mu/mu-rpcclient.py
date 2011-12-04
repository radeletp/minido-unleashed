#!/usr/bin/env python
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


import argparse
import textwrap
import sys
import xmlrpclib


parser = argparse.ArgumentParser(
    formatter_class=argparse.RawDescriptionHelpFormatter,
    description=textwrap.dedent('''\
    Minido Unleashed command line interface

    Commands :
        list : to list all objects available
        set : to change the state of an object
        get : to get the state of an object

    Low level commands :
        You must know the exo id and the output id for these commands
        and specify them with -e 1 -o 1 (for exi 1 output 1)

        setouput  : low level command to set an exo output state.
        getoutput : low level command to get an exo output state.

    Programming commands :
        Warning. These commands will turn programming mode on the EXI,
        you must ALWAYS issue a cancelmode when you've finished.

        You must know the exo id and the output id for these commands
        and specify them with -e 1 -o 1 (for exi 1 output 1)

        addmode    : Add a button to the specified exi output. 
        delmode    : Remove a button to the specified exi output. 
        cancelmode : Cancel programming mode.

    Examples :
        ./muclient.py list
        ./muclient.py get CentreWC
        ./muclient.py set CentreWC on
        ./muclient.py get CentreWC
        ./muclient.py set CentreWC off

    Examples for more advanced commands (directly command exo)
        ./muclient.py -e 1 -o 1 setoutput 0
        ./muclient.py -e 1 -o 1 getoutput 
        ./muclient.py -e 1 -o 1 setoutput 255
    ''') )
parser.add_argument("command", default="list", nargs="+",
    help="Command : list, setoutput, getoutput, set, get, " +
    "addmode, delmode, cancelmode, listmethods (for dev)")
parser.add_argument("-u", "--url", dest="url",
    default='http://localhost:8000', 
    help="MU XMLRPC server url (default http://localhost:8000)")
parser.add_argument("-e", "--exo", type=int, dest="exo", required=False,
    help="EXO module to read or write")
parser.add_argument("-o", "--output", type=int, dest="output",
    choices = [1,2,3,4,5,6,7,8], required=False,
    help="Output/channel of the exo (from 1 to 8)")

parser.add_argument('-v', '--verbose', action="store_true", 
    help="Verbose mode")

args = parser.parse_args()

try:
    if args.verbose == True:
        client = xmlrpclib.ServerProxy(args.url, verbose=True)
    else:
        client = xmlrpclib.ServerProxy(args.url)
except(IOError):
    print("Unable to connect to web service server.")
    sys.exit(0)






if args.command[0] == 'setoutput':
    print('Writing value to exo : ' + str(args.exo) + ', output : ' 
        + str(args.output) + ', value : ' + str(args.command[1]))
    result = client.set_output(args.exo, args.output, args.command[1])
    if args.verbose == True:
        print(result)
    else:
        print(result)
elif args.command[0] == 'getoutput':
    print('Reading value on exo : ' + str(args.exo) + ', output : ' 
        + str(args.output))
    result = client.get_output(args.exo, args.output)
    if args.verbose == True:
        print(result)
    else:
        print(result)
elif args.command[0] == 'listmethods':
    print client.system.listMethods()


elif args.command[0] == 'list':
    # result = client.get_device_details()
    result = client.get_device_dict()
    for i in result:
        print(i, result[i])
elif args.command[0] == 'get':
    try:
        result = client.get_device_value(args.command[1])
        print(result)
    except(xmlrpclib.Fault):
        print('This object does not exists on the server. Please use list command to check')
elif args.command[0] == 'set':
    try:
        result = client.set_device_value(args.command[1], args.command[2])
        print(result)
    except(xmlrpclib.Fault):
        print('This object does not exists on the server. Please use list command to check')
elif args.command[0] == 'on':
    try:
        result = client.set_device_on(args.command[1])
        print(result)
    except(xmlrpclib.Fault):
        print('This object does not exists on the server. Please use list command to check')
elif args.command[0] == 'off':
    try:
        result = client.set_device_off(args.command[1])
        print(result)
    except(xmlrpclib.Fault):
        print('This object does not exists on the server. Please use list command to check')

elif args.command[0] == 'cancelmode':
    result = client.minido_programming(args.exo, args.output, 'cancel')
    # print(result)
elif args.command[0] == 'delmode':
    result = client.minido_programming(args.exo, args.output, 'remove')
    # print(result)
elif args.command[0] == 'addmode':
    result = client.minido_programming(args.exo, args.output, 'add')
    # print(result)
elif args.command[0] == 'getnext':
    result = client.get_nextevent()
