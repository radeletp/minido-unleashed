from collections import deque
import datetime
class Exo(object):
    """ One instanciation for each physical EXO module """
    # self.history is a tuple of 8 deque containing (date, value) tuples.
    def __init__(self, src, exoid, mydb, protocol, hist):
        self.src = src
        self.exoid = exoid
        self.mydb = mydb
        self.protocol = protocol
        self.oldstatus = list()
        self.history = tuple([deque(maxlen=hist) for i in range(8)])
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
