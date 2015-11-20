#! /usr/bin/python
# -*- coding: utf-8 -*-
"""
Created: 2015-08-19

@author: Bobby McKinney (bobbymckinney@gmail.com)

__Title__ : voltagepanel
Description:
Comments:
"""
import os
import sys
import wx
from wx.lib.pubsub import pub # For communicating b/w the thread and the GUI
import wx.lib.scrolledpanel as scrolled
import matplotlib
matplotlib.interactive(False)
matplotlib.use('WXAgg') # The recommended way to use wx with mpl is with WXAgg backend.

from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from matplotlib.figure import Figure
from matplotlib.pyplot import gcf, setp
import matplotlib.animation as animation # For plotting
import pylab
import numpy as np
import matplotlib.pyplot as plt
import minimalmodbus as modbus # For communicating with the cn7500s
import omegacn7500 # Driver for cn7500s under minimalmodbus, adds a few easy commands
import visa # pyvisa, essential for communicating with the Keithley
from threading import Thread # For threading the processes going on behind the GUI
import time
from datetime import datetime # for getting the current date and time
# Modules for saving logs of exceptions
import exceptions
import sys
from logging_utils import setup_logging_to_file, log_exception

# for a fancy status bar:
import EnhancedStatusBar as ESB

#==============================================================================
# Keeps Windows from complaining that the port is already open:
modbus.CLOSE_PORT_AFTER_EACH_CALL = True

version = '7.0 (2015-11-19)'

'''
Global Variables:
'''

# Naming a data file:
dataFile = 'Data.csv'
statusFile = 'Status.csv'
seebeckFile = 'Seebeck.csv'

APP_EXIT = 1 # id for File\Quit


stability_threshold = 0.25/60
oscillation = 8 # Degree range that the PID will oscillate in
tolerance = (oscillation/8) # This must be set to less than oscillation
measureList = []
#dTlist = [0,-2,-4,-6,-8,-6,-4,-2,0,2,4,6,8,6,4,2,0]
dTlist = [0,-4,-8,-4,0,4,8,4,0]

maxLimit = 650 # Restricts the user to a max temperature

abort_ID = 0 # Abort method

# Global placers for instruments
k2700 = ''
sampleApid = ''
sampleBpid = ''
blockApid = ''
blockBpid = ''

tc_type = "k-type" # Set the thermocouple type in order to use the correct voltage correction

# Channels corresponding to switch card:
#tempAChannel = '109'
#tempBChannel = '110'
chromelChannel = '107'
alumelChannel = '108'

# placer for directory
filePath = 'global file path'

# placer for files to be created
myfile = 'global file'
rawfile = 'global file'
processfile = 'global file'

# Placers for the GUI plots:
chromelV_list = []
tchromelV_list = []
alumelV_list=[]
talumelV_list = []
sampletempA_list = []
tsampletempA_list = []
sampletempB_list = []
tsampletempB_list = []
tblocktemp_list = []
blocktempA_list = []
blocktempB_list = []

timecalclist = []
Vchromelcalclist = []
Valumelcalclist = []
dTcalclist = []
avgTcalclist = []

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
        measure = False
        while (not measure):
            try:
                self.ctrl.write(":ROUTe:SCAN:INTernal (@ %s)" % (channel)) # Specify Channel
                #keithley.write(":SENSe1:FUNCtion 'TEMPerature'") # Specify Data type
                self.ctrl.write(":ROUTe:SCAN:LSELect INTernal") # Scan Selected Channel
                time.sleep(.1)
                self.ctrl.write(":ROUTe:SCAN:LSELect NONE") # Stop Scan
                time.sleep(.1)
                data = self.ctrl.query(":FETCh?")
                time.sleep(.1)
                data = float(str(data)[0:15])
                measure = True
            except exceptions.ValueError as VE:
                print(VE)
                measure = False
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

###############################################################################
class Setup:
    """
    Call this class to run the setup for the Keithley and the PID.
    """
    def __init__(self):
        """
        Prepare the Keithley to take data on the specified channels:
        """
        global k2700
        global sampleApid
        global sampleBpid
        global blockApid
        global blockBpid

        # Define Keithley instrument port:
        self.k2700 = k2700 = Keithley_2700('GPIB0::1::INSTR')
        # Define the ports for the PID
        self.sampleApid = sampleApid = PID('/dev/cu.usbserial', 1) # Top heater
        self.sampleBpid = sampleBpid = PID('/dev/cu.usbserial', 2) # Bottom heater
        self.blockApid = blockApid = PID('/dev/cu.usbserial', 3) # Top block
        self.blockBpid = blockBpid = PID('/dev/cu.usbserial', 4) # Top block


        """
        Prepare the Keithley for operation:
        """
        self.k2700.openAllChannels
        # Define the type of measurement for the channels we are looking at:
        #self.k2700.ctrl.write(":SENSe1:TEMPerature:TCouple:TYPE K") # Set ThermoCouple type
        #self.k2700.ctrl.write(":SENSe1:FUNCtion 'TEMPerature', (@ 109,110)")
        self.k2700.ctrl.write(":SENSe1:FUNCtion 'VOLTage:DC', (@ 107,108)")

        self.k2700.ctrl.write(":TRIGger:SEQuence1:DELay 0")
        self.k2700.ctrl.write(":TRIGger:SEQuence1:COUNt 1")    # Set the count rate

        # Sets the the acquisition rate of the measurements
        self.k2700.ctrl.write(":SENSe1:VOLTage:DC:NPLCycles 4, (@ 107,108)") # Sets integration period based on frequency
        #self.k2700.ctrl.write(":SENSe1:TEMPerature:NPLCycles 4, (@ 109,110)")

        """
        Prepare the PID for operation:
        """
        # Set the control method to PID
        self.sampleApid.write_register(PID.control, PID.pIDcontrol)
        self.sampleBpid.write_register(PID.control, PID.pIDcontrol)

        # Set the PID to auto parameter
        self.sampleApid.write_register(PID.pIDparam, PID.pIDparam_Auto)
        self.sampleBpid.write_register(PID.pIDparam, PID.pIDparam_Auto)

        # Set the thermocouple type
        self.sampleApid.write_register(PID.tCouple, PID.tCouple_K)
        self.sampleBpid.write_register(PID.tCouple, PID.tCouple_K)
        self.blockApid.write_register(PID.tCouple, PID.tCouple_K)
        self.blockBpid.write_register(PID.tCouple, PID.tCouple_K)

        # Set the control to heating only
        self.sampleApid.write_register(PID.heatingCoolingControl, PID.heating)
        self.sampleBpid.write_register(PID.heatingCoolingControl, PID.heating)

        # Run the controllers
        self.sampleApid.run()
        self.sampleBpid.run()

#end class
###############################################################################

###############################################################################
class ProcessThread(Thread):
    """
    Thread that runs the operations behind the GUI. This includes measuring
    and plotting.
    """

    #--------------------------------------------------------------------------
    def __init__(self):
        """ Init Worker Thread Class """
        Thread.__init__(self)
        self.start()

    #end init

    #--------------------------------------------------------------------------
    def run(self):
        """ Run Worker Thread """
        #Setup()
        td=TakeData()
        #td = TakeDataTest()
    #end def

#end class
###############################################################################

###############################################################################
class InitialCheck:
    """
    Intial Check of temperatures and voltages.
    """
    #--------------------------------------------------------------------------
    def __init__(self):
        self.k2700 = k2700
        self.sampleApid = sampleApid
        self.sampleBpid = sampleBpid
        self.blockApid = blockApid
        self.blockBpid = blockBpid

        self.take_temperature_Data()

        self.take_voltage_Data()

        #end init

    #--------------------------------------------------------------------------
    def take_temperature_Data(self):
        """ Takes data from the PID
        """

        # Take Data and time stamps:
        self.sampletempA = float(self.sampleApid.get_pv())
        time.sleep(0.1)
        self.sampletempB = float(self.sampleBpid.get_pv())
        time.sleep(0.1)
        self.blocktempA = float(self.blockApid.get_pv())
        time.sleep(0.1)
        self.blocktempB = float(self.blockBpid.get_pv())
        time.sleep(0.1)
        self.samplesetpointA = float(self.sampleApid.get_setpoint())
        time.sleep(0.1)
        self.samplesetpointB = float(self.sampleBpid.get_setpoint())
        time.sleep(0.1)

        self.updateGUI(stamp="Sample Temp A Init", data=self.sampletempA)
        self.updateGUI(stamp="Sample Temp B Init", data=self.sampletempB)

        self.updateGUI(stamp="Setpoint A Init", data=self.samplesetpointA)
        self.updateGUI(stamp="Setpoint B Init", data=self.samplesetpointB)

        self.updateGUI(stamp="Block Temp A Init", data=self.blocktempA)
        self.updateGUI(stamp="Block Temp B Init", data=self.blocktempB)

        print "\nsample temp A: %f C\nblock temp A: %f C\nsample temp B: %f C\nblock temp B: %f C" % (self.sampletempA, self.blocktempA, self.sampletempB, self.blocktempB)

    #end def

    #--------------------------------------------------------------------------
    def take_voltage_Data(self):
        """ Takes data from the PID
        """
        self.Vchromelraw = float(self.k2700.fetch(chromelChannel))*10**6
        self.Vchromelcalc = self.voltage_Correction(self.Vchromelraw,self.sampletempA,self.sampletempB, 'chromel')
        self.Valumelraw = float(self.k2700.fetch(alumelChannel))*10**6
        self.Valumelcalc = self.voltage_Correction(self.Valumelraw,self.sampletempA,self.sampletempB, 'alumel')

        self.updateGUI(stamp="Chromel Voltage Init", data=float(self.Vchromelcalc))
        self.updateGUI(stamp="Alumel Voltage Init", data=float(self.Valumelcalc))

        print "\nvoltage (Chromel): %f uV\nvoltage (Alumel): %f uV" % (self.Vchromelcalc, self.Valumelcalc)

    #end def


    #--------------------------------------------------------------------------
    def voltage_Correction(self, raw_voltage, tempA, tempB, side):
        ''' raw_data must be in uV '''
        # Kelvin conversion for polynomial correction.
        dT = tempA - tempB
        avgT = (tempA + tempB)/2 + 273.15

        # Correction for effect from Thermocouple Seebeck
        out = self.alpha(avgT, side)*dT - raw_voltage

        return out
    #end def
    #--------------------------------------------------------------------------
    def alpha(self, x, side):
        ''' x = avgT
            alpha in uV/K
        '''
        global tc_type

        if tc_type == "k-type":

            ### If Chromel, taken from Chromel_Seebeck.txt
            if side == 'chromel':
                if ( x >= 270 and x < 700):
                    alpha = -2467.61114613*x**0 + 55.6028987953*x**1 + \
                            -0.552110359087*x**2 + 0.00320554346691*x**3 + \
                            -1.20477254034e-05*x**4 + 3.06344710205e-08*x**5 + \
                            -5.33914758601e-11*x**6 + 6.30044607727e-14*x**7 + \
                            -4.8197269477e-17*x**8 + 2.15928374212e-20*x**9 + \
                            -4.30421084091e-24*x**10

                #end if

                elif ( x >= 700 and x < 1599):
                    alpha = 1165.13254764*x**0 + -9.49622421414*x**1 + \
                            0.0346344390853*x**2 + -7.27785048931e-05*x**3 + \
                            9.73981855547e-08*x**4 + -8.64369652227e-11*x**5 + \
                            5.10080771762e-14*x**6 + -1.93318725171e-17*x**7 + \
                            4.27299905603e-21*x**8 + -4.19761748937e-25*x**9

                #end if

                else:
                    print "Error in voltage correction, out of range."

            #end if (Chromel)

            ### If Alumel, taken from Alumel_Seebeck.txt
            elif side == 'alumel':
                if ( x >= 270 and x < 570):
                    alpha = -3465.28789643*x**0 + 97.4007289124*x**1 + \
                            -1.17546754681*x**2 + 0.00801252041119*x**3 + \
                            -3.41263237031e-05*x**4 + 9.4391002358e-08*x**5 + \
                            -1.69831949233e-10*x**6 + 1.91977765586e-13*x**7 + \
                            -1.2391854625e-16*x**8 + 3.48576207577e-20*x**9

                #end if

                elif ( x >= 570 and x < 1599):
                    alpha = 254.644633774*x**0 + -2.17639940109*x**1 + \
                            0.00747127856327*x**2 + -1.41920634198e-05*x**3 + \
                            1.61971537881e-08*x**4 + -1.14428153299e-11*x**5 + \
                            4.969263632e-15*x**6 + -1.27526741699e-18*x**7 + \
                            1.80403838088e-22*x**8 + -1.23699936952e-26*x**9

                #end if

                else:
                    print "Error in voltage correction, out of range."

            #end if (Alumel)

            else:
                print "Error in voltage correction."

        #end if (K-type)

        return alpha

    #end def
    #--------------------------------------------------------------------------
    def updateGUI(self, stamp, data):
        """
        Sends data to the GUI (main thread), for live updating while the process is running
        in another thread.
        """
        time.sleep(0.1)
        wx.CallAfter(pub.sendMessage, stamp, msg=data)

    #end def

#end class
###############################################################################

###############################################################################
class TakeData:
    ''' Takes measurements and saves them to file. '''
    #--------------------------------------------------------------------------
    def __init__(self):
        global abort_ID
        global k2700
        global sampleApid
        global sampleBpid
        global blockApid
        global blockBpid

        global tolerance
        global stability_threshold
        global oscillation

        global measureList
        global dTlist

        global timecalclist, Vchromelcalclist, Valumelcalclist, dTcalclist, avgTcalclist

        self.k2700 = k2700
        self.sampleApid = sampleApid
        self.sampleBpid = sampleBpid
        self.blockApid = blockApid
        self.blockBpid = blockBpid

        self.tolerance = tolerance
        self.stability_threshold = stability_threshold

        self.tol = 'NO'
        self.stable = 'NO'
        self.measurement = 'OFF'
        self.measurement_indicator = 'none'
        self.updateGUI(stamp='Measurement', data=self.measurement)

        self.plotnumber = 0

        self.exception_ID = 0

        self.updateGUI(stamp='Status Bar', data='Running')

        self.start = time.time()
        print "start take data"

        try:
            while abort_ID == 0:
                for avgtemp in measureList:
                    self.avgtemp = avgtemp
                    self.dT = 0
                    print "Set avg temp to %f" %(self.avgtemp)
                    self.sampleApid.set_setpoint(self.avgtemp)
                    self.sampleBpid.set_setpoint(self.avgtemp)
                    self.plotnumber +=1
                    timecalclist = []
                    Vchromelcalclist = []
                    Valumelcalclist = []
                    dTcalclist = []
                    avgTcalclist = []

                    self.recenttempA = []
                    self.recenttempAtime=[]
                    self.recenttempB = []
                    self.recenttempBtime=[]
                    self.stabilityA = '-'
                    self.stabilityB = '-'
                    self.updateGUI(stamp="Stability A", data=self.stabilityA)
                    self.updateGUI(stamp="Stability B", data=self.stabilityB)

                    self.take_temperature_Data()
                    self.take_voltage_Data()
                    self.check_tolerance()

                    condition = False
                    print 'start tolerance and stability loop'
                    while (not condition):
                        self.take_temperature_Data()
                        self.take_voltage_Data()
                        self.check_tolerance()
                        if abort_ID == 1: break
                        condition = (self.tol == 'OK' and self.stable == 'OK')
                    #end while
                    if abort_ID == 1: break
                    # vary dT
                    self.measurement_indicator = 'start'
                    for dT in dTlist:
                        self.dT = dT
                        print "Set dT to %f" %(self.dT)
                        print 'set sample pid A to %f' %(self.avgtemp+self.dT/2.0)
                        print 'set sample pid B to %f' %(self.avgtemp-self.dT/2.0)
                        # ramp to correct dT
                        self.sampleApid.set_setpoint(self.avgtemp+self.dT/2.0)
                        self.sampleBpid.set_setpoint(self.avgtemp-self.dT/2.0)
                        print 'reset stability'
                        self.recenttempA = []
                        self.recenttempAtime=[]
                        self.recenttempB = []
                        self.recenttempBtime=[]
                        self.stabilityA = '-'
                        self.stabilityB = '-'
                        self.updateGUI(stamp="Stability A", data=self.stabilityA)
                        self.updateGUI(stamp="Stability B", data=self.stabilityB)

                        condition = False
                        print 'start tolerance and stability loop'
                        while (not condition):
                            self.take_temperature_Data()
                            self.take_voltage_Data()
                            self.check_tolerance()
                            if abort_ID == 1: break
                            condition = (self.tol == 'OK' and self.stable == 'OK')
                        #end while
                        if abort_ID == 1: break

                        # start measurement
                        print 'begin seebeck measurement'
                        self.measurement = 'ON'
                        self.updateGUI(stamp='Measurement', data=self.measurement)
                        for i in range(4):
                            self.data_measurement()
                            if (self.dT == dTlist[-1] and i == 3):
                                self.measurement_indicator = 'stop'
                            self.write_data_to_file()
                            if abort_ID == 1: break
                        #end for
                        print 'end seebeck measurement'
                        self.measurement = 'OFF'
                        self.tol = 'NO'
                        self.stable = 'NO'
                        self.updateGUI(stamp='Measurement', data=self.measurement)
                        if abort_ID == 1: break
                    #end for
                    print 'process seebeck data'
                    self.process_data()
                    if abort_ID == 1: break
                #end for
                print 'huzzah! program finished'
                abort_ID = 1
            #end while
        #end try

        except exceptions.Exception as e:
            log_exception(e)
            abort_ID = 1
            self.exception_ID = 1
            print "Error Occurred, check error_log.log"
            print e
        #end except

        if self.exception_ID == 1:
            self.updateGUI(stamp='Status Bar', data='Exception Occurred')
        #end if
        else:
            self.updateGUI(stamp='Status Bar', data='Finished, Ready')
        #end else
        print 'set sample temps A and B to 25'
        self.sampleApid.set_setpoint(25)
        self.sampleBpid.set_setpoint(25)
        self.save_files()

        wx.CallAfter(pub.sendMessage, 'Enable Buttons')
    #end init

    #--------------------------------------------------------------------------
    def take_temperature_Data(self):
        """ Takes data from the PID and proceeds to a
            function that checks the PID setpoints.
        """
        print 'take temperature data'
        try:
            # Take Data and time stamps:
            self.sampletempA = float(self.sampleApid.get_pv())
            time.sleep(0.1)
            self.sampletempB = float(self.sampleBpid.get_pv())
            time.sleep(0.1)
            self.blocktempA = float(self.blockApid.get_pv())
            time.sleep(0.1)
            self.blocktempB = float(self.blockBpid.get_pv())
            time.sleep(0.1)

            # Get the current setpoints on the PID:
            self.samplesetpointA = float(self.sampleApid.get_setpoint())
            time.sleep(0.1)
            self.samplesetpointB = float(self.sampleBpid.get_setpoint())
            time.sleep(0.1)

        except exceptions.ValueError as VE:
            # Take Data and time stamps:
            self.sampletempA = float(self.sampleApid.get_pv())
            time.sleep(0.1)
            self.sampletempB = float(self.sampleBpid.get_pv())
            time.sleep(0.1)
            self.blocktempA = float(self.blockApid.get_pv())
            time.sleep(0.1)
            self.blocktempB = float(self.blockBpid.get_pv())
            time.sleep(0.1)

            # Get the current setpoints on the PID:
            self.samplesetpointA = float(self.sampleApid.get_setpoint())
            time.sleep(0.1)
            self.samplesetpointB = float(self.sampleBpid.get_setpoint())
            time.sleep(0.1)

        self.time_temperature = time.time() - self.start

        print "\ntime: %.2f s\nsample temp A: %f C\nblock temp A: %f C\nsample temp B: %f C\nblock temp B: %f C" % (self.time_temperature, self.sampletempA, self.blocktempA, self.sampletempB, self.blocktempB)

        #check stability of PID
        if (len(self.recenttempA)<3):
            self.recenttempA.append(self.sampletempA)
            self.recenttempAtime.append(self.time_temperature)
        #end if
        else:
            self.recenttempA.pop(0)
            self.recenttempAtime.pop(0)
            self.recenttempA.append(self.sampletempA)
            self.recenttempAtime.append(self.time_temperature)
            self.stabilityA = self.getStability(self.recenttempA,self.recenttempAtime)
            print "stability A: %.4f C/min" % (self.stabilityA*60)
            self.updateGUI(stamp="Stability A", data=self.stabilityA*60)
        #end else

        if (len(self.recenttempB)<3):
            self.recenttempB.append(self.sampletempB)
            self.recenttempBtime.append(self.time_temperature)
        #end if
        else:
            self.recenttempB.pop(0)
            self.recenttempBtime.pop(0)
            self.recenttempB.append(self.sampletempB)
            self.recenttempBtime.append(self.time_temperature)
            self.stabilityB = self.getStability(self.recenttempB,self.recenttempBtime)
            print "stability B: %.4f C/min" % (self.stabilityB*60)
            self.updateGUI(stamp="Stability B", data=self.stabilityB*60)
        #end else

        self.updateGUI(stamp="Time Sample Temp A", data=self.time_temperature)
        self.updateGUI(stamp="Time Sample Temp B", data=self.time_temperature)
        self.updateGUI(stamp="Sample Temp A", data=self.sampletempA)
        self.updateGUI(stamp="Sample Temp B", data=self.sampletempB)

        self.updateGUI(stamp="Setpoint A", data=self.samplesetpointA)
        self.updateGUI(stamp="Setpoint B", data=self.samplesetpointB)

        self.updateGUI(stamp="Block Temp A", data=self.blocktempA)
        self.updateGUI(stamp="Block Temp B", data=self.blocktempB)
        self.updateGUI(stamp="Time Block Temp", data=self.time_temperature)

        global rawfile
        print('\nwrite temperatures to file\n')
        rawfile.write('%.1f,'%(self.time_temperature))
        rawfile.write('%.2f,%.2f,%.2f,' %(self.sampletempA,self.samplesetpointA,self.blocktempA))
        rawfile.write(str(self.stabilityA)+',')
        rawfile.write('%.2f,%.2f,%.2f,' %(self.sampletempB,self.samplesetpointB,self.blocktempB))
        rawfile.write(str(self.stabilityB)+',')
        self.safety_check()
    #end def

    #--------------------------------------------------------------------------
    def safety_check(self):
        global maxLimit
        global abort_ID
        print 'safety check'
        if self.sampletempA > maxLimit:
            abort_ID = 1
            print 'Safety Failure: Sample Temp A greater than Max Limit'
        #end if
        if self.sampletempB > maxLimit:
            abort_ID = 1
            print 'Safety Failure: Sample Temp B greater than Max Limit'
        #end if
        if self.blocktempA > maxLimit:
            abort_ID = 1
            print 'Safety Failure: Block Temp A greater than Max Limit'
        #end if
        if self.blocktempB > maxLimit:
            abort_ID = 1
            print 'Safety Failure: Block Temp B greater than Max Limit'
        #end if
        if self.blocktempA > self.sampletempA + 100:
            abort_ID = 1
            print 'Safety Failure: Block Temp A  100 C greater than Sample Temp A'
        #end if
        if self.blocktempB > self.sampletempB + 100:
            abort_ID = 1
            print 'Safety Failure: Block Temp B  100 C greater than Sample Temp B'
        #end if
        if self.sampletempA > self.blocktempA + 100:
            abort_ID = 1
            print 'Safety Failure: Sample Temp A  100 C greater than Block Temp A'
        #end if
        if self.sampletempB > self.blocktempB + 100:
            abort_ID = 1
            print 'Safety Failure: Sample Temp B  100 C greater than Block Temp B'
        #end if
    #end def

    #--------------------------------------------------------------------------
    def take_voltage_Data(self):
        print('take voltage data\n')

        self.Vchromelraw = float(self.k2700.fetch(chromelChannel))*10**6
        self.Vchromelcalc = self.voltage_Correction(self.Vchromelraw,self.sampletempA,self.sampletempB, 'chromel')
        self.Valumelraw = float(self.k2700.fetch(alumelChannel))*10**6
        self.Valumelcalc = self.voltage_Correction(self.Valumelraw,self.sampletempA,self.sampletempB, 'alumel')
        self.time_voltage = time.time() - self.start

        self.updateGUI(stamp="Time Chromel Voltage", data=float(self.time_voltage))
        self.updateGUI(stamp="Time Alumel Voltage", data=float(self.time_voltage))
        self.updateGUI(stamp="Chromel Voltage", data=float(self.Vchromelcalc))
        self.updateGUI(stamp="Alumel Voltage", data=float(self.Valumelcalc))

        print "\ntime: %f s\nvoltage (Chromel): %f uV\nvoltage (Alumel): %f uV" % (self.time_voltage, self.Vchromelcalc, self.Valumelcalc)


        global rawfile
        print('write voltages to file')
        rawfile.write('%.3f,%.3f,%.3f,%.3f,'%(self.Vchromelraw, self.Vchromelcalc,self.Valumelraw, self.Valumelcalc))
    #end def

    #--------------------------------------------------------------------------
    def getStability(self, temps, times):
        coeffs = np.polyfit(times, temps, 1)

        # Polynomial Coefficients
        results = coeffs.tolist()
        return results[0]
    #end def

    #--------------------------------------------------------------------------
    def check_tolerance(self):
        print 'check tolerance'
        self.tolA = (np.abs(self.sampletempA-(self.avgtemp+self.dT/2.0)) < self.tolerance)
        self.tolB = (np.abs(self.sampletempB-(self.avgtemp-self.dT/2.0)) < self.tolerance)
        print 'tolerance A: ',self.tolA
        print 'tolerance B:', self.tolB

        if (self.tolA and self.tolB):
            self.tol = 'OK'
        #end if
        else:
            self.tol = 'NO'
        #end else

        print 'check stability'

        if (self.stabilityA != '-'):
            self.stableA = (np.abs(self.stabilityA) < self.stability_threshold)
            print 'stable A: ',self.stableA
        #end if
        else:
            self.stableA = False
            print 'stable A: ',self.stableA
        #end else
        if (self.stabilityB != '-'):
            self.stableB = (np.abs(self.stabilityB) < self.stability_threshold)
            print 'stable B: ',self.stableB
        #end if
        else:
            self.stableB = False
            print 'stable B: ',self.stableB
        #end else
        if (self.stableA and self.stableB):
            self.stable = 'OK'
        #end if
        else:
            self.stable = 'NO'
        #end else

        print "\ntolerance: %s\nstable: %s\n" % (self.tol, self.stable)
            #end else
        #end elif

        global rawfile
        print('write status to file')
        rawfile.write(str(self.tol)+','+str(self.stable)+'\n')

        self.updateGUI(stamp="Status Bar", data=[self.tol, self.stable])
    #end def

    #--------------------------------------------------------------------------
    def data_measurement(self):
        global rawfile
        print '\nseebeck data measurement'
        # Takes and writes to file the data on the Keithley
        # The only change between blocks like this one is the specific
        # channel on the Keithley that is being measured.
        self.sampletempA = float(self.sampleApid.get_pv())
        self.time_sampletempA = time.time() - self.start
        self.updateGUI(stamp="Time Sample Temp A", data=self.time_sampletempA)
        self.updateGUI(stamp="Sample Temp A", data=self.sampletempA)
        print "time: %.2f s\t sample temp A: %.2f C" % (self.time_sampletempA, self.sampletempA)

        time.sleep(0.2)

        self.sampletempB = float(self.sampleBpid.get_pv())
        self.time_sampletempB = time.time() - self.start
        self.updateGUI(stamp="Time Sample Temp B", data=self.time_sampletempB)
        self.updateGUI(stamp="Sample Temp B", data=self.sampletempB)
        print "time: %.2f s\ttempB: %.2f C" % (self.time_sampletempB, self.sampletempB)

        time.sleep(0.2)

        self.Vchromelraw = float(self.k2700.fetch(chromelChannel))*10**6
        self.Vchromelcalc = self.voltage_Correction(self.Vchromelraw,self.sampletempA,self.sampletempB, 'chromel')
        self.time_Vchromel = time.time() - self.start
        self.updateGUI(stamp="Time Chromel Voltage", data=self.time_Vchromel)
        self.updateGUI(stamp="Chromel Voltage", data=self.Vchromelcalc)
        print "time: %.2f s\t voltage (Chromel) %f uV" % (self.time_Vchromel, self.Vchromelcalc)

        time.sleep(0.2)

        self.Valumelraw = float(self.k2700.fetch(alumelChannel))*10**6
        self.Valumelcalc = self.voltage_Correction(self.Valumelraw,self.sampletempA,self.sampletempB, 'alumel')
        self.time_Valumel = time.time() - self.start
        self.updateGUI(stamp="Time Alumel Voltage", data=self.time_Valumel)
        self.updateGUI(stamp="Alumel Voltage", data=self.Valumelcalc)
        print "time: %.2f s\t voltage (Alumel) %f uV" % (self.time_Valumel, self.Valumelcalc)

        time.sleep(0.2)


        rawfile.write('%.1f,'%(self.time_sampletempA))
        rawfile.write('%.2f,%.2f,%.2f,' %(self.sampletempA,self.samplesetpointA,self.blocktempA))
        rawfile.write(str(self.stabilityA)+',')
        rawfile.write('%.2f,%.2f,%.2f,' %(self.sampletempB,self.samplesetpointB,self.blocktempB))
        rawfile.write(str(self.stabilityB)+',')
        rawfile.write('%.3f,%.3f,%.3f,%.3f,'%(self.Vchromelraw, self.Vchromelcalc,self.Valumelraw, self.Valumelcalc))
        rawfile.write(str(self.tol)+','+str(self.stable)+'\n')

        print('Symmetrize the measurement and repeat')

        self.Valumelraw2 = float(self.k2700.fetch(alumelChannel))*10**6
        self.Valumelcalc2 = self.voltage_Correction(self.Valumelraw2,self.sampletempA,self.sampletempB, 'alumel')
        self.time_Valumel2 = time.time() - self.start
        self.updateGUI(stamp="Time Alumel Voltage", data=self.time_Valumel2)
        self.updateGUI(stamp="Alumel Voltage", data=self.Valumelcalc2)
        print "time: %.2f s\t voltage (Alumel) %f uV" % (self.time_Valumel2, self.Valumelcalc2)

        time.sleep(0.2)

        self.Vchromelraw2 = float(self.k2700.fetch(chromelChannel))*10**6
        self.Vchromelcalc2 = self.voltage_Correction(self.Vchromelraw2,self.sampletempA,self.sampletempB, 'chromel')
        self.time_Vchromel2 = time.time() - self.start
        self.updateGUI(stamp="Time Chromel Voltage", data=self.time_Vchromel2)
        self.updateGUI(stamp="Chromel Voltage", data=self.Vchromelcalc2)
        print "time: %.2f s\t voltage (Chromel) %f uV" % (self.time_Vchromel2, self.Vchromelcalc2)

        time.sleep(0.2)

        self.sampletempB2 = float(self.sampleBpid.get_pv())
        self.time_sampletempB2 = time.time() - self.start
        self.updateGUI(stamp="Time Sample Temp B", data=self.time_sampletempB2)
        self.updateGUI(stamp="Sample Temp B", data=self.sampletempB2)
        print "time: %.2f s\ttempB: %.2f C" % (self.time_sampletempB2, self.sampletempB2)

        time.sleep(0.2)

        self.sampletempA2 = float(self.sampleApid.get_pv())
        self.time_sampletempA2 = time.time() - self.start
        self.updateGUI(stamp="Time Sample Temp A", data=self.time_sampletempA2)
        self.updateGUI(stamp="Sample Temp A", data=self.sampletempA2)
        print "time: %.2f s\t sample temp A: %.2f C" % (self.time_sampletempA2, self.sampletempA2)

        rawfile.write('%.1f,'%(self.time_Valumel2))
        rawfile.write('%.2f,%.2f,%.2f,' %(self.sampletempA2,self.samplesetpointA,self.blocktempA))
        rawfile.write(str(self.stabilityA)+',')
        rawfile.write('%.2f,%.2f,%.2f,' %(self.sampletempB2,self.samplesetpointB,self.blocktempB))
        rawfile.write(str(self.stabilityB)+',')
        rawfile.write('%.3f,%.3f,%.3f,%.3f,'%(self.Vchromelraw2, self.Vchromelcalc2,self.Valumelraw2, self.Valumelcalc2))
        rawfile.write(str(self.tol)+','+str(self.stable)+'\n')
    #end def

    #--------------------------------------------------------------------------
    def voltage_Correction(self, raw_voltage, tempA, tempB, side):
        ''' raw_data must be in uV '''
        # Kelvin conversion for polynomial correction.
        dT = tempA - tempB
        avgT = (tempA + tempB)/2 + 273.15

        # Correction for effect from Thermocouple Seebeck
        out = self.alpha(avgT, side)*dT - raw_voltage

        return out
    #end def

    #--------------------------------------------------------------------------
    def alpha(self, x, side):
        ''' x = avgT
            alpha in uV/K
        '''

        if tc_type == "k-type":

            ### If Chromel, taken from Chromel_Seebeck.txt
            if side == 'chromel':
                if ( x >= 270 and x < 700):
                    alpha = -2467.61114613*x**0 + 55.6028987953*x**1 + \
                            -0.552110359087*x**2 + 0.00320554346691*x**3 + \
                            -1.20477254034e-05*x**4 + 3.06344710205e-08*x**5 + \
                            -5.33914758601e-11*x**6 + 6.30044607727e-14*x**7 + \
                            -4.8197269477e-17*x**8 + 2.15928374212e-20*x**9 + \
                            -4.30421084091e-24*x**10

                #end if

                elif ( x >= 700 and x < 1599):
                    alpha = 1165.13254764*x**0 + -9.49622421414*x**1 + \
                            0.0346344390853*x**2 + -7.27785048931e-05*x**3 + \
                            9.73981855547e-08*x**4 + -8.64369652227e-11*x**5 + \
                            5.10080771762e-14*x**6 + -1.93318725171e-17*x**7 + \
                            4.27299905603e-21*x**8 + -4.19761748937e-25*x**9

                #end if

                else:
                    print "Error in voltage correction, out of range."

            #end if (Chromel)

            ### If Alumel, taken from Alumel_Seebeck.txt
            elif side == 'alumel':
                if ( x >= 270 and x < 570):
                    alpha = -3465.28789643*x**0 + 97.4007289124*x**1 + \
                            -1.17546754681*x**2 + 0.00801252041119*x**3 + \
                            -3.41263237031e-05*x**4 + 9.4391002358e-08*x**5 + \
                            -1.69831949233e-10*x**6 + 1.91977765586e-13*x**7 + \
                            -1.2391854625e-16*x**8 + 3.48576207577e-20*x**9

                #end if

                elif ( x >= 570 and x < 1599):
                    alpha = 254.644633774*x**0 + -2.17639940109*x**1 + \
                            0.00747127856327*x**2 + -1.41920634198e-05*x**3 + \
                            1.61971537881e-08*x**4 + -1.14428153299e-11*x**5 + \
                            4.969263632e-15*x**6 + -1.27526741699e-18*x**7 + \
                            1.80403838088e-22*x**8 + -1.23699936952e-26*x**9

                #end if

                else:
                    print "Error in voltage correction, out of range."

            #end if (Alumel)

            else:
                print "Error in voltage correction."

        #end if (K-type)

        return alpha

    #end def

    #--------------------------------------------------------------------------
    def write_data_to_file(self):
        global timecalclist, Vchromelcalclist, Valumelcalclist, dTcalclist, avgTcalclist
        global myfile

        print('\nWrite data to file\n')
        time = (self.time_sampletempA + self.time_sampletempB + self.time_Valumel + self.time_Vchromel + self.time_sampletempA2 + self.time_sampletempB2 + self.time_Valumel2 + self.time_Vchromel2)/8
        ta = (self.sampletempA + self.sampletempA2)/2
        tb = (self.sampletempB + self.sampletempB2)/2
        avgt = (ta + tb)/2
        dt = ta-tb
        vchromel = (self.Vchromelcalc + self.Vchromelcalc2)/2
        valumel = (self.Valumelcalc + self.Valumelcalc2)/2
        myfile.write('%f,' %(time))
        myfile.write('%f,%f,%f,%f,' % (ta, tb, avgt, dt) )
        myfile.write('%.3f,%.3f' % (vchromel,valumel))

        timecalclist.append(time)
        Vchromelcalclist.append(vchromel)
        Valumelcalclist.append(valumel)
        dTcalclist.append(dt)
        avgTcalclist.append(avgt)

        # indicates whether an oscillation has started or stopped
        if self.measurement_indicator == 'start':
            myfile.write(',Start Oscillation')
            self.measurement_indicator = 'none'

        elif self.measurement_indicator == 'stop':
            myfile.write(',Stop Oscillation')
            self.measurement_indicator = 'none'

        elif self.measurement_indicator == 'none':
            myfile.write(', ')

        else:
            myfile.write(', ')

        myfile.write('\n')
    #end def

    #--------------------------------------------------------------------------
    def updateGUI(self, stamp, data):
        """
        Sends data to the GUI (main thread), for live updating while the process is running
        in another thread.
        """
        time.sleep(0.1)
        wx.CallAfter(pub.sendMessage, stamp, msg=data)
    #end def

    #--------------------------------------------------------------------------
    def process_data(self):
        global timecalclist, Vchromelcalclist, Valumelcalclist, dTcalclist, avgTcalclist
        global processfile
        print '\nprocess data to get seebeck coefficient'
        time = np.average(timecalclist)
        avgT = np.average(avgTcalclist)

        dTchromellist = dTcalclist
        dTalumellist = dTcalclist

        results_chromel = {}
        results_alumel = {}

        coeffs_chromel = np.polyfit(dTchromellist, Vchromelcalclist, 1)
        coeffs_alumel = np.polyfit(dTalumellist,Valumelcalclist,1)
        # Polynomial Coefficients
        polynomial_chromel = coeffs_chromel.tolist()
        polynomial_alumel = coeffs_alumel.tolist()

        seebeck_chromel = polynomial_chromel[0]
        offset_chromel = polynomial_chromel[1]
        seebeck_alumel = polynomial_alumel[0]
        offset_alumel = polynomial_alumel[1]

        # Calculate coefficient of determination (r-squared):
        p_chromel = np.poly1d(coeffs_chromel)
        p_alumel = np.poly1d(coeffs_alumel)
        # fitted values:
        yhat_chromel = p_chromel(dTchromellist)
        yhat_alumel = p_alumel(dTalumellist)
        # mean of values:
        ybar_chromel = np.sum(Vchromelcalclist)/len(Vchromelcalclist)
        ybar_alumel = np.sum(Valumelcalclist)/len(Valumelcalclist)
        # regression sum of squares:
        ssreg_chromel = np.sum((yhat_chromel-ybar_chromel)**2)   # or sum([ (yihat - ybar)**2 for yihat in yhat])
        ssreg_alumel = np.sum((yhat_alumel-ybar_alumel)**2)
        # total sum of squares:
        sstot_chromel = np.sum((Vchromelcalclist - ybar_chromel)**2)
        sstot_alumel = np.sum((Valumelcalclist - ybar_alumel)**2)    # or sum([ (yi - ybar)**2 for yi in y])

        rsquared_chromel = ssreg_chromel / sstot_chromel
        rsquared_alumel = ssreg_alumel / sstot_alumel

        processfile.write('%.1f,%.3f,%.3f,%.3f,%.2f,%.2f,%.5f,%.5f\n'%(time,avgT,seebeck_chromel,offset_chromel,rsquared_chromel,seebeck_alumel,offset_alumel,rsquared_alumel))

        fitchromel = {}
        fitalumel = {}
        fitchromel['polynomial'] = polynomial_chromel
        fitalumel['polynomial'] = polynomial_alumel
        fitchromel['r-squared'] = rsquared_chromel
        fitalumel['r-squared'] = rsquared_alumel
        celsius = u"\u2103"
        self.create_plot(dTalumellist,dTchromellist,Valumelcalclist,Vchromelcalclist,fitalumel,fitchromel,str(self.plotnumber)+'_'+str(avgT)+ 'C')

        self.updateGUI(stamp="Chromel Seebeck", data=seebeck_chromel)
        self.updateGUI(stamp="Alumel Seebeck", data=seebeck_alumel)
    #end def

    #--------------------------------------------------------------------------
    def create_plot(self, xalumel, xchromel, yalumel, ychromel, fitalumel, fitchromel, title):
        global filePath
        print 'create seebeck plot'
        dpi = 400

        plt.ioff()

        # Create Plot:
        fig = plt.figure(self.plotnumber, dpi=dpi)
        ax = fig.add_subplot(111)
        ax.grid()
        ax.set_title(title)
        ax.set_xlabel("dT (K)")
        ax.set_ylabel("dV (uV)")

        # Plot data points:
        ax.scatter(xalumel, yalumel, color='r', marker='.', label="alumel Voltage")
        ax.scatter(xchromel, ychromel, color='b', marker='.', label="chromel Voltage")

        # Overlay linear fits:
        coeffsalumel = fitalumel['polynomial']
        coeffschromel = fitchromel['polynomial']
        p_alumel = np.poly1d(coeffsalumel)
        p_chromel = np.poly1d(coeffschromel)
        xp = np.linspace(min(xalumel+xchromel), max(xalumel+xchromel), 5000)
        alumel_eq = 'dV = %.2f*(dT) + %.2f' % (coeffsalumel[0], coeffsalumel[1])
        chromel_eq = 'dV = %.2f*(dT) + %.2f' % (coeffschromel[0], coeffschromel[1])
        ax.plot(xp, p_alumel(xp), '-', c='#FF9900', label="alumel Voltage Fit\n %s" % alumel_eq)
        ax.plot(xp, p_chromel(xp), '-', c='g', label="chromel Voltage Fit\n %s" % chromel_eq)

        ax.legend(loc='upper left', fontsize='10')

        # Save:
        plot_folder = filePath + '/Seebeck Plots/'
        if not os.path.exists(plot_folder):
            os.makedirs(plot_folder)

        fig.savefig('%s.png' % (plot_folder + title) , dpi=dpi)

        plt.close()
    #end def

    #--------------------------------------------------------------------------
    def save_files(self):
        ''' Function saving the files after the data acquisition loop has been
            exited.
        '''

        print('Save Files')

        global myfile
        global rawfile
        global processfile

        myfile.close() # Close the file
        rawfile.close()
        processfile.close()

        # Save the GUI plots
        global save_plots_ID
        save_plots_ID = 1
        self.updateGUI(stamp='Save_All', data='Save')
    #end def

#end class
###############################################################################

###############################################################################
class BoundControlBox(wx.Panel):
    """ A static box with a couple of radio buttons and a text
        box. Alalumels to switch between an automatic mode and a
        manual mode with an associated value.
    """
    #--------------------------------------------------------------------------
    def __init__(self, parent, ID, label, initval):
        wx.Panel.__init__(self, parent, ID)

        self.value = initval

        box = wx.StaticBox(self, -1, label)
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)

        self.radio_auto = wx.RadioButton(self, -1, label="Auto", style=wx.RB_GROUP)
        self.radio_manual = wx.RadioButton(self, -1, label="Manual")
        self.manual_text = wx.TextCtrl(self, -1,
            size=(30,-1),
            value=str(initval),
            style=wx.TE_PROCESS_ENTER)

        self.Bind(wx.EVT_UPDATE_UI, self.on_update_manual_text, self.manual_text)
        self.Bind(wx.EVT_TEXT_ENTER, self.on_text_enter, self.manual_text)

        manual_box = wx.BoxSizer(wx.HORIZONTAL)
        manual_box.Add(self.radio_manual, flag=wx.ALIGN_CENTER_VERTICAL)
        manual_box.Add(self.manual_text, flag=wx.ALIGN_CENTER_VERTICAL)

        sizer.Add(self.radio_auto, 0, wx.ALL, 10)
        sizer.Add(manual_box, 0, wx.ALL, 10)

        self.SetSizer(sizer)
        sizer.Fit(self)

    #end init

    #--------------------------------------------------------------------------
    def on_update_manual_text(self, event):
        self.manual_text.Enable(self.radio_manual.GetValue())

    #end def

    #--------------------------------------------------------------------------
    def on_text_enter(self, event):
        self.value = self.manual_text.GetValue()

    #end def

    #--------------------------------------------------------------------------
    def is_auto(self):
        return self.radio_auto.GetValue()

    #end def

    #--------------------------------------------------------------------------
    def manual_value(self):
        return self.value

    #end def

#end class
###############################################################################

###############################################################################
class UserPanel(wx.Panel):
    ''' User Input Panel '''

    #--------------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)
        global tolerance
        global oscillation
        global stability_threshold

        self.oscillation = oscillation
        self.tolerance = tolerance
        self.stability_threshold = stability_threshold*60


        self.create_title("User Panel") # Title

        self.celsius = u"\u2103"
        self.font2 = wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.NORMAL)

        self.oscillation_control() # Oscillation range control
        self.tolerance_control() # PID tolerance level Control
        self.stability_control() # PID stability threshold control


        self.measurementListBox()
        self.maxLimit_label()

        self.linebreak1 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak2 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak3 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak4 = wx.StaticLine(self, pos=(-1,-1), size=(600,1), style=wx.LI_HORIZONTAL)

        self.run_stop() # Run and Stop buttons

        self.create_sizer() # Set Sizer for panel

        pub.subscribe(self.enable_buttons, "Enable Buttons")

    #end init

    #--------------------------------------------------------------------------
    def create_title(self, name):
        self.titlePanel = wx.Panel(self, -1)
        title = wx.StaticText(self.titlePanel, label=name)
        font_title = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        title.SetFont(font_title)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add((0,-1))
        hbox.Add(title, 0, wx.LEFT, 5)

        self.titlePanel.SetSizer(hbox)
    #end def

    #--------------------------------------------------------------------------
    def run_stop(self):
        self.run_stopPanel = wx.Panel(self, -1)
        rs_sizer = wx.GridBagSizer(3, 3)

        self.btn_check = btn_check = wx.Button(self.run_stopPanel, label='check', style=0, size=(60,30)) # Initial Status Button
        btn_check.SetBackgroundColour((0,0,255))
        caption_check = wx.StaticText(self.run_stopPanel, label='*check inital status')
        self.btn_run = btn_run = wx.Button(self.run_stopPanel, label='run', style=0, size=(60,30)) # Run Button
        btn_run.SetBackgroundColour((0,255,0))
        caption_run = wx.StaticText(self.run_stopPanel, label='*run measurement')
        self.btn_stop = btn_stop = wx.Button(self.run_stopPanel, label='stop', style=0, size=(60,30)) # Stop Button
        btn_stop.SetBackgroundColour((255,0,0))
        caption_stop = wx.StaticText(self.run_stopPanel, label = '*quit operation')

        btn_check.Bind(wx.EVT_BUTTON, self.check)
        btn_run.Bind(wx.EVT_BUTTON, self.run)
        btn_stop.Bind(wx.EVT_BUTTON, self.stop)

        controlPanel = wx.StaticText(self.run_stopPanel, label='Control Panel')
        controlPanel.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.BOLD))

        rs_sizer.Add(controlPanel,(0,0), span=(1,3),flag=wx.ALIGN_CENTER_HORIZONTAL)
        rs_sizer.Add(btn_check,(1,0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        rs_sizer.Add(caption_check,(2,0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        rs_sizer.Add(btn_run,(1,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        rs_sizer.Add(caption_run,(2,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        rs_sizer.Add(btn_stop,(1,2),flag=wx.ALIGN_CENTER_HORIZONTAL)
        rs_sizer.Add(caption_stop,(2,2),flag=wx.ALIGN_CENTER_HORIZONTAL)

        self.run_stopPanel.SetSizer(rs_sizer)

        btn_stop.Disable()

    # end def

    #--------------------------------------------------------------------------
    def check(self, event):

        InitialCheck()

    #end def

    #--------------------------------------------------------------------------
    def run(self, event):
        global dataFile
        global statusFile
        global seebeckFile
        global myfile
        global rawfile
        global processfile
        global measureList
        global dTlist

        global abort_ID

        measureList = [None]*self.listbox.GetCount()
        for k in xrange(self.listbox.GetCount()):
            measureList[k] = int(self.listbox.GetString(k))
        #end for

        if (len(measureList) > 0 and len(dTlist) > 0 ):
            try:

                self.name_folder()

                if self.run_check == wx.ID_OK:

                    myfile = open(dataFile, 'w') # opens file for writing/overwriting
                    rawfile = open(statusFile,'w')
                    processfile = open(seebeckFile,'w')
                    begin = datetime.now() # Current date and time
                    myfile.write('Seebeck Data File\nStart Time: ' + str(begin) + '\n')
                    rawfile.write('System Status\nStart Time: ' + str(begin) + '\n')
                    processfile.write('Processed Seebeck Coefficent\nStart Time: ' + str(begin) + '\n')

                    dataheaders = 'time (s), tempA (C), tempB (C), avgtemp (C), deltatemp (C), Vchromel (uV), Valumel (uV), indicator\n'
                    myfile.write(dataheaders)

                    rawheaders1 = 'time (s), sampletempA (C), samplesetpointA (C), blocktempA (C), stabilityA (C/min), sampletempB (C), samplesetpointB (C), blocktempB (C), stabilityB (C/min),'
                    rawheaders2 = 'chromelvoltageraw (uV), chromelvoltagecalc (uV), alumelvoltageraw(C), alumelvoltagecalc (uV), tolerance, stability\n'
                    rawfile.write(rawheaders1 + rawheaders2)

                    processheaders = 'time(s),temperature (C),seebeck_chromel (uV/K),offset_chromel (uV),R^2_chromel,seebeck_alumel (uV/K),offset_alumel (uV),R^2_alumel\n'
                    processfile.write(processheaders)

                    abort_ID = 0

                    self.btn_osc.Disable()
                    self.btn_tol.Disable()
                    self.btn_stab.Disable()
                    self.btn_new.Disable()
                    self.btn_ren.Disable()
                    self.btn_dlt.Disable()
                    self.btn_clr.Disable()
                    self.btn_check.Disable()
                    self.btn_run.Disable()
                    self.btn_stop.Enable()

                    #start the threading process
                    thread = ProcessThread()

                #end if

            #end try

            except visa.VisaIOError:
                wx.MessageBox("Not all instruments are connected!", "Error")
            #end except
        #end if
    #end def

    #--------------------------------------------------------------------------
    def name_folder(self):
        question = wx.MessageDialog(None, 'The data files are saved into a folder upon ' + \
                    'completion. \nBy default, the folder will be named with a time stamp.\n\n' + \
                    'Would you like to name your own folder?', 'Question',
                    wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        answer = question.ShowModal()

        if answer == wx.ID_YES:
            self.folder_name = wx.GetTextFromUser('Enter the name of your folder.\n' + \
                                                'Only type in a name, NOT a file path.')
            if self.folder_name == "":
                wx.MessageBox("Canceled")
            else:
                self.choose_dir()

        #end if

        else:
            date = str(datetime.now())
            self.folder_name = 'Seebeck Data %s.%s.%s' % (date[0:13], date[14:16], date[17:19])

            self.choose_dir()

        #end else

    #end def

    #--------------------------------------------------------------------------
    def choose_dir(self):
        found = False

        dlg = wx.DirDialog (None, "Choose the directory to save your files.", "",
                    wx.DD_DEFAULT_STYLE)

        self.run_check = dlg.ShowModal()

        if self.run_check == wx.ID_OK:
            global filePath
            filePath = dlg.GetPath()

            filePath = filePath + '/' + self.folder_name

            if not os.path.exists(filePath):
                os.makedirs(filePath)
                os.chdir(filePath)
            else:
                n = 1

                while found == False:
                    path = filePath + ' - ' + str(n)

                    if os.path.exists(path):
                        n = n + 1
                    else:
                        os.makedirs(path)
                        os.chdir(path)
                        n = 1
                        found = True

                #end while

            #end else

        #end if

        # Set the global path to the newly created path, if applicable.
        if found == True:
            filePath = path
        #end if
    #end def

    #--------------------------------------------------------------------------
    def stop(self, event):
        global abort_ID
        abort_ID = 1

        self.enable_buttons

    #end def

    #--------------------------------------------------------------------------
    def oscillation_control(self):
        self.oscPanel = wx.Panel(self, -1)
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        self.label_osc = wx.StaticText(self, label="PID Oscillaton (%s):"% self.celsius)
        self.text_osc = text_osc = wx.StaticText(self.oscPanel, label=str(self.oscillation) + ' '+self.celsius)
        text_osc.SetFont(self.font2)
        self.edit_osc = edit_osc = wx.TextCtrl(self.oscPanel, size=(40, -1))
        self.btn_osc = btn_osc = wx.Button(self.oscPanel, label="save", size=(40, -1))
        text_guide_osc = wx.StaticText(self.oscPanel, label="The PID will oscillate within this \ndegree range when oscillating at \na measurement.")

        btn_osc.Bind(wx.EVT_BUTTON, self.save_oscillation)

        hbox.Add((0, -1))
        hbox.Add(text_osc, 0, wx.LEFT, 5)
        hbox.Add(edit_osc, 0, wx.LEFT, 40)
        hbox.Add(btn_osc, 0, wx.LEFT, 5)
        hbox.Add(text_guide_osc, 0, wx.LEFT, 5)

        self.oscPanel.SetSizer(hbox)

    #end def

    #--------------------------------------------------------------------------
    def save_oscillation(self, e):
        global oscillation
        global dTlist
        try:
            self.oscillation = self.edit_osc.GetValue()
            if float(self.oscillation) > maxLimit:
                self.oscillation = str(maxLimit)
            self.text_osc.SetLabel(self.oscillation)
            oscillation = float(self.oscillation)
            #dTlist = [oscillation*i/4 for i in range(0,-5,-1)+range(-3,5)+range(3,-1,-1)]
            dTlist = [oscillation*i/2 for i in range(0,-3,-1)+range(-1,3)+range(1,-1,-1)]
        except ValueError:
            wx.MessageBox("Invalid input. Must be a number.", "Error")
    #end def

    #--------------------------------------------------------------------------
    def tolerance_control(self):

        self.tolPanel = wx.Panel(self, -1)
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        self.label_tol = wx.StaticText(self, label="Tolerance ("+self.celsius+")")
        self.text_tol = text_tol = wx.StaticText(self.tolPanel, label=str(self.tolerance) + ' '+self.celsius)
        text_tol.SetFont(self.font2)
        self.edit_tol = edit_tol = wx.TextCtrl(self.tolPanel, size=(40, -1))
        self.btn_tol = btn_tol = wx.Button(self.tolPanel, label="save", size=(40, -1))
        text_guide_tol = wx.StaticText(self.tolPanel, label="The tolerance within the\nPID set points necessary\nto start a measurement")

        btn_tol.Bind(wx.EVT_BUTTON, self.save_tolerance)

        hbox.Add((0, -1))
        hbox.Add(text_tol, 0, wx.LEFT, 5)
        hbox.Add(edit_tol, 0, wx.LEFT, 40)
        hbox.Add(btn_tol, 0, wx.LEFT, 5)
        hbox.Add(text_guide_tol, 0, wx.LEFT, 5)

        self.tolPanel.SetSizer(hbox)

    #end def

    #--------------------------------------------------------------------------
    def save_tolerance(self, e):
        global tolerance
        global oscillation
        try:
            self.tolerance = self.edit_tol.GetValue()
            if float(self.tolerance) > oscillation:
                self.tolerance = str(oscillation-1)
            self.text_tol.SetLabel(self.tolerance)
            tolerance = float(self.tolerance)
        except ValueError:
            wx.MessageBox("Invalid input. Must be a number.", "Error")

    #end def

    #--------------------------------------------------------------------------
    def stability_control(self):
        self.stability_threshold_Panel = wx.Panel(self, -1)
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        self.label_stability_threshold = wx.StaticText(self, label="Stability Threshold ("+self.celsius+"/min)")
        self.text_stability_threshold = text_stability_threshold = wx.StaticText(self.stability_threshold_Panel, label=str(self.stability_threshold) + ' '+self.celsius+'/min')
        text_stability_threshold.SetFont(self.font2)
        self.edit_stability_threshold = edit_stability_threshold = wx.TextCtrl(self.stability_threshold_Panel, size=(40, -1))
        self.btn_stab = btn_stab = wx.Button(self.stability_threshold_Panel, label="save", size=(40, -1))
        text_guide_stability_threshold = wx.StaticText(self.stability_threshold_Panel, label='The change in the PID must\nbe bealumel this threshold before\na measurement will begin.')

        btn_stab.Bind(wx.EVT_BUTTON, self.save_stability_threshold)

        hbox.Add((0, -1))
        hbox.Add(text_stability_threshold, 0, wx.LEFT, 5)
        hbox.Add(edit_stability_threshold, 0, wx.LEFT, 40)
        hbox.Add(btn_stab, 0, wx.LEFT, 5)
        hbox.Add(text_guide_stability_threshold, 0, wx.LEFT, 5)

        self.stability_threshold_Panel.SetSizer(hbox)

    #end def

    #--------------------------------------------------------------------------
    def save_stability_threshold(self, e):
        global stability_threshold
        try:
            self.stability_threshold = self.edit_stability_threshold.GetValue()
            self.text_stability_threshold.SetLabel(self.stability_threshold)
            stability_threshold = float(self.stability_threshold)/60
        except ValueError:
            wx.MessageBox("Invalid input. Must be a number.", "Error")

    #end def

    #--------------------------------------------------------------------------
    def measurementListBox(self):
        # ids for measurement List Box
        ID_NEW = 1
        ID_CHANGE = 2
        ID_CLEAR = 3
        ID_DELETE = 4

        self.measurementPanel = wx.Panel(self, -1)
        hbox = wx.BoxSizer(wx.HORIZONTAL)

        self.label_measurements = wx.StaticText(self,
                                             label="Measurements (%s):"
                                             % self.celsius
                                             )
        self.label_measurements.SetFont(self.font2)

        self.listbox = wx.ListBox(self.measurementPanel, size=(75,150))

        btnPanel = wx.Panel(self.measurementPanel, -1)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.btn_new = new = wx.Button(btnPanel, ID_NEW, 'New', size=(50, 20))
        self.btn_ren = ren = wx.Button(btnPanel, ID_CHANGE, 'Change', size=(50, 20))
        self.btn_dlt = dlt = wx.Button(btnPanel, ID_DELETE, 'Delete', size=(50, 20))
        self.btn_clr = clr = wx.Button(btnPanel, ID_CLEAR, 'Clear', size=(50, 20))

        self.Bind(wx.EVT_BUTTON, self.NewItem, id=ID_NEW)
        self.Bind(wx.EVT_BUTTON, self.OnRename, id=ID_CHANGE)
        self.Bind(wx.EVT_BUTTON, self.OnDelete, id=ID_DELETE)
        self.Bind(wx.EVT_BUTTON, self.OnClear, id=ID_CLEAR)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.OnRename)

        vbox.Add((-1, 5))
        vbox.Add(new)
        vbox.Add(ren, 0, wx.TOP, 5)
        vbox.Add(dlt, 0, wx.TOP, 5)
        vbox.Add(clr, 0, wx.TOP, 5)

        btnPanel.SetSizer(vbox)
        #hbox.Add(self.label_measurements, 0, wx.LEFT, 5)
        hbox.Add(self.listbox, 1, wx.ALL, 5)
        hbox.Add(btnPanel, 0, wx.RIGHT, 5)

        self.measurementPanel.SetSizer(hbox)

    #end def

    #--------------------------------------------------------------------------
    def NewItem(self, event):
        text = wx.GetTextFromUser('Enter a new measurement', 'Insert dialog')
        if text != '':
            self.listbox.Append(text)

            time.sleep(0.2)

            self.listbox_max_limit(maxLimit)

    #end def

    #--------------------------------------------------------------------------
    def OnRename(self, event):
        sel = self.listbox.GetSelection()
        text = self.listbox.GetString(sel)
        renamed = wx.GetTextFromUser('Rename item', 'Rename dialog', text)
        if renamed != '':
            self.listbox.Delete(sel)
            self.listbox.Insert(renamed, sel)

            self.listbox_max_limit(maxLimit)

    #end def

    #--------------------------------------------------------------------------
    def OnDelete(self, event):
        sel = self.listbox.GetSelection()
        if sel != -1:
            self.listbox.Delete(sel)

            self.listbox_max_limit(maxLimit)
    #end def

    #--------------------------------------------------------------------------
    def OnClear(self, event):
        self.listbox.Clear()

        self.listbox_max_limit(maxLimit)

    #end def

    #--------------------------------------------------------------------------
    def listbox_max_limit(self, limit):
        """ Sets user input to only alalumel a maximum temperature. """
        mlist = [None]*self.listbox.GetCount()
        for i in xrange(self.listbox.GetCount()):
            mlist[i] = int(self.listbox.GetString(i))

            if mlist[i] > limit:
                self.listbox.Delete(i)
                self.listbox.Insert(str(limit), i)

    #end def

    #--------------------------------------------------------------------------
    def maxLimit_label(self):
        self.maxLimit_Panel = wx.Panel(self, -1)
        maxLimit_label = wx.StaticText(self.maxLimit_Panel, label='Max Limit Temp:')
        maxLimit_text = wx.StaticText(self.maxLimit_Panel, label='%s %s' % (str(maxLimit), self.celsius))

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add((0,-1))
        hbox.Add(maxLimit_label, 0, wx.LEFT, 5)
        hbox.Add(maxLimit_text, 0, wx.LEFT, 5)

        self.maxLimit_Panel.SetSizer(hbox)

    #edn def

    #--------------------------------------------------------------------------
    def create_sizer(self):

        sizer = wx.GridBagSizer(8,2)
        sizer.Add(self.titlePanel, (0, 1), span=(1,2), flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_osc, (1, 1))
        sizer.Add(self.oscPanel, (1, 2))

        sizer.Add(self.label_tol, (2,1))
        sizer.Add(self.tolPanel, (2, 2))
        sizer.Add(self.label_stability_threshold, (3,1))
        sizer.Add(self.stability_threshold_Panel, (3, 2))

        sizer.Add(self.label_measurements, (4,1))
        sizer.Add(self.measurementPanel, (4, 2))
        sizer.Add(self.maxLimit_Panel, (5, 1), span=(1,2))
        sizer.Add(self.linebreak4, (6,1),span = (1,2))
        sizer.Add(self.run_stopPanel, (7,1),span = (1,2), flag=wx.ALIGN_CENTER_HORIZONTAL)

        self.SetSizer(sizer)

    #end def

    #--------------------------------------------------------------------------
    def enable_buttons(self):
        self.btn_check.Enable()
        self.btn_run.Enable()
        self.btn_osc.Enable()
        self.btn_tol.Enable()
        self.btn_stab.Enable()
        self.btn_ren.Enable()
        self.btn_dlt.Enable()
        self.btn_clr.Enable()

        self.btn_stop.Disable()

    #end def

#end class
###############################################################################

###############################################################################
class StatusPanel(wx.Panel):
    """
    Current Status of Measurements
    """
    #--------------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)

        self.celsius = u"\u2103"
        self.delta = u"\u0394"
        self.mu = u"\u00b5"

        self.ctime = str(datetime.now())[11:19]
        self.t='0:00:00'
        self.chromelV=str(0)
        self.alumelV = str(0)
        self.sampletempA=str(30)
        self.sampletempB=str(30)
        self.blocktempA=str(30)
        self.blocktempB=str(30)
        self.samplesetpointA=str(30)
        self.samplesetpointB=str(30)
        self.stabilityA = '-'
        self.stabilityB = '-'
        self.dT = str(float(self.sampletempA)-float(self.sampletempB))
        self.avgT = str((float(self.sampletempA)+float(self.sampletempB))/2)
        self.seebeckchromel = '-'
        self.seebeckalumel = '-'
        self.mea = '-'

        self.create_title("Status Panel")
        self.create_status()
        self.linebreak1 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak2 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak3 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak4 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak5 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak6 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak7 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak8 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))

        # Updates from running program
        pub.subscribe(self.OnTime, "Time Chromel Voltage")
        pub.subscribe(self.OnTime, "Time Alumel Voltage")
        pub.subscribe(self.OnTime, "Time Sample Temp A")
        pub.subscribe(self.OnTime, "Time Sample Temp B")

        pub.subscribe(self.OnChromelVoltage, "Chromel Voltage")
        pub.subscribe(self.OnAlumelVoltage, "Alumel Voltage")
        pub.subscribe(self.OnSampleTempA, "Sample Temp A")
        pub.subscribe(self.OnSampleTempB, "Sample Temp B")
        pub.subscribe(self.OnBlockTempA, "Block Temp A")
        pub.subscribe(self.OnBlockTempB, "Block Temp B")
        pub.subscribe(self.OnSetpointA, "Setpoint A")
        pub.subscribe(self.OnSetpointB, "Setpoint B")
        pub.subscribe(self.OnStabilityA, "Stability A")
        pub.subscribe(self.OnStabilityB, "Stability B")
        pub.subscribe(self.OnMeasurement, 'Measurement')
        pub.subscribe(self.OnSeebeckchromel, "Chromel Seebeck")
        pub.subscribe(self.OnSeebeckalumel, "Alumel Seebeck")


        # Updates from inital check
        pub.subscribe(self.OnChromelVoltage, "Chromel Voltage Init")
        pub.subscribe(self.OnAlumelVoltage, "Alumel Voltage Init")
        pub.subscribe(self.OnSampleTempA, "Sample Temp A Init")
        pub.subscribe(self.OnSampleTempB, "Sample Temp B Init")
        pub.subscribe(self.OnBlockTempA, "Block Temp A Init")
        pub.subscribe(self.OnBlockTempB, "Block Temp B Init")
        pub.subscribe(self.OnSetpointA, "Setpoint A Init")
        pub.subscribe(self.OnSetpointB, "Setpoint B Init")

        #self.update_values()

        self.create_sizer()

    #end init

    #--------------------------------------------------------------------------
    def OnChromelVoltage(self, msg):
        self.chromelV = '%.1f'%(float(msg))
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnAlumelVoltage(self, msg):
        self.alumelV = '%.1f'%(float(msg))
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnSampleTempA(self, msg):
        self.sampletempA = '%.1f'%(float(msg))
        self.dT = str(float(self.sampletempA)-float(self.sampletempB))
        self.avgT = str((float(self.sampletempA)+float(self.sampletempB))/2)
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnSampleTempB(self, msg):
        self.sampletempB = '%.1f'%(float(msg))
        self.dT = str(float(self.sampletempA)-float(self.sampletempB))
        self.avgT = str((float(self.sampletempA)+float(self.sampletempB))/2)
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnBlockTempA(self, msg):
        self.blocktempA = '%.1f'%(float(msg))
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnBlockTempB(self, msg):
        self.blocktempB = '%.1f'%(float(msg))
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnSetpointA(self, msg):
        self.samplesetpointA = '%.1f'%(float(msg))
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnSetpointB(self, msg):
        self.samplesetpointB = '%.1f'%(float(msg))
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnStabilityA(self, msg):
        if msg != '-':
            self.stabilityA = '%.2f'%(float(msg))
        else:
            self.stabilityA = msg
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnStabilityB(self, msg):
        if msg != '-':
            self.stabilityB = '%.2f'%(float(msg))
        else:
            self.stabilityB = msg
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnSeebeckchromel(self, msg):
        self.seebeckchromel = '%.2f'%(float(msg))
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnSeebeckalumel(self, msg):
        self.seebeckalumel = '%.2f'%(float(msg))
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnMeasurement(self, msg):
        self.mea = msg
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def OnTime(self, msg):
        time = int(float(msg))

        hours = str(time/3600)
        minutes = int(time%3600/60)
        if (minutes < 10):
            minutes = '0%i'%(minutes)
        else:
            minutes = '%i'%(minutes)
        seconds = int(time%60)
        if (seconds < 10):
            seconds = '0%i'%(seconds)
        else:
            seconds = '%i'%(seconds)

        self.t = '%s:%s:%s'%(hours,minutes,seconds)
        self.ctime = str(datetime.now())[11:19]
        self.update_values()
    #end def

    #--------------------------------------------------------------------------
    def create_title(self, name):
        self.titlePanel = wx.Panel(self, -1)
        title = wx.StaticText(self.titlePanel, label=name)
        font_title = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        title.SetFont(font_title)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add((0,-1))
        hbox.Add(title, 0, wx.LEFT, 5)

        self.titlePanel.SetSizer(hbox)
    #end def

    #--------------------------------------------------------------------------
    def create_status(self):
        self.label_ctime = wx.StaticText(self, label="current time:")
        self.label_ctime.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_t = wx.StaticText(self, label="run time (s):")
        self.label_t.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_chromelV = wx.StaticText(self, label="voltage (chromel) ("+self.mu+"V):")
        self.label_chromelV.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_alumelV = wx.StaticText(self, label="voltage (alumel) ("+self.mu+"V):")
        self.label_alumelV.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_sampletempA = wx.StaticText(self, label="sample temp A ("+self.celsius+"):")
        self.label_sampletempA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_sampletempB = wx.StaticText(self, label="sample temp B ("+self.celsius+"):")
        self.label_sampletempB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_blocktempA = wx.StaticText(self, label="block temp A ("+self.celsius+"):")
        self.label_blocktempA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_blocktempB = wx.StaticText(self, label="block temp B ("+self.celsius+"):")
        self.label_blocktempB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_samplesetpointA = wx.StaticText(self, label="sample setpoint A ("+self.celsius+"):")
        self.label_samplesetpointA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_samplesetpointB = wx.StaticText(self, label="sample setpoint B ("+self.celsius+"):")
        self.label_samplesetpointB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_stabilityA = wx.StaticText(self, label="sample stability A ("+self.celsius+ "/min):")
        self.label_stabilityA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_stabilityB = wx.StaticText(self, label="sample stability B ("+self.celsius+ "/min):")
        self.label_stabilityB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_avgT = wx.StaticText(self, label="avg T ("+self.celsius+"):")
        self.label_avgT.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_dT = wx.StaticText(self, label=self.delta+"T ("+self.celsius+"):")
        self.label_dT.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_seebeckchromel = wx.StaticText(self, label="seebeck (chromel) ("+self.mu+"V/"+self.celsius+"):")
        self.label_seebeckchromel.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_seebeckalumel = wx.StaticText(self, label="seebeck (alumel) ("+self.mu+"V/"+self.celsius+"):")
        self.label_seebeckalumel.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_mea = wx.StaticText(self, label="seebeck measurement")
        self.label_mea.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))

        self.ctimecurrent = wx.StaticText(self, label=self.ctime)
        self.ctimecurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.tcurrent = wx.StaticText(self, label=self.t)
        self.tcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.chromelVcurrent = wx.StaticText(self, label=self.chromelV)
        self.chromelVcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.alumelVcurrent = wx.StaticText(self, label=self.alumelV)
        self.alumelVcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.sampletempAcurrent = wx.StaticText(self, label=self.sampletempA)
        self.sampletempAcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.sampletempBcurrent = wx.StaticText(self, label=self.sampletempB)
        self.sampletempBcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.blocktempAcurrent = wx.StaticText(self, label=self.blocktempA)
        self.blocktempAcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.blocktempBcurrent = wx.StaticText(self, label=self.blocktempB)
        self.blocktempBcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.samplesetpointAcurrent = wx.StaticText(self, label=self.samplesetpointA)
        self.samplesetpointAcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.samplesetpointBcurrent = wx.StaticText(self, label=self.samplesetpointB)
        self.samplesetpointBcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.stabilityAcurrent = wx.StaticText(self, label=self.stabilityA)
        self.stabilityAcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.stabilityBcurrent = wx.StaticText(self, label=self.stabilityB)
        self.stabilityBcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.avgTcurrent = wx.StaticText(self, label=self.avgT)
        self.avgTcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.dTcurrent = wx.StaticText(self, label=self.dT)
        self.dTcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.seebeckchromelcurrent = wx.StaticText(self, label=self.seebeckchromel)
        self.seebeckchromelcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.seebeckalumelcurrent = wx.StaticText(self, label=self.seebeckalumel)
        self.seebeckalumelcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.meacurrent = wx.StaticText(self, label=self.mea)
        self.meacurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
    #end def

    #--------------------------------------------------------------------------
    def update_values(self):
        self.ctimecurrent.SetLabel(self.ctime)
        self.tcurrent.SetLabel(self.t)
        self.chromelVcurrent.SetLabel(self.chromelV)
        self.alumelVcurrent.SetLabel(self.alumelV)
        self.sampletempAcurrent.SetLabel(self.sampletempA)
        self.sampletempBcurrent.SetLabel(self.sampletempB)
        self.blocktempAcurrent.SetLabel(self.blocktempA)
        self.blocktempBcurrent.SetLabel(self.blocktempB)
        self.samplesetpointAcurrent.SetLabel(self.samplesetpointA)
        self.samplesetpointBcurrent.SetLabel(self.samplesetpointB)
        self.stabilityAcurrent.SetLabel(self.stabilityA)
        self.stabilityBcurrent.SetLabel(self.stabilityB)
        self.avgTcurrent.SetLabel(self.avgT)
        self.dTcurrent.SetLabel(self.dT)
        self.seebeckchromelcurrent.SetLabel(self.seebeckchromel)
        self.seebeckalumelcurrent.SetLabel(self.seebeckalumel)
        self.meacurrent.SetLabel(self.mea)
    #end def

    #--------------------------------------------------------------------------
    def create_sizer(self):
        sizer = wx.GridBagSizer(20,2)

        sizer.Add(self.titlePanel, (0, 0), span = (1,2), border=5, flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.linebreak1,(1,0), span = (1,2))

        sizer.Add(self.label_ctime, (2,0))
        sizer.Add(self.ctimecurrent, (2, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_t, (3,0))
        sizer.Add(self.tcurrent, (3, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)

        #sizer.Add(self.linebreak2,(4,0), span = (1,2))

        sizer.Add(self.label_chromelV, (4, 0))
        sizer.Add(self.chromelVcurrent, (4, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_alumelV, (5,0))
        sizer.Add(self.alumelVcurrent, (5,1),flag=wx.ALIGN_CENTER_HORIZONTAL)

        #sizer.Add(self.linebreak3,(7,0), span = (1,2))

        sizer.Add(self.label_sampletempA, (6,0))
        sizer.Add(self.sampletempAcurrent, (6,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_samplesetpointA, (7,0))
        sizer.Add(self.samplesetpointAcurrent, (7,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_stabilityA, (8,0))
        sizer.Add(self.stabilityAcurrent, (8, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_blocktempA, (9,0))
        sizer.Add(self.blocktempAcurrent, (9,1),flag=wx.ALIGN_CENTER_HORIZONTAL)

        #sizer.Add(self.linebreak4,(12,0), span = (1,2))

        sizer.Add(self.label_sampletempB, (10,0))
        sizer.Add(self.sampletempBcurrent, (10,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_samplesetpointB, (11,0))
        sizer.Add(self.samplesetpointBcurrent, (11,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_stabilityB, (12,0))
        sizer.Add(self.stabilityBcurrent, (12, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_blocktempB, (13,0))
        sizer.Add(self.blocktempBcurrent, (13,1),flag=wx.ALIGN_CENTER_HORIZONTAL)

        #sizer.Add(self.linebreak5,(17,0), span = (1,2))

        sizer.Add(self.label_avgT, (14,0))
        sizer.Add(self.avgTcurrent, (14,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_dT, (15,0))
        sizer.Add(self.dTcurrent, (15,1),flag=wx.ALIGN_CENTER_HORIZONTAL)

        #sizer.Add(self.linebreak6,(20,0), span = (1,2))

        sizer.Add(self.label_seebeckchromel, (16,0))
        sizer.Add(self.seebeckchromelcurrent, (16,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_seebeckalumel, (17,0))
        sizer.Add(self.seebeckalumelcurrent, (17,1),flag=wx.ALIGN_CENTER_HORIZONTAL)

        #sizer.Add(self.linebreak7,(23,0), span = (1,2))

        sizer.Add(self.label_mea, (18,0))
        sizer.Add(self.meacurrent, (18,1),flag=wx.ALIGN_CENTER_HORIZONTAL)

        sizer.Add(self.linebreak2, (19,0), span = (1,2))

        self.SetSizer(sizer)
    #end def

#end class
###############################################################################

###############################################################################
class VoltagePanel(wx.Panel):
    """
    GUI Window for plotting voltage data.
    """
    #--------------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)
        global filePath

        global tchromelV_list
        global chromelV_list
        global talumelV_list
        global alumelV_list

        self.create_title("Voltage Panel")
        self.init_plot()
        self.canvas = FigureCanvasWxAgg(self, -1, self.figure)
        self.create_control_panel()
        self.create_sizer()

        pub.subscribe(self.OnChromelVoltage, "Chromel Voltage")
        pub.subscribe(self.OnchromelVTime, "Time Chromel Voltage")
        pub.subscribe(self.OnAlumelVoltage, "Alumel Voltage")
        pub.subscribe(self.OnalumelVTime, "Time Alumel Voltage")

        # For saving the plots at the end of data acquisition:
        pub.subscribe(self.save_plot, "Save_All")

        self.animator = animation.FuncAnimation(self.figure, self.draw_plot, interval=500, blit=False)
    #end init

    #--------------------------------------------------------------------------
    def create_title(self, name):
        self.titlePanel = wx.Panel(self, -1)
        title = wx.StaticText(self.titlePanel, label=name)
        font_title = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        title.SetFont(font_title)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add((0,-1))
        hbox.Add(title, 0, wx.LEFT, 5)

        self.titlePanel.SetSizer(hbox)
    #end def

    #--------------------------------------------------------------------------
    def create_control_panel(self):

        self.xmin_control = BoundControlBox(self, -1, "t min", 0)
        self.xmax_control = BoundControlBox(self, -1, "t max", 100)
        self.ymin_control = BoundControlBox(self, -1, "V min", -1000)
        self.ymax_control = BoundControlBox(self, -1, "V max", 1000)

        self.hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.hbox1.AddSpacer(10)
        self.hbox1.Add(self.xmin_control, border=5, flag=wx.ALL)
        self.hbox1.Add(self.xmax_control, border=5, flag=wx.ALL)
        self.hbox1.AddSpacer(10)
        self.hbox1.Add(self.ymin_control, border=5, flag=wx.ALL)
        self.hbox1.Add(self.ymax_control, border=5, flag=wx.ALL)
    #end def

    #--------------------------------------------------------------------------
    def OnChromelVoltage(self, msg):
        self.chromelV = float(msg)
        chromelV_list.append(self.chromelV)
        tchromelV_list.append(self.tchromelV)
    #end def

    #--------------------------------------------------------------------------
    def OnchromelVTime(self, msg):
        self.tchromelV = float(msg)

    #end def

    #--------------------------------------------------------------------------
    def OnAlumelVoltage(self, msg):
        self.alumelV = float(msg)
        alumelV_list.append(self.alumelV)
        talumelV_list.append(self.talumelV)
    #end def

    #--------------------------------------------------------------------------
    def OnalumelVTime(self, msg):
        self.talumelV = float(msg)


    #end def

    #--------------------------------------------------------------------------
    def init_plot(self):
        self.dpi = 100
        self.colorH = 'g'
        self.colorL = 'y'

        self.figure = Figure((6,2), dpi=self.dpi)
        self.subplot = self.figure.add_subplot(111)
        self.lineH, = self.subplot.plot(tchromelV_list,chromelV_list, color=self.colorH, linewidth=1)
        self.lineL, = self.subplot.plot(talumelV_list,alumelV_list, color=self.colorL, linewidth=1)

        self.legend = self.figure.legend( (self.lineH, self.lineL), (r"$V_{chromel}$",r"$V_{alumel}$"), (0.15,0.7),fontsize=8)
        #self.subplot.text(0.05, .95, r'$X(f) = \mathcal{F}\{x(t)\}$', \
            #verticalalignment='top', transform = self.subplot.transAxes)
    #end def

    #--------------------------------------------------------------------------
    def draw_plot(self,i):
        self.subplot.clear()
        #self.subplot.set_title("voltage vs. time", fontsize=12)
        self.subplot.set_ylabel(r"voltage ($\mu V$)", fontsize = 8)
        self.subplot.set_xlabel("time (s)", fontsize = 8)

        # Adjustable scale:
        if self.xmax_control.is_auto():
            xmax = max(tchromelV_list+talumelV_list)
        else:
            xmax = float(self.xmax_control.manual_value())
        if self.xmin_control.is_auto():
            xmin = 0
        else:
            xmin = float(self.xmin_control.manual_value())
        if self.ymin_control.is_auto():
            minV = min(chromelV_list+alumelV_list)
            ymin = minV - abs(minV)*0.3
        else:
            ymin = float(self.ymin_control.manual_value())
        if self.ymax_control.is_auto():
            maxV = max(chromelV_list+alumelV_list)
            ymax = maxV + abs(maxV)*0.3
        else:
            ymax = float(self.ymax_control.manual_value())


        self.subplot.set_xlim([xmin, xmax])
        self.subplot.set_ylim([ymin, ymax])

        pylab.setp(self.subplot.get_xticklabels(), fontsize=8)
        pylab.setp(self.subplot.get_yticklabels(), fontsize=8)

        self.lineH, = self.subplot.plot(tchromelV_list,chromelV_list, color=self.colorH, linewidth=1)
        self.lineL, = self.subplot.plot(talumelV_list,alumelV_list, color=self.colorL, linewidth=1)

        return (self.lineH, self.lineL)
        #return (self.subplot.plot( tchromelV_list, chromelV_list, color=self.colorH, linewidth=1),
            #self.subplot.plot( talumelV_list, alumelV_list, color=self.colorL, linewidth=1))

    #end def

    #--------------------------------------------------------------------------
    def save_plot(self, msg):
        path = filePath + "/Voltage_Plot.png"
        self.canvas.print_figure(path)

    #end def

    #--------------------------------------------------------------------------
    def create_sizer(self):
        sizer = wx.GridBagSizer(3,1)
        sizer.Add(self.titlePanel, (0, 0), flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.canvas, ( 1,0), flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.hbox1, (2,0), flag=wx.ALIGN_CENTER_HORIZONTAL)

        self.SetSizer(sizer)
    #end def

#end class
###############################################################################

###############################################################################
class TemperaturePanel(wx.Panel):
    """
    GUI Window for plotting temperature data.
    """
    #--------------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        wx.Panel.__init__(self, *args, **kwargs)
        global filePath

        global tsampletempA_list
        global sampletempA_list
        global tsampletempB_list
        global sampletempB_list
        global tblocktemp_list
        global blocktempA_list
        global blocktempB_list

        self.create_title("Temperature Panel")
        self.init_plot()
        self.canvas = FigureCanvasWxAgg(self, -1, self.figure)
        self.create_control_panel()
        self.create_sizer()

        pub.subscribe(self.OnTimeSampleTempA, "Time Sample Temp A")
        pub.subscribe(self.OnSampleTempA, "Sample Temp A")
        pub.subscribe(self.OnTimeSampleTempB, "Time Sample Temp B")
        pub.subscribe(self.OnSampleTempB, "Sample Temp B")
        pub.subscribe(self.OnTimeBlockTemp, "Time Block Temp")
        pub.subscribe(self.OnBlockTempA, "Block Temp A")
        pub.subscribe(self.OnBlockTempB, "Block Temp B")

        # For saving the plots at the end of data acquisition:
        pub.subscribe(self.save_plot, "Save_All")

        self.animator = animation.FuncAnimation(self.figure, self.draw_plot, interval=500, blit=False)
    #end init

    #--------------------------------------------------------------------------
    def create_title(self, name):
        self.titlePanel = wx.Panel(self, -1)
        title = wx.StaticText(self.titlePanel, label=name)
        font_title = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        title.SetFont(font_title)

        hbox = wx.BoxSizer(wx.HORIZONTAL)
        hbox.Add((0,-1))
        hbox.Add(title, 0, wx.LEFT, 5)

        self.titlePanel.SetSizer(hbox)
    #end def

    #--------------------------------------------------------------------------
    def create_control_panel(self):

        self.xmin_control = BoundControlBox(self, -1, "t min", 0)
        self.xmax_control = BoundControlBox(self, -1, "t max", 100)
        self.ymin_control = BoundControlBox(self, -1, "T min", 0)
        self.ymax_control = BoundControlBox(self, -1, "T max", 500)

        self.hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.hbox1.AddSpacer(10)
        self.hbox1.Add(self.xmin_control, border=5, flag=wx.ALL)
        self.hbox1.Add(self.xmax_control, border=5, flag=wx.ALL)
        self.hbox1.AddSpacer(10)
        self.hbox1.Add(self.ymin_control, border=5, flag=wx.ALL)
        self.hbox1.Add(self.ymax_control, border=5, flag=wx.ALL)
    #end def

    #--------------------------------------------------------------------------
    def OnTimeSampleTempA(self, msg):
        self.tsampletempA = float(msg)
    #end def

    #--------------------------------------------------------------------------
    def OnSampleTempA(self, msg):
        self.sampletempA = float(msg)
        sampletempA_list.append(self.sampletempA)
        tsampletempA_list.append(self.tsampletempA)
    #end def

    #--------------------------------------------------------------------------
    def OnTimeSampleTempB(self, msg):
        self.tsampletempB = float(msg)
    #end def

    #--------------------------------------------------------------------------
    def OnSampleTempB(self, msg):
        self.sampletempB = float(msg)
        sampletempB_list.append(self.sampletempB)
        tsampletempB_list.append(self.tsampletempB)
    #end def

    #--------------------------------------------------------------------------
    def OnTimeBlockTemp(self, msg):
        self.tblocktemp = float(msg)
        tblocktemp_list.append(self.tblocktemp)
        blocktempA_list.append(self.blocktempA)
        blocktempB_list.append(self.blocktempB)
    #end def

    #--------------------------------------------------------------------------
    def OnBlockTempA(self, msg):
        self.blocktempA = float(msg)
    #end def

    #--------------------------------------------------------------------------
    def OnBlockTempB(self, msg):
        self.blocktempB = float(msg)
    #end def

    #--------------------------------------------------------------------------
    def init_plot(self):
        self.dpi = 100
        self.colorSTA = 'r'
        self.colorSTB = 'b'
        self.colorBTA = 'm'
        self.colorBTB = 'c'

        self.figure = Figure((6,2), dpi=self.dpi)
        self.subplot = self.figure.add_subplot(111)

        self.lineSTA, = self.subplot.plot(tsampletempA_list,sampletempA_list, color=self.colorSTA, linewidth=1)
        self.lineSTB, = self.subplot.plot(tsampletempB_list,sampletempB_list, color=self.colorSTB, linewidth=1)
        self.lineBTA, = self.subplot.plot(tblocktemp_list,blocktempA_list, color=self.colorBTA, linewidth=1)
        self.lineBTB, = self.subplot.plot(tblocktemp_list,blocktempB_list, color=self.colorBTB, linewidth=1)

        self.legend = self.figure.legend( (self.lineSTA, self.lineBTA, self.lineSTB, self.lineBTB), (r"$T_A$ (sample)",r"$T_A$ (block)",r"$T_B$ (sample)",r"$T_B$ (block)"), (0.15,0.50),fontsize=8)
        #self.subplot.text(0.05, .95, r'$X(f) = \mathcal{F}\{x(t)\}$', \
            #verticalalignment='top', transform = self.subplot.transAxes)
    #end def

    #--------------------------------------------------------------------------
    def draw_plot(self,i):
        self.subplot.clear()
        #self.subplot.set_title("temperature vs. time", fontsize=12)
        self.subplot.set_ylabel(r"temperature ($\degree C$)", fontsize = 8)
        self.subplot.set_xlabel("time (s)", fontsize = 8)

        # Adjustable scale:
        if self.xmax_control.is_auto():
            xmax = max(tsampletempA_list+tsampletempB_list+tblocktemp_list)
        else:
            xmax = float(self.xmax_control.manual_value())
        if self.xmin_control.is_auto():
            xmin = 0
        else:
            xmin = float(self.xmin_control.manual_value())
        if self.ymin_control.is_auto():
            minT = min(sampletempA_list+sampletempB_list+blocktempA_list+blocktempB_list)
            ymin = minT - abs(minT)*0.3
        else:
            ymin = float(self.ymin_control.manual_value())
        if self.ymax_control.is_auto():
            maxT = max(sampletempA_list+sampletempB_list+blocktempA_list+blocktempB_list)
            ymax = maxT + abs(maxT)*0.3
        else:
            ymax = float(self.ymax_control.manual_value())

        self.subplot.set_xlim([xmin, xmax])
        self.subplot.set_ylim([ymin, ymax])

        pylab.setp(self.subplot.get_xticklabels(), fontsize=8)
        pylab.setp(self.subplot.get_yticklabels(), fontsize=8)

        self.lineSTA, = self.subplot.plot(tsampletempA_list,sampletempA_list, color=self.colorSTA, linewidth=1)
        self.lineSTB, = self.subplot.plot(tsampletempB_list,sampletempB_list, color=self.colorSTB, linewidth=1)
        self.lineBTA, = self.subplot.plot(tblocktemp_list,blocktempA_list, color=self.colorBTA, linewidth=1)
        self.lineBTB, = self.subplot.plot(tblocktemp_list,blocktempB_list, color=self.colorBTB, linewidth=1)

        return (self.lineSTA, self.lineSTB, self.lineBTA, self.lineBTB)

    #end def

    #--------------------------------------------------------------------------
    def save_plot(self, msg):
        path = filePath + "/Temperature_Plot.png"
        self.canvas.print_figure(path)

    #end def

    #--------------------------------------------------------------------------
    def create_sizer(self):
        sizer = wx.GridBagSizer(3,1)
        sizer.Add(self.titlePanel, (0, 0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.canvas, ( 1,0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.hbox1, (2,0),flag=wx.ALIGN_CENTER_HORIZONTAL)

        self.SetSizer(sizer)
    #end def

#end class
###############################################################################

###############################################################################
class Frame(wx.Frame):
    """
    Main frame window in which GUI resides
    """
    #--------------------------------------------------------------------------
    def __init__(self, *args, **kwargs):
        wx.Frame.__init__(self, *args, **kwargs)
        self.init_UI()
        self.create_statusbar()
        self.create_menu()
        pub.subscribe(self.update_statusbar, "Status Bar")

    #end init

    #--------------------------------------------------------------------------
    def init_UI(self):
        self.SetBackgroundColour('#E0EBEB')
        self.userpanel = UserPanel(self, size=wx.DefaultSize)
        self.statuspanel = StatusPanel(self,size=wx.DefaultSize)
        self.voltagepanel = VoltagePanel(self, size=wx.DefaultSize)
        self.temperaturepanel = TemperaturePanel(self, size=wx.DefaultSize)

        self.statuspanel.SetBackgroundColour('#ededed')

        sizer = wx.GridBagSizer(2, 3)
        sizer.Add(self.userpanel, (0,0),flag=wx.ALIGN_CENTER_HORIZONTAL, span = (2,1))
        sizer.Add(self.statuspanel, (0,2),flag=wx.ALIGN_CENTER_HORIZONTAL, span = (2,1))
        sizer.Add(self.voltagepanel, (0,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.temperaturepanel, (1,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Fit(self)

        self.SetSizer(sizer)
        self.SetTitle('High Temp Seebeck GUI')
        self.Centre()
    #end def

    #--------------------------------------------------------------------------
    def create_menu(self):
        # Menu Bar with File, Quit
        menubar = wx.MenuBar()
        fileMenu = wx.Menu()
        qmi = wx.MenuItem(fileMenu, APP_EXIT, '&Quit\tCtrl+Q')
        #qmi.SetBitmap(wx.Bitmap('exit.png'))
        fileMenu.AppendItem(qmi)

        self.Bind(wx.EVT_MENU, self.onQuit, id=APP_EXIT)

        menubar.Append(fileMenu, 'File')
        self.SetMenuBar(menubar)
    #end def

    #--------------------------------------------------------------------------
    def onQuit(self, e):
        global abort_ID

        abort_ID=1
        self.Destroy()
        self.Close()

        sys.stdout.close()
        sys.stderr.close()
    #end def

    #--------------------------------------------------------------------------
    def create_statusbar(self):
        self.statusbar = ESB.EnhancedStatusBar(self, -1)
        self.statusbar.SetSize((-1, 23))
        self.statusbar.SetFieldsCount(8)
        self.SetStatusBar(self.statusbar)

        self.space_between = 10

        ### Create Widgets for the statusbar:
        # Status:
        self.status_text = wx.StaticText(self.statusbar, -1, "Ready")
        self.width0 = 105

        # Placer 1:
        placer1 = wx.StaticText(self.statusbar, -1, " ")

        # Title:
        #measurement_text = wx.StaticText(self.statusbar, -1, "Measurement Indicators:")
        #boldFont = wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        #measurement_text.SetFont(boldFont)
        #self.width1 = measurement_text.GetRect().width + self.space_between

        # PID Tolerance:
        pidTol_text = wx.StaticText(self.statusbar, -1, "Within Tolerance:")
        self.width2 = pidTol_text.GetRect().width + self.space_between

        self.indicator_tol = wx.StaticText(self.statusbar, -1, "-")
        self.width3 = 25

        # Stability Threshold:
        stableThresh_text = wx.StaticText(self.statusbar, -1, "Within Stability Threshold:")
        self.width4 = stableThresh_text.GetRect().width + 5

        self.indicator_stable = wx.StaticText(self.statusbar, -1, "-")
        self.width5 = self.width3



        # Placer 2:
        placer2 = wx.StaticText(self.statusbar, -1, " ")

        # Version:
        version_label = wx.StaticText(self.statusbar, -1, "Version: %s" % version)
        self.width8 = version_label.GetRect().width + self.space_between

        # Set widths of each piece of the status bar:
        self.statusbar.SetStatusWidths([self.width0, 50, self.width2, self.width3, self.width4, self.width5, -1, self.width8])

        ### Add the widgets to the status bar:
        # Status:
        self.statusbar.AddWidget(self.status_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)

        # Placer 1:
        self.statusbar.AddWidget(placer1)

        # Title:
        #self.statusbar.AddWidget(measurement_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)

        # PID Tolerance:
        self.statusbar.AddWidget(pidTol_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        self.statusbar.AddWidget(self.indicator_tol, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)

        # Stability Threshold:
        self.statusbar.AddWidget(stableThresh_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        self.statusbar.AddWidget(self.indicator_stable, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)


        # Placer 2
        self.statusbar.AddWidget(placer2)

        # Version:
        self.statusbar.AddWidget(version_label, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)

    #end def

    #--------------------------------------------------------------------------
    def update_statusbar(self, msg):
        string = msg

        # Status:
        if string == 'Running' or string == 'Finished, Ready' or string == 'Exception Occurred' or string=='Checking':
            self.status_text.SetLabel(string)
            self.status_text.SetBackgroundColour(wx.NullColour)

            if string == 'Exception Occurred':
                self.status_text.SetBackgroundColour("RED")
            #end if

        #end if

        else:
            tol = string[0]
            stable = string[1]

            # PID Tolerance indicator:
            self.indicator_tol.SetLabel(tol)
            if tol == 'OK':
                self.indicator_tol.SetBackgroundColour("GREEN")
            #end if
            else:
                self.indicator_tol.SetBackgroundColour("RED")
            #end else

            # Stability Threshold indicator:
            self.indicator_stable.SetLabel(stable)
            if stable == 'OK':
                self.indicator_stable.SetBackgroundColour("GREEN")
            #end if
            else:
                self.indicator_stable.SetBackgroundColour("RED")
            #end else
        #end else

    #end def

#end class
###############################################################################

###############################################################################
class App(wx.App):
    """
    App for initializing program
    """
    #--------------------------------------------------------------------------
    def OnInit(self):
        self.frame = Frame(parent=None, title="High Temp Seebeck GUI", size=(1280,1280))
        self.frame.Show()

        setup = Setup()
        return True
    #end init

#end class
###############################################################################

#==============================================================================
if __name__=='__main__':
    app = App()
    app.MainLoop()

#end if
