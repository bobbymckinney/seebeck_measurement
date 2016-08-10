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

# For post processing:
import Seebeck_Processing_v3

#==============================================================================
version = '2.1 2015-03-30)'

# Keeps Windows from complaining that the port is already open:
modbus.CLOSE_PORT_AFTER_EACH_CALL = True

APP_EXIT = 1 # id for File\Quit
# ids for measurement List Box
ID_NEW = 1
ID_CHANGE = 2
ID_CLEAR = 3
ID_DELETE = 4

# placer for directory
filePath = ''

# Naming a data file:
dataFile = 'Data_Backup.txt'
finaldataFile = 'Data.txt'
pidFile = 'Data_pid.txt'

# Placeholders for files to be created
myfile = "global file"
pfile = "global file"

tc_type = "k-type" # Set the thermocouple type in order to use the correct voltage correction

equil_tolerance = 1 # PID temp must not change by this value for a set time in order to reach an equilibrium
equil_time = 100 # How many measurements until the PID will change after reaching an equilibrium point
tolerance = '5' # This must be set to at least oscillation/2
oscillation = '8' # Degree range that the PID will oscillate in
measureList = []

maxLimit = 600 # Restricts the user to a max temperature

indicator = 'none' # Used to indicate that an oscillation has started or stopped
i = 0 # For Take_Data.check_step()
n = 0 # Iterator in order to check each step individually, only checks one step
      #     at a time.

abort_ID = 0 # For stopping the process

# Placers for the GUI plots:
highV_list = [0]
thighV_list = [0]
lowV_list=[0]
tlowV_list = [0]
tempA_list = [0]
ttempA_list = [0]
tempB_list = [0]
ttempB_list = [0]
pidA_list = [0]
tpidA_list = [0]
pidB_list = [0]
tpidB_list = [0]

"""
Keithley Setup:
"""
# Channels corresponding to switch card:
tempAChannel = '109'
tempBChannel = '110'
highVChannel = '107'
lowVChannel = '108'

#ResourceManager for visa instrument control
ResourceManager = visa.ResourceManager()

# Set placers for instrument ports to be defined when the program starts:
k2700 = ''
heaterA = ''
heaterB = ''

###############################################################################
class Keithley_2700:
    """ 
    Provides definitions for Keithley operation. 
    """
    
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
class FakeKeithley_2700:
    """ 
    Provides definitions for Keithley operation. 
    """
    
    #--------------------------------------------------------------------------
    def __init__(self):
        self.temp = 200
        
    #end init
    
    #--------------------------------------------------------------------------
    def fetch(self, channel):
        """ 
        Scan the channel and take a reading 
        """
        if channel == tempAChannel or channel==tempBChannel:
            data = str(self.temp*np.random.random())
            return str(data) # Fetches Reading
        else:
            data = str(np.random.random()*10**-4)
            return str(data)
            
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
class FakePID:
    
    #--------------------------------------------------------------------------
    def __init__(self):
        #omegacn7500.OmegaCN7500.__init__(self, portname, slaveaddress)
        self.setpoint = 400
        
    def get_pv(self):
        return self.setpoint/2*np.random.random()+200
        
    def get_setpoint(self):
        return self.setpoint
    
    def set_setpoint(self,sp):
        self.setpoint = sp

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
        
        
        self.k2700.openAllChannels
        # Define the type of measurement for the channels we are looking at:
        self.k2700.ctrl.write(":SENSe1:TEMPerature:TCouple:TYPE K") # Set ThermoCouple type
        self.k2700.ctrl.write(":SENSe1:FUNCtion 'TEMPerature', (@ 109,110)")
        self.k2700.ctrl.write(":SENSe1:FUNCtion 'VOLTage:DC', (@ 107,108)")
        
        self.k2700.ctrl.write(":TRIGger:SEQuence1:DELay 0")
        self.k2700.ctrl.write(":TRIGger:SEQuence1:COUNt 1")    # Set the count rate
        
        # Sets the the acquisition rate of the measurements
        self.k2700.ctrl.write(":SENSe1:VOLTage:DC:NPLCycles 1, (@ 107,108)") # Sets integration period based on frequency
        self.k2700.ctrl.write(":SENSe1:TEMPerature:NPLCycles 1, (@ 109,110)")
            
        
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
class FakeSetup:
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
        self.k2700 = k2700 = FakeKeithley_2700()
        # Define the ports for the PID
        self.heaterB = heaterB = FakePID() # TOP heater
        self.heaterA = heaterA = FakePID() # BOTTOM heater

#end class
###############################################################################

###############################################################################
class ProcessThreadCheck(Thread):
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
        ic = InitialCheck()
    #end def
        
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
        
        self.update_statusBar('Checking')
        
        self.take_PID_Data()
        
        self.take_Keithley_Data()
        
        self.update_statusBar('Ready')
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
        
        self.updateGUI(plot="PID A Status", data=self.pA)
        self.updateGUI(plot="PID B Status", data=self.pB)
        self.updateGUI(plot="PID A SP Status", data=self.pAset)
        self.updateGUI(plot="PID B SP Status", data=self.pBset)
        
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
        
        self.updateGUI(plot="High Voltage Status", data=self.highV)
        self.updateGUI(plot="Low Voltage Status", data=self.lowV)
        self.updateGUI(plot="Temp A Status", data=self.tA)
        self.updateGUI(plot="Temp B Status", data=self.tB)
        
        print "Temp A: %.2f C\nTemp B: %.2f C" % (float(self.tA), float(self.tB))
        print "High Voltage: %.1f uV\nLow Voltage: %.1f uV" % (self.highV, self.lowV)
        
    #end def
    
    #--------------------------------------------------------------------------
    def update_statusBar(self, msg):
        if msg == 'Running' or msg == 'Finished, Ready' or msg == 'Exception Occurred' or msg == 'Checking':
            wx.CallAfter(pub.sendMessage, "Status Bar", msg=msg)
        #end if
            
        elif len(msg) == 2:
            tol = msg[0] + 'tol'
            equil = msg[1] + 'equ'
            
            if tol[:2] == 'OK' and equil[:2] == 'OK':
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=tol)
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=equil)
                
                self.measurement_countdown()
                self.start_equil_timer()
                
                self.measurements_left = str(self.measurements_left) + 'mea'
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=self.measurements_left)
                
                self.time_left = str(self.time_left) + 'tim'
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=self.time_left)
            
            #end if
            
            else:
                self.time_left_ID = 0
                self.measurement_countdown_integer = 0
                
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=tol)
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=equil)
                wx.CallAfter(pub.sendMessage, "Status Bar", msg='-mea')
                wx.CallAfter(pub.sendMessage, "Status Bar", msg='-tim')
                
            #end else
                
        #end elif
        
    #end def
    
    #--------------------------------------------------------------------------
    def updateGUI(self, plot, data):
        """
        Sends data to the GUI (main thread), for live updating while the process is running
        in another thread.
        
        There are 3 possible plots that correspond to their respective data.
        There are 11 possible types of data to send to the GUI, these include:
        
            - "PID A"
            - "PID B"
            - "PID Time"
            
            - "Voltage High"
            - "Voltage High Time"
            - "Voltage Low"
            - "Voltage Low Time"
            
            - "Temperature A"
            - "Temperature A Time"
            - "Temperature B"
            - "Temperature B Time"
        """
        time.sleep(0.1)
        wx.CallAfter(pub.sendMessage, plot, msg=data)
        
    #end def
    
#end class    
###############################################################################

###############################################################################
class TakeDataTest:
    """
    Main data aquisition loop. Takes data and Publishes to txt interface and GUI.
    """
    #--------------------------------------------------------------------------
    def __init__(self):
        self.start = time.time()
        self.updatedata()
        
        while self.t < 20:
            time.sleep(1)
            self.updatedata()
    
    #end init
    
    #--------------------------------------------------------------------------           
    def updatedata(self):
        self.t = time.time()-self.start
        self.highV = np.sin(self.t)*10**-3
        self.lowV = np.cos(self.t)*10**-3
        self.tA = 100 + 100*np.cos(self.t/2)
        self.tB = 100 + 100*np.sin(self.t/2)
        self.pA = 200 + 100*np.cos(self.t/2)
        self.pB = 200 + 100*np.sin(self.t/2)
        
        self.printdata()
        self.updateGUI(plot="High Voltage", data=self.highV)
        self.updateGUI(plot="Time High Voltage", data=self.t)
        self.updateGUI(plot="Low Voltage", data=self.lowV)
        self.updateGUI(plot="Time Low Voltage", data=self.t)
        self.updateGUI(plot="Temp A", data=self.tA)
        self.updateGUI(plot="Time Temp A", data=self.t)
        self.updateGUI(plot="Temp B", data=self.tB)
        self.updateGUI(plot="Time Temp B", data=self.t)
        self.updateGUI(plot="PID A", data=self.pA)
        self.updateGUI(plot="Time PID A", data=self.t)
        self.updateGUI(plot="PID B", data=self.pB)
        self.updateGUI(plot="Time PID B", data=self.t)
    #end def
    
    #-------------------------------------------------------------------------- 
    def printdata(self):
        print "Run Time: %.2f s\nHigh Voltage: %.2f uV\nLow Voltage: %.2f uV" % (self.t, self.highV, self.lowV)
        print "Temp A: %.2f C\nTemp B: %.2f C\nPID A: %.2f C\nPID B: %.2f C" % (self.tA, self.tB, self.pA, self.pB)        
    #end def
    
    #--------------------------------------------------------------------------
    def updateGUI(self, plot, data):
        """
        Sends data to the GUI (main thread), for live updating while the process is running
        in another thread.
        
        There are 3 possible plots that correspond to their respective data.
        There are 11 possible types of data to send to the GUI, these include:
        
            - "PID A"
            - "PID B"
            - "PID Time"
            
            - "Voltage High"
            - "Voltage High Time"
            - "Voltage Low"
            - "Voltage Low Time"
            
            - "Temperature A"
            - "Temperature A Time"
            - "Temperature B"
            - "Temperature B Time"
        """
        
        wx.CallAfter(pub.sendMessage, plot, msg=data)
        
    #end def
     
#end class    
###############################################################################

###############################################################################
class TakeData:
    """ A loop that acquires, saves, and plots data coming from the Keithley
        and the PID. It also continuously checks the setpoints and tells the 
        PID to ramp up or oscillate. This is the meat of the code, and it 
        allows the process of measurement with the Seebeck machine to 
        be entirely automated. 
    """  
    
    #--------------------------------------------------------------------------
    def __init__(self):
        
        global indicator
        global abort_ID
        
        self.k2700 = k2700
        self.heaterA = heaterA
        self.heaterB = heaterB
        
        self.pidA_list = []
        self.pidB_list = []
        
        self.pidAset_list = []
        self.pidBset_list = []
        
        self.exception_ID = 0
        
        # The Run button was pressed.
        self.start = time.time()
        
        # Set PID setpoints to the starting temperature:
        self.heaterA.set_setpoint(int(measureList[0])-oscillation/2) # 5 degrees below the setpoint
        self.heaterB.set_setpoint(int(measureList[0])+oscillation/2) # 5 degrees above the setpoint
        
        self.time_left_ID = 0
        self.start_timer = 0
        self.measurement_countdown_integer = 0
        self.update_statusBar('Running')
        
        try:
            while abort_ID == 0:
                ''' - while loop that runs until the max temp has been measured,
                      or until the stop button is pressed.
                    - The loop checks and adjusts the PID setpoints and takes 
                      Keithley data for each channel.
                    - Note that the Keithley takes a second to switch and send 
                      data, so we check the PID in between each Keithley 
                      measurement. 
                '''
                
                self.take_PID_Data() # refer to definition)
                if abort_ID == 1: break
                
                # Takes and writes to file the data on the Keithley
                # The only change between blocks like this one is the specific
                # channel on the Keithley that is being measured.
                self.tempA = tempA = self.k2700.fetch(tempAChannel)
                #tempA = self.tempConversion(float(A))
                ttempA = time.time() - self.start
                myfile.write( '%.2f,%s,' % (ttempA, tempA) )
                self.updateGUI(plot="Temp A", data=float(tempA))
                self.updateGUI(plot="Time Temp A", data=float(ttempA))
                print "ttempA: %.2f s\ttempA: %s C" % (ttempA, tempA) 
                
                time.sleep(0.02)
                # The rest is a repeat of the above code, for different
                # channels.
                
                self.take_PID_Data()
                if abort_ID == 1: break
                
                self.tempB = tempB = self.k2700.fetch(tempBChannel)
                #tempB = self.tempConversion(float(B))
                ttempB = time.time() - self.start
                myfile.write( '%.2f,%s,' % (ttempB, tempB) )
                self.updateGUI(plot="Temp B", data=float(tempB))
                self.updateGUI(plot="Time Temp B", data=float(ttempB))
                print "ttempB: %.2f s\ttempB: %s C" % (ttempB, tempB) 
                
                time.sleep(0.02)
                
                self.take_PID_Data()
                self.safety_check()
                if abort_ID == 1: break
                    
                
                highV_raw = self.k2700.fetch(highVChannel)
                self.highV_raw = highV_raw = float(highV_raw)*10**6 # uV
                highV_corrected = self.voltage_Correction(float(highV_raw), 'high')
                thighV = time.time() - self.start
                myfile.write( '%.2f,%f,' % (thighV, highV_raw))
                self.updateGUI(plot="High Voltage", data=float(highV_corrected))
                self.updateGUI(plot="Time High Voltage", data=float(thighV))
                print "thighV: %.2f s\thighV_raw: %f uV\thighV_corrected: %f uV" % (thighV, highV_raw, highV_corrected)
                
                time.sleep(0.02)
                
                self.take_PID_Data()
                self.safety_check()
                if abort_ID == 1: break
                
                
                lowV_raw = self.k2700.fetch(lowVChannel)
                self.lowV_raw = lowV_raw = float(lowV_raw)*10**6 # uV
                lowV_corrected = self.voltage_Correction(float(lowV_raw), 'low')
                tlowV = time.time() - self.start
                myfile.write( '%.2f,%f,' % (tlowV, lowV_raw) )
                self.updateGUI(plot="Low Voltage", data=float(lowV_corrected))
                self.updateGUI(plot="Time Low Voltage", data=float(tlowV))
                print "tlowV: %.2f s\tlowV_raw: %f uV\tlowV_corrected: %f uV" % (tlowV, lowV_raw, lowV_corrected)
                
                time.sleep(0.02)
                
                # Symmetrize the measurement and repeat in reverse
                
                self.take_PID_Data()
                self.safety_check()
                if abort_ID == 1: break
                
                
                lowV_raw2 = self.k2700.fetch(lowVChannel)
                self.lowV_raw2 = lowV_raw2 = float(lowV_raw2)*10**6 # uV
                lowV_corrected2 = self.voltage_Correction(float(lowV_raw2), 'low')
                tlowV2 = time.time() - self.start
                myfile.write( '%.2f,%f,' % (tlowV2, lowV_raw2) )
                self.updateGUI(plot="Low Voltage", data=float(lowV_corrected2))
                self.updateGUI(plot="Time Low Voltage", data=float(tlowV2))
                print "tlowV: %.2f s\tlowV_raw: %f uV\tlowV_corrected: %f uV" % (tlowV2, lowV_raw2, lowV_corrected2)
                
                time.sleep(0.02)
                
                self.take_PID_Data()
                self.safety_check()
                if abort_ID == 1: break
                    
                
                highV_raw2 = self.k2700.fetch(highVChannel)
                self.highV_raw2 = highV_raw2 = float(highV_raw2)*10**6 # uV
                highV_corrected2 = self.voltage_Correction(float(highV_raw2), 'high')
                thighV2 = time.time() - self.start
                myfile.write( '%.2f,%f,' % (thighV2, highV_raw2) )
                self.updateGUI(plot="High Voltage", data=float(highV_corrected2))
                self.updateGUI(plot="Time High Voltage", data=float(thighV2))
                print "thighV: %.2f s\thighV_raw: %f uV\thighV_corrected: %f uV" % (thighV2, highV_raw2, highV_corrected2)
                
                time.sleep(0.02)
                
                self.take_PID_Data()
                if abort_ID == 1: break
                
                self.tempB2 = tempB2 = self.k2700.fetch(tempBChannel)
                #tempB = self.tempConversion(float(B))
                ttempB2 = time.time() - self.start
                myfile.write( '%.2f,%s,' % (ttempB2, tempB2) )
                self.updateGUI(plot="Temp B", data=float(tempB2))
                self.updateGUI(plot="Time Temp B", data=float(ttempB2))
                print "ttempB: %.2f s\ttempB: %s C" % (ttempB2, tempB2)
                
                time.sleep(0.02)
                
                self.take_PID_Data() # refer to definition)
                if abort_ID == 1: break
                
                self.tempA2 = tempA2 = self.k2700.fetch(tempAChannel)
                #tempA = self.tempConversion(float(A))
                ttempA2 = time.time() - self.start
                myfile.write( '%.2f,%s' % (ttempA2, tempA2) )
                self.updateGUI(plot="Temp A", data=float(tempA2))
                self.updateGUI(plot="Time Temp A", data=float(ttempA2))
                print "ttempA: %.2f s\ttempA: %s C" % (ttempA2, tempA2)
                
                # indicates whether an oscillation has started or stopped
                if indicator == 'start':
                    myfile.write(',Start Oscillation')
                    indicator = 'none'
                    
                elif indicator == 'half-way':
                    myfile.write(',Half-way')
                    indicator = 'none'
                    
                elif indicator == 'stop':
                    myfile.write(',Stop Oscillation')
                    indicator = 'none'
                    
                elif indicator == 'none':
                    myfile.write(', ')
                
                myfile.write('\n')
                
                
                self.safety_check()
                if abort_ID == 1: break
                
                    
                time.sleep(0.02)
            #end while
        #end try
        
        except exceptions.Exception as e:
            log_exception(e)
            
            abort_ID = 1
            
            self.exception_ID = 1
            
            print "Error Occurred, check error_log.log"
        
        #end except
        
        if self.exception_ID == 1:
            self.update_statusBar('Exception Occurred')
        #end if    
        else:
            self.update_statusBar('Finished, Ready')
        #end else  
        
        # Stop the PID and the heaters
        #self.heaterA.stop()
        #self.heaterB.stop()
        self.heaterA.set_setpoint(20)
        self.heaterB.set_setpoint(20)
        
        # Save files:
        self.save_files()
        
        
        wx.CallAfter(pub.sendMessage, 'Post Process')
            
        wx.CallAfter(pub.sendMessage, 'Enable Buttons')
        
    #end init
        
    #--------------------------------------------------------------------------
    def voltage_Correction(self, raw_data, side):
        ''' raw_data must be in uV '''
        
        # Kelvin conversion for polynomial correction.
        tempA = float(self.tempA) + 273.15
        tempB = float(self.tempB) + 273.15
        
        dT = tempA - tempB
        avgT = (tempA + tempB)/2
        
        # Correction for effect from Thermocouple Seebeck
        out = self.alpha(avgT, side)*dT - raw_data
        
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
    def tempConversion(self, data):
        """
        Converts mV to Kelvin for different thermocouples. The polynomials were
        derived from lookup tables from NIST/NASA/CalTech.
        
        Refer to Thermocouples.py for the code to retrieve the polynomials.
        """
        data = data*1000 # millivolts conversion
        
        # inverse polynomial to convert voltage to temperature. Same program
        # and data used as for the voltage correction, except we use a
        # combined thermocouple table.
        
        if tc_type == "k-type":
            # From 'k-type Polynomials.txt'
            
            if ( data >= 273 and data < 573):
                a0 = 300.422570995
                a1 = 24.5247416871
                a2 = -0.214042158781
                a3 = 0.0485329865958
                a4 = -0.00265073431981
                
            if ( data >= 573 and data < 873):
                a0 = 295.719939849
                a1 = 25.9337873878
                a2 = -0.0943659556599
                a3 = 0.000290979735614
                a4 = 2.94975574243e-05
                
            if ( data >= 873 and data < 1173):
                a0 = 274.619963794
                a1 = -54.44913029
                a2 = -1.966106698
                a3 = -1.476161077
                a4 = -0.196445169
        
        value = a0 + data(a1 + data(a2 + data(a3 + a4*data)))
        #value = value - 273.15 # Kelvin to Celsius
        return value
    
    #--------------------------------------------------------------------------
    def updateGUI(self, plot, data):
        """
        Sends data to the GUI (main thread), for live updating while the process is running
        in another thread.
        
        There are 3 possible plots that correspond to their respective data.
        There are 11 possible types of data to send to the GUI, these include:
        
            - "PID A"
            - "PID B"
            - "PID Time"
            
            - "Voltage High"
            - "Voltage High Time"
            - "Voltage Low"
            - "Voltage Low Time"
            
            - "Temperature A"
            - "Temperature A Time"
            - "Temperature B"
            - "Temperature B Time"
        """
        
        wx.CallAfter(pub.sendMessage, plot, msg=data)
        
    #end def
    
    #--------------------------------------------------------------------------        
    def take_PID_Data(self):
        """ Takes data from the PID, writes it to file, and proceeds to a 
            function that checks the PID setpoints.
        """
        
        # Take Data and time stamps:
        self.pidA = self.heaterA.get_pv()
        self.tpidA = time.time() - self.start
        self.pidB = self.heaterB.get_pv()
        self.tpidB = time.time() - self.start
        
        # Get the current setpoints on the PID:
        self.pidAset = self.heaterA.get_setpoint()
        self.pidBset = self.heaterB.get_setpoint()
        
        self.check_status()
        
        self.updateGUI(plot="PID A", data=self.pidA)
        self.updateGUI(plot="Time PID A", data=self.tpidA)
        self.updateGUI(plot="PID B", data=self.pidB)
        self.updateGUI(plot="Time PID B", data=self.tpidB)
        self.updateGUI(plot="PID A SP", data=self.pidAset)
        self.updateGUI(plot="PID B SP", data=self.pidBset)
        
        
        self.pidA_list.append(self.pidA)
        self.pidB_list.append(self.pidB)
        
        pfile.write("%.2f, %.1f, %.2f, %.1f \n" % (self.tpidA, self.pidA, self.tpidB, self.pidB) )
        
        print "tpidA: %.2f s\tpidA: %s C\ntpidB: %.2f s\tpidB: %s C" % (self.tpidA, self.pidA, self.tpidB, self.pidB)
        self.check_PID_setpoint()
        
    #end def
        
    #--------------------------------------------------------------------------
    def check_status(self):
        if (self.pidA <= self.pidAset+tolerance and self.pidA >= self.pidAset-tolerance and \
             self.pidB <= self.pidBset+tolerance and self.pidB >= self.pidBset-tolerance):
            
            tol = 'OK'
        #end if
            
        else:
            tol = 'NO'
            
        #end else
         
        if (self.pidA < self.pidAset + equil_tolerance and self.pidA > self.pidAset - equil_tolerance and \
             self.pidB < self.pidBset + equil_tolerance and self.pidB > self.pidBset - equil_tolerance ):
            
            equil = 'OK'
        #end if
            
        else:
            equil = 'NO'
        #end else
            
        
        self.update_statusBar([tol, equil])
        
    #end def
        
    #--------------------------------------------------------------------------
    def update_statusBar(self, msg):
        if msg == 'Running' or msg == 'Finished, Ready' or msg == 'Exception Occurred':
            wx.CallAfter(pub.sendMessage, "Status Bar", msg=msg)
        #end if
            
        elif len(msg) == 2:
            tol = msg[0] + 'tol'
            equil = msg[1] + 'equ'
            
            if tol[:2] == 'OK' and equil[:2] == 'OK':
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=tol)
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=equil)
                
                self.measurement_countdown()
                self.start_equil_timer()
                
                self.measurements_left = str(self.measurements_left) + 'mea'
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=self.measurements_left)
                
                self.time_left = str(self.time_left) + 'tim'
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=self.time_left)
            
            #end if
            
            else:
                self.time_left_ID = 0
                self.measurement_countdown_integer = 0
                
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=tol)
                wx.CallAfter(pub.sendMessage, "Status Bar", msg=equil)
                wx.CallAfter(pub.sendMessage, "Status Bar", msg='-mea')
                wx.CallAfter(pub.sendMessage, "Status Bar", msg='-tim')
                
            #end else
                
        #end elif
        
    #end def
        
    #--------------------------------------------------------------------------
    def measurement_countdown(self):
        self.measurement_countdown_integer = self.measurement_countdown_integer + 1
        
        self.measurements_left = equil_time - self.measurement_countdown_integer
        
    #end def
        
    #--------------------------------------------------------------------------    
    def start_equil_timer(self):
        if self.time_left_ID == 0:
            self.start_timer = time.time()
            
        self.time_left_ID = 1
        
        time_passed = time.time() - self.start_timer
        self.time_left = int(equil_time*3 - time_passed)
        
    #end def
        
    #--------------------------------------------------------------------------
    def check_PID_setpoint(self):
        
        """ Function that requires that all conditions must be met to change 
            the setpoints. 
        """
                
        # These first several if statements check to make sure that the
        # temperature has reached an equilibrium.
        if (len(self.pidA_list) > abs(-equil_time) and \
        len(self.pidB_list) > abs(-equil_time) ):
            
            if self.pidA_list[-1] < self.pidA_list[-equil_time]+equil_tolerance and \
                    self.pidA_list[-1] > self.pidA_list[-equil_time]-equil_tolerance and \
                    self.pidB_list[-1] < self.pidB_list[-equil_time]+equil_tolerance and \
                    self.pidB_list[-1] > self.pidB_list[-equil_time]-equil_tolerance and \
                    self.pidA_list[-1] < self.pidA_list[-(equil_time*3/4)]+equil_tolerance and \
                    self.pidA_list[-1] > self.pidA_list[-(equil_time*3/4)]-equil_tolerance and \
                    self.pidB_list[-1] < self.pidB_list[-(equil_time*3/4)]+equil_tolerance and \
                    self.pidB_list[-1] > self.pidB_list[-(equil_time*3/4)]-equil_tolerance and \
                    self.pidA_list[-1] < self.pidA_list[-(equil_time*2/3)]+equil_tolerance and \
                    self.pidA_list[-1] > self.pidA_list[-(equil_time*2/3)]-equil_tolerance and \
                    self.pidB_list[-1] < self.pidB_list[-(equil_time*2/3)]+equil_tolerance and \
                    self.pidB_list[-1] > self.pidB_list[-(equil_time*2/3)]-equil_tolerance and \
                    self.pidA_list[-1] < self.pidA_list[-(equil_time*1/2)]+equil_tolerance and \
                    self.pidA_list[-1] > self.pidA_list[-(equil_time*1/2)]-equil_tolerance and \
                    self.pidB_list[-1] < self.pidB_list[-(equil_time*1/2)]+equil_tolerance and \
                    self.pidB_list[-1] > self.pidB_list[-(equil_time*1/2)]-equil_tolerance and \
                    self.pidA_list[-1] < self.pidA_list[-(equil_time*1/3)]+equil_tolerance and \
                    self.pidA_list[-1] > self.pidA_list[-(equil_time*1/3)]-equil_tolerance and \
                    self.pidB_list[-1] < self.pidB_list[-(equil_time*1/3)]+equil_tolerance and \
                    self.pidB_list[-1] > self.pidB_list[-(equil_time*1/3)]-equil_tolerance and \
                    self.pidA_list[-1] < self.pidA_list[-(equil_time*1/4)]+equil_tolerance and \
                    self.pidA_list[-1] > self.pidA_list[-(equil_time*1/4)]-equil_tolerance and \
                    self.pidB_list[-1] < self.pidB_list[-(equil_time*1/4)]+equil_tolerance and \
                    self.pidB_list[-1] > self.pidB_list[-(equil_time*1/4)]-equil_tolerance and \
                    self.pidA_list[-1] < self.pidA_list[-10]+equil_tolerance and \
                    self.pidA_list[-1] > self.pidA_list[-10]-equil_tolerance and \
                    self.pidB_list[-1] < self.pidB_list[-10]+equil_tolerance and \
                    self.pidB_list[-1] > self.pidB_list[-10]-equil_tolerance and \
                    self.pidA_list[-1] < self.pidA_list[-2]+equil_tolerance and \
                    self.pidA_list[-1] > self.pidA_list[-2]-equil_tolerance and \
                    self.pidB_list[-1] < self.pidB_list[-2]+equil_tolerance and \
                    self.pidB_list[-1] > self.pidB_list[-2]-equil_tolerance :
                    
            #if:
                
                # If the reading is within tolerance of the current setpoint
                if (self.pidA <= self.pidAset+tolerance and self.pidA >= self.pidAset-tolerance and self.pidB <= self.pidBset+tolerance and self.pidB >= self.pidBset-tolerance):
                    
                    self.pidAset_list.append(self.pidAset)
                    
                    if len(measureList) == 1:
                        self.check_last(measureList[0])
                    
                    elif n < len(measureList)-1:
                        self.check_step(measureList[n], measureList[n+1])
                        
                    # if we're on the last element of the list:
                    elif n == len(measureList)-1:
                        self.check_last(measureList[-1])
                    
                    # Print out a statement when the setpoints change
                    pidAset = self.heaterA.get_setpoint()
                    pidBset = self.heaterB.get_setpoint()
                    ifTime = time.time() - self.start
                    print "Time: %.2f Set Points: %.1f, %.1f Temps: %.1f, %.1f" % (ifTime, pidAset, pidBset, self.pidA, self.pidB)
                
                #end if
                
            #end if  
                
        #end if      
                
    #end def    
    
    #--------------------------------------------------------------------------
    def check_step(self, step, nextStep):
        """ Function defining what to do if we reach a measurement step and 
            what to do if we haven't yet. A measurement step is a temperature
            where we want to take an oscillating measurement. If we have not
            reached the measurement step yet, the function will increase the
            PID setpoint by the defined ramp step.
            
            step - define measurement step
            lastStep - define what the last measurement step was
        """
        global i
        global n
        global indicator
        
        # This first block checks if we are at a measurement step. If we
        # are, it proceeds to tell the PID to begin oscillations.
        # When the oscillations are completed, the PID setpoint will increase
        # by the defined rampstep.
        
        # Are both the PID measured temp and the setpoint at the measurement 
        # step? :
        if (self.pidA <= step+tolerance and self.pidA >= step-tolerance and self.pidB <= step+tolerance and self.pidB >= step-tolerance):
            if (self.pidAset <= step+tolerance and self.pidAset >= step-tolerance and self.pidBset <= step+tolerance and self.pidBset >= step-tolerance):
                
                # Is this the first stop? If so, goto else.:
                if ( len(self.pidAset_list) >= 2):
                    
                    # If the last measured setpoint is the same as the current
                    if ( i == 0 ):
                        indicator = 'start'
                        self.heaterA.set_setpoint(self.pidAset+oscillation)
                        self.heaterB.set_setpoint(self.pidBset-oscillation)
                        i = 1
                    #end if
                    elif ( i == 1 ):
                        indicator = 'half-way'
                        self.heaterA.set_setpoint(self.pidAset-oscillation)
                        self.heaterB.set_setpoint(self.pidBset+oscillation)
                        i = 2
                    #end elif
                    elif ( i == 2 ):
                        indicator = 'stop'
                        self.heaterA.set_setpoint(nextStep-oscillation/2)
                        self.heaterB.set_setpoint(nextStep+oscillation/2)
                            
                        i = 0
                        n = n + 1
                    #end elif
                #end if
                        
                # If this is the first stop, then start the oscillation.
                else:
                    indicator = 'start'
                    self.heaterA.set_setpoint(self.pidAset+oscillation)
                    self.heaterB.set_setpoint(self.pidBset-oscillation)
                    i = 1
                #end else
                            
            #end if
        #end if
        
        ## This block checks if we are in between measurement steps. If we are,
        ## it proceeds to increase the setpoint up by the rampstep.            
        #elif (self.pidAset < step-tolerance and self.pidBset < step-tolerance and self.pidAset > lastStep+tolerance and self.pidBset > lastStep+tolerance):
        #    self.heaterA.set_setpoint(self.pidAset + rampstep)
        #    self.heaterB.set_setpoint(self.pidBset + rampstep)
        ##end elif
                                    
    #end def
                                    
    #--------------------------------------------------------------------------
    def check_last(self, maxT):
        """ Function defining what to do if we reach the last measurement, and
            what to do if haven't reached it yet. This is the same function
            as the check_step function, except it breaks from the while loop
            when all of its stages (oscillations) have been completed. Once
            we break from the while loop, the entire measurement process has
            been completed.
            
            maxT - define the maximum temperature  
            lastStep - define what the last measurement step was
        """
        
        global abort_ID
        global i
        global indicator
        
        # This block does the same function as check_step
        if (self.pidA <= maxT+tolerance and self.pidA >= maxT-tolerance and self.pidB <= maxT+tolerance and self.pidB >= maxT-tolerance):
            if (self.pidAset <= maxT+tolerance and self.pidAset >= maxT-tolerance and self.pidBset <= maxT+tolerance and self.pidBset >= maxT-tolerance):
                if (i == 0):
                    indicator = 'start'
                    self.heaterA.set_setpoint(self.pidAset+oscillation)
                    self.heaterB.set_setpoint(self.pidBset-oscillation)
                    i = 1
                #end if
                elif (i == 1):
                    indicator = 'half-way'
                    self.heaterA.set_setpoint(self.pidAset-oscillation)
                    self.heaterB.set_setpoint(self.pidBset+oscillation)
                    i = 2
                #end elif
                elif (i == 2 ):
                    indicator = 'stop'
                    abort_ID = 1
                #end elif
            #end if    
        #end if
                    
        ## This block checks if we are in between measurement steps. If we are,
        ## it proceeds to increase the setpoint up by the rampstep.            
        #elif (self.pidAset < maxT-tolerance and self.pidBset < maxT-tolerance and self.pidAset > lastStep+tolerance and self.pidBset > lastStep+tolerance):
        #    self.heaterA.set_setpoint(self.pidAset + rampstep)
        #    self.heaterB.set_setpoint(self.pidBset + rampstep)
        ##end elif
        
    #end def
    
    #--------------------------------------------------------------------------    
    def safety_check(self):
        global abort_ID
        
        if float(self.tempA) > self.pidB + 50 or \
                float(self.tempB) > self.pidA + 50 :
            if float(self.tempA) > self.pidB + 50:
                myfile.write('Keithley saw a 50C difference from the PID temperature in the top heater. Program was aborted.')
                print 'Keithley saw a 50C difference from the PID temperature in the top heater. Program was aborted.'
            if float(self.tempB) > self.pidA + 50:
                myfile.write('Keithley saw a 50C difference from the PID temperature in the bottom heater. Program was aborted.')
                print 'Keithley saw a 50C difference from the PID temperature in the bottom heater Program was aborted..'
                
            abort_ID = 1
            
            
        
    #end def
    
    #--------------------------------------------------------------------------
    def save_files(self):
        ''' Function saving the files after the data acquisition loop has been
            exited. 
        '''
        
        global dataFile
        global finaldataFile
        global pidFile
        global myfile
        global pfile
        
        stop = time.time()
        end = datetime.now() # End time
        totalTime = stop - self.start # Elapsed Measurement Time (seconds)
        
        myfile.close() # Close the files
        pfile.close()
        
        myfile = open(filePath + '/Raw Data/' + dataFile, 'r') # Opens the file for Reading
        contents = myfile.readlines() # Reads the lines of the file into python set
        myfile.close()
        
        # Adds elapsed measurement time to the read file list
        endStr = 'End Time: %s \nElapsed Measurement Time: %s Seconds \n \n' % (str(end), str(totalTime))
        contents.insert(1, endStr) # Specify which line and what value to insert
        # NOTE: First line is line 0
        
        # Writes the elapsed measurement time to the final file
        file = filePath + '/Raw Data/' + finaldataFile
        myfinalfile = open(file,'w')
        contents = "".join(contents)
        myfinalfile.write(contents)
        myfinalfile.close()
        
        # Save the GUI plots
        global save_plots_ID
        save_plots_ID = 1
        os.makedirs(filePath + '/Raw Data/' + 'Plots')
        self.updateGUI(plot='Save_All', data='Save')
    
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
        
        self.create_title("User Panel") # Title
        
        self.tc_control()
        self.linebreak1 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.oscillation_control() # Oscillation range control
        self.linebreak2 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.tolerance_control() # PID tolerance level Control
        self.linebreak3 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.measurementListBox() # List box for inputting measurement steps
        self.maxLimit_label()

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
    def check(self, e):
        
        ProcessThreadCheck()
        
    #end def
    
    #--------------------------------------------------------------------------
    def run(self, event):
        global measureList
        measureList = [None]*self.listbox.GetCount()
        for k in xrange(self.listbox.GetCount()):
            measureList[k] = int(self.listbox.GetString(k))
        #end for
        
        
        if len(measureList) > 0:
            self.name_folder()
            
            if self.run_check == wx.ID_OK:
                global dataFile
                global finaldataFile
                global pidFile
                global myfile
                global pfile
                global i
                global n
                global indicator
                global abort_ID
                global highV_list, thighV_list, lowV_list, tlowV_list
                global tempA_list, ttempA_list, tempB_list, ttempB_list
                global pidA_list, tpidA_list, pidB_list, tpidB_list
                global oscillation
                global tolerance
                
                file = filePath + '/Raw Data/' + dataFile # creates a data file
                myfile = open(file, 'w') # opens file for writing/overwriting
                begin = datetime.now() # Current date and time
                myfile.write('Start Time: ' + str(begin) + '\n')
                myfile.write('Time (s),Temperature A (C),Time (s),Temperature B (C),Time (s),Raw Voltage High (uV),Time (s),Raw Voltage Low (uV),Time (s),Raw Voltage Low 2 (uV),Time (s),Raw Voltage High 2 (uV),Time (s),Temperature B 2 (C),Time (s),Temperature A 2 (C),Oscillation Start/Stop\n')
                
                # File for PID data:
                file = filePath + '/Raw Data/' + pidFile
                pfile = open(file, 'w')
                pfile.write('Start Time: ' + str(begin) + '\n')
                pfile.write('Time (s),Heater A (C),Time (s),Heater B (C)\n')
                
                i = 0
                n = 0
                indicator = 'none'
                abort_ID = 0
                
                highV_list = [0]
                thighV_list = [0]
                lowV_list = [0]
                tlowV_list = [0]
                tempA_list = [0]
                ttempA_list = [0]
                tempB_list = [0]
                ttempB_list = [0]
                pidA_list = [0]
                tpidA_list = [0]
                pidB_list = [0]
                tpidB_list = [0]
                
                oscillation = float(oscillation)
                tolerance = float(tolerance)
                
                #start the threading process
                thread = ProcessThreadRun()
                
                btn = event.GetEventObject()
                btn.Disable()
                self.btn_osc.Disable()
                self.btn_tolerance.Disable()
                self.btn_new.Disable()
                self.btn_ren.Disable()
                self.btn_dlt.Disable()
                self.btn_clr.Disable()
                self.btn_check.Disable()
                self.btn_stop.Enable()
                
            #end if
        #end if
                
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
                os.makedirs(filePath + '/Raw Data/')
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
                        os.makedirs(path + '/Raw Data/')
                        
                #end while
                        
            #end else
                        
        #end if
        
        # Set the global path to the newly created path, if applicable.
        if found == True:
            filePath = path
        #end if
    #end def
    
    #--------------------------------------------------------------------------
    def stop(self, e):
        global abort_ID
        abort_ID = 1
        
        self.enable_buttons
        
    #end def        
        
    #--------------------------------------------------------------------------
    def tc_control(self):
        self.tcPanel = wx.Panel(self, -1)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.label_tc = wx.StaticText(self, label="Thermocouple Type:")
        #self.font2 = wx.Font(12, wx.DEFAULT, wx.NORMAL, wx.NORMAL)
        #self.label_tc.SetFont(self.font2)
        
        tcTypes = ['k-type','other']
        cb = wx.ComboBox(self.tcPanel, choices=tcTypes, style=wx.CB_READONLY)
        cb.SetValue('k-type')
        
        cb.Bind(wx.EVT_COMBOBOX, self.tc_save)
        
        hbox.Add((0,-1))
        hbox.Add(cb, 0, wx.LEFT, 25)
        
        self.tcPanel.SetSizer(hbox)
        
    #end def
        
    #--------------------------------------------------------------------------
    def tc_save(self,e):
        global tc_type
        tc_type = e.GetString()
        self.label_tc.SetLabel(tc_type)
        
    #end def
        
    #--------------------------------------------------------------------------
    def oscillation_control(self):
        self.oscPanel = wx.Panel(self, -1)        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.celsius = u"\u2103"
        
        self.label_osc = wx.StaticText(self, 
                                            label="PID Oscillaton (%s):"
                                            % self.celsius
                                            )
        #self.font2 = wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.NORMAL)
        #self.label_osc.SetFont(self.font2)
        self.text_osc = text_osc = wx.StaticText(self.oscPanel, label=oscillation)
        #text_osc.SetFont(self.font2)
        self.edit_osc = edit_osc = wx.TextCtrl(self.oscPanel, size=(60, -1))
        self.btn_osc = btn_osc = wx.Button(self.oscPanel, label="save", size=(60, -1))
        text_guide = wx.StaticText(self.oscPanel, label="The PID will oscillate within this \ndegree range when oscillating at \na measurement.")
        
        btn_osc.Bind(wx.EVT_BUTTON, self.save_oscillation)
        
        hbox.Add((0, -1))
        hbox.Add(text_osc, 0, wx.LEFT, 5)
        hbox.Add(edit_osc, 0, wx.LEFT, 25)
        hbox.Add(btn_osc, 0, wx.LEFT, 5)
        hbox.Add(text_guide, 0, wx.LEFT, 5)
        
        self.oscPanel.SetSizer(hbox)
        
    #end def  
    
    #--------------------------------------------------------------------------
    def save_oscillation(self, e):
        global oscillation
        global tolerance
        oscillation = self.edit_osc.GetValue()
        if float(oscillation) > maxLimit:
            oscillation = str(maxLimit)
        self.text_osc.SetLabel(oscillation)
        oscillation = float(oscillation)
        
        if float(tolerance) < float(oscillation)/2 + 1:
            tolerance = str(float(oscillation)/2 + 1)
            self.text_tolerance.SetLabel(tolerance)
            tolerance = float(tolerance)
        if float(tolerance) >= float(oscillation):
            tolerance = str(float(oscillation)-1)
            self.text_tolerance.SetLabel(tolerance)
            tolerance = float(tolerance)
        
    #end def
    
    #--------------------------------------------------------------------------
    def tolerance_control(self):
        self.tolPanel = wx.Panel(self, -1)        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        self.label_tolerance = wx.StaticText(self, 
                                            label="Tolerance (%s):"
                                            % self.celsius
                                            )
        #self.font2 = wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.NORMAL)
        #self.label_tolerance.SetFont(self.font2)
        self.text_tolerance = text_tolerance = wx.StaticText(self.tolPanel, label=tolerance)
        #text_tolerance.SetFont(self.font2)
        self.edit_tolerance = edit_tolerance = wx.TextCtrl(self.tolPanel, size=(60, -1))
        self.btn_tolerance = btn_tolerance = wx.Button(self.tolPanel, label="save", size=(60, -1))
        text_guide = wx.StaticText(self.tolPanel, label="The tolerance of the PID's. \nSet this smaller than the difference \nbetween measurements.")
        
        btn_tolerance.Bind(wx.EVT_BUTTON, self.save_tolerance)
        
        hbox.Add((0, -1))
        hbox.Add(text_tolerance, 0, wx.LEFT, 5)
        hbox.Add(edit_tolerance, 0, wx.LEFT, 25)
        hbox.Add(btn_tolerance, 0, wx.LEFT, 5)
        hbox.Add(text_guide, 0, wx.LEFT, 5)
        
        self.tolPanel.SetSizer(hbox)
        
    #end def  
    
    #--------------------------------------------------------------------------
    def save_tolerance(self, e):
        global tolerance
        tolerance = self.edit_tolerance.GetValue()
        if float(tolerance) > maxLimit:
            tolerance = str(maxLimit)
        if float(tolerance) < float(oscillation)/2 + 1:
            tolerance = str(float(oscillation)/2 + 1)
        if float(tolerance) >= int(oscillation):
            tolerance = str(float(oscillation)-1)
        self.text_tolerance.SetLabel(tolerance)
        tolerance = float(tolerance)
        
    #end def
    
    #--------------------------------------------------------------------------
    def measurementListBox(self):
        self.measurementPanel = wx.Panel(self, -1)
        hbox = wx.BoxSizer(wx.HORIZONTAL)        
        
        self.label_measurements = wx.StaticText(self, 
                                             label="Measurements (%s):"
                                             % self.celsius
                                             )        
        #self.label_measurements.SetFont(self.font2)
        
        self.listbox = wx.ListBox(self.measurementPanel, size=(75,100))
        hbox.Add(self.listbox, 1, wx.ALL, 5)
         
        btnPanel = wx.Panel(self.measurementPanel, -1)
        vbox = wx.BoxSizer(wx.VERTICAL)
        self.btn_new = new = wx.Button(btnPanel, ID_NEW, 'new', size=(60, 20))
        self.btn_ren = ren = wx.Button(btnPanel, ID_CHANGE, 'change', size=(60, 20))
        self.btn_dlt = dlt = wx.Button(btnPanel, ID_DELETE, 'delete', size=(60, 20))
        self.btn_clr = clr = wx.Button(btnPanel, ID_CLEAR, 'clear', size=(60, 20))
        
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
        hbox.Add(btnPanel, 0, wx.RIGHT, 5)
        
        text_guide = wx.StaticText(self.measurementPanel, label="List of measurement temperatures. \nEnter each temperature in order to set \nthe measurement program.")
        hbox.Add(text_guide, 0, wx.RIGHT, 5)
        
        self.measurementPanel.SetSizer(hbox)
        
    #end def
    
    #--------------------------------------------------------------------------
    def NewItem(self, event):
        text = wx.GetTextFromUser('Enter a new measurement', 'Insert dialog')
        if text != '':
            self.listbox.Append(text)
            
            time.sleep(0.02)
            
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
        hbox.Add(maxLimit_text, 0, wx.LEFT, 50)
        
        self.maxLimit_Panel.SetSizer(hbox)
    
    #end def
    
    #--------------------------------------------------------------------------
    def create_sizer(self):
      
        sizer = wx.GridBagSizer(8,2)
        sizer.Add(self.titlePanel, (0, 1), span=(1,2), flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_tc, (1, 1))
        sizer.Add(self.tcPanel, (1, 2))
        sizer.Add(self.label_osc, (2, 1))
        sizer.Add(self.oscPanel, (2, 2))       
        sizer.Add(self.label_tolerance, (3,1))
        sizer.Add(self.tolPanel, (3, 2))
        sizer.Add(self.label_measurements, (4,1))
        sizer.Add(self.measurementPanel, (4, 2))
        sizer.Add(self.maxLimit_Panel, (5, 1), span=(1,2))
        sizer.Add(self.linebreak4, (6,1),span = (1,2))
        sizer.Add(self.run_stopPanel, (7,1),span = (1,2), flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        self.SetSizer(sizer)
        
    #end def
    
    #--------------------------------------------------------------------------
    def post_process_data(self):
        try:
            # Post processing:
            Seebeck_Processing_v3.create_processed_files(filePath, finaldataFile, tc_type)
        except IndexError:
            wx.MessageBox('Not enough data for post processing to occur. \n\nIt is likely that we did not even complete any oscillations.', 'Error', wx.OK | wx.ICON_INFORMATION)
   
   #end def
        
    #--------------------------------------------------------------------------
    def enable_buttons(self):
        self.btn_check.Enable()
        self.btn_run.Enable()
        self.btn_osc.Enable()
        self.btn_tolerance.Enable()
        self.btn_new.Enable()
        self.btn_ren.Enable()
        self.btn_dlt.Enable()
        self.btn_clr.Enable()
        
        self.btn_stop.Disable()
        
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
        
        self.t=str(0)
        self.highV=str(0)
        self.lowV = str(0)
        self.tA=str(30)
        self.tB=str(30)
        self.pA=str(30)
        self.pB=str(30)
        self.pAset=str(30)
        self.pBset=str(30)
        
        self.create_title("Status Panel")
        self.linebreak1 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.create_status()
        self.linebreak2 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        
        self.linebreak3 = wx.StaticLine(self, pos=(-1,-1), size=(1,300), style=wx.LI_VERTICAL)
        
        # Updates from running program
        pub.subscribe(self.OnTime, "Time High Voltage")
        pub.subscribe(self.OnHighVoltage, "High Voltage")
        pub.subscribe(self.OnLowVoltage, "Low Voltage")
        pub.subscribe(self.OnTempA, "Temp A")
        pub.subscribe(self.OnTempB, "Temp B")
        pub.subscribe(self.OnPIDA, "PID A")
        pub.subscribe(self.OnPIDB, "PID B")
        pub.subscribe(self.OnPIDAset, "PID A SP")
        pub.subscribe(self.OnPIDBset, "PID B SP")   
        
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
        self.tA = '%.2f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnTempB(self, msg):
        self.tB = '%.2f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnPIDA(self, msg):
        self.pA = '%.2f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnPIDB(self, msg):
        self.pB = '%.2f'%(float(msg)) 
        self.update_values()  
    #end def
    
    #--------------------------------------------------------------------------
    def OnPIDAset(self, msg):
        self.pAset = '%.2f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnPIDBset(self, msg):
        self.pBset = '%.2f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnTime(self, msg):
        self.t = '%.2f'%(float(msg)) 
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
        self.label_t = wx.StaticText(self, label="Time (s):")
        self.label_t.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_highV = wx.StaticText(self, label="High Voltage (uV):")
        self.label_highV.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_lowV = wx.StaticText(self, label="Low Voltage (uV):")
        self.label_lowV.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_tA = wx.StaticText(self, label="Temp A (C):")
        self.label_tA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_tB = wx.StaticText(self, label="Temp B (C):")
        self.label_tB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_pA = wx.StaticText(self, label="PID A (C):")
        self.label_pA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_pB = wx.StaticText(self, label="PID B (C):")
        self.label_pB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_pAset = wx.StaticText(self, label="PID A SP (C):")
        self.label_pAset.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_pBset = wx.StaticText(self, label="PID B SP (C):")
        self.label_pBset.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        
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
        
        
    #end def
        
    #-------------------------------------------------------------------------- 
    def update_values(self):
        self.tcurrent.SetLabel(self.t)
        self.highVcurrent.SetLabel(self.highV)
        self.lowVcurrent.SetLabel(self.lowV)
        self.tAcurrent.SetLabel(self.tA)
        self.tBcurrent.SetLabel(self.tB)
        self.pAcurrent.SetLabel(self.pA)
        self.pBcurrent.SetLabel(self.pB)
        self.pAsetcurrent.SetLabel(self.pAset)
        self.pBsetcurrent.SetLabel(self.pBset)
    #end def
       
    #--------------------------------------------------------------------------
    def create_sizer(self):    
        sizer = wx.GridBagSizer(12,2)
        sizer.Add(self.titlePanel, (0, 0), span = (1,2), border=5, flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.linebreak1,(1,0), span = (1,2))
        sizer.Add(self.label_t, (2,0))
        sizer.Add(self.tcurrent, (2, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        sizer.Add(self.label_highV, (3, 0))
        sizer.Add(self.highVcurrent, (3, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_lowV, (4,0))
        sizer.Add(self.lowVcurrent, (4,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
          
        sizer.Add(self.label_tA, (5,0))
        sizer.Add(self.tAcurrent, (5,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_tB, (6,0))
        sizer.Add(self.tBcurrent, (6,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_pA, (7,0))
        sizer.Add(self.pAcurrent, (7,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_pAset, (8,0))
        sizer.Add(self.pAsetcurrent, (8,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_pB, (9,0))
        sizer.Add(self.pBcurrent, (9,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_pBset, (10,0))
        sizer.Add(self.pBsetcurrent, (10,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        sizer.Add(self.linebreak2, (11,0), span = (1,2))
        
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
        
        self.animator = animation.FuncAnimation(self.figure, self.draw_plot, interval=500, blit=True)
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
    #end def

    #--------------------------------------------------------------------------
    def OnHighVTime(self, msg):
        self.thighV = float(msg)   
        thighV_list.append(self.thighV)
    #end def

    #--------------------------------------------------------------------------
    def OnLowVoltage(self, msg):
        self.lowV = float(msg)
        lowV_list.append(self.lowV)    
    #end def

    #--------------------------------------------------------------------------
    def OnLowVTime(self, msg):
        self.tlowV = float(msg)   
        tlowV_list.append(self.tlowV)
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

        #self.subplot.text(0.05, .95, r'$X(f) = \mathcal{F}\{x(t)\}$', \
            #verticalalignment='top', transform = self.subplot.transAxes)
    #end def

    #--------------------------------------------------------------------------
    def draw_plot(self,i):
        self.subplot.clear()
        #self.subplot.set_title("voltage vs. time", fontsize=12)
        self.subplot.set_ylabel("voltage (uV)", fontsize = 8)
        self.subplot.set_xlabel("time (s)", fontsize = 8)
        self.subplot.set_xlim([0, 100])
        self.subplot.set_ylim([-1000, 1000])
        
        pylab.setp(self.subplot.get_xticklabels(), fontsize=8)
        pylab.setp(self.subplot.get_yticklabels(), fontsize=8)
        
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
        
        self.lineH, = self.subplot.plot(thighV_list,highV_list, color=self.colorH, linewidth=1)
        self.lineL, = self.subplot.plot(tlowV_list,lowV_list, color=self.colorL, linewidth=1)
        
        return (self.lineH, self.lineL)
        #return (self.subplot.plot( thighV_list, highV_list, color=self.colorH, linewidth=1),
            #self.subplot.plot( tlowV_list, lowV_list, color=self.colorL, linewidth=1))
        
    #end def
    
    #--------------------------------------------------------------------------
    def save_plot(self, msg):
        path = filePath + '/Raw Data/' + 'Plots/' + "Voltage_Plot.png"
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
        
        global ttempA_list
        global tempA_list
        global ttempB_list
        global tempB_list
        global tpidA_list
        global pidA_list
        global tpidB_list
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
        pub.subscribe(self.OnTimePIDA, "Time PID A")
        pub.subscribe(self.OnPIDA, "PID A")
        pub.subscribe(self.OnTimePIDB, "Time PID B")
        pub.subscribe(self.OnPIDB, "PID B")
        
        # For saving the plots at the end of data acquisition:
        pub.subscribe(self.save_plot, "Save_All")
        
        self.animator = animation.FuncAnimation(self.figure, self.draw_plot, interval=500, blit=True)
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
        ttempA_list.append(self.ttA)
    #end def
        
    #--------------------------------------------------------------------------
    def OnTempA(self, msg):
        self.tA = float(msg)
        tempA_list.append(self.tA)    
    #end def
    
    #--------------------------------------------------------------------------
    def OnTimeTempB(self, msg):
        self.ttB = float(msg)    
        ttempB_list.append(self.ttB)
    #end def
        
    #--------------------------------------------------------------------------
    def OnTempB(self, msg):
        self.tB = float(msg)
        tempB_list.append(self.tB)    
    #end def
    
    #--------------------------------------------------------------------------
    def OnTimePIDA(self, msg):
        self.tpA = float(msg)  
        tpidA_list.append(self.tpA)
    #end def
        
    #--------------------------------------------------------------------------
    def OnPIDA(self, msg):
        self.pA = float(msg)
        pidA_list.append(self.pA)    
    #end def
    
    #--------------------------------------------------------------------------
    def OnTimePIDB(self, msg):
        self.tpB = float(msg)    
        tpidB_list.append(self.tpB)
    #end def
        
    #--------------------------------------------------------------------------
    def OnPIDB(self, msg):
        self.pB = float(msg)
        pidB_list.append(self.pB)    
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
        self.linePA, = self.subplot.plot(tpidA_list,pidA_list, color=self.colorPA, linewidth=1)
        self.linePB, = self.subplot.plot(tpidB_list,pidB_list, color=self.colorPB, linewidth=1)
        

        #self.subplot.text(0.05, .95, r'$X(f) = \mathcal{F}\{x(t)\}$', \
            #verticalalignment='top', transform = self.subplot.transAxes)
    #end def

    #--------------------------------------------------------------------------
    def draw_plot(self,i):
        self.subplot.clear()
        #self.subplot.set_title("temperature vs. time", fontsize=12)
        self.subplot.set_ylabel("temperature (C)", fontsize = 8)
        self.subplot.set_xlabel("time (s)", fontsize = 8)
        self.subplot.set_xlim([0, 100])
        self.subplot.set_ylim([0, 500])
        
        pylab.setp(self.subplot.get_xticklabels(), fontsize=8)
        pylab.setp(self.subplot.get_yticklabels(), fontsize=8)
        
        # Adjustable scale:
        if self.xmax_control.is_auto():
            xmax = max(ttempA_list+ttempB_list+tpidA_list+tpidB_list)
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
        
        self.lineTA, = self.subplot.plot(ttempA_list,tempA_list, color=self.colorTA, linewidth=1)
        self.lineTB, = self.subplot.plot(ttempB_list,tempB_list, color=self.colorTB, linewidth=1)
        self.linePA, = self.subplot.plot(tpidA_list,pidA_list, color=self.colorPA, linewidth=1)
        self.linePB, = self.subplot.plot(tpidB_list,pidB_list, color=self.colorPB, linewidth=1)
        
        return (self.lineTA, self.lineTB, self.linePA, self.linePB)
        
    #end def
    
    #--------------------------------------------------------------------------
    def save_plot(self, msg):
        path = filePath + '/Raw Data/' + 'Plots/' + "Temperature_Plot.png"
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
        
        sizer = wx.GridBagSizer(2, 2)
        sizer.Add(self.userpanel, (0,0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.statuspanel, (1,0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.voltagepanel, (0,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.temperaturepanel, (1,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Fit(self)
        
        self.SetSizer(sizer)
        self.SetTitle('Seebeck GUI')
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
        self.statusbar.SetFieldsCount(13)
        self.SetStatusBar(self.statusbar)
        
        self.space_between = 10
        
        self.status_text = wx.StaticText(self.statusbar, -1, "Ready")
        self.width0 = 105
        
        placer1 = wx.StaticText(self.statusbar, -1, " ")
        
        oscillation_text = wx.StaticText(self.statusbar, -1, "Oscillation Indicators:")
        boldFont = wx.Font(9, wx.DEFAULT, wx.NORMAL, wx.BOLD)
        oscillation_text.SetFont(boldFont)
        self.width1 = oscillation_text.GetRect().width + self.space_between
        
        pidTol_text = wx.StaticText(self.statusbar, -1, "Within PID Tolerance:")
        self.width2 = pidTol_text.GetRect().width + self.space_between
        
        self.indicator_tol = wx.StaticText(self.statusbar, -1, "-")
        self.width3 = 25
        
        equilThresh_text = wx.StaticText(self.statusbar, -1, "Within Equilibrium Threshold:")
        self.width4 = equilThresh_text.GetRect().width + 5
        
        self.indicator_equil = wx.StaticText(self.statusbar, -1, "-")
        self.width5 = self.width3
        
        measurements_left_text = wx.StaticText(self.statusbar, -1, "Measurements Left Until Change:")
        self.width6 = measurements_left_text.GetRect().width + self.space_between
        
        self.indicator_measurements_left = wx.StaticText(self.statusbar, -1, "-")
        self.width7 = 40
        
        estimated_time_text = wx.StaticText(self.statusbar, -1, "Estimated Time Until Change:")
        self.width8 = estimated_time_text.GetRect().width + self.space_between
        
        self.indicator_estimated_time = wx.StaticText(self.statusbar, -1, "-")
        self.width9 = self.width7
        
        placer2 = wx.StaticText(self.statusbar, -1, " ")
        
        version_label = wx.StaticText(self.statusbar, -1, "Version: %s" % version)
        self.width10 = version_label.GetRect().width + self.space_between
        
        self.statusbar.SetStatusWidths([self.width0, 50, self.width1, self.width2, self.width3, self.width4, self.width5, self.width6, self.width7, self.width8, self.width9, -1, self.width10])
        
        self.statusbar.AddWidget(self.status_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
        self.statusbar.AddWidget(placer1)
        
        self.statusbar.AddWidget(oscillation_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
        self.statusbar.AddWidget(pidTol_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        self.statusbar.AddWidget(self.indicator_tol, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
        self.statusbar.AddWidget(equilThresh_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        self.statusbar.AddWidget(self.indicator_equil, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
        self.statusbar.AddWidget(measurements_left_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        self.statusbar.AddWidget(self.indicator_measurements_left, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
        self.statusbar.AddWidget(estimated_time_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        self.statusbar.AddWidget(self.indicator_estimated_time, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
        self.statusbar.AddWidget(placer2)
        
        self.statusbar.AddWidget(version_label, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
    #end def
        
    #--------------------------------------------------------------------------
    def update_statusbar(self, msg):
        string = msg
        
        if string == 'Running' or string == 'Finished, Ready' or string == 'Exception Occurred':
            self.status_text.SetLabel(string)
            self.status_text.SetBackgroundColour(wx.NullColour)
            
            if string == 'Exception Occurred':
                self.status_text.SetBackgroundColour("RED")
            #end if
        
        #end if
        
        elif string[-3:] == 'tol':
            self.indicator_tol.SetLabel(string[:2])
            
            if string[:2] == 'OK':
                self.indicator_tol.SetBackgroundColour("GREEN")
            else:
                self.indicator_tol.SetBackgroundColour("RED")
        
        #end elif
        
        elif string[-3:] == 'equ':
            self.indicator_equil.SetLabel(string[:2])
            
            if string[:2] == 'OK':
                self.indicator_equil.SetBackgroundColour("GREEN")
            else:
                self.indicator_equil.SetBackgroundColour("RED")
                
        #end elif
                
        elif string[-3:] == 'mea':
            self.indicator_measurements_left.SetLabel(string[:-3])
            
        #end elif
            
        elif string[-3:] == 'tim':
            self.indicator_estimated_time.SetLabel(string[:-3] + ' (s)')
            
        #end elif
         
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
        self.frame = Frame(parent=None, title="Voltage Panel", size=(1200,1200))
        self.frame.Show()
        
        setup = FakeSetup()
        return True
    #end init
    
#end class
###############################################################################

#==============================================================================
if __name__=='__main__':
    app = App()
    app.MainLoop()
    
#end if