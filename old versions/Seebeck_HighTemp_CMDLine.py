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

#==============================================================================
version = '1.0 (2016-02-09)'

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
class Main:
    def __init__(self):
        
        self.Get_User_Input()
        self.open_files()
        self.Setup()
        
        self.abort_ID = 0
        self.start = time.time()
        self.delay = 1.0
        self.plotnumber = 0
        try:
            for self.avgtemp in self.measureList:
                self.dT = 0
                self.plotnumber +=1
                self.timecalclist = []
                self.Vchromelcalclist = []
                self.Valumelcalclist = []
                self.dTcalclist = []
                self.avgTcalclist = []
                print "\n****\nSet avg temp to %f C\n****" %(self.avgtemp)
                print "set sample A temp to %f" %(self.avgtemp)
                while True:
                    try:
                        self.sampleApid.set_setpoint(self.avgtemp)
                        break
                    except IOError:
                        print 'IOError: communication failure'
                #end while
                print "set sample B temp to %f" %(self.avgtemp)
                while True:
                    try:
                        self.sampleBpid.set_setpoint(self.avgtemp)
                        break
                    except IOError:
                        print 'IOError: communication failure'
                #end while
                self.recenttempA = []
                self.recenttempAtime=[]
                self.recenttempB = []
                self.recenttempBtime=[]
                self.stabilityA = '-'
                self.stabilityB = '-'
            
                while True:
                    self.data_measurement()
                    self.write_data_to_file('status')
                    time.sleep(5)
                    if self.abort_ID==1: break
                    if (self.tol == 'OK' and self.stable == 'OK'):
                        for self.dT in self.dTlist:
                            print "\n****\nSet delta temp to %f C\n\n" %(self.dT)
                            print "set sample A temp to %f" %(self.avgtemp+self.dT/2.0)
                            while True:
                                try:
                                    self.sampleApid.set_setpoint(self.avgtemp+self.dT/2.0)
                                    break
                                except IOError:
                                    print 'IOError: communication failure'
                            #end while
                            print "set sample B temp to %f" %(self.avgtemp-self.dT/2.0)
                            while True:
                                try:
                                    self.sampleBpid.set_setpoint(self.avgtemp-self.dT/2.0)
                                    break
                                except IOError:
                                    print 'IOError: communication failure'
                            #end while
                            self.recenttempA = []
                            self.recenttempAtime=[]
                            self.recenttempB = []
                            self.recenttempBtime=[]
                            self.stabilityA = '-'
                            self.stabilityB = '-'

                            while True:
                                self.data_measurement()
                                self.write_data_to_file('status')
                                time.sleep(3)
                                if self.abort_ID==1: break
                                if (self.tol == 'OK' and self.stable == 'OK'):
                                    for n in range(self.measurement_number):
                                        # start measurement
                                        print "\n****\nseebeck measurement"
                                        print 'measurement number: ', n
                                        self.data_measurement()
                                        self.write_data_to_file('status')
                                        self.write_data_to_file('data')
                                        if self.abort_ID==1: break
                                    #end for
                                    if self.abort_ID==1: break
                                    self.tol = 'NO'
                                    self.stable = 'NO'
                                    break
                                #end if
                            # end while
                            if self.abort_ID==1: break
                        #end for
                        break
                    #end if
                # end while
                self.process_data()
                if self.abort_ID==1: break
            #end for
        except KeyboardInterrupt:
            print '\n****\nprogram interrupted\nsaving files at current location\n****\n'
        self.save_files()
        print "set sample A temp to %f" %(20)
        while True:
            try:
                self.sampleApid.set_setpoint(20)
                break
            except IOError:
                print 'IOError: communication failure'
        #end while
        print "set sample B temp to %f" %(20)
        while True:
            try:
                self.sampleBpid.set_setpoint(20)
                break
            except IOError:
                print 'IOError: communication failure'
        #end while
        
        self.sampleApid.stop()
        self.sampleBpid.stop()
        print "Huzzah! Your program finished! You are awesome, sir or maam!"
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
    #end def
    #--------------------------------------------------------------------------
    def Get_User_Input(self):
        print "Get Input From User"
        self.oscillation = input("Please enter PID oscillation in deg C (example: 6 or 8): ")
        self.oscillation = float(self.oscillation)
        self.dTlist = [self.oscillation*i/2 for i in range(0,-3,-1)+range(-1,3)+range(1,-1,-1)]
        #self.oscillation = 4
        #self.dTlist = [-4,0,4]
        
        self.tolerance = input("Please enter PID tolerance in deg C (example: 1): ")
        self.tolerance = float(self.tolerance)
    
        self.stability_threshold  = input("Please enter stability threshold in deg C per min (example: .25): ")
        self.stability_threshold  = float(self.stability_threshold) / 60
    
        self.measurement_number = input("Please enter measurement number at each delta temp (example: 3): ")
        self.measurement_number = int(self.measurement_number)
    
        self.measureList = input("Please enter the temperatures to measure as a list (example: [50, 75, ...]): ")
        for self.temp in self.measureList:
            if self.temp > 600:
                self.temp = 600
            #end if
        #end for
    
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
        self.seebeckfile = open('Seebeck.csv','w')
    
        begin = datetime.now() # Current date and time
        self.datafile.write('Start Time: ' + str(begin) + '\n')
        self.statusfile.write('Start Time: ' + str(begin) + '\n')
        self.seebeckfile.write('Start Time: ' + str(begin) + '\n')

        dataheaders = 'time (s), tempA (C), tempB (C), avgtemp (C), deltatemp (C), Vchromel (uV), Valumel (uV)\n'
        self.datafile.write(dataheaders)

        statusheaders1 = 'time (s), sampletempA (C), samplesetpointA (C), blocktempA (C), stabilityA (C/min), sampletempB (C), samplesetpointB (C), blocktempB (C), stabilityB (C/min),'
        statusheaders2 = 'chromelvoltageraw (uV), chromelvoltagecalc (uV), alumelvoltageraw(C), alumelvoltagecalc (uV), tolerance, stability\n'
        self.statusfile.write(statusheaders1 + statusheaders2)

        seebeckheaders = 'time(s),temperature (C),seebeck_chromel (uV/K),offset_chromel (uV),R^2_chromel,seebeck_alumel (uV/K),offset_alumel (uV),R^2_alumel\n'
        self.seebeckfile.write(seebeckheaders)
    #end def

    #--------------------------------------------------------------------------
    def data_measurement(self):
        # Takes and writes to file the data on the Keithley
        # The only change between blocks like this one is the specific
        # channel on the Keithley that is being measured.
        self.sampletempA = float(self.sampleApid.get_pv())
        self.samplesetpointA = float(self.sampleApid.get_setpoint())
        self.blocktempA = float(self.blockApid.get_pv())
        self.time_sampletempA = time.time() - self.start
        print "time: %.2f s\ttempA: %.2f C\tsetpointA: %.2f C" % (self.time_sampletempA, self.sampletempA,self.samplesetpointA)

        time.sleep(self.delay)

        self.sampletempB = float(self.sampleBpid.get_pv())
        self.samplesetpointB = float(self.sampleBpid.get_setpoint())
        self.blocktempB = float(self.blockBpid.get_pv())
        self.time_sampletempB = time.time() - self.start
        print "time: %.2f s\ttempB: %.2f C\tsetpointB: %.2f C" % (self.time_sampletempB, self.sampletempB, self.samplesetpointB)

        time.sleep(self.delay)

        self.Vchromelraw = float(self.k2700.fetch('107'))*10**6
        self.Vchromelcalc = self.voltage_Correction(self.Vchromelraw,self.sampletempA,self.sampletempB, 'chromel')
        self.time_Vchromel = time.time() - self.start
        print "time: %.2f s\tvoltage (Ch): %f uV" % (self.time_Vchromel, self.Vchromelcalc)

        time.sleep(self.delay)

        self.Valumelraw = float(self.k2700.fetch('108'))*10**6
        self.Valumelcalc = self.voltage_Correction(self.Valumelraw,self.sampletempA,self.sampletempB, 'alumel')
        self.time_Valumel = time.time() - self.start
        print "time: %.2f s\tvoltage (Al): %f uV" % (self.time_Valumel, self.Valumelcalc)

        time.sleep(self.delay)

        self.Valumelraw2 = float(self.k2700.fetch('108'))*10**6
        self.Valumelcalc2 = self.voltage_Correction(self.Valumelraw2,self.sampletempA,self.sampletempB, 'alumel')
        self.time_Valumel2 = time.time() - self.start
        print "time: %.2f s\tvoltage (Al): %f uV" % (self.time_Valumel2, self.Valumelcalc2)

        time.sleep(self.delay)

        self.Vchromelraw2 = float(self.k2700.fetch('107'))*10**6
        self.Vchromelcalc2 = self.voltage_Correction(self.Vchromelraw2,self.sampletempA,self.sampletempB, 'chromel')
        self.time_Vchromel2 = time.time() - self.start
        print "time: %.2f s\tvoltage (Ch): %f uV" % (self.time_Vchromel2, self.Vchromelcalc2)

        time.sleep(self.delay)

        self.sampletempB2 = float(self.sampleBpid.get_pv())
        self.samplesetpointB = float(self.sampleBpid.get_setpoint())
        self.blocktempB = float(self.blockApid.get_pv())
        self.time_sampletempB2 = time.time() - self.start
        print "time: %.2f s\ttempB: %.2f C\tsetpointB: %.2f C" % (self.time_sampletempB2, self.sampletempB2,self.samplesetpointB)

        time.sleep(self.delay)

        self.sampletempA2 = float(self.sampleApid.get_pv())
        self.samplesetpointA = float(self.sampleApid.get_setpoint())
        self.blocktempA = float(self.blockApid.get_pv())
        self.time_sampletempA2 = time.time() - self.start
        print "time: %.2f s\ttempA: %.2f C\tsetpointA: %.2f C" % (self.time_sampletempA2, self.sampletempA2,self.samplesetpointA)
        
        self.time = ( self.time_sampletempA + self.time_sampletempB + self.time_Vchromel + self.time_Valumel + self.time_Valumel2 + self.time_Vchromel2 + self.time_sampletempB2 + self.time_sampletempA2 ) / 8
        
        #check stability of PID
        if (len(self.recenttempA)<3):
            self.recenttempA.append(self.sampletempA)
            self.recenttempAtime.append(self.time_sampletempA)
            self.recenttempA.append(self.sampletempA2)
            self.recenttempAtime.append(self.time_sampletempA2)
        #end if
        else:
            self.recenttempA.pop(0)
            self.recenttempAtime.pop(0)
            self.recenttempA.pop(0)
            self.recenttempAtime.pop(0)
            self.recenttempA.append(self.sampletempA)
            self.recenttempAtime.append(self.time_sampletempA)
            self.recenttempA.append(self.sampletempA2)
            self.recenttempAtime.append(self.time_sampletempA2)
            self.stabilityA = self.getStability(self.recenttempA,self.recenttempAtime)
            print "stability A: %.4f C/min" % (self.stabilityA*60)
        #end else

        if (len(self.recenttempB)<3):
            self.recenttempB.append(self.sampletempB)
            self.recenttempBtime.append(self.time_sampletempB)
            self.recenttempB.append(self.sampletempB2)
            self.recenttempBtime.append(self.time_sampletempB2)
        #end if
        else:
            self.recenttempB.pop(0)
            self.recenttempBtime.pop(0)
            self.recenttempB.pop(0)
            self.recenttempBtime.pop(0)
            self.recenttempB.append(self.sampletempB)
            self.recenttempBtime.append(self.time_sampletempB)
            self.recenttempB.append(self.sampletempB2)
            self.recenttempBtime.append(self.time_sampletempB2)
            self.stabilityB = self.getStability(self.recenttempB,self.recenttempBtime)
            print "stability B: %.4f C/min" % (self.stabilityB*60)
        #end else
        self.safety_check()
        self.check_status()
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
    def getStability(self, temps, times):
        coeffs = np.polyfit(times, temps, 1)
        # Polynomial Coefficients
        results = coeffs.tolist()
        return results[0]
    #end def

    #--------------------------------------------------------------------------
    def safety_check(self):
        print 'safety check'
        if self.sampletempA >600 or self.sampletempA2 > 600:
            self.abort_ID = 1
            print 'Safety Failure: Sample Temp A greater than 600'
        #end if
        if self.sampletempB > 600 or self.sampletempA2 > 600:
            self.abort_ID = 1
            print 'Safety Failure: Sample Temp B greater than Max Limit'
        #end if
        if self.blocktempA > 600:
            self.abort_ID = 1
            print 'Safety Failure: Block Temp A greater than Max Limit'
        #end if
        if self.blocktempB > 600:
            self.abort_ID = 1
            print 'Safety Failure: Block Temp B greater than Max Limit'
        #end if
        if self.blocktempA > self.sampletempA + 100 or self.blocktempA > self.sampletempA2 + 100:
            self.abort_ID = 1
            print 'Safety Failure: Block Temp A  100 C greater than Sample Temp A'
        #end if
        if self.blocktempB > self.sampletempB + 100 or self.blocktempB > self.sampletempB2 + 100:
            self.abort_ID = 1
            print 'Safety Failure: Block Temp B  100 C greater than Sample Temp B'
        #end if
        if self.sampletempA > self.blocktempA + 100 or self.sampletempA2 > self.blocktempA + 100:
            self.abort_ID = 1
            print 'Safety Failure: Sample Temp A  100 C greater than Block Temp A'
        #end if
        if self.sampletempB > self.blocktempB + 100 or self.sampletempB2 > self.blocktempB + 100:
            self.abort_ID = 1
            print 'Safety Failure: Sample Temp B  100 C greater than Block Temp B'
        #end if
    #end def

    #--------------------------------------------------------------------------
    def check_status(self):
        print 'check tolerance'
        tempA = (self.sampletempA + self.sampletempA2)/2
        tempB = (self.sampletempB + self.sampletempB2)/2
        
        self.tolA = (np.abs(tempA-(self.avgtemp+self.dT/2.0)) < self.tolerance)
        self.tolB = (np.abs(tempB-(self.avgtemp-self.dT/2.0)) < self.tolerance)
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
    #end def

    #--------------------------------------------------------------------------
    def process_data(self):
        print '\n***\n'
        print 'process data to get seebeck coefficient'
        time = np.average(self.timecalclist)
        avgT = np.average(self.avgTcalclist)

        dTchromellist = self.dTcalclist
        dTalumellist = self.dTcalclist

        results_chromel = {}
        results_alumel = {}

        coeffs_chromel = np.polyfit(dTchromellist, self.Vchromelcalclist, 1)
        coeffs_alumel = np.polyfit(dTalumellist,self.Valumelcalclist,1)
        # Polynomial Coefficients
        polynomial_chromel = coeffs_chromel.tolist()
        polynomial_alumel = coeffs_alumel.tolist()

        seebeck_chromel = polynomial_chromel[0]
        offset_chromel = polynomial_chromel[1]
        seebeck_alumel = polynomial_alumel[0]
        offset_alumel = polynomial_alumel[1]
        print 'seebeck (chromel): %.3f uV/K'%(seebeck_chromel)
        print 'seebeck (alumel): %.3f uV/K'%(seebeck_alumel)
        print '\n***\n'

        # Calculate coefficient of determination (r-squared):
        p_chromel = np.poly1d(coeffs_chromel)
        p_alumel = np.poly1d(coeffs_alumel)
        # fitted values:
        yhat_chromel = p_chromel(dTchromellist)
        yhat_alumel = p_alumel(dTalumellist)
        # mean of values:
        ybar_chromel = np.sum(self.Vchromelcalclist)/len(self.Vchromelcalclist)
        ybar_alumel = np.sum(self.Valumelcalclist)/len(self.Valumelcalclist)
        # regression sum of squares:
        ssreg_chromel = np.sum((yhat_chromel-ybar_chromel)**2)   # or sum([ (yihat - ybar)**2 for yihat in yhat])
        ssreg_alumel = np.sum((yhat_alumel-ybar_alumel)**2)
        # total sum of squares:
        sstot_chromel = np.sum((self.Vchromelcalclist - ybar_chromel)**2)
        sstot_alumel = np.sum((self.Valumelcalclist - ybar_alumel)**2)    # or sum([ (yi - ybar)**2 for yi in y])

        rsquared_chromel = ssreg_chromel / sstot_chromel
        rsquared_alumel = ssreg_alumel / sstot_alumel

        self.seebeckfile.write('%.3f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f,%.5f\n'%(time,avgT,seebeck_chromel,offset_chromel,rsquared_chromel,seebeck_alumel,offset_alumel,rsquared_alumel))

        fitchromel = {}
        fitalumel = {}
        fitchromel['polynomial'] = polynomial_chromel
        fitalumel['polynomial'] = polynomial_alumel
        fitchromel['r-squared'] = rsquared_chromel
        fitalumel['r-squared'] = rsquared_alumel
        celsius = u"\u2103"
        
        self.create_backup_file(str(self.plotnumber)+'_'+str(avgT)+ 'C_backupfile.csv',self.timecalclist,self.avgTcalclist,self.dTcalclist,self.Vchromelcalclist,self.Valumelcalclist)
        self.create_plot(dTalumellist,dTchromellist,self.Valumelcalclist,self.Vchromelcalclist,fitalumel,fitchromel,str(self.plotnumber)+'_'+str(avgT)+ 'C')
    #end def
    
    #--------------------------------------------------------------------------
    def create_backup_file(self, title,tlist,avgTlist,dTlist,Vchlist,Vallist):
        backup_folder = self.filePath + '/Seebeck Backup Files/'
        if not os.path.exists(backup_folder):
            os.makedirs(backup_folder)
        #end if
        
        tempfile = open('Seebeck Backup Files/' + title,'w')
        tempfile.write(title + '\n')
        tempfile.write('time,avgT,dT,Vch,Val\n')
        for i in range(len(tlist)):
            tempfile.write('%.3f,%.4f,%.4f,%.6f,%.6f\n'%(tlist[i],avgTlist[i],dTlist[i],Vchlist[i],Vallist[i]))
        #end for
        tempfile.close()
        
        
    #end def
    
    #--------------------------------------------------------------------------
    def create_plot(self, xalumel, xchromel, yalumel, ychromel, fitalumel, fitchromel, title):
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
        plot_folder = self.filePath + '/Seebeck Plots/'
        if not os.path.exists(plot_folder):
            os.makedirs(plot_folder)

        fig.savefig('%s.png' % (plot_folder + title) , dpi=dpi)

        plt.close()
    #end def

    #--------------------------------------------------------------------------
    def write_data_to_file(self, file):
        if file == 'status':
            print('Write status to file\n')
            self.statusfile.write('%.1f,'%(self.time))
            self.statusfile.write('%.2f,%.2f,%.2f,' %(self.sampletempA2,self.samplesetpointA,self.blocktempA))
            self.statusfile.write(str(self.stabilityA)+',')
            self.statusfile.write('%.2f,%.2f,%.2f,' %(self.sampletempB2,self.samplesetpointB,self.blocktempB))
            self.statusfile.write(str(self.stabilityB)+',')
            self.statusfile.write('%.3f,%.3f,%.3f,%.3f,'%(self.Vchromelraw2, self.Vchromelcalc2,self.Valumelraw2, self.Valumelcalc2))
            self.statusfile.write(str(self.tol)+','+str(self.stable)+'\n')
        #end if
        elif file == 'data':
            print('Write data to file\n')
            ta = (self.sampletempA + self.sampletempA2)/2
            tb = (self.sampletempB + self.sampletempB2)/2
            avgt = (ta + tb)/2
            dt = ta-tb
            vchromel = (self.Vchromelcalc + self.Vchromelcalc2)/2
            valumel = (self.Valumelcalc + self.Valumelcalc2)/2
            self.datafile.write('%.3f,' %(self.time))
            self.datafile.write('%.4f,%.4f,%.4f,%.4f,' % (ta, tb, avgt, dt) )
            self.datafile.write('%.6f,%.6f\n' % (vchromel,valumel))
            
            self.timecalclist.append(self.time)
            self.Vchromelcalclist.append(vchromel)
            self.Valumelcalclist.append(valumel)
            self.dTcalclist.append(dt)
            self.avgTcalclist.append(avgt)
        #end elif
    #end def

    #--------------------------------------------------------------------------
    def save_files(self):
        print('\nSave Files\n')
        self.datafile.close()
        self.statusfile.close()
        self.seebeckfile.close()
    #end def
#end class
###############################################################################

#==============================================================================
if __name__=='__main__':
    runprogram = Main()
#end if