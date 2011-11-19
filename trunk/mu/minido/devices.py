from threading import Timer
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
