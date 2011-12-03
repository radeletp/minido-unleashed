import textwrap
import sqlite3
import datetime
# from exo import *
from devices import *
from twisted.internet import reactor, defer, error

SQLITEDB = "minido_unleashed.db"

class Db(object):
    """ Every access to DB from here """
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Db, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """
        Open the SQLite DB, and check that all tables are existing
        otherwise create them.
        """
        # self.exodict = dict()
        # Open the DB
        try:
            self.initcount += 1
        except AttributeError:
            self.initcount = 0

        if self.initcount > 0:
            return

        try:
            self.conn = sqlite3.connect(SQLITEDB,
                detect_types=sqlite3.PARSE_DECLTYPES|\
                sqlite3.PARSE_COLNAMES, check_same_thread = False)
        except:
            print("I am unable to connect to the SQLITE database ( " + str(SQLITEDB)
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

        self.clean_history()
        # Obsolete ?
        # self.mdev = dict()

    def history(self, now, type_, exoid, output, status):
        """ history( now, self.exoid, self.status[i] )"""
        self.cur.execute("INSERT INTO history \
            ( dtime, type, busid, channel, status ) \
            VALUES ( ?, ?, ?, ?, ?)", [now, type_, exoid, output, status])
        self.schedule_commit()


    def get_device_details(self):
        """
        Retrieve devices from the DB (only)
        Quite similar to populate_devdict.
        We could probably get rid of it, using the data
        directly in the devices.
        """
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

    def populate_exodict(self, exodict):
        """ Retrieve/populate exodict object by replaying
        the history """
        self.cur.execute("SELECT dtime, busid, channel, status \
            FROM history WHERE type = 'EXO'")
        for row in self.cur:
            exoid = int(row[1])
            output = int(row[2])
            status = int(row[3])
            if row[1] in exodict:
                exodict[exoid].update_history(row[0], output, status)

        print(datetime.datetime.now(), 'self.exodict restored')
        return(exodict)

    def populate_devdict(self, exodict):
        """ Retrieve known devices from DB """
        print(('{0!s:.23} : Initialisation : ' +
            'Importing known devices...').format(
            datetime.datetime.now()))
        self.cur.execute("SELECT id, devtype, name, floor, room, \
            posx, posy, description FROM device")
        devdict = dict()
        # Sample devdict structure :
        # ToDo : Update the following description
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
                        'exo': exodict[int(row2[1])],
                        'channel': int(row2[2]) 
                        }
                except(KeyError):
                    print('Probably major problem in the DB as all exos are in exodict already')
                    print('Exo ' + str(row2[1]) + ' does not exists in exodict')
            # End fetch the exo/channels for the device.
            if devtype == 'Light':
                devdict[ devid ] = LightDevice( channels, name)
            elif devtype == 'RCS':
                devdict[ devid ] = LightDevice( channels, name)
            elif devtype == 'Store':
                devdict[ devid ] = StoreDevice( channels, name)
                print('Debug', devdict[ devid ] , "StoreDevice : ", channels)
        print(('{0!s:.23} : Initialisation : ' +
            'Known devices imported.').format(
            datetime.datetime.now()))
        return( devdict )

    def get_dev_details(self, filter_=None, sort=None):
        """Get device detail from DB.
        Probably obsolete also"""
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
    def clean_history(self):
        """Used at startup to clean history in the DB (last 60 days)"""
        now = datetime.datetime.now()
        td = datetime.timedelta( days=-60 )
        print("Cleaning history")
        self.cur.execute("DELETE FROM history WHERE dtime < ?", [now + td,])
        self.schedule_commit()

    def schedule_commit(self):
        try:
            self.delayed_commit.reset(5)
        except (error.AlreadyCalled, AttributeError):
            # Initialize the Deferred used for the Deferred Commit
            self.cdf = defer.Deferred()
            self.delayed_commit = reactor.callLater(5, self.cdf.callback, None)
            self.cdf.addCallback(self.commit)

    def commit(self, x):
        """ Commit (Called back after 5 seconds of inactivity on the bus.) """
        print('Commit into DB')
        self.conn.commit()

    def closedb(self):
        """ Cleanly close the DB """
        self.conn.commit()
        self.cur.close()
        self.conn.close()

