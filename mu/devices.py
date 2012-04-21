from threading import Timer
class GenericDevice(object):
    def __init__(self,channels, name):
        self.type_ = 'Generic'
        self.name = name
        self.channels = channels
    def __str__(self):
        return "Device : type {0} name {1} channels {2!s}".format(
            self.type_, self.name, self.channels)

class DefaultDevice(GenericDevice):
    """ Light states & methods """
    def __init__(self, channels, name):

        self.channels = channels
        self.type_ = 'Default'
        self.name = name

    def on(self):
        """ Set device status """
        exo = self.channels['power']['exo']
        channel = self.channels['power']['channel']
        print("exo.set_output(channel, 255)")
        exo.set_output(channel, 255)

    def off(self):
        """ Set device status """
        exo = self.channels['power']['exo']
        channel = self.channels['power']['channel']
        print("exo.set_output(channel, 0)")
        exo.set_output(channel, 0)

    def toggle(self):
        """ Set device status """
        exo = self.channels['power']['exo']
        channel = self.channels['power']['channel']
        if exo.get_output(channel) == 0:
            exo.set_output(channel, 255)
        else:
            exo.set_output(channel, 0)

    def status(self):
        """ Get device status """
        exo = self.channels['power']['exo']
        return(exo.get_output(self.channels['power']['channel']))

class LightDevice(GenericDevice):
    """ Light states & methods """
    def __init__(self, channels, name):

        self.channels = channels
        self.type_ = 'Light'
        self.name = name

    def on(self):
        """ Set device status """
        exo = self.channels['power']['exo']
        channel = self.channels['power']['channel']
        print("exo.set_output(channel, 255)")
        exo.set_output(channel, 255)

    def off(self):
        """ Set device status """
        exo = self.channels['power']['exo']
        channel = self.channels['power']['channel']
        print("exo.set_output(channel, 0)")
        exo.set_output(channel, 0)

    def toggle(self):
        """ Set device status """
        exo = self.channels['power']['exo']
        channel = self.channels['power']['channel']
        if exo.get_output(channel) == 0:
            exo.set_output(channel, 255)
        else:
            exo.set_output(channel, 0)

    def status(self):
        """ Get device status """
        exo = self.channels['power']['exo']
        return(exo.get_output(self.channels['power']['channel']))

class StoreDevice(GenericDevice):
    """ Store """
    def __init__(self, channels, name):
        GenericDevice.__init__(self, channels, name)
        self.name = name
        self.type_ = 'Store'
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

class VMCDevice(GenericDevice):
    """ Ventilation Mecanique Constolee """
    pass
