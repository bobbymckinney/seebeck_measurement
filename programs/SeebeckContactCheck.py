# -*- coding: utf-8 -*-
"""
Created on 26-02-2016
Bobby McKinney
PID initial program
"""
import omegacn7500
import visa
import time

#ResourceManager for visa instrument control
ResourceManager = visa.ResourceManager()

###############################################################################
class Keithley_2700:
    ''' Used for the matrix card operations. '''
    #--------------------------------------------------------------------------
    def __init__(self, instr):
        self.ctrl = ResourceManager.open_resource(instr)

    #end init

    #--------------------------------------------------------------------------
    def fetch(self, channel):
        """
        Scan the channel and take a reading
        """
        while True:
            try:
                self.ctrl.write(":ROUTe:SCAN:INTernal (@ %s)" % (channel)) # Specify Channel
                #keithley.write(":SENSe1:FUNCtion 'TEMPerature'") # Specify Data type
                self.ctrl.write(":ROUTe:SCAN:LSELect INTernal") # Scan Selected Channel
                time.sleep(.2)
                self.ctrl.write(":ROUTe:SCAN:LSELect NONE") # Stop Scan
                time.sleep(.05)
                data = self.ctrl.query(":FETCh?")
                time.sleep(.05)
                data = float(str(data)[0:15])
                break
            except ValueError:
                data = '-'
                break
            except IOError:
                print IOError
        #end while
        return data # Fetches Reading
    #end def

    #--------------------------------------------------------------------------
    def openAllChannels(self):
        self.ctrl.write("ROUTe:OPEN:ALL")
    #end def

#end class
###############################################################################

###############################################################################
class PID(omegacn7500.OmegaCN7500):

    #--------------------------------------------------------------------------
    def __init__(self, portname, slaveaddress):
        omegacn7500.OmegaCN7500.__init__(self, portname, slaveaddress)

    #end init

    #--------------------------------------------------------------------------

    # Commands for easy reference:
    #    Use .write_register(command, value) and .read_register(command)
    #    All register values can be found in the Manual or Instruction Sheet.
    #    You must convert each address from Hex to Decimal.
    control = 4101 # Register for control method
    pIDcontrol = 0 # Value for PID control method
    pIDparam = 4124 # Register for PID parameter selection
    pIDparam_Auto = 4 # Value for Auto PID
    tCouple = 4100 # Register for setting the temperature sensor type
    tCouple_K = 0 # K type thermocouple
    heatingCoolingControl = 4102 # Register for Heating/Cooling control selection
    heating = 0 # Value for Heating setting

#end class
###############################################################################


def SeebeckContactCheck(pid1,pid2,pid3,pid4,k2700):
    print "\n***Check PID Data***\n"
    time.sleep(0.1)
    while True:
        try:
            print 'PID 1 (sample) temperature: %.2f C' %(pid1.get_pv())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 3 (block) temperature: %.2f C' %(pid3.get_pv())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 1 setpoint: %.2f C' %(pid1.get_setpoint())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 2 (sample) temperature: %.2f C' %(pid2.get_pv())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 4 (block) temperature: %.2f C' %(pid4.get_pv())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 2 setpoint: %.2f C' %(pid2.get_setpoint())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    
    print "\n***Check Keithley Data***\n"
    while True:
        try:
            TempA = float(k2700.fetch('117'))
            print "temp A: %f C" % (TempA)
            break
        except ValueError:
            print 'temp A: ', ValueError
            break
    #end while
    time.sleep(0.1)
    while True:
        try:
            TempB = float(k2700.fetch('118'))
            print "temp B: %f C" % (TempB)
            break
        except ValueError:
            print 'temp B: ', ValueError
            break
    #end while
    time.sleep(0.1)
    while True:
        try:
            Vchromel = float(k2700.fetch('107'))*10**6
            print "raw voltage (Ch): %f uV" % (Vchromel)
            break
        except ValueError:
            print 'raw voltage (Ch): ', ValueError
            break
    #end while
    time.sleep(0.1)
    while True:
        try:
            Valumel = float(k2700.fetch('108'))*10**6
            print "raw voltage (Al): %f uV" % (Valumel)
            break
        except ValueError:
            print 'raw voltage (Al): ', ValueError
            break
    #end while
    
    print '\n\n'
#end def

if __name__=='__main__':
    pid1 = PID('/dev/cu.usbserial',1)
    pid2 = PID('/dev/cu.usbserial',2)
    pid3 = PID('/dev/cu.usbserial',3)
    pid4 = PID('/dev/cu.usbserial',4)
    k2700 = Keithley_2700('GPIB0::1::INSTR')
    
    k2700.openAllChannels
    # Define the type of measurement for the channels we are looking at:
    k2700.ctrl.write(":SENSe1:TEMPerature:TCouple:TYPE K") # Set ThermoCouple type
    k2700.ctrl.write(":SENSe1:FUNCtion 'TEMPerature', (@ 117,118)")
    k2700.ctrl.write(":SENSe1:FUNCtion 'VOLTage:DC', (@ 107,108)")
    k2700.ctrl.write(":TRIGger:SEQuence1:DELay 0")
    k2700.ctrl.write(":TRIGger:SEQuence1:COUNt 1")    # Set the count rate
    # Sets the the acquisition rate of the measurements
    k2700.ctrl.write(":SENSe1:VOLTage:DC:NPLCycles 5, (@ 107,108)") # Sets integration period based on frequency
    k2700.ctrl.write(":SENSe1:TEMPerature:NPLCycles 5, (@ 117,118)")
    
    SeebeckContactCheck(pid1,pid2,pid3,pid4,k2700)   