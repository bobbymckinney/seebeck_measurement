#! /usr/bin/python
# -*- coding: utf-8 -*-
"""
Created: 2015-03-31

@author: Bobby McKinney (bobbymckinney@gmail.com)

__Title__ : voltagepanel
Description:
Comments:
"""
import os
import sys
import wx
from wx.lib.pubsub import pub # For communicating b/w the thread and the GUI
import matplotlib
matplotlib.interactive(False)
matplotlib.use('WXAgg') # The recommended way to use wx with mpl is with WXAgg backend.

from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg
from matplotlib.figure import Figure
from matplotlib.pyplot import gcf, setp
import matplotlib.animation as animation # For plotting
import pylab
import numpy as np
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

# For finding sheet resistance:
import Seebeck_Processing_v4

#==============================================================================
# Keeps Windows from complaining that the port is already open:
modbus.CLOSE_PORT_AFTER_EACH_CALL = True

version = '3.0 (2015-05-20)'

'''
Global Variables:
'''

# Naming a data file:
dataFile = 'Data_Backup.csv'
pidFile = 'PID_Data.csv'
finaldataFile = 'Data.csv'

APP_EXIT = 1 # id for File\Quit

equil_time = 180 # How much time until the PID will change after reaching an equilibrium point
tolerance = 2 # This must be set to less than oscillation
stability_threshold = 0.2/60
oscillation = 8 # Degree range that the PID will oscillate in
measureList = []

maxLimit = 700 # Restricts the user to a max temperature

abort_ID = 0 # Abort method

# Global placers for instruments
k2700 = ''
heaterA = ''
heaterB = ''

tc_type = "k-type" # Set the thermocouple type in order to use the correct voltage correction

# Channels corresponding to switch card:
tempAChannel = '109'
tempBChannel = '110'
highVChannel = '107'
lowVChannel = '108'

# placer for directory
filePath = 'global file path'

# placer for files to be created
myfile = 'global file'
pfile = 'global file'

# Placers for the GUI plots:
highV_list = []
thighV_list = []
lowV_list=[]
tlowV_list = []
tempA_list = []
ttempA_list = []
tempB_list = []
ttempB_list = []
tpid_list = []
pidA_list = []
pidB_list = []

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
        self.ctrl.write(":ROUTe:SCAN:INTernal (@ %s)" % (channel)) # Specify Channel
        #keithley.write(":SENSe1:FUNCtion 'TEMPerature'") # Specify Data type
        self.ctrl.write(":ROUTe:SCAN:LSELect INTernal") # Scan Selected Channel
        self.ctrl.write(":ROUTe:SCAN:LSELect NONE") # Stop Scan
        data = self.ctrl.query(":FETCh?")
        return str(data)[0:15] # Fetches Reading    
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
        global heaterA
        global heaterB
        
        # Define Keithley instrument port:
        self.k2700 = k2700 = Keithley_2700('GPIB0::1::INSTR')
        # Define the ports for the PID
        self.heaterB = heaterB = PID('/dev/cu.usbserial', 1) # TOP heater
        self.heaterA = heaterA = PID('/dev/cu.usbserial', 2) # BOTTOM heater

        
        """
        Prepare the Keithley for operation:
        """
        self.k2700.openAllChannels
        # Define the type of measurement for the channels we are looking at:
        self.k2700.ctrl.write(":SENSe1:TEMPerature:TCouple:TYPE K") # Set ThermoCouple type
        self.k2700.ctrl.write(":SENSe1:FUNCtion 'TEMPerature', (@ 109,110)")
        self.k2700.ctrl.write(":SENSe1:FUNCtion 'VOLTage:DC', (@ 107,108)")
        
        self.k2700.ctrl.write(":TRIGger:SEQuence1:DELay 0")
        self.k2700.ctrl.write(":TRIGger:SEQuence1:COUNt 1")    # Set the count rate
        
        # Sets the the acquisition rate of the measurements
        self.k2700.ctrl.write(":SENSe1:VOLTage:DC:NPLCycles 4, (@ 107,108)") # Sets integration period based on frequency
        self.k2700.ctrl.write(":SENSe1:TEMPerature:NPLCycles 4, (@ 109,110)")
        
        """
        Prepare the PID for operation:
        """
        # Set the control method to PID
        self.heaterA.write_register(PID.control, PID.pIDcontrol)
        self.heaterB.write_register(PID.control, PID.pIDcontrol)
        
        # Set the PID to auto parameter
        self.heaterA.write_register(PID.pIDparam, PID.pIDparam_Auto)
        self.heaterB.write_register(PID.pIDparam, PID.pIDparam_Auto)
        
        # Set the thermocouple type
        self.heaterA.write_register(PID.tCouple, PID.tCouple_K)
        self.heaterB.write_register(PID.tCouple, PID.tCouple_K)
        
        # Set the control to heating only
        self.heaterA.write_register(PID.heatingCoolingControl, PID.heating)
        self.heaterB.write_register(PID.heatingCoolingControl, PID.heating)
        
        # Run the controllers
        self.heaterA.run()
        self.heaterB.run()

#end class
###############################################################################

###############################################################################
class ProcessThreadRun(Thread):
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
        self.heaterA = heaterA
        self.heaterB = heaterB
        
        self.take_PID_Data()
        
        self.take_Keithley_Data()
        
        self.updateGUI(stamp='Status Bar', data='Ready')
        #end init
    
    #--------------------------------------------------------------------------        
    def take_PID_Data(self):
        """ Takes data from the PID
        """
        
        # Take Data and time stamps:
        self.pA = self.heaterA.get_pv()
        self.pB = self.heaterB.get_pv()
        self.pAset = self.heaterA.get_setpoint()
        self.pBset = self.heaterB.get_setpoint()
        
        self.updateGUI(stamp="PID A Status", data=self.pA)
        self.updateGUI(stamp="PID B Status", data=self.pB)
        self.updateGUI(stamp="PID A SP Status", data=self.pAset)
        self.updateGUI(stamp="PID B SP Status", data=self.pBset)
        
        print "PID A: %.2f C\nPID B: %.2f C" % (self.pA, self.pB)
    #end def
    
    #--------------------------------------------------------------------------        
    def take_Keithley_Data(self):
        """ Takes data from the PID
        """
        
        # Take Data and time stamps:
        self.tA = self.k2700.fetch(tempAChannel)
        self.tB = self.k2700.fetch(tempBChannel)
        self.highV = float(self.k2700.fetch(highVChannel))*10**6
        self.lowV = float(self.k2700.fetch(lowVChannel))*10**6
        
        self.updateGUI(stamp="High Voltage Status", data=self.highV)
        self.updateGUI(stamp="Low Voltage Status", data=self.lowV)
        self.updateGUI(stamp="Temp A Status", data=self.tA)
        self.updateGUI(stamp="Temp B Status", data=self.tB)
        
        print "Temp A: %.2f C\nTemp B: %.2f C" % (float(self.tA), float(self.tB))
        print "High Voltage: %.1f uV\nLow Voltage: %.1f uV" % (self.highV, self.lowV)
        
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
        global heaterA
        global heaterB
        
        global tolerance
        global stability_threshold
        global oscillation
        global equil_time
        
        global measureList
        
        self.k2700 = k2700
        self.heaterA = heaterA
        self.heaterB = heaterB
        
        self.check_measurement_iterator = 0  # Iterator in order to check each  
                                             # step individually, only checks 
                                             # one step at a time.
        
        self.measurement_indicator = 'none' # Indicates the start of a measurement
        self.oscillation_indicator = 0 # indicates where we are in an oscillation
        
        self.pidA_list = []
        self.pidB_list = []
        
        self.pidAset_list = []
        self.pidBset_list = []
        
        self.tolerance = tolerance
        self.stability_threshold = stability_threshold
        self.equil_time = equil_time
        self.oscillation = oscillation
        
        self.tol = 'NO'
        self.stable = 'NO'
        self.equil_timer = 0
        self.equil_time_left = '-'
        
        #stability lists
        self.recentPIDtime=[]
        self.recentPIDA = []
        self.stabilityA = '-'
        self.recentPIDB = []
        self.stabilityB = '-'
        
        self.equil_time_left = '-'
        self.hold = 'OFF'
        
        #time initializations
        self.ttempA = 0
        self.ttempA2 = 0
        self.ttempB = 0
        self.ttempB2 = 0
        
        self.exception_ID = 0
        
        # Set PID setpoints to the starting temperature:
        self.heaterA.set_setpoint(int(measureList[0])-oscillation/2) # 5 degrees below the setpoint
        self.heaterB.set_setpoint(int(measureList[0])+oscillation/2) # 5 degrees above the setpoint
        
        self.updateGUI(stamp='Status Bar', data='Running')
        
        self.start = time.time()
        
        try:
            while abort_ID == 0:
                
                self.take_PID_Data()
                
                self.safety_check()
                
                self.check_status()
        
                self.check_PID_setpoint()
                
                self.seebeck_data_measurement()
                
                self.write_data_to_file()
                
                if abort_ID == 1: break
                
                #end if
            #end while
        #end try
                
        except exceptions.Exception as e:
            log_exception(e)
            
            abort_ID = 1
            
            self.exception_ID = 1
            
            print "Error Occurred, check error_log.log"
        #end except
            
        if self.exception_ID == 1:
            self.updateGUI(stamp='Status Bar', data='Exception Occurred')
        #end if    
        else:
            self.updateGUI(stamp='Status Bar', data='Finished, Ready')
        #end else
        
        self.save_files()
        
        self.heaterA.stop()
        self.heaterA.set_setpoint(25)
        self.heaterB.stop()
        self.heaterB.set_setpoint(25)

        
        wx.CallAfter(pub.sendMessage, 'Post Process')        
        wx.CallAfter(pub.sendMessage, 'Enable Buttons')
        wx.CallAfter(pub.sendMessage, 'Join Thread')
        
    #end init
        
    #--------------------------------------------------------------------------        
    def take_PID_Data(self):
        """ Takes data from the PID and proceeds to a 
            function that checks the PID setpoints.
        """
        try: 
            # Take Data and time stamps:
            self.pidA = self.heaterA.get_pv()
            self.pidB = self.heaterB.get_pv()
            
            # Get the current setpoints on the PID:
            self.pidAset = float(self.heaterA.get_setpoint())
            self.pidBset = float(self.heaterB.get_setpoint())
        
        except exceptions.ValueError as VE:
            print(VE)
            # Take Data and time stamps:
            self.pidA = self.heaterA.get_pv()
            self.pidB = self.heaterB.get_pv()
            
            # Get the current setpoints on the PID:
            self.pidAset = float(self.heaterA.get_setpoint())
            self.pidBset = float(self.heaterB.get_setpoint())
            
        self.tpid = time.time() - self.start
        
        print "tpid: %.2f s\tpidA: %s C\tpidB: %s C" % (self.tpid, self.pidA, self.pidB)
        
        #check stability of PID
        if (len(self.recentPIDtime)<10):
            self.recentPIDA.append(self.pidA)
            self.recentPIDB.append(self.pidB)
            self.recentPIDtime.append(self.tpid)
        #end if
        else:
            self.recentPIDA.pop(0)
            self.recentPIDB.pop(0)
            self.recentPIDtime.pop(0)
            self.recentPIDA.append(self.pidA)
            self.recentPIDB.append(self.pidB)
            self.recentPIDtime.append(self.tpid)
            
            self.stabilityA = self.getStability(self.recentPIDA,self.recentPIDtime)
            self.stabilityB = self.getStability(self.recentPIDB,self.recentPIDtime)
            
            print "stabilityA: %.4f C/min" % (self.stabilityA*60)
            print "stabilityB: %.4f C/min" % (self.stabilityB*60)
            print "stability threshold: %.4f C/min" % (self.stability_threshold*60)
            self.updateGUI(stamp="Stability A", data=self.stabilityA*60)
            self.updateGUI(stamp="Stability B", data=self.stabilityB*60)
        #end else
        
        self.updateGUI(stamp="PID A", data=self.pidA)
        self.updateGUI(stamp="PID B", data=self.pidB)
        self.updateGUI(stamp="Time PID", data=self.tpid)
        
        self.updateGUI(stamp="PID A SP", data=self.pidAset)
        self.updateGUI(stamp="PID B SP", data=self.pidBset)
        
    #end def
    
    #--------------------------------------------------------------------------
    def getStability(self, temps, times):
        coeffs = np.polyfit(times, temps, 1)

        # Polynomial Coefficients
        results = coeffs.tolist()
        return results[0]
    #end def
    
    #--------------------------------------------------------------------------
    def check_status(self):
        if (np.abs(self.pidA-self.pidAset) < self.tolerance and  np.abs(self.pidB-self.pidBset) < self.tolerance ):
            self.tol = 'OK'
        #end if
            
        else:
            self.tol = 'NO'
            
        #end else
        
        if (self.stabilityA != '-' and self.stabilityB != '-'):
            if (np.abs(self.stabilityA) < self.stability_threshold and np.abs(self.stabilityB) < self.stability_threshold):
                self.stable = 'OK'
            #end if
            else:
                self.stable = 'NO'
        #end if
        else:
            self.stable = 'NO'

        #end else
        self.updateGUI(stamp="Status Bar", data=[self.tol, self.stable])
        
        if ( self.equil_time_left < 0 ):
            self.updateGUI(stamp="Status Bar", data='-mea')
        #end if
        else:
            self.updateGUI(stamp="Status Bar", data=str(self.equil_time_left) + 'mea')
    #end def
    
    #--------------------------------------------------------------------------
    def check_PID_setpoint(self):
        
        """ Function that requires that all conditions must be met to change 
            the setpoints. 
        """
                
        # These first several if statements check to make sure that the
        # temperature has reached an equilibrium.
            
        if (self.tol=='OK' and self.stable=='OK'):
            n = self.check_measurement_iterator        
            
            if n < len(measureList)-1:
                self.check_step(measureList[n], measureList[n+1])
            #end if
            
            elif n == len(measureList)-1:
                self.check_step(measureList[n], None)
            #end elif
            print "measurement iterator: %.0f\n" % (float(n))   
        #end if      
                
    #end def
    
    #--------------------------------------------------------------------------
    def check_step(self, step, nextStep):
        global abort_ID
        
        if (self.tol == 'OK' and self.stable=='OK'):
            
            if (self.hold == 'OFF'):
                self.hold = 'ON'
                if (self.oscillation_indicator == 0):
                    self.measurement_indicator = 'start'
                    self.updateGUI(stamp='Oscillation', data='start')
                    self.updateGUI(stamp='Measurement', data='ON')
                #end if
                elif (self.oscillation_indicator == 1):
                    self.measurement_indicator = '1/4'
                    self.updateGUI(stamp='Oscillation', data='1/4')
                #end elif
                elif (self.oscillation_indicator == 2):
                    self.measurement_indicator = '1/2'
                    self.updateGUI(stamp='Oscillation', data='1/2')
                #end elif
                elif (self.oscillation_indicator == 3):
                    self.measurement_indicator = '3/4'
                    self.updateGUI(stamp='Oscillation', data='3/4')   
                #end elif
                self.equil_timer = time.time()
                #end if
            #end if
            
            # if we reach the time for measurement to complete:
            if ( self.hold == 'ON'):
                
                self.equil_time_left = int(self.equil_time - ( time.time() - self.equil_timer ))
                
                if ( self.equil_time_left < 0 ):
                    
                    self.equil_time_left = '-'
                    self.hold = 'OFF'
                    
                    if (self.oscillation_indicator == 0):
                        if (step>150):
                            self.oscillation_indicator = 1
                            self.heaterA.set_setpoint(step)
                            self.heaterB.set_setpoint(step)
                        #end if
                        else:
                            self.oscillation_indicator = 2
                            self.heaterA.set_setpoint(step+oscillation/2)
                            self.heaterB.set_setpoint(step-oscillation/2)
                        #end else
                    #end if
                    elif (self.oscillation_indicator == 1):
                        self.oscillation_indicator = 2
                        self.heaterA.set_setpoint(step+oscillation/2)
                        self.heaterB.set_setpoint(step-oscillation/2)
                    #end elif
                    elif (self.oscillation_indicator == 2):
                        if (step>150):
                            self.oscillation_indicator = 3
                            self.heaterA.set_setpoint(step)
                            self.heaterB.set_setpoint(step)
                        #end if
                        else:
                            self.oscillation_indicator = 4
                            self.heaterA.set_setpoint(step-oscillation/2)
                            self.heaterB.set_setpoint(step+oscillation/2)
                        #end else
                    #end elif
                    elif (self.oscillation_indicator == 3):
                        self.oscillation_indicator = 4
                        self.heaterA.set_setpoint(step-oscillation/2)
                        self.heaterB.set_setpoint(step+oscillation/2)
                    #end elif
                    elif (self.oscillation_indicator == 4):
                        self.oscillation_indicator = 0
                        self.measurement_indicator = 'stop'
                        self.updateGUI(stamp='Oscillation', data='end')
                        self.updateGUI(stamp='Measurement', data='OFF')
                    
                        # if we're on the last element of the list:
                        if ( self.check_measurement_iterator == len(measureList)-1 ):
                            abort_ID = 1
                        #end if
                        else: 
                            self.heaterA.set_setpoint(nextStep-oscillation/2)
                            self.heaterB.set_setpoint(nextStep+oscillation/2)

                            self.check_measurement_iterator = self.check_measurement_iterator + 1
                        #end else
                    #end elif
                    
                #end if
            #end if
        #end if
    #end def
    
    #--------------------------------------------------------------------------    
    def safety_check(self):
        global maxLimit
        global abort_ID
        
        if float(self.pidA) > maxLimit or float(self.pidB) > maxLimit:
            abort_ID = 1
            
            
        
    #end def
    
    #--------------------------------------------------------------------------
    def seebeck_data_measurement(self):
        # Takes and writes to file the data on the Keithley
        # The only change between blocks like this one is the specific
        # channel on the Keithley that is being measured.
        self.tempA = self.k2700.fetch(tempAChannel)
        self.ttempA = time.time() - self.start
        self.updateGUI(stamp="Time Temp A", data=float(self.ttempA))
        self.updateGUI(stamp="Temp A", data=float(self.tempA))
        print "ttempA: %.2f s\ttempA: %s C" % (self.ttempA, self.tempA) 
        
        time.sleep(0.2)
        # The rest is a repeat of the above code, for different
        # channels.
        
        self.tempB = self.k2700.fetch(tempBChannel)
        self.ttempB = time.time() - self.start
        self.updateGUI(stamp="Time Temp B", data=float(self.ttempB))
        self.updateGUI(stamp="Temp B", data=float(self.tempB))
        print "ttempB: %.2f s\ttempB: %s C" % (self.ttempB, self.tempB) 
        
        time.sleep(0.2)
        
        self.highV_raw = self.k2700.fetch(highVChannel)
        self.highV_raw = float(self.highV_raw)*10**6 # uV
        self.highV_corrected = self.voltage_Correction(float(self.highV_raw), 'high')
        self.thighV = time.time() - self.start
        self.updateGUI(stamp="Time High Voltage", data=float(self.thighV))
        self.updateGUI(stamp="High Voltage", data=float(self.highV_corrected))
        print "thighV: %.2f s\thighV_raw: %f uV\thighV_corrected: %f uV" % (self.thighV, self.highV_raw, self.highV_corrected)
        
        time.sleep(0.2)

        self.lowV_raw = self.k2700.fetch(lowVChannel)
        self.lowV_raw = float(self.lowV_raw)*10**6 # uV
        self.lowV_corrected = self.voltage_Correction(float(self.lowV_raw), 'low')
        self.tlowV = time.time() - self.start
        self.updateGUI(stamp="Time Low Voltage", data=float(self.tlowV))
        self.updateGUI(stamp="Low Voltage", data=float(self.lowV_corrected))
        print "tlowV: %.2f s\tlowV_raw: %f uV\tlowV_corrected: %f uV" % (self.tlowV, self.lowV_raw, self.lowV_corrected)
        
        time.sleep(0.2)
        
        # Symmetrize the measurement and repeat in reverse
        
        self.lowV_raw2 = self.k2700.fetch(lowVChannel)
        self.lowV_raw2 = float(self.lowV_raw2)*10**6 # uV
        self.lowV_corrected2 = self.voltage_Correction(float(self.lowV_raw2), 'low')
        self.tlowV2 = time.time() - self.start
        self.updateGUI(stamp="Time Low Voltage", data=float(self.tlowV2))
        self.updateGUI(stamp="Low Voltage", data=float(self.lowV_corrected2))
        print "tlowV: %.2f s\tlowV_raw: %f uV\tlowV_corrected: %f uV" % (self.tlowV2, self.lowV_raw2, self.lowV_corrected2)
        
        time.sleep(0.2)
        
        self.highV_raw2 = self.k2700.fetch(highVChannel)
        self.highV_raw2 = float(self.highV_raw2)*10**6 # uV
        self.highV_corrected2 = self.voltage_Correction(float(self.highV_raw2), 'high')
        self.thighV2 = time.time() - self.start
        self.updateGUI(stamp="Time High Voltage", data=float(self.thighV2))
        self.updateGUI(stamp="High Voltage", data=float(self.highV_corrected2))
        print "thighV: %.2f s\thighV_raw: %f uV\thighV_corrected: %f uV" % (self.thighV2, self.highV_raw2, self.highV_corrected2)
        
        time.sleep(0.2)

        self.tempB2 = self.k2700.fetch(tempBChannel)
        self.ttempB2 = time.time() - self.start
        self.updateGUI(stamp="Time Temp B", data=float(self.ttempB2))
        self.updateGUI(stamp="Temp B", data=float(self.tempB2))
        print "ttempB: %.2f s\ttempB: %s C" % (self.ttempB2, self.tempB2)
        
        time.sleep(0.2)
        
        self.tempA2 = self.k2700.fetch(tempAChannel)
        self.ttempA2 = time.time() - self.start
        self.updateGUI(stamp="Time Temp A", data=float(self.ttempA2))
        self.updateGUI(stamp="Temp A", data=float(self.tempA2))
        print "ttempA: %.2f s\ttempA: %s C" % (self.ttempA2, self.tempA2)
        
    #end def
    
    #--------------------------------------------------------------------------
    def voltage_Correction(self, raw_data, side):
        ''' raw_data must be in uV '''
        
        # Kelvin conversion for polynomial correction.
        if self.ttempA > self.ttempA2:
            tempA = float(self.tempA) + 273.15
        else:
            tempA = float(self.tempA2) + 273.15 
        if self.ttempB > self.ttempB2:
            tempB = float(self.tempB) + 273.15
        else:
            tempB = float(self.tempB2) + 273.15   
        
        self.dT = tempA - tempB
        avgT = (tempA + tempB)/2
        
        # Correction for effect from Thermocouple Seebeck
        out = self.alpha(avgT, side)*self.dT - raw_data
        
        return out
        
    #end def
     
    #--------------------------------------------------------------------------
    def alpha(self, x, side):
        ''' x = avgT 
            alpha in uV/K
        '''
        
        if tc_type == "k-type":
            
            ### If Chromel, taken from Chromel_Seebeck.txt
            if side == 'high':
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
            elif side == 'low':
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
        print('Write data to file')
        pfile.write("%.2f, %.1f, %.1f \n" % (self.tpid, self.pidA, self.pidB) )
        
        myfile.write('%.2f,%s,%.2f,%s,%.2f,%f,%.2f,%f,' % (self.ttempA, self.tempA, self.ttempB, self.tempB,self.thighV, self.highV_raw, self.tlowV, self.lowV_raw) )
        myfile.write( '%.2f,%f,%.2f,%f,%.2f,%s,%.2f,%s' % (self.tlowV2, self.lowV_raw2, self.thighV2, self.highV_raw2, self.ttempB2, self.tempB2, self.ttempA2, self.tempA2) )
        
        
        # indicates whether an oscillation has started or stopped
        if self.measurement_indicator == 'start':
            myfile.write(',Start Oscillation')
            self.measurement_indicator = 'none'
            
        elif self.measurement_indicator == '1/2':
            myfile.write(',Half-way')
            self.measurement_indicator = 'none'
            
        elif self.measurement_indicator == 'stop':
            myfile.write(',Stop Oscillation')
            self.measurement_indicator = 'none'
            
        elif self.measurement_indicator == '1/4':
            myfile.write(',1/4-way')
            self.measurement_indicator = 'none'
        
        elif self.measurement_indicator == '3/4':
            myfile.write(',3/4-way')
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
    def save_files(self):
        ''' Function saving the files after the data acquisition loop has been
            exited. 
        '''
        
        print('Save Files')
        
        global dataFile
        global finaldataFile
        global myfile
        global pfile
        
        stop = time.time()
        end = datetime.now() # End time
        totalTime = stop - self.start # Elapsed Measurement Time (seconds)
        
        myfile.close() # Close the file
        pfile.close()
        
        myfile = open(dataFile, 'r') # Opens the file for Reading
        contents = myfile.readlines() # Reads the lines of the file into python set
        myfile.close()
        
        # Adds elapsed measurement time to the read file list
        endStr = 'end time: %s \nelapsed measurement time: %s seconds \n \n' % (str(end), str(totalTime))
        contents.insert(1, endStr) # Specify which line and what value to insert
        # NOTE: First line is line 0
        
        # Writes the elapsed measurement time to the final file
        myfinalfile = open(finaldataFile,'w')
        contents = "".join(contents)
        myfinalfile.write(contents)
        myfinalfile.close()
        
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
        box. Allows to switch between an automatic mode and a 
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
        global equil_time
        global oscillation
        global stability_threshold
        
        self.oscillation = oscillation
        self.tolerance = tolerance
        self.stability_threshold = stability_threshold*60
        self.equil_time = equil_time/60
        
        
        self.create_title("User Panel") # Title
        
        self.celsius = u"\u2103"
        self.font2 = wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.NORMAL)
        
        self.oscillation_control() # Oscillation range control
        self.tolerance_control() # PID tolerance level Control
        self.stability_control() # PID stability threshold control
        self.equilibrium_control() #PID equilibrium time Control

        
        self.measurementListBox()
        self.maxLimit_label()
        
        self.linebreak1 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak2 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak3 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.linebreak4 = wx.StaticLine(self, pos=(-1,-1), size=(600,1), style=wx.LI_HORIZONTAL)
        
        self.run_stop() # Run and Stop buttons
        
        self.create_sizer() # Set Sizer for panel
        
        pub.subscribe(self.post_process_data, "Post Process")
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
        global measureList
        global dataFile
        global pidFile
        global finaldataFile
        global myfile
        global pfile
        global i
        global n
        global indicator
        global abort_ID
        global oscillation
        global tolerance
        global highV_list, thighV_list, lowV_list, tlowV_list
        global tempA_list, ttempA_list, tempB_list, ttempB_list
        global pidA_list, pidB_list, tpid_list
        
        measureList = [None]*self.listbox.GetCount()
        for k in xrange(self.listbox.GetCount()):
            measureList[k] = int(self.listbox.GetString(k))
        #end for
            
        if len(measureList) > 0:
            
            try:
                global k2700, heaterA, heaterB
                
                self.name_folder()
                
                if self.run_check == wx.ID_OK:
                    

                    
                    begin = datetime.now() # Current date and time
                    file = dataFile # creates a data file
                    myfile = open(dataFile, 'w') # opens file for writing/overwriting
                    myfile.write('start time: ' + str(begin) + '\n')
                    myfile.write('time (s),tempA (C),time (s),tempB (C),time (s),rawVhigh (uV),time (s),rawVlow (uV),Time (s),rawVlow2 (uV),time (s),rawVhigh2 (uV),time (s),tempB2 (C),time (s),tempA2 (C),indicator\n')
                    file = pidFile # creates a data file
                    pfile = open(pidFile, 'w') # opens file for writing/overwriting
                    pfile.write('start Time: ' + str(begin) + '\n')
                    pfile.write('time (s),pidA (C),pidB (C)\n')               
                    
                    # Global variables:

                    abort_ID = 0
                    
                    # Placers for the GUI plots:

                    highV_list = []
                    thighV_list = []
                    lowV_list = []
                    tlowV_list = []
                    tempA_list = []
                    ttempA_list = []
                    tempB_list = []
                    ttempB_list = []
                    pidA_list = []
                    pidB_list = []
                    tpid_list = []

                    #start the threading process
                    thread = ProcessThreadRun()
                    
                    self.btn_osc.Disable()
                    self.btn_tol.Disable()
                    self.btn_equil_time.Disable()
                    self.btn_stability_threshold.Disable()
                    self.btn_new.Disable()
                    self.btn_ren.Disable()
                    self.btn_dlt.Disable()
                    self.btn_clr.Disable()
                    self.btn_check.Disable()
                    self.btn_stop.Enable()
                    
                #end if
                
            #end try
                
            except visa.VisaIOError:
                wx.MessageBox("Not all instruments are connected!", "Error")
            #end except
                
        else:
            wx.MessageBox('No measurements were specified!', 'Error', wx.OK | wx.ICON_INFORMATION)
        #end else
            
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
        try:
            self.oscillation = self.edit_osc.GetValue()
            if float(self.oscillation) > maxLimit:
                self.oscillation = str(maxLimit)
            self.text_osc.SetLabel(self.oscillation)
            oscillation = float(self.oscillation)
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
        self.btn_stability_threshold = btn_stability_threshold = wx.Button(self.stability_threshold_Panel, label="save", size=(40, -1))
        text_guide_stability_threshold = wx.StaticText(self.stability_threshold_Panel, label='The change in the PID must\nbe below this threshold before\na measurement will begin.')

        btn_stability_threshold.Bind(wx.EVT_BUTTON, self.save_stability_threshold)

        hbox.Add((0, -1))
        hbox.Add(text_stability_threshold, 0, wx.LEFT, 5)
        hbox.Add(edit_stability_threshold, 0, wx.LEFT, 40)
        hbox.Add(btn_stability_threshold, 0, wx.LEFT, 5)
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
    def equilibrium_control(self):
        global equil_time
        self.equilPanel = wx.Panel(self, -1)        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.label_equil_time = wx.StaticText(self, label="Equilibrium Time (min):")
        self.text_equil_time = text_equil_time = wx.StaticText(self.equilPanel, label=str(self.equil_time)+' min')
        text_equil_time.SetFont(self.font2)
        self.edit_equil_time = edit_equil_time = wx.TextCtrl(self.equilPanel, size=(40, -1))
        self.btn_equil_time = btn_equil_time = wx.Button(self.equilPanel, label="save", size=(40, -1))
        text_guide_equil = wx.StaticText(self.equilPanel, label="The equilibrium time to\nhold at set points\nduring measurements.")
        
        btn_equil_time.Bind(wx.EVT_BUTTON, self.save_equilibrium)
        
        hbox.Add((0, -1))
        hbox.Add(text_equil_time, 0, wx.LEFT, 5)
        hbox.Add(edit_equil_time, 0, wx.LEFT, 40)
        hbox.Add(btn_equil_time, 0, wx.LEFT, 5)
        hbox.Add(text_guide_equil, 0, wx.LEFT, 5)
        
        self.equilPanel.SetSizer(hbox)
        
    #end def  
    
    #--------------------------------------------------------------------------
    def save_equilibrium(self, e):
        global equil_time
        try:
            self.equil_time = self.edit_equil_time.GetValue()
            self.text_equil_time.SetLabel(self.equil_time)
            equil_time = float(self.equil_time)*60
        
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
        """ Sets user input to only allow a maximum temperature. """
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
      
        sizer = wx.GridBagSizer(9,2)
        sizer.Add(self.titlePanel, (0, 1), span=(1,2), flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_osc, (1, 1))
        sizer.Add(self.oscPanel, (1, 2))
     
        sizer.Add(self.label_tol, (2,1))
        sizer.Add(self.tolPanel, (2, 2))
        sizer.Add(self.label_stability_threshold, (3,1))
        sizer.Add(self.stability_threshold_Panel, (3, 2))
        sizer.Add(self.label_equil_time, (4,1))
        sizer.Add(self.equilPanel, (4,2))

        sizer.Add(self.label_measurements, (5,1))
        sizer.Add(self.measurementPanel, (5, 2))
        sizer.Add(self.maxLimit_Panel, (6, 1), span=(1,2))
        sizer.Add(self.linebreak4, (7,1),span = (1,2))
        sizer.Add(self.run_stopPanel, (8,1),span = (1,2), flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        self.SetSizer(sizer)
        
    #end def
    
    #--------------------------------------------------------------------------
    def post_process_data(self):
        global filePath, finaldataFile, tc_type
        
        try:
            # Post processing:
            Seebeck_Processing_v4.create_processed_files(filePath, finaldataFile, tc_type)
        except IndexError:
            wx.MessageBox('Not enough data for post processing to occur. \n\nIt is likely that we did not even complete any oscillations.', 'Error', wx.OK | wx.ICON_INFORMATION)
   #end def
    
    #--------------------------------------------------------------------------    
    def enable_buttons(self):
        self.btn_check.Enable()
        self.btn_run.Enable()
        self.btn_osc.Enable()
        self.btn_tol.Enable()
        self.btn_equil_time.Enable()
        self.btn_stability_threshold.Enable()
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
        self.highV=str(0)
        self.lowV = str(0)
        self.tA=str(30)
        self.tB=str(30)
        self.pA=str(30)
        self.pB=str(30)
        self.pAset=str(30)
        self.pBset=str(30)
        self.stabilityA = '-'
        self.stabilityB = '-'
        self.dT = str(float(self.tA)-float(self.tB))
        self.mea = '-'
        self.osc = '-'
        
        self.create_title("Status Panel")
        self.linebreak1 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.create_status()
        self.linebreak2 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        
        self.linebreak3 = wx.StaticLine(self, pos=(-1,-1), size=(1,300), style=wx.LI_VERTICAL)
        
        # Updates from running program
        pub.subscribe(self.OnTime, "Time High Voltage")
        pub.subscribe(self.OnTime, "Time Low Voltage")
        pub.subscribe(self.OnTime, "Time Temp A")
        pub.subscribe(self.OnTime, "Time Temp B")
        
        pub.subscribe(self.OnHighVoltage, "High Voltage")
        pub.subscribe(self.OnLowVoltage, "Low Voltage")
        pub.subscribe(self.OnTempA, "Temp A")
        pub.subscribe(self.OnTempB, "Temp B")
        pub.subscribe(self.OnPIDA, "PID A")
        pub.subscribe(self.OnPIDB, "PID B")
        pub.subscribe(self.OnPIDAset, "PID A SP")
        pub.subscribe(self.OnPIDBset, "PID B SP")
        pub.subscribe(self.OnStabilityA, "Stability A")
        pub.subscribe(self.OnStabilityB, "Stability B")
        pub.subscribe(self.OnMeasurement, 'Measurement')   
        pub.subscribe(self.OnOscillation, 'Oscillation')
        
        # Updates from inital check
        pub.subscribe(self.OnHighVoltage, "High Voltage Status")
        pub.subscribe(self.OnLowVoltage, "Low Voltage Status")
        pub.subscribe(self.OnTempA, "Temp A Status")
        pub.subscribe(self.OnTempB, "Temp B Status")
        pub.subscribe(self.OnPIDA, "PID A Status")
        pub.subscribe(self.OnPIDB, "PID B Status")
        pub.subscribe(self.OnPIDAset, "PID A SP Status")
        pub.subscribe(self.OnPIDBset, "PID B SP Status")
        
        #self.update_values()
        
        self.create_sizer()
        
    #end init
    
    #--------------------------------------------------------------------------
    def OnHighVoltage(self, msg):
        self.highV = '%.1f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnLowVoltage(self, msg):
        self.lowV = '%.1f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnTempA(self, msg):
        self.tA = '%.1f'%(float(msg)) 
        self.dT = str(float(self.tA)-float(self.tB)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnTempB(self, msg):
        self.tB = '%.1f'%(float(msg)) 
        self.dT = str(float(self.tA)-float(self.tB)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnPIDA(self, msg):
        self.pA = '%.1f'%(float(msg))
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnPIDB(self, msg):
        self.pB = '%.1f'%(float(msg)) 
        self.update_values()  
    #end def
    
    #--------------------------------------------------------------------------
    def OnPIDAset(self, msg):
        self.pAset = '%.1f'%(float(msg))  
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnPIDBset(self, msg):
        self.pBset = '%.1f'%(float(msg))  
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnStabilityA(self, msg):
        self.stabilityA = '%.3f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnStabilityB(self, msg):
        self.stabilityB = '%.3f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnMeasurement(self, msg):
        self.mea = msg  
        self.update_values()    
    #end def

    #--------------------------------------------------------------------------
    def OnOscillation(self, msg):
        self.osc = msg  
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
        self.label_highV = wx.StaticText(self, label="high voltage ("+self.mu+"V):")
        self.label_highV.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_lowV = wx.StaticText(self, label="low voltage ("+self.mu+"V):")
        self.label_lowV.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_tA = wx.StaticText(self, label="temp A ("+self.celsius+"):")
        self.label_tA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_tB = wx.StaticText(self, label="temp B ("+self.celsius+"):")
        self.label_tB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_pA = wx.StaticText(self, label="pid A ("+self.celsius+"):")
        self.label_pA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_pB = wx.StaticText(self, label="pid B ("+self.celsius+"):")
        self.label_pB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_pAset = wx.StaticText(self, label="pid A setpoint ("+self.celsius+"):")
        self.label_pAset.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_pBset = wx.StaticText(self, label="pid B setpoint ("+self.celsius+"):")
        self.label_pBset.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_stabilityA = wx.StaticText(self, label="stability A ("+self.celsius+ "/min):")
        self.label_stabilityA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_stabilityB = wx.StaticText(self, label="stability B ("+self.celsius+ "/min):")
        self.label_stabilityB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_dT = wx.StaticText(self, label=self.delta+"T ("+self.celsius+"):")
        self.label_dT.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_mea = wx.StaticText(self, label="seebeck measurement")
        self.label_mea.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_osc = wx.StaticText(self, label="oscillation point")
        self.label_osc.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        
        self.ctimecurrent = wx.StaticText(self, label=self.ctime)
        self.ctimecurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.tcurrent = wx.StaticText(self, label=self.t)
        self.tcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.highVcurrent = wx.StaticText(self, label=self.highV)
        self.highVcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.lowVcurrent = wx.StaticText(self, label=self.lowV)
        self.lowVcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.tAcurrent = wx.StaticText(self, label=self.tA)
        self.tAcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.tBcurrent = wx.StaticText(self, label=self.tB)
        self.tBcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.pAcurrent = wx.StaticText(self, label=self.pA)
        self.pAcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.pBcurrent = wx.StaticText(self, label=self.pB)
        self.pBcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.pAsetcurrent = wx.StaticText(self, label=self.pAset)
        self.pAsetcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.pBsetcurrent = wx.StaticText(self, label=self.pBset)
        self.pBsetcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.stabilityAcurrent = wx.StaticText(self, label=self.stabilityA)
        self.stabilityAcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.stabilityBcurrent = wx.StaticText(self, label=self.stabilityB)
        self.stabilityBcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.dTcurrent = wx.StaticText(self, label=self.dT)
        self.dTcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.meacurrent = wx.StaticText(self, label=self.mea)
        self.meacurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.osccurrent = wx.StaticText(self, label=self.osc)
        self.osccurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        
        
    #end def
        
    #-------------------------------------------------------------------------- 
    def update_values(self):
        self.ctimecurrent.SetLabel(self.ctime)
        self.tcurrent.SetLabel(self.t)
        self.highVcurrent.SetLabel(self.highV)
        self.lowVcurrent.SetLabel(self.lowV)
        self.tAcurrent.SetLabel(self.tA)
        self.tBcurrent.SetLabel(self.tB)
        self.pAcurrent.SetLabel(self.pA)
        self.pBcurrent.SetLabel(self.pB)
        self.pAsetcurrent.SetLabel(self.pAset)
        self.pBsetcurrent.SetLabel(self.pBset)
        self.stabilityAcurrent.SetLabel(self.stabilityA)
        self.stabilityBcurrent.SetLabel(self.stabilityB)
        self.dTcurrent.SetLabel(self.dT)
        self.meacurrent.SetLabel(self.mea)
        self.osccurrent.SetLabel(self.osc)
    #end def
       
    #--------------------------------------------------------------------------
    def create_sizer(self):    
        sizer = wx.GridBagSizer(18,2)
        
        sizer.Add(self.titlePanel, (0, 0), span = (1,2), border=5, flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.linebreak1,(1,0), span = (1,2))
        
        sizer.Add(self.label_ctime, (2,0))
        sizer.Add(self.ctimecurrent, (2, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_t, (3,0))
        sizer.Add(self.tcurrent, (3, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        sizer.Add(self.label_highV, (4, 0))
        sizer.Add(self.highVcurrent, (4, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_lowV, (5,0))
        sizer.Add(self.lowVcurrent, (5,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
          
        sizer.Add(self.label_tA, (6,0))
        sizer.Add(self.tAcurrent, (6,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_pA, (7,0))
        sizer.Add(self.pAcurrent, (7,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_pAset, (8,0))
        sizer.Add(self.pAsetcurrent, (8,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_stabilityA, (9,0))
        sizer.Add(self.stabilityAcurrent, (9, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        sizer.Add(self.label_tB, (10,0))
        sizer.Add(self.tBcurrent, (10,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_pB, (11,0))
        sizer.Add(self.pBcurrent, (11,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_pBset, (12,0))
        sizer.Add(self.pBsetcurrent, (12,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_stabilityB, (13,0))
        sizer.Add(self.stabilityBcurrent, (13, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        sizer.Add(self.label_dT, (14,0))
        sizer.Add(self.dTcurrent, (14,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_mea, (15,0))
        sizer.Add(self.meacurrent, (15,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_osc, (16,0))
        sizer.Add(self.osccurrent, (16,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        sizer.Add(self.linebreak2, (17,0), span = (1,2))
        
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
        
        global thighV_list
        global highV_list
        global tlowV_list
        global lowV_list
        
        self.create_title("Voltage Panel")
        self.init_plot()
        self.canvas = FigureCanvasWxAgg(self, -1, self.figure)
        self.create_control_panel()
        self.create_sizer()
        
        pub.subscribe(self.OnHighVoltage, "High Voltage")
        pub.subscribe(self.OnHighVTime, "Time High Voltage")
        pub.subscribe(self.OnLowVoltage, "Low Voltage")
        pub.subscribe(self.OnLowVTime, "Time Low Voltage")
        
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
    def OnHighVoltage(self, msg):
        self.highV = float(msg)
        highV_list.append(self.highV)
        thighV_list.append(self.thighV)   
    #end def

    #--------------------------------------------------------------------------
    def OnHighVTime(self, msg):
        self.thighV = float(msg)   
        
    #end def

    #--------------------------------------------------------------------------
    def OnLowVoltage(self, msg):
        self.lowV = float(msg)
        lowV_list.append(self.lowV)
        tlowV_list.append(self.tlowV)    
    #end def

    #--------------------------------------------------------------------------
    def OnLowVTime(self, msg):
        self.tlowV = float(msg)
           
        
    #end def

    #--------------------------------------------------------------------------
    def init_plot(self):
        self.dpi = 100
        self.colorH = 'g'
        self.colorL = 'y'
        
        self.figure = Figure((6,2), dpi=self.dpi)
        self.subplot = self.figure.add_subplot(111)
        self.lineH, = self.subplot.plot(thighV_list,highV_list, color=self.colorH, linewidth=1)
        self.lineL, = self.subplot.plot(tlowV_list,lowV_list, color=self.colorL, linewidth=1)
        
        self.legend = self.figure.legend( (self.lineH, self.lineL), (r"$V_{high}$",r"$V_{low}$"), (0.15,0.7),fontsize=8)
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
            xmax = max(thighV_list+tlowV_list)
        else:
            xmax = float(self.xmax_control.manual_value())    
        if self.xmin_control.is_auto():            
            xmin = 0
        else:
            xmin = float(self.xmin_control.manual_value())
        if self.ymin_control.is_auto():
            minV = min(highV_list+lowV_list)
            ymin = minV - abs(minV)*0.3
        else:
            ymin = float(self.ymin_control.manual_value())
        if self.ymax_control.is_auto():
            maxV = max(highV_list+lowV_list)
            ymax = maxV + abs(maxV)*0.3
        else:
            ymax = float(self.ymax_control.manual_value())
        
        
        self.subplot.set_xlim([xmin, xmax])
        self.subplot.set_ylim([ymin, ymax])
        
        pylab.setp(self.subplot.get_xticklabels(), fontsize=8)
        pylab.setp(self.subplot.get_yticklabels(), fontsize=8)
        
        self.lineH, = self.subplot.plot(thighV_list,highV_list, color=self.colorH, linewidth=1)
        self.lineL, = self.subplot.plot(tlowV_list,lowV_list, color=self.colorL, linewidth=1)
        
        return (self.lineH, self.lineL)
        #return (self.subplot.plot( thighV_list, highV_list, color=self.colorH, linewidth=1),
            #self.subplot.plot( tlowV_list, lowV_list, color=self.colorL, linewidth=1))
        
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
        
        global ttempA_list
        global tempA_list
        global ttempB_list
        global tempB_list
        global tpid_list
        global pidA_list
        global pidB_list
        
        self.create_title("Temperature Panel")
        self.init_plot()
        self.canvas = FigureCanvasWxAgg(self, -1, self.figure)
        self.create_control_panel()
        self.create_sizer()
        
        pub.subscribe(self.OnTimeTempA, "Time Temp A")
        pub.subscribe(self.OnTempA, "Temp A")
        pub.subscribe(self.OnTimeTempB, "Time Temp B")
        pub.subscribe(self.OnTempB, "Temp B")
        pub.subscribe(self.OnTimePID, "Time PID")
        pub.subscribe(self.OnPIDA, "PID A")
        pub.subscribe(self.OnPIDB, "PID B")
        
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
    def OnTimeTempA(self, msg):
        self.ttA = float(msg)   
    #end def
        
    #--------------------------------------------------------------------------
    def OnTempA(self, msg):
        self.tA = float(msg)
        tempA_list.append(self.tA)
        ttempA_list.append(self.ttA)    
    #end def
    
    #--------------------------------------------------------------------------
    def OnTimeTempB(self, msg):
        self.ttB = float(msg)    
    #end def
        
    #--------------------------------------------------------------------------
    def OnTempB(self, msg):
        self.tB = float(msg)
        tempB_list.append(self.tB) 
        ttempB_list.append(self.ttB)   
    #end def
    
    #--------------------------------------------------------------------------
    def OnTimePID(self, msg):
        self.tpid = float(msg)  
        tpid_list.append(self.tpid)
        pidA_list.append(self.pA) 
        pidB_list.append(self.pB)
    #end def
        
    #--------------------------------------------------------------------------
    def OnPIDA(self, msg):
        self.pA = float(msg)   
    #end def
        
    #--------------------------------------------------------------------------
    def OnPIDB(self, msg):
        self.pB = float(msg)    
    #end def

    #--------------------------------------------------------------------------
    def init_plot(self):
        self.dpi = 100
        self.colorTA = 'r'
        self.colorTB = 'b'
        self.colorPA = 'm'
        self.colorPB = 'c'
        
        self.figure = Figure((6,2), dpi=self.dpi)
        self.subplot = self.figure.add_subplot(111)
        
        self.lineTA, = self.subplot.plot(ttempA_list,tempA_list, color=self.colorTA, linewidth=1)
        self.lineTB, = self.subplot.plot(ttempB_list,tempB_list, color=self.colorTB, linewidth=1)
        self.linePA, = self.subplot.plot(tpid_list,pidA_list, color=self.colorPA, linewidth=1)
        self.linePB, = self.subplot.plot(tpid_list,pidB_list, color=self.colorPB, linewidth=1)
        
        self.legend = self.figure.legend( (self.lineTA, self.linePA, self.lineTB, self.linePB), (r"$T_A$ (sample)",r"$T_A$ (PID)",r"$T_B$ (sample)",r"$T_B$ (PID)"), (0.15,0.50),fontsize=8)
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
            xmax = max(ttempA_list+ttempB_list+tpid_list)
        else:
            xmax = float(self.xmax_control.manual_value())    
        if self.xmin_control.is_auto():            
            xmin = 0
        else:
            xmin = float(self.xmin_control.manual_value())
        if self.ymin_control.is_auto():
            ymin = 0
        else:
            ymin = float(self.ymin_control.manual_value())
        if self.ymax_control.is_auto():
            maxT = max(tempA_list+tempB_list+pidA_list+pidB_list)
            ymax = maxT + abs(maxT)*0.3
        else:
            ymax = float(self.ymax_control.manual_value())
        
        self.subplot.set_xlim([xmin, xmax])
        self.subplot.set_ylim([ymin, ymax])
        
        pylab.setp(self.subplot.get_xticklabels(), fontsize=8)
        pylab.setp(self.subplot.get_yticklabels(), fontsize=8)
        
        self.lineTA, = self.subplot.plot(ttempA_list,tempA_list, color=self.colorTA, linewidth=1)
        self.lineTB, = self.subplot.plot(ttempB_list,tempB_list, color=self.colorTB, linewidth=1)
        self.linePA, = self.subplot.plot(tpid_list,pidA_list, color=self.colorPA, linewidth=1)
        self.linePB, = self.subplot.plot(tpid_list,pidB_list, color=self.colorPB, linewidth=1)
        
        return (self.lineTA, self.lineTB, self.linePA, self.linePB)
        
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
        self.statusbar.SetFieldsCount(10)
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
        pidTol_text = wx.StaticText(self.statusbar, -1, "Within PID Tolerance:")
        self.width2 = pidTol_text.GetRect().width + self.space_between
        
        self.indicator_tol = wx.StaticText(self.statusbar, -1, "-")
        self.width3 = 25
        
        # Stability Threshold:
        stableThresh_text = wx.StaticText(self.statusbar, -1, "Within Stability Threshold:")
        self.width4 = stableThresh_text.GetRect().width + 5
        
        self.indicator_stable = wx.StaticText(self.statusbar, -1, "-")
        self.width5 = self.width3
        
        # Equilibrium Time:
        equil_time_text = wx.StaticText(self.statusbar, -1, "Time Until Equilibrium Complete:")
        self.width6 = equil_time_text.GetRect().width + self.space_between
        
        self.indicator_equil_time = wx.StaticText(self.statusbar, -1, "-")
        self.width7 = 40
        
        # Placer 2:
        placer2 = wx.StaticText(self.statusbar, -1, " ")
        
        # Version:
        version_label = wx.StaticText(self.statusbar, -1, "Version: %s" % version)
        self.width8 = version_label.GetRect().width + self.space_between
        
        # Set widths of each piece of the status bar:
        self.statusbar.SetStatusWidths([self.width0, 50, self.width2, self.width3, self.width4, self.width5, self.width6, self.width7, -1, self.width8])
        
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
        
        # Equilibrium Time:
        self.statusbar.AddWidget(equil_time_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        self.statusbar.AddWidget(self.indicator_equil_time, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
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
                
        # Measurement Timer:
        elif string[-3:] == 'mea':
            self.indicator_equil_time.SetLabel(string[:-3] + ' (s)')
            
        #end elif
            
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