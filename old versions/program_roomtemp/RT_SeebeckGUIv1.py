#! /usr/bin/python
# -*- coding: utf-8 -*-
"""
Created: 2015-05-29

@author: Bobby McKinney (bobbymckinney@gmail.com)

__Title__ : room temp seebeck
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
import RT_Seebeck_Processing_v1

#==============================================================================

version = '1.0 (2015-05-29)'

'''
Global Variables:
'''

# Naming a data file:
dataFile = 'Data_Backup.csv'
finaldataFile = 'Data.csv'

APP_EXIT = 1 # id for File\Quit

maxLimit = 70 # Restricts the user to a max temperature

abort_ID = 0 # Abort method

# Global placers for instruments
k2000 = ''

tc_type = "k-type" # Set the thermocouple type in order to use the correct voltage correction

# Channels corresponding to switch card:
tempAChannel = '2'
tempBChannel = '7'
VlowChannel = '4'
VhighChannel = '5'

# placer for directory
filePath = 'global file path'

# placer for files to be created
myfile = 'global file'

# Placers for the GUI plots:
Vhigh_list = [0]
tVhigh_list = [0]
Vlow_list = [0]
tVlow_list = [0]
tempA_list = [0]
ttempA_list = [0]
tempB_list = [0]
ttempB_list = [0]
dT_list = [0]


#ResourceManager for visa instrument control
ResourceManager = visa.ResourceManager()

###############################################################################
class Keithley_2000:
    ''' Used for the matrix card operations. '''
    #--------------------------------------------------------------------------
    def __init__(self, instr):
        self.ctrl = ResourceManager.open_resource(instr)
        #self.ctrl.write("*rst")
        self.ctrl.write("trig:delay 0")
        self.ctrl.write("trig:count 1")
        self.ctrl.write("temp:tcouple:type k")
        self.ctrl.write("volt:dc:nplcycles 1")
        self.ctrl.write("temp:nplcycles 1")

    #end init
        
    #--------------------------------------------------------------------------
    def fetch(self, channel):
        """ 
        Scan the channel and take a reading 
        """
        if (channel == VlowChannel or channel == VhighChannel):
            self.ctrl.write("func 'volt:dc'")
            
        #end if
        else:
            self.ctrl.write("func 'temperature'")
            
            
        #end else
        time.sleep(0.2)
        self.ctrl.write("rout:clos (@ %s)" % (channel)) # Specify Channel
        time.sleep(1)
        data = self.ctrl.query("fetch?")
        return str(data)[0:-1] # Fetches Reading    
    #end def
        
    #--------------------------------------------------------------------------
    def openAllChannels(self):
        self.ctrl.write("ROUTe:OPEN:ALL")    
    #end def

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
        global k2000
        
        # Define Keithley instrument port:
        self.k2000 = k2000 = Keithley_2000('GPIB0::16::INSTR')
            
        """
        Prepare the Keithley for operation:
        """
        self.k2000.openAllChannels

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
class TakeData:
    ''' Takes measurements and saves them to file. '''
    #--------------------------------------------------------------------------
    def __init__(self):
        global abort_ID
        global k2000
        
        self.k2000 = k2000
        
        #time initializations
        self.ttempA = 0
        self.ttempA2 = 0
        self.ttempB = 0
        self.ttempB2 = 0
        self.dT = 0
        
        self.exception_ID = 0
        
        self.updateGUI(stamp='Status Bar', data='Running')
        
        self.start = time.time()
        
        try:
            while abort_ID == 0:
                
                self.seebeck_data_measurement()
                
                self.write_data_to_file()
                
                self.safety_check()
                
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
            
        wx.CallAfter(pub.sendMessage, 'Post Process')        
        wx.CallAfter(pub.sendMessage, 'Enable Buttons')

    #end init
    
    #--------------------------------------------------------------------------    
    def safety_check(self):
        global maxLimit
        global abort_ID
        
        if float(self.tempA) > maxLimit or float(self.tempB) > maxLimit:
            abort_ID = 1
            
            
        
    #end def
    
    #--------------------------------------------------------------------------
    def seebeck_data_measurement(self):
        # get temp A
        self.tempA = float(self.k2000.fetch(tempAChannel))
        self.ttempA = time.time() - self.start
        self.updateGUI(stamp="Time Temp A", data=float(self.ttempA))
        self.updateGUI(stamp="Temp A", data=float(self.tempA))
        print "ttempA: %.2f s\ttempA: %s C" % (self.ttempA, self.tempA) 
        
        time.sleep(.1)
        
        # get temp B
        self.tempB = float(self.k2000.fetch(tempBChannel))
        self.ttempB = time.time() - self.start
        self.updateGUI(stamp="Time Temp B", data=float(self.ttempB))
        self.updateGUI(stamp="Temp B", data=float(self.tempB))
        print "ttempB: %.2f s\ttempB: %s C" % (self.ttempB, self.tempB) 
        
        time.sleep(.1)
        
        self.dT = self.tempA - self.tempB
        
        # get V low
        self.Vlow = float(self.k2000.fetch(VlowChannel))*10**6 #uV
        self.Vlowcalc = self.alpha(self.tempA,self.tempB,'low')*self.dT - self.Vlow
        self.tVlow = time.time() - self.start
        self.updateGUI(stamp="Time Voltage Low", data=float(self.tVlow))
        self.updateGUI(stamp="Voltage Low", data=float(self.Vlowcalc))
        print "tV: %.2f s\tV: %f uV" % (self.tVlow, self.Vlow)
        
        time.sleep(.1)
        
        # get V high
        self.Vhigh = float(self.k2000.fetch(VhighChannel))*10**6 #uV
        self.Vhighcalc = self.alpha(self.tempA,self.tempB,'high')*self.dT - self.Vhigh
        self.tVhigh = time.time() - self.start
        self.updateGUI(stamp="Time Voltage High", data=float(self.tVhigh))
        self.updateGUI(stamp="Voltage High", data=float(self.Vhighcalc))
        print "tV: %.2f s\tV: %f uV" % (self.tVhigh, self.Vhigh)
        
        time.sleep(.1)
        
        
        # Symmetrize the measurement and repeat in reverse

        self.Vhigh2 = float(self.k2000.fetch(VhighChannel))*10**6 #uV
        self.Vhighcalc = self.alpha(self.tempA,self.tempB,'high')*self.dT - self.Vhigh2
        self.tVhigh2 = time.time() - self.start
        self.updateGUI(stamp="Time Voltage High", data=float(self.tVhigh2))
        self.updateGUI(stamp="Voltage High", data=float(self.Vhighcalc))
        print "tV: %.2f s\tV: %f uV" % (self.tVhigh2, self.Vhigh2)
        
        time.sleep(.1)
        
        self.Vlow2 = float(self.k2000.fetch(VlowChannel))*10**6 #uV
        self.Vlowcalc = self.alpha(self.tempA,self.tempB,'low')*self.dT - self.Vlow2
        self.tVlow2 = time.time() - self.start
        self.updateGUI(stamp="Time Voltage Low", data=float(self.tVlow2))
        self.updateGUI(stamp="Voltage Low", data=float(self.Vlowcalc))
        print "tV: %.2f s\tV: %f uV" % (self.tVlow2, self.Vlow2)
        
        time.sleep(.1)

        self.tempB2 = float(self.k2000.fetch(tempBChannel))
        self.ttempB2 = time.time() - self.start
        self.updateGUI(stamp="Time Temp B", data=float(self.ttempB2))
        self.updateGUI(stamp="Temp B", data=float(self.tempB2))
        print "ttempB: %.2f s\ttempB: %s C" % (self.ttempB2, self.tempB2)
        
        time.sleep(.1)
        
        self.tempA2 = float(self.k2000.fetch(tempAChannel))
        self.ttempA2 = time.time() - self.start
        self.updateGUI(stamp="Time Temp A", data=float(self.ttempA2))
        self.updateGUI(stamp="Temp A", data=float(self.tempA2))
        print "ttempA: %.2f s\ttempA: %s C" % (self.ttempA2, self.tempA2)
        
    #end def
    
    #--------------------------------------------------------------------------
    def alpha(self,t1,t2, side):
        x = (t1+t2)/2 + 273.15
        
        #print "average temp: %f K" %(tkelvin)
        
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
    
        print "alpha for %s: %f"% (side,alpha)
        return alpha
    #end def
    
    #--------------------------------------------------------------------------
    def write_data_to_file(self):
        print('Write data to file')
        myfile.write('%.2f,%f,%.2f,%f,%.2f,%f,%.2f,%f,' % (self.ttempA, self.tempA, self.ttempB, self.tempB, self.tVlow, self.Vlow, self.tVhigh, self.Vhigh) )
        myfile.write( '%.2f,%f,%.2f,%f,%.2f,%f,%.2f,%f\n' % (self.tVhigh2, self.Vhigh2, self.tVlow2, self.Vlow2, self.ttempB2, self.tempB2, self.ttempA2, self.tempA2) )
        
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
        
        stop = time.time()
        end = datetime.now() # End time
        totalTime = stop - self.start # Elapsed Measurement Time (seconds)
        
        myfile.close() # Close the file
        
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

        self.create_title("Control Panel") # Title
        
        self.celsius = u"\u2103"
        self.font2 = wx.Font(11, wx.DEFAULT, wx.NORMAL, wx.NORMAL)
        
        self.maxLimit_label()
        
        
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
        rs_sizer = wx.GridBagSizer(2, 2)

        self.btn_run = btn_run = wx.Button(self.run_stopPanel, label='run', style=0, size=(60,30)) # Run Button
        btn_run.SetBackgroundColour((0,255,0))
        caption_run = wx.StaticText(self.run_stopPanel, label='*run measurement')
        self.btn_stop = btn_stop = wx.Button(self.run_stopPanel, label='stop', style=0, size=(60,30)) # Stop Button
        btn_stop.SetBackgroundColour((255,0,0))
        caption_stop = wx.StaticText(self.run_stopPanel, label = '*quit operation')
        
        btn_run.Bind(wx.EVT_BUTTON, self.run)
        btn_stop.Bind(wx.EVT_BUTTON, self.stop)
        

        rs_sizer.Add(btn_run,(0,0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        rs_sizer.Add(caption_run,(1,0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        rs_sizer.Add(btn_stop,(0,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        rs_sizer.Add(caption_stop,(1,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        self.run_stopPanel.SetSizer(rs_sizer)
        
        btn_stop.Disable()
        
    # end def
    
    #--------------------------------------------------------------------------
    def run(self, event):
        global dataFile
        global finaldataFile
        global myfile
        global abort_ID
        global Vhigh_list, tVhigh_list, Vlow_list, tVlow_list
        global tempA_list, ttempA_list, tempB_list, ttempB_list
        
            
        try:
            global k2000
            
            self.name_folder()
            
            if self.run_check == wx.ID_OK:
                

                
                begin = datetime.now() # Current date and time
                file = dataFile # creates a data file
                myfile = open(dataFile, 'w') # opens file for writing/overwriting
                myfile.write('start time: ' + str(begin) + '\n')
                myfile.write('time (s),tempA (C),time (s),tempB (C),time (s),Vlow (uV),time (s),Vhigh (uV),time (s),Vhigh2 (uV),time (s),Vlow2 (uV),time (s),tempB2 (C),time (s),tempA2 (C)\n')              
                
                # Global variables:

                abort_ID = 0
                
                # Placers for the GUI plots:

                Vhigh_list = [0]
                tVhigh_list = [0]
                Vlow_list = [0]
                tVlow_list = [0]
                tempA_list = [0]
                ttempA_list = [0]
                tempB_list = [0]
                ttempB_list = [0]


                #start the threading process
                thread = ProcessThreadRun()
                self.btn_stop.Enable()
                
            #end if
            
        #end try
            
        except visa.VisaIOError:
            wx.MessageBox("Not all instruments are connected!", "Error")
        #end except
            
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
      
        sizer = wx.GridBagSizer(3,1)
        sizer.Add(self.titlePanel, (0, 1), flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.run_stopPanel, (1,1), flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.maxLimit_Panel, (2, 1))
        
        
        self.SetSizer(sizer)
        
    #end def
    
    #--------------------------------------------------------------------------
    def post_process_data(self):
        global filePath, finaldataFile, tc_type
        
        try:
            # Post processing:
            RT_Seebeck_Processing_v1.create_processed_files(filePath, finaldataFile)
        except IndexError:
            wx.MessageBox('Not enough data for post processing to occur. \n\nIt is likely that we did not even complete any oscillations.', 'Error', wx.OK | wx.ICON_INFORMATION)
   #end def
    
    #--------------------------------------------------------------------------    
    def enable_buttons(self):
        self.btn_run.Enable()
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
        self.Vlow=str(0)
        self.Vhigh =str(0)
        self.tA=str(30)
        self.tB=str(30)
        self.dT = str(float(self.tA)-float(self.tB))

        
        self.create_title("Status Panel")
        self.linebreak1 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        self.create_status()
        self.linebreak2 = wx.StaticLine(self, pos=(-1,-1), size=(300,1))
        
        self.linebreak3 = wx.StaticLine(self, pos=(-1,-1), size=(1,300), style=wx.LI_VERTICAL)
        
        # Updates from running program
        pub.subscribe(self.OnTime, "Time Voltage High")
        pub.subscribe(self.OnTime, "Time Voltage Low")
        pub.subscribe(self.OnTime, "Time Temp A")
        pub.subscribe(self.OnTime, "Time Temp B")
        
        pub.subscribe(self.OnVoltageHigh, "Voltage High")
        pub.subscribe(self.OnVoltageLow, "Voltage Low")
        pub.subscribe(self.OnTempA, "Temp A")
        pub.subscribe(self.OnTempB, "Temp B")

        
        #self.update_values()
        
        self.create_sizer()
        
    #end init
    
    #--------------------------------------------------------------------------
    def OnVoltageHigh(self, msg):
        self.Vhigh = '%.1f'%(float(msg)) 
        self.update_values()  
    #end def

    #--------------------------------------------------------------------------
    def OnVoltageLow(self, msg):
        self.Vlow = '%.1f'%(float(msg)) 
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
        self.label_Vhigh = wx.StaticText(self, label="voltage high ("+self.mu+"V):")
        self.label_Vhigh.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_Vlow = wx.StaticText(self, label="voltage low ("+self.mu+"V):")
        self.label_Vlow.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_tA = wx.StaticText(self, label="temp A ("+self.celsius+"):")
        self.label_tA.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_tB = wx.StaticText(self, label="temp B ("+self.celsius+"):")
        self.label_tB.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.label_dT = wx.StaticText(self, label=self.delta+"T ("+self.celsius+"):")
        self.label_dT.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))

        
        self.ctimecurrent = wx.StaticText(self, label=self.ctime)
        self.ctimecurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.tcurrent = wx.StaticText(self, label=self.t)
        self.tcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.Vhighcurrent = wx.StaticText(self, label=self.Vhigh)
        self.Vhighcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.Vlowcurrent = wx.StaticText(self, label=self.Vlow)
        self.Vlowcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.tAcurrent = wx.StaticText(self, label=self.tA)
        self.tAcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.tBcurrent = wx.StaticText(self, label=self.tB)
        self.tBcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))
        self.dTcurrent = wx.StaticText(self, label=self.dT)
        self.dTcurrent.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))

        
        
    #end def
        
    #-------------------------------------------------------------------------- 
    def update_values(self):
        self.ctimecurrent.SetLabel(self.ctime)
        self.tcurrent.SetLabel(self.t)
        self.Vhighcurrent.SetLabel(self.Vhigh)
        self.Vlowcurrent.SetLabel(self.Vlow)
        self.tAcurrent.SetLabel(self.tA)
        self.tBcurrent.SetLabel(self.tB)
        self.dTcurrent.SetLabel(self.dT)
    #end def
       
    #--------------------------------------------------------------------------
    def create_sizer(self):    
        sizer = wx.GridBagSizer(10,2)
        
        sizer.Add(self.titlePanel, (0, 0), span = (1,2), border=5, flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.linebreak1,(1,0), span = (1,2))
        
        sizer.Add(self.label_ctime, (2,0))
        sizer.Add(self.ctimecurrent, (2, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_t, (3,0))
        sizer.Add(self.tcurrent, (3, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        sizer.Add(self.label_Vhigh, (4, 0))
        sizer.Add(self.Vhighcurrent, (4, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.label_Vlow, (5, 0))
        sizer.Add(self.Vlowcurrent, (5, 1),flag=wx.ALIGN_CENTER_HORIZONTAL)
          
        sizer.Add(self.label_tA, (6,0))
        sizer.Add(self.tAcurrent, (6,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        sizer.Add(self.label_tB, (7,0))
        sizer.Add(self.tBcurrent, (7,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        
        sizer.Add(self.label_dT, (8,0))
        sizer.Add(self.dTcurrent, (8,1),flag=wx.ALIGN_CENTER_HORIZONTAL)

        
        sizer.Add(self.linebreak2, (9,0), span = (1,2))
        
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
        
        global tVhigh_list, tVlow_list
        global Vhigh_list, Vlow_list
        
        self.create_title("Voltage Panel")
        self.init_plot()
        self.canvas = FigureCanvasWxAgg(self, -1, self.figure)
        self.create_control_panel()
        self.create_sizer()
        
        pub.subscribe(self.OnVoltageHigh, "Voltage High")
        pub.subscribe(self.OnVHighTime, "Time Voltage High")
        pub.subscribe(self.OnVoltageLow, "Voltage Low")
        pub.subscribe(self.OnVLowTime, "Time Voltage Low")
        
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
        self.ymin_control = BoundControlBox(self, -1, "V min", -500)
        self.ymax_control = BoundControlBox(self, -1, "V max", 500)
        
        self.hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.hbox1.AddSpacer(10)
        self.hbox1.Add(self.xmin_control, border=5, flag=wx.ALL)
        self.hbox1.Add(self.xmax_control, border=5, flag=wx.ALL)
        self.hbox1.AddSpacer(10)
        self.hbox1.Add(self.ymin_control, border=5, flag=wx.ALL)
        self.hbox1.Add(self.ymax_control, border=5, flag=wx.ALL)     
    #end def
        
    #--------------------------------------------------------------------------
    def OnVoltageHigh(self, msg):
        self.Vhigh = float(msg)
        tVhigh_list.append(self.tVhigh)
        Vhigh_list.append(self.Vhigh)   
    #end def

    #--------------------------------------------------------------------------
    def OnVHighTime(self, msg):
        self.tVhigh = float(msg)   
        
    #end def

    #--------------------------------------------------------------------------
    def OnVoltageLow(self, msg):
        self.Vlow = float(msg)
        tVlow_list.append(self.tVlow)
        Vlow_list.append(self.Vlow)   
    #end def

    #--------------------------------------------------------------------------
    def OnVLowTime(self, msg):
        self.tVlow = float(msg)   
        
    #end def

    #--------------------------------------------------------------------------
    def init_plot(self):
        self.dpi = 100
        self.colorHigh = 'g'
        self.colorLow = 'y'
        
        self.figure = Figure((6,3), dpi=self.dpi)
        self.subplot = self.figure.add_subplot(111)
        self.lineVhigh, = self.subplot.plot(tVhigh_list,Vhigh_list, color=self.colorHigh, linewidth=1)
        self.lineVlow, = self.subplot.plot(tVlow_list,Vlow_list, color=self.colorLow, linewidth=1)
        self.legend = self.figure.legend( (self.lineVhigh,self.lineVlow), (r"$V_{high}$",r"$V_{low}$"), (0.15,0.75),fontsize=8)
        #self.subplot.text(0.05, .95, r'$X(f) = \mathcal{F}\{x(t)\}$', \
            #verticalalignment='top', transform = self.subplot.transAxes)
    #end def

    #--------------------------------------------------------------------------
    def draw_plot(self,i):
        self.subplot.clear()
        #self.subplot.set_title("voltage vs. time", fontsize=12)
        self.subplot.set_ylabel(r"voltage ($\mu$V)", fontsize = 8)
        self.subplot.set_xlabel("time (s)", fontsize = 8)
        
        # Adjustable scale:
        if self.xmax_control.is_auto():
            xmax = max(tVhigh_list+tVlow_list)
        else:
            xmax = float(self.xmax_control.manual_value())    
        if self.xmin_control.is_auto():            
            xmin = 0
        else:
            xmin = float(self.xmin_control.manual_value())
        if self.ymin_control.is_auto():
            minV = min(Vhigh_list+Vlow_list)
            ymin = minV*1.5
        else:
            ymin = float(self.ymin_control.manual_value())
        if self.ymax_control.is_auto():
            maxV = max(Vhigh_list+Vlow_list)
            ymax = maxV*1.5
        else:
            ymax = float(self.ymax_control.manual_value())
        
        
        self.subplot.set_xlim([xmin, xmax])
        self.subplot.set_ylim([ymin, ymax])
        
        pylab.setp(self.subplot.get_xticklabels(), fontsize=8)
        pylab.setp(self.subplot.get_yticklabels(), fontsize=8)
        
        self.lineVhigh, = self.subplot.plot(tVhigh_list,Vhigh_list, color=self.colorHigh, linewidth=1)
        self.lineVlow, = self.subplot.plot(tVlow_list,Vlow_list, color=self.colorLow, linewidth=1)
        
        return (self.lineVhigh, self.lineVlow)
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
        global dT_list
        
        self.create_title("Temperature Panel")
        self.init_plot()
        self.canvas = FigureCanvasWxAgg(self, -1, self.figure)
        self.create_control_panel()
        self.create_sizer()
        
        pub.subscribe(self.OnTimeTempA, "Time Temp A")
        pub.subscribe(self.OnTempA, "Temp A")
        pub.subscribe(self.OnTimeTempB, "Time Temp B")
        pub.subscribe(self.OnTempB, "Temp B")

        
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
        self.ymax_control = BoundControlBox(self, -1, "T max", 40)
        
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
        ttempA_list.append(self.ttA)
        tempA_list.append(self.tA)    
    #end def
    
    #--------------------------------------------------------------------------
    def OnTimeTempB(self, msg):
        self.ttB = float(msg)    
        
    #end def
        
    #--------------------------------------------------------------------------
    def OnTempB(self, msg):
        self.tB = float(msg)
        self.dT = self.tA - self.tB
        ttempB_list.append(self.ttB)
        tempB_list.append(self.tB)
        dT_list.append(self.dT)    
    #end def

    #--------------------------------------------------------------------------
    def init_plot(self):
        self.dpi = 100
        self.colorTA = 'r'
        self.colorTB = 'b'
        self.colordT = 'm'
        
        self.figure = Figure((6,3), dpi=self.dpi)
        self.subplot = self.figure.add_subplot(111)
        
        self.lineTA, = self.subplot.plot(ttempA_list,tempA_list, color=self.colorTA, linewidth=1)
        self.lineTB, = self.subplot.plot(ttempB_list,tempB_list, color=self.colorTB, linewidth=1)
        self.linedT, = self.subplot.plot(ttempB_list,dT_list, color=self.colordT, linewidth=1)
        
        self.legend = self.figure.legend( (self.lineTA, self.lineTB, self.linedT), (r"$T_A$",r"$T_B$",r"$\Delta T$"), (0.15,0.65),fontsize=8)
        #self.subplot.text(0.05, .95, r'$X(f) = \mathcal{F}\{x(t)\}$', \
            #verticalalignment='top', transform = self.subplot.transAxes)
    #end def

    #--------------------------------------------------------------------------
    def draw_plot(self,i):
        self.subplot.clear()
        #self.subplot.set_title("temperature vs. time", fontsize=12)
        self.subplot.set_ylabel(r"temperature ($\degree$C)", fontsize = 8)
        self.subplot.set_xlabel("time (s)", fontsize = 8)
        
        # Adjustable scale:
        if self.xmax_control.is_auto():
            xmax = max(ttempA_list+ttempB_list + dT_list)
        else:
            xmax = float(self.xmax_control.manual_value())    
        if self.xmin_control.is_auto():            
            xmin = 0
        else:
            xmin = float(self.xmin_control.manual_value())
        if self.ymin_control.is_auto():
            minT = min(tempA_list+tempB_list + dT_list)
            ymin = minT - abs(minT)*0.3
        else:
            ymin = float(self.ymin_control.manual_value())
        if self.ymax_control.is_auto():
            maxT = max(tempA_list+tempB_list)
            ymax = maxT + abs(maxT)*0.3
        else:
            ymax = float(self.ymax_control.manual_value())
        
        self.subplot.set_xlim([xmin, xmax])
        self.subplot.set_ylim([ymin, ymax])
        
        pylab.setp(self.subplot.get_xticklabels(), fontsize=8)
        pylab.setp(self.subplot.get_yticklabels(), fontsize=8)
        
        self.lineTA, = self.subplot.plot(ttempA_list,tempA_list, color=self.colorTA, linewidth=1)
        self.lineTB, = self.subplot.plot(ttempB_list,tempB_list, color=self.colorTB, linewidth=1)
        self.linedT, = self.subplot.plot(ttempB_list,dT_list, color=self.colordT, linewidth=1)
        
        return (self.lineTA, self.lineTB, self.linedT)
        
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
        
        sizer = wx.GridBagSizer(2, 2)
        sizer.Add(self.userpanel, (0,0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.statuspanel, (1,0),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.voltagepanel, (0,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Add(self.temperaturepanel, (1,1),flag=wx.ALIGN_CENTER_HORIZONTAL)
        sizer.Fit(self)
        
        self.SetSizer(sizer)
        self.SetTitle('Room Temp Seebeck GUI')
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
        self.statusbar.SetFieldsCount(4)
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
        
        # Placer 2:
        placer2 = wx.StaticText(self.statusbar, -1, " ")
        
        # Version:
        version_label = wx.StaticText(self.statusbar, -1, "Version: %s" % version)
        self.width8 = version_label.GetRect().width + self.space_between
        
        # Set widths of each piece of the status bar:
        self.statusbar.SetStatusWidths([self.width0,50, -1, self.width8])
        
        ### Add the widgets to the status bar:
        # Status:
        self.statusbar.AddWidget(self.status_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
        # Placer 1:
        self.statusbar.AddWidget(placer1)
        
        # Title:
        #self.statusbar.AddWidget(measurement_text, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
        # Placer 2
        self.statusbar.AddWidget(placer2)
        
        # Version:
        self.statusbar.AddWidget(version_label, ESB.ESB_ALIGN_CENTER_HORIZONTAL, ESB.ESB_ALIGN_CENTER_VERTICAL)
        
    #end def
        
    #--------------------------------------------------------------------------
    def update_statusbar(self, msg):
        string = msg
        
        # Status:
        if string == 'Running' or string == 'Finished, Ready' or string == 'Exception Occurred':
            self.status_text.SetLabel(string)
            self.status_text.SetBackgroundColour(wx.NullColour)
            
            if string == 'Exception Occurred':
                self.status_text.SetBackgroundColour("RED")
            #end if
        
        #end if
         
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
        self.frame = Frame(parent=None, title="Room Temp Seebeck GUI", size=(1280,1280))
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