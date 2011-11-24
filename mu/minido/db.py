import textwrap
import sqlite3
import datetime
from minido.exo import Exo
from minido.devices import *

HIST = 5
class Db(object):
    """ Every access to DB from here """
    def __init__(self, protocol, sqlitedb):
        print(sqlitedb, protocol)
        self.sqlitedb = sqlitedb
        self.exodict = dict()
        self.protocol = protocol
        try:
            self.conn = sqlite3.connect(self.sqlitedb,
                detect_types=sqlite3.PARSE_DECLTYPES|\
                sqlite3.PARSE_COLNAMES, check_same_thread = False)
        except:
            print("I am unable to connect to the SQLITE database ( " + str(self.sqlitedb)
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
                self.exodict[exoid] = Exo( 255, exoid, self, self.protocol, HIST)
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
        # print('exodict : ', self.exodict)
        cur2 = self.conn.cursor()
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
