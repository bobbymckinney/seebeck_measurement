#! /usr/bin/python
# -*- coding: utf-8 -*-
"""
Created: 2016-02-09
@author: Bobby McKinney (bobbymckinney@gmail.com)
"""
import os
import numpy as np
import matplotlib.pyplot as plt
import minimalmodbus as modbus # For communicating with the cn7500s
import omegacn7500 # Driver for cn7500s under minimalmodbus, adds a few easy commands
import visa # pyvisa, essential for communicating with the Keithley
import time
from datetime import datetime # for getting the current date and time
import exceptions

from SeebeckProcessing import SeebeckProcessing
from SeebeckProcessingRT import SeebeckProcessingRT
from PIDprogramset2 import PID_Program_Set

#==============================================================================
version = '1.0 (2016-02-25)'

# Keeps Windows from complaining that the port is already open:
modbus.CLOSE_PORT_AFTER_EACH_CALL = True

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
                time.sleep(.1)
                self.ctrl.write(":ROUTe:SCAN:LSELect NONE") # Stop Scan
                time.sleep(.1)
                data = self.ctrl.query(":FETCh?")
                time.sleep(.1)
                data = float(str(data)[0:15])
                break
            except IOError as IE:
                print IE
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
class Main:
    def __init__(self):
        
        self.Get_User_Input()
        self.open_files()
        self.Setup()
        #self.setPID()
        
        self.abort = 0
        self.start = time.time()
        self.backuptime = time.time()
        self.time = time.time() - self.start
        self.delay = 0.1
        '''
        while True:
            try:
                self.sampleApid.run()
                self.sampleBpid.run()
                break
            except IOError:
                print IOError
        #end while
        '''
        #data list initializaton
        self.time_list = []
        self.TA_list = []
        self.TB_list = []
        self.SPA_list = []
        self.SPB_list = []
        self.avgT_list = []
        self.dT_list = []
        self.Vch_list = []
        self.Val_list = []
        
        self.endtimer = '-'
        
        try:
            while True:
                self.seebeck_measurement()
                self.write_data_to_file()
                if time.time() - self.backuptime > 900:
                    self.create_backup_file()
                    self.backuptime = time.time()
                #end if
                self.safety_check()
                if self.abort == 1:
                    break
                #end if
            #end while
        #end try
        except KeyboardInterrupt:
            print '\n****\nprogram ended\nsaving files at current location\n****\n'
        self.save_files()
        print "Huzzah! Your program finished! You are awesome, sir or maam!"
        
        print 'processing data'
        self.processData()
        
        while True:
            try:
                self.sampleApid.stop()
                time.sleep(0.1)
                break
            except IOError:
                print IOError
        #end while
        while True:
            try:
                self.sampleBpid.stop()
                time.sleep(0.1)
                break
            except IOError:
                print IOError
        #end while

    #end def
    #--------------------------------------------------------------------------
    def Setup(self):
        """
        Prepare the Keithley to take data on the specified channels:
        """
        # Define Keithley instrument port:
        self.k2700 = Keithley_2700('GPIB0::1::INSTR')
        # Define the ports for the PID
        self.sampleApid = PID('/dev/cu.usbserial', 1) # Top heater
        self.sampleBpid = PID('/dev/cu.usbserial', 2) # Bottom heater
        self.blockApid = PID('/dev/cu.usbserial', 3) # Top block
        self.blockBpid = PID('/dev/cu.usbserial', 4) # Top block


        """
        Prepare the Keithley for operation:
        """
        self.k2700.openAllChannels
        # Define the type of measurement for the channels we are looking at:
        self.k2700.ctrl.write(":SENSe1:FUNCtion 'VOLTage:DC', (@ 107,108)")
        self.k2700.ctrl.write(":TRIGger:SEQuence1:DELay 0")
        self.k2700.ctrl.write(":TRIGger:SEQuence1:COUNt 1")    # Set the count rate
        # Sets the the acquisition rate of the measurements
        self.k2700.ctrl.write(":SENSe1:VOLTage:DC:NPLCycles 4, (@ 107,108)") # Sets integration period based on frequency
    #end def
    #--------------------------------------------------------------------------
    def Get_User_Input(self):
        print "Get Input From User"
        print "Your data folder will be saved to Desktop automatically"
        self.folder_name = raw_input("Please enter name for folder: ")
        self.folder_name = str(self.folder_name)
        if self.folder_name == '':
            date = str(datetime.now())
            self.folder_name = 'Seebeck_Data %s.%s.%s' % (date[0:13], date[14:16], date[17:19])
        #end if
        self.make_new_folder(self.folder_name)
    #end def
    
    #--------------------------------------------------------------------------
    def make_new_folder(self, folder_name):
        self.filePath = "/Users/tobererlab1/Desktop/" + folder_name
        found = False
        if not os.path.exists(self.filePath):
            os.makedirs(self.filePath)
            os.chdir(self.filePath)
        #end if
        else:
            n = 1
            while found == False:
                path = self.filePath + ' - ' + str(n)
                if os.path.exists(path):
                    n = n + 1
                #end if
                else:
                    os.makedirs(path)
                    os.chdir(path)
                    n = 1
                    found = True
                #end else
            #end while
        #end else
        if found == True:
            self.filePath = path
        #end if
    #end def
    
    #--------------------------------------------------------------------------
    def open_files(self):
        self.datafile = open('Data.csv', 'w') # opens file for writing/overwriting
        self.statusfile = open('Status.csv','w')
    
        begin = datetime.now() # Current date and time
        self.datafile.write('Start Time: ' + str(begin) + '\n')
        self.statusfile.write('Start Time: ' + str(begin) + '\n')

        dataheaders = 'time (s),tempA (C),tempB (C),avgtemp (C),deltatemp (C),Vchromel (uV),Valumel (uV)\n'
        self.datafile.write(dataheaders)

        statusheaders1 = 'time (s),sampletempA1 (C),sampletempA2 (C),samplesetpointA (C),blocktempA (C),sampletempB1 (C),sampletempB2 (C),samplesetpointB (C),blocktempB (C),'
        statusheaders2 = 'chromelvoltagecalc1 (uV),chromelvoltagecalc2 (uV),chromelvoltagecalc1 (uV),chromelvoltagecalc2 (uV)\n'
        self.statusfile.write(statusheaders1 + statusheaders2)
    #end def
    
    #--------------------------------------------------------------------------
    def setPID(self):
        displayprogram = raw_input('Would you like to see the current PID programs? (y or n): ' )
        if displayprogram == 'y' or displayprogram == 'Y':
            for pattern in range(8):
                print '\nHere are your pattern values for PIDA for pattern %d' % (pattern)
                print self.sampleApid.get_all_pattern_variables(pattern)
                print '\n'
                
                print '\nHere are your pattern values for PIDB for pattern %d' % (pattern)
                print self.sampleBpid.get_all_pattern_variables(pattern)
                print '\n'
            #end for
        #end if
        setprogram = raw_input('Would you like to change the PID program? (y or n): ')
        if setprogram == 'y' or setprogram == 'Y':
            while True:
                PID_Program_Set()
                programset = raw_input('Are you satisfied with the program? (y or n): ')
                if not (programset == 'n' or programset == 'N'):
                    break
                #end if
            #end while
        #end if
    #end def

    #--------------------------------------------------------------------------
    def getTime(self):
        hours = int((time.time()-self.start)/3600)
        minutes = int((time.time()-self.start)%3600/60)
        if (minutes < 10):
            minutes = '0%i'%(minutes)
        else:
            minutes = '%i'%(minutes)
        seconds = int((time.time()-self.start)%60)
        if (seconds < 10):
            seconds = '0%i'%(seconds)
        else:
            seconds = '%i'%(seconds)
        ctime = str(datetime.now())[11:19]
        
        return '%s:%s:%s'%(hours,minutes,seconds), ctime
    #end def

    #--------------------------------------------------------------------------
    def seebeck_measurement(self):
        # Takes and writes to file the data on the Keithley
        # The only change between blocks like this one is the specific
        # channel on the Keithley that is being measured.
        t,ct = self.getTime()
        print '\ncurrent time: %s\nrun time: %s\n' % (ct, t)
        
        try:
            # Take temp data
            self.sampletempA = float(self.sampleApid.get_pv())
            self.samplesetpointA = float(self.sampleApid.get_setpoint())
            self.blocktempA = float(self.blockApid.get_pv())
        #end try
        except exceptions.ValueError as VE:
            print(VE)
            self.sampletempA = float(self.sampleApid.get_pv())
            self.samplesetpointA = float(self.sampleApid.get_setpoint())
            self.blocktempA = float(self.blockApid.get_pv())
        #end except
        self.time_sampletempA = time.time() - self.start
        print "sampletempA: %.2f C\tblocktempA: %.2f\tsetpointA: %.2f C" % (self.sampletempA,self.blocktempA,self.samplesetpointA)

        time.sleep(self.delay)

        try:
            # Take temp data
            self.sampletempB = float(self.sampleBpid.get_pv())
            self.samplesetpointB = float(self.sampleBpid.get_setpoint())
            self.blocktempB = float(self.blockBpid.get_pv())
        #end try
        except exceptions.ValueError as VE:
            print(VE)
            self.sampletempB = float(self.sampleBpid.get_pv())
            self.samplesetpointB = float(self.sampleBpid.get_setpoint())
            self.blocktempB = float(self.blockBpid.get_pv())
        #end except
        self.time_sampletempB = time.time() - self.start
        print "sampletempB: %.2f C\tblocktempB: %.2f\tsetpointB: %.2f C" % (self.sampletempB,self.blocktempB,self.samplesetpointB)

        time.sleep(self.delay)

        self.Vchromelraw = float(self.k2700.fetch('107'))*10**6
        self.Vchromelcalc = self.voltage_Correction(self.Vchromelraw,self.sampletempA,self.sampletempB, 'chromel')
        self.time_Vchromel = time.time() - self.start
        print "voltage (Ch): %f uV" % (self.Vchromelcalc)

        time.sleep(self.delay)

        self.Valumelraw = float(self.k2700.fetch('108'))*10**6
        self.Valumelcalc = self.voltage_Correction(self.Valumelraw,self.sampletempA,self.sampletempB, 'alumel')
        self.time_Valumel = time.time() - self.start
        print "voltage (Al): %f uV" % (self.Valumelcalc)

        time.sleep(self.delay)

        self.Valumelraw2 = float(self.k2700.fetch('108'))*10**6
        self.Valumelcalc2 = self.voltage_Correction(self.Valumelraw2,self.sampletempA,self.sampletempB, 'alumel')
        self.time_Valumel2 = time.time() - self.start
        print "voltage (Al): %f uV" % (self.Valumelcalc2)

        time.sleep(self.delay)

        self.Vchromelraw2 = float(self.k2700.fetch('107'))*10**6
        self.Vchromelcalc2 = self.voltage_Correction(self.Vchromelraw2,self.sampletempA,self.sampletempB, 'chromel')
        self.time_Vchromel2 = time.time() - self.start
        print "voltage (Ch): %f uV" % (self.Vchromelcalc2)

        time.sleep(self.delay)

        try:
            # Take temp data
            self.sampletempB2 = float(self.sampleBpid.get_pv())
            self.samplesetpointB = float(self.sampleBpid.get_setpoint())
            self.blocktempB = float(self.blockBpid.get_pv())
        #end try
        except exceptions.ValueError as VE:
            print(VE)
            self.sampletempB2 = float(self.sampleBpid.get_pv())
            self.samplesetpointB = float(self.sampleBpid.get_setpoint())
            self.blocktempB = float(self.blockBpid.get_pv())
        #end except
        self.time_sampletempB2 = time.time() - self.start
        print "sampletempB: %.2f C\tblocktempB: %.2f\tsetpointB: %.2f C" % (self.sampletempB,self.blocktempB,self.samplesetpointB)

        time.sleep(self.delay)

        try:
            # Take temp data
            self.sampletempA2 = float(self.sampleApid.get_pv())
            self.samplesetpointA = float(self.sampleApid.get_setpoint())
            self.blocktempA = float(self.blockApid.get_pv())
        #end try
        except exceptions.ValueError as VE:
            print(VE)
            self.sampletempA2 = float(self.sampleApid.get_pv())
            self.samplesetpointA = float(self.sampleApid.get_setpoint())
            self.blocktempA = float(self.blockApid.get_pv())
        #end except
        self.time_sampletempA2 = time.time() - self.start
        print "sampletempA: %.2f C\tblocktempA: %.2f\tsetpointA: %.2f C" % (self.sampletempA,self.blocktempA,self.samplesetpointA)
        
        self.time = ( self.time_sampletempA + self.time_sampletempB + self.time_Vchromel + self.time_Valumel + self.time_Valumel2 + self.time_Vchromel2 + self.time_sampletempB2 + self.time_sampletempA2 ) / 8
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
        #end else

        return alpha

    #end def

    #--------------------------------------------------------------------------
    def write_data_to_file(self):
        self.statusfile.write('%.1f,'%(self.time))
        self.statusfile.write('%.2f,%.2f,%.2f,%.2f,' %(self.sampletempA,self.sampletempA2,self.samplesetpointA,self.blocktempA))
        self.statusfile.write('%.2f,%.2f,%.2f,%.2f,' %(self.sampletempB,self.sampletempB2,self.samplesetpointB,self.blocktempB))
        self.statusfile.write('%.3f,%.3f,%.3f,%.3f\n'%(self.Vchromelcalc, self.Vchromelcalc2,self.Valumelcalc, self.Valumelcalc2))

        print('Write data to file')
        ta = self.slopemethod(self.sampletempA,self.sampletempA2,self.time_sampletempA,self.time_sampletempA2,self.time)
        tb = self.slopemethod(self.sampletempB,self.sampletempB2,self.time_sampletempB,self.time_sampletempB2,self.time)
        avgt = (ta + tb)/2
        dt = ta-tb
        vchromel = self.slopemethod(self.Vchromelcalc,self.Vchromelcalc2,self.time_Vchromel,self.time_Vchromel2,self.time)
        valumel = self.slopemethod(self.Valumelcalc,self.Valumelcalc2,self.time_Valumel,self.time_Valumel2,self.time)
        self.datafile.write('%.3f,' %(self.time))
        self.datafile.write('%.4f,%.4f,%.4f,%.4f,' % (ta, tb, avgt, dt) )
        self.datafile.write('%.6f,%.6f\n' % (vchromel,valumel))
        
        self.time_list.append(self.time)
        self.TA_list.append(ta)
        self.TB_list.append(tb)
        self.SPA_list.append(self.samplesetpointA)
        self.SPB_list.append(self.samplesetpointB)
        self.avgT_list.append(avgt)
        self.dT_list.append(dt)
        self.Vch_list.append(vchromel)
        self.Val_list.append(valumel)
    #end def
    
    #--------------------------------------------------------------------------
    def slopemethod(self, val1, val2, t1, t2, t0):
        m = (val2 - val1) / (t2 - t1)
        val0 = m * (t0 - t1) + val1
        return val0
    #end def

    #--------------------------------------------------------------------------
    def safety_check(self):
        print 'safety check'
        if self.sampletempA >650 or self.sampletempA2 > 650:
            self.abort = 1
            print 'Safety Failure: Sample Temp A greater than 600'
        #end if
        if self.sampletempB > 650 or self.sampletempA2 > 650:
            self.abort = 1
            print 'Safety Failure: Sample Temp B greater than Max Limit'
        #end if
        if self.blocktempA > 650:
            self.abort = 1
            print 'Safety Failure: Block Temp A greater than Max Limit'
        #end if
        if self.blocktempB > 650:
            self.abort = 1
            print 'Safety Failure: Block Temp B greater than Max Limit'
        #end if
        if self.blocktempA > self.sampletempA + 100 or self.blocktempA > self.sampletempA2 + 100:
            self.abort = 1
            print 'Safety Failure: Block Temp A  100 C greater than Sample Temp A'
        #end if
        if self.blocktempB > self.sampletempB + 100 or self.blocktempB > self.sampletempB2 + 100:
            self.abort = 1
            print 'Safety Failure: Block Temp B  100 C greater than Sample Temp B'
        #end if
        if self.sampletempA > self.blocktempA + 100 or self.sampletempA2 > self.blocktempA + 100:
            self.abort = 1
            print 'Safety Failure: Sample Temp A  100 C greater than Block Temp A'
        #end if
        if self.sampletempB > self.blocktempB + 100 or self.sampletempB2 > self.blocktempB + 100:
            self.abort = 1
            print 'Safety Failure: Sample Temp B  100 C greater than Block Temp B'
        #end if
        
        
        #kill the PID's
        if self.abort == 1:
            print 'KILL EVERYTHING!!!'
            self.sampleApid.stop()
            self.sampleBpid.stop()
        #end if
    #end def
    
    #--------------------------------------------------------------------------
    def create_backup_file(self):
        print '\n***\ncreate backup file\n***\n'
        backup_folder = self.filePath + '/Seebeck Backup Files/'
        if not os.path.exists(backup_folder):
            os.makedirs(backup_folder)
        #end if
        tempfile = open('Seebeck Backup Files/databackup_%.0f.csv'%self.time ,'w')
        tempfile.write('databackup,%.0f\n' % self.time )
        tempfile.write('time,tempA,setpointA,tempB,setpointB,avgT,dT,Vch,Val\n')
        for i in range(len(self.time_list)):
            tempfile.write('%.3f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.6f,%.6f\n'%(self.time_list[i],self.TA_list[i],self.SPA_list[i],self.TB_list[i],self.SPB_list[i],self.avgT_list[i],self.dT_list[i],self.Vch_list[i],self.Val_list[i]))
        #end for
        tempfile.close()
    #end def

    #--------------------------------------------------------------------------
    def save_files(self):
        print('\nSave Files\n')
        self.datafile.close()
        self.statusfile.close()
    #end def
    
    #--------------------------------------------------------------------------
    def processData(self):
        while True:
            try:
                measuretype = input('What type of measurement?\n1: Room Temp\n2: High Temp\n')
                if measuretype == 1 or measuretype == 2:
                    break
                print 'try again' 
            except NameError:
                print 'try again'
        #end while
        if measuretype == 1:
            while True:
                try:
                    measuretemp = input("Please enter the measurement temp: ")
                    if measuretemp > 25 and measuretemp < 75:
                        break
                    #end if
                    print 'try again'
                except NameError:
                    print 'try again'
            #end while
            SeebeckProcessingRT(self.filePath,measuretemp)
        #end if
        elif measuretype == 2:
            measureList = []
            print '\nYou will need to enter the temperature values that you would like to process.'
            while True:    
                while True:
                    try: 
                        maxtemp = input('Please enter the maximum measurement temp: ')
                        if maxtemp > 50 and maxtemp < 625:
                            break
                        else: 
                            print 'try again'
                    except NameError:
                        print 'try again'
                #end while
                while True:
                    try: 
                        tempinc = input('Please enter the measurement temperature increment: ')
                        if tempinc > 10 and tempinc < 125:
                            break
                        else: 
                            print 'try again'
                    except NameError:
                        print 'try again'
                #end while
                measureList.append(50)
                while measureList[-1] < maxtemp:
                    measureList.append(measureList[-1] + tempinc)
                #end while
                while measureList[-1] > 50:
                    measureList.append(measureList[-1] - tempinc)
                #end while
                print 'Process temperatures:\n',measureList
        
                correct = raw_input('Is your list correct (y or n)? ')
            
                if correct != 'n':
                    break
                #end if
            #end while
            SeebeckProcessing(self.filePath,measureList)
        #end if
        
    #end def
    
#end class
###############################################################################

#==============================================================================
if __name__=='__main__':
    runprogram = Main()
#end if