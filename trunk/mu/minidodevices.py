from collections import deque
import datetime
from db import Db

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

HIST = 5

class Exi(object):
    """ One instanciation for each physical EXI module """
    # ToDo : Write the Exi and ExiStore classes.
    def __init__(self, send_data):
        self.send_data = send_data
        self.mydb = Db()
        self.history = tuple([deque(maxlen=HIST) for i in range(8)])
        # Not necessary, but ensure queues are not empty.
        for i in range(8):
            self.history[i].append( ( datetime.datetime.now(), None ) )
        self.config = list()

    def update(self, src, statuslist):
        """
        Detect the configuration of the Exi by watching the recent 
        Exo commands associated with the last Exi command.
        Up to 32 buttons can be behind an Exi, and each of them
        can command up to 3 outputs.
        """
        # I must first wait 1s to ensure all commands are passed.
        # Then, I must ensure there was no other EXI command in the last s.
        # And finally associate the triggered outputs with the pressed
        # button, and record in the Exi config.

class ExiStore(object):
    pass


class Exo(object):
    """ One instanciation for each physical EXO module """
    # self.history is a tuple of 8 deque containing (date, value) tuples.
    def __init__(self, exoid, send_data):
        self.send_data = send_data
        self.exoid = exoid
        self.mydb = Db()
        self.is_present = False
        # I must find a way to provide the protocol mpd
        # self.protocol = protocol
        # self.oldstatus = list()
        self.history = tuple([deque(maxlen=HIST) for i in range(8)])
        # Not necessary, but ensure queues are not empty.
        for i in range(8):
            self.history[i].append( ( datetime.datetime.now(), None ) )

    def update(self, src, statuslist):
        """
        Update the Exo status
        And return the list of changes as tupple : ( channel, new_state, last_state )
        """
        # self.oldstatus = [self.history[i][-1][1] for i in range(8)]
        list_of_changes = list()

        for i in range(8):
            try:
                if self.history[i][-1][1] != statuslist[i]:
                    now = datetime.datetime.now()
                    # Ok, we update the Exo history here.
                    self.history[i].append( ( now, statuslist[i] ) )
                    # But is it the right place to update the db history ?
                    self.mydb.history( now, 'EXO', self.exoid, i+1, statuslist[i] )
                    list_of_changes.append((i, statuslist[i], self.history[i][-2][1]))
            except IndexOutOfRange:
                print("No history yet for this Output.")
        return list_of_changes

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
        # FixMe : The factory shouldn't be called here !!!
        self.send_packet( self.exoid + EXOOFFSET, [01] + newdata )
        # return [self.history[i][-1][1] for i in range(8)]
        return 'Ok'

    def send_packet(self, dst, data):
        valuelist = [0x23, dst, EXIID, len(data) + 1] + data
        # valuelist.append(checksum( data ))
        print('Debug : sending packet : ' + ' '.join(
            [ '%0.2x' % c for c in valuelist ]))
        # packet = ''.join([chr(x) for x in valuelist])
        # FixMe
        self.send_data(valuelist)

    def get_output(self, channel):
        """Get status of an EXO output"""
        return self.history[ channel -1 ][-1][1]

class Exodict(dict):
    """
    Initialize the Exodict as a dictionary of 16 Exo with all outputs down
    and empty history.
    This class can be Singleton as there is only a set of 16 Exo in a
    Minido installation.
    self.exodict[exoid] = Exo( 255, exoid, self, self.protocol, HIST)
    """
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Exodict, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, send_data):
        # self = dict()
        for i in range(16):
            self[i+1] = Exo(i+1, send_data)
        Db().populate_exodict(self)

