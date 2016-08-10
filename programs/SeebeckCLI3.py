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
from SeebeckProcessingContinuous import SeebeckContinuousProcessing
#from PIDprogram_import import PID_Program_import
from PIDprogramrun import PIDrun
from PIDprogramstop import PIDstop

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
                time.sleep(.2)
                self.ctrl.write(":ROUTe:SCAN:LSELect NONE") # Stop Scan
                time.sleep(.05)
                data = self.ctrl.query(":FETCh?")
                time.sleep(.05)
                data = float(str(data)[0:15])
                break
            except ValueError as VE:
                print VE
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
        self.Setup()
        
        self.Get_User_Input()
        self.open_files()
        
        
        #start the PID program
        PIDrun(self.sampleApid,self.sampleBpid,self.blockApid,self.blockBpid)
        
        self.abort = 0
        self.start = time.time()
        self.backuptime = time.time()
        self.pidtime = time.time()
        self.time = time.time() - self.start
        self.delay = 0.1
        
        #data list initializaton
        self.time_list = []
        self.TA_list = []
        self.TB_list = []
        self.avgT_list = []
        self.dT_list = []
        self.Vch_list = []
        self.Val_list = []
        
        self.pidtime_list = []
        self.pidAsample_list = []
        self.pidAblock_list = []
        self.pidAsetpoint_list = []
        self.pidBsample_list = []
        self.pidBblock_list = []
        self.pidBsetpoint_list = []
        self.pidavgT_list = []
        self.piddT_list = []
        
        self.pid_measurement()
        self.safety_check()
        
        try:
            while True:
                self.seebeck_measurement()
                self.write_data_to_file()
                if time.time() - self.pidtime > 120:
                    self.pid_measurement()
                    self.safety_check()
                    self.pidtime = time.time()
                #end if
                if time.time() - self.backuptime > 900:
                    self.create_backup_file()
                    self.backuptime = time.time()
                #end if
                if self.abort == 1:
                    print '\n****\nprogram ended\nsaving files at current location\n****\n'
                    break
                #end if
            #end while
        #end try
        except KeyboardInterrupt:
            print '\n****\nprogram ended\nsaving files at current location\n****\n'
        self.save_files()
        print "Huzzah! Your program finished! You are awesome, sir or maam!"
        PIDstop(self.sampleApid,self.sampleBpid,self.blockApid,self.blockBpid)
        print 'processing data'
        self.processData()

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
        self.k2700.ctrl.write(":SENSe1:TEMPerature:TCouple:TYPE K") # Set ThermoCouple type
        self.k2700.ctrl.write(":SENSe1:FUNCtion 'TEMPerature', (@ 117,118)")
        self.k2700.ctrl.write(":SENSe1:FUNCtion 'VOLTage:DC', (@ 107,108)")
        self.k2700.ctrl.write(":TRIGger:SEQuence1:DELay 0")
        self.k2700.ctrl.write(":TRIGger:SEQuence1:COUNt 1")    # Set the count rate
        # Sets the the acquisition rate of the measurements
        self.k2700.ctrl.write(":SENSe1:VOLTage:DC:NPLCycles 5, (@ 107,108)") # Sets integration period based on frequency
        self.k2700.ctrl.write(":SENSe1:TEMPerature:NPLCycles 5, (@ 117,118)")
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
        while True:
            try:
                choices1 = '\n1: 200C\n2: 225C\n3: 250C\n4: 275C\n5: 300C\n6: 325C\n7: 350C\n8: 375C\n9: 400C\n10: 425C\n11: 450C\n12: 475C\n13: 500C\n'
                choices2 = '14: continuous\n15: other\n'
                profile = input('Which temperature profile? %s' % ( choices1 + choices2 ))
                if profile == 1:
                    self.profile=200
                    break
                elif profile == 2:
                    self.profile=225
                    break
                elif profile == 3:
                    self.profile=250
                    break
                elif profile == 4:
                    self.profile=275
                    break
                elif profile == 5:
                    self.profile=300
                    break
                elif profile == 6:
                    self.profile=325
                    break
                elif profile == 7:
                    self.profile=350
                    break
                elif profile == 8:
                    self.profile=375
                    break
                elif profile == 9:
                    self.profile=400
                    break
                elif profile == 10:
                    self.profile=425
                    break
                elif profile == 11:
                    self.profile=450
                    break
                elif profile == 12:
                    self.profile=475
                    break
                elif profile == 13:
                    self.profile = 500
                    break
                elif profile == 14:
                    self.profile='cont'
                    break
                elif profile == 15:
                    file = raw_input('You will have to process your data manually')
                    self.profile = 'other'
                    break
                print 'try again' 
            except NameError:
                print 'try again'
        #end while
        
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
        self.pidfile = open('PID_Data.csv','w')
    
        begin = datetime.now() # Current date and time
        self.datafile.write('Start Time: ' + str(begin) + '\n')
        self.statusfile.write('Start Time: ' + str(begin) + '\n')

        dataheaders = 'time (s),tempA (C),tempB (C),avgtemp (C),deltatemp (C),Vchromel (uV),Valumel (uV)\n'
        self.datafile.write(dataheaders)

        statusheaders1 = 'time (s),tempA1 (C),tempA2 (C),tempB1 (C),tempB2 (C),'
        statusheaders2 = 'chromelvoltagecalc1 (uV),chromelvoltagecalc2 (uV),chromelvoltagecalc1 (uV),chromelvoltagecalc2 (uV)\n'
        self.statusfile.write(statusheaders1 + statusheaders2)
        
        pidheaders = 'time,sampletempA,blocktempA,setpointA,sampletempB,blocktempB,setpointB,avgT,dT\n'
        self.pidfile.write(pidheaders)
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
    def pid_measurement(self):
        print '\ntake data from pid controller'
        while True:
            try:
                time.sleep(0.1)
                # Take temp data
                self.sampletempA = float(self.sampleApid.get_pv())
                self.samplesetpointA = float(self.sampleApid.get_setpoint())
                self.blocktempA = float(self.blockApid.get_pv())
                break
            #end try
            except IOError:
                print IOError
            #end except
        #end while
        self.time_pidA = time.time() - self.start
        print "sampletempA: %.2f C\tblocktempA: %.2f\tsetpointA: %.2f C" % (self.sampletempA,self.blocktempA,self.samplesetpointA)
        
        time.sleep(self.delay)
        while True:
            try:
                time.sleep(0.1)
                # Take temp data
                self.sampletempB = float(self.sampleBpid.get_pv())
                self.samplesetpointB = float(self.sampleBpid.get_setpoint())
                self.blocktempB = float(self.blockBpid.get_pv())
                break
            #end try
            except IOError:
                print IOError
            #end except
        #end while
        self.time_pidB = time.time() - self.start
        print "sampletempB: %.2f C\tblocktempB: %.2f\tsetpointB: %.2f C" % (self.sampletempB,self.blocktempB,self.samplesetpointB)
        
        while True:
            try:
                time.sleep(0.1)
                # Take temp data
                self.pidArunning = self.sampleApid.is_running()
                self.pidBrunning = self.sampleBpid.is_running()
                break
            #end try
            except IOError:
                print IOError
            #end except
        #end while
        if self.pidArunning == False and self.pidBrunning == False:
            self.abort = 1
        #end if
        
        Time = ( self.time_pidA + self.time_pidB ) / 2
        avgT = ( self.sampletempA + self.sampletempB ) / 2
        dT = (self.sampletempA - self.sampletempB)
        
        self.pidtime_list.append(Time)
        self.pidAsample_list.append(self.sampletempA)
        self.pidAblock_list.append(self.blocktempA)
        self.pidAsetpoint_list.append(self.samplesetpointA)
        self.pidBsample_list.append(self.sampletempB)
        self.pidBblock_list.append(self.blocktempB)
        self.pidBsetpoint_list.append(self.samplesetpointB)
        self.pidavgT_list.append(avgT)
        self.piddT_list.append(dT)
        
        print 'write pid data to file\n'
        self.pidfile.write('%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f,%.2f\n'%(Time,self.sampletempA,self.blocktempA,self.samplesetpointA,self.sampletempB,self.blocktempB,self.samplesetpointB,avgT,dT))
    #end def
    
    #--------------------------------------------------------------------------
    def seebeck_measurement(self):
        # Takes and writes to file the data on the Keithley
        # The only change between blocks like this one is the specific
        # channel on the Keithley that is being measured.
        t,ct = self.getTime()
        print '\ncurrent time: %s\nrun time: %s\n' % (ct, t)
        
        self.TempA = float(self.k2700.fetch('117'))
        self.time_TempA = time.time() - self.start
        print "temp A: %f C" % (self.TempA)

        time.sleep(self.delay)

        self.TempB = float(self.k2700.fetch('118'))
        self.time_TempB = time.time() - self.start
        print "temp B: %f C" % (self.TempB)

        time.sleep(self.delay)

        self.Vchromelraw = float(self.k2700.fetch('107'))*10**6
        self.Vchromelcalc = self.voltage_Correction(self.Vchromelraw,self.TempA,self.TempB, 'chromel')
        self.time_Vchromel = time.time() - self.start
        print "voltage (Ch): %f uV" % (self.Vchromelcalc)

        time.sleep(self.delay)

        self.Valumelraw = float(self.k2700.fetch('108'))*10**6
        self.Valumelcalc = self.voltage_Correction(self.Valumelraw,self.TempA,self.TempB, 'alumel')
        self.time_Valumel = time.time() - self.start
        print "voltage (Al): %f uV" % (self.Valumelcalc)

        time.sleep(self.delay)

        self.Valumelraw2 = float(self.k2700.fetch('108'))*10**6
        self.Valumelcalc2 = self.voltage_Correction(self.Valumelraw2,self.TempA,self.TempB, 'alumel')
        self.time_Valumel2 = time.time() - self.start
        print "voltage (Al): %f uV" % (self.Valumelcalc2)

        time.sleep(self.delay)

        self.Vchromelraw2 = float(self.k2700.fetch('107'))*10**6
        self.Vchromelcalc2 = self.voltage_Correction(self.Vchromelraw2,self.TempA,self.TempB, 'chromel')
        self.time_Vchromel2 = time.time() - self.start
        print "voltage (Ch): %f uV" % (self.Vchromelcalc2)

        time.sleep(self.delay)

        self.TempB2 = float(self.k2700.fetch('118'))
        self.time_TempB2 = time.time() - self.start
        print "temp B: %f C" % (self.TempB2)

        time.sleep(self.delay)

        self.TempA2 = float(self.k2700.fetch('117'))
        self.time_TempA2 = time.time() - self.start
        print "temp A: %f C" % (self.TempA2)
        
        self.time = ( self.time_TempA + self.time_TempB + self.time_Vchromel + self.time_Valumel + self.time_Valumel2 + self.time_Vchromel2 + self.time_TempB2 + self.time_TempA2 ) / 8
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
        self.statusfile.write('%.2f,%.2f,%.2f,%.2f,' %(self.TempA,self.TempA2,self.TempB,self.TempB2))
        self.statusfile.write('%.3f,%.3f,%.3f,%.3f\n'%(self.Vchromelcalc, self.Vchromelcalc2,self.Valumelcalc, self.Valumelcalc2))

        print('Write data to file')
        ta = self.slopemethod(self.TempA,self.TempA2,self.time_TempA,self.time_TempA2,self.time)
        tb = self.slopemethod(self.TempB,self.TempB2,self.time_TempB,self.time_TempB2,self.time)
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
        if self.sampletempA >650:
            self.abort = 1
            print 'Safety Failure: Sample Temp A greater than 600'
        #end if
        if self.sampletempB > 650:
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
        if self.blocktempA > self.sampletempA + 100:
            self.abort = 1
            print 'Safety Failure: Block Temp A  100 C greater than Sample Temp A'
        #end if
        if self.blocktempB > self.sampletempB + 100:
            self.abort = 1
            print 'Safety Failure: Block Temp B  100 C greater than Sample Temp B'
        #end if
        if self.sampletempA > self.blocktempA + 100:
            self.abort = 1
            print 'Safety Failure: Sample Temp A  100 C greater than Block Temp A'
        #end if
        if self.sampletempB > self.blocktempB + 100:
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
        tempfile.write('time,tempA,tempB,avgT,dT,Vch,Val\n')
        for i in range(len(self.time_list)):
            tempfile.write('%.3f,%.4f,%.4f,%.4f,%.4f,%.6f,%.6f\n'%(self.time_list[i],self.TA_list[i],self.TB_list[i],self.avgT_list[i],self.dT_list[i],self.Vch_list[i],self.Val_list[i]))
        #end for
        tempfile.close()
        
        tempfile2 = open('Seebeck Backup Files/pidbackup_%.0f.csv'%self.time ,'w')
        tempfile2.write('pidbackup,%.0f\n' % self.time )
        tempfile2.write('time,sampletempA,blocktempA,setpointA,sampletempB,blocktempB,setpointB,avgT,dT\n')
        for i in range(len(self.pidtime_list)):
            tempfile2.write('%.3f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.6f,%.6f\n'%(self.pidtime_list[i],self.pidAsample_list[i],self.pidAblock_list[i],self.pidAsetpoint_list[i],self.pidBsample_list[i],self.pidBblock_list[i],self.pidBsetpoint_list[i],self.pidavgT_list[i],self.piddT_list[i]))
        #end for
        tempfile2.close()
    #end def

    #--------------------------------------------------------------------------
    def save_files(self):
        print('\nSave Files\n')
        self.datafile.close()
        self.statusfile.close()
        self.pidfile.close()
    #end def
    
    #--------------------------------------------------------------------------
    def processData(self):
        print "\n*** Processing Data ***\n"
        if self.profile == 200:
            measureList = [50,60,70,80,90,100,110,120,130,140,150,160,170,180,190,200,190,180,170,160,150,140,130,120,110,100,90,80,70,60,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 225:
            measureList = [50,62,74,86,98,110,122,134,146,158,170,182,194,206,218,225,218,206,194,182,170,158,146,134,122,110,98,86,74,62,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 250:
            measureList = [50,64,78,92,106,120,134,148,162,176,190,204,218,232,246,250,246,232,218,204,190,176,162,148,134,120,106,92,78,64,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 275:
            measureList = [50,65,80,95,110,125,140,155,170,185,200,215,230,245,260,275,260,245,230,215,200,185,170,155,140,125,110,95,80,65,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 300:
            measureList = [50,67,84,101,118,135,152,169,186,203,220,237,254,271,288,300,288,271,254,237,220,203,186,169,152,135,118,101,84,67,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 325:
            measureList = [50,69,88,107,126,145,164,183,202,221,240,259,278,297,316,325,316,297,278,259,240,221,202,183,164,145,126,107,88,69,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 350:
            measureList = [50,70,90,110,130,150,170,190,210,230,250,270,290,310,330,350,330,310,290,270,250,230,210,190,170,150,130,110,90,70,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 375:
            measureList = [50,72,94,116,138,160,182,204,226,248,270,292,314,336,358,375,358,336,314,292,270,248,226,204,182,160,138,116,94,72,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 400:
            measureList = [50,74,98,122,146,170,194,218,242,266,290,314,338,362,386,400,386,362,338,314,290,266,242,218,194,170,146,122,98,74,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 425:
            measureList = [50,75,100,125,150,175,200,225,250,275,300,325,350,375,400,425,400,375,350,325,300,275,250,225,200,175,150,125,100,75,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 450:
            measureList = [50,77,104,131,158,185,212,239,266,293,320,347,374,401,428,450,428,401,374,347,320,293,266,239,212,185,158,131,104,77,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 475:
            measureList = [50,79,108,137,166,195,224,253,282,311,340,369,398,427,456,475,456,427,398,369,340,311,282,253,224,195,166,137,108,79,50]
            SeebeckProcessing(self.filePath,measureList)
        #end if
        elif self.profile == 500:
            measureList = [50,80,110,140,170,200,230,260,290,320,350,380,410,440,470,500,470,440,410,380,350,320,290,260,230,200,170,140,110,80,50]
            SeebeckProcessing(self.filePath,measureList)
        #end elif
        elif self.profile == 'cont':
            SeebeckContinuousProcessing(self.filePath)
        else:
            print "You'll need to process the data manually"
    #end def
    
#end class
###############################################################################

#==============================================================================
if __name__=='__main__':
    runprogram = Main()
#end if