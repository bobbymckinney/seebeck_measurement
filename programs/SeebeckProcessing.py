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
import time
from datetime import datetime # for getting the current date and time
import exceptions

#==============================================================================
version = '1.0 (2016-02-09)'

###############################################################################
class SeebeckProcessing:
    def __init__(self,filepath,measureList):
        
        #self.Get_User_Input()
        #self.filePath = "/Users/tobererlab1/Desktop/Skutt_0p010_PID"
        self.filePath = filepath
        os.chdir(self.filePath)
        self.open_files()
        
        #self.measureList = [50,75,100,125,150,175,200,225,250,275,300,325,350,375,350,325,300,275,250,225,200,175,150,125,100,75,50]
        self.measureList = measureList

        self.get_data()
        self.plotnumber = 0
        self.tolerance = 4.0
        
        index = 0
        
        for temp in self.measureList:
            print 'measure temp: ', temp
            self.timecalclist = []
            self.avgTcalclist = []
            self.dTcalclist = []
            self.Vchromelcalclist = []
            self.Valumelcalclist = []
            
            # bin around an average temp and calculate seebeck
            for i in range(index,len(self.time)):
                if (self.avgT[i] > (temp-self.tolerance)) and (self.avgT[i] < (temp+self.tolerance)):
                    index = i
                    while (self.avgT[index] > (temp-self.tolerance)) and (self.avgT[index] < (temp+self.tolerance)):
                        self.timecalclist.append(self.time[index])
                        self.avgTcalclist.append(self.avgT[index])
                        self.dTcalclist.append(self.dT[index])
                        self.Vchromelcalclist.append(self.Vch[index])
                        self.Valumelcalclist.append(self.Val[index])
                        index += 1
                    #end while
                    self.process_data()
                    self.plotnumber += 1
                    break
                #end if
            #end for
        #end for
        self.save_file()
    #end def

    #--------------------------------------------------------------------------
    def Get_User_Input(self):    
        self.measureList = input("Please enter the temperatures to measure as a list (example: [50, 75, ...]): ")
    
        print "Your data will be saved to Desktop automatically"
        self.folder_name = raw_input("Please enter name for folder: ")
        self.folder_name = str(self.folder_name)
        if self.folder_name == '':
            date = str(datetime.now())
            self.folder_name = 'Seebeck_Processed_Data %s.%s.%s' % (date[0:13], date[14:16], date[17:19])
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
        self.datafile = open('Data.csv', 'r') # opens file for writing/overwriting
        self.seebeckfile = open('Seebeck.csv', 'w')
        seebeckheaders = 'time(s),temperature (C),seebeck_chromel (uV/K),offset_chromel (uV),R^2_chromel,seebeck_alumel (uV/K),offset_alumel (uV),R^2_alumel\n'
        self.seebeckfile.write(seebeckheaders)
    #end def
    
    #--------------------------------------------------------------------------
    def get_data(self):
        self.data = self.datafile.readlines()
        self.start = self.data.pop(0)
        self.quantities = self.data.pop(0).split(',')
        self.time = []
        self.tempA = []
        self.tempB = []
        self.avgT = []
        self.dT = []
        self.Vch = []
        self.Val = []
        
        for d in self.data:
            self.time.append( float(d.split(',')[0]) )
            self.tempA.append( float(d.split(',')[1]) )
            self.tempB.append( float(d.split(',')[2]) )
            self.avgT.append( float(d.split(',')[3]) )
            self.dT.append( float(d.split(',')[4]) )
            self.Vch.append( float(d.split(',')[5]) )
            self.Val.append( float(d.split(',')[6]) )
        #end for
        print "length of data: ", len(self.avgT)
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
        
        self.create_plot(dTalumellist,dTchromellist,self.Valumelcalclist,self.Vchromelcalclist,fitalumel,fitchromel,str(self.plotnumber)+'_'+str(avgT)+ 'C')
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
    def save_file(self):
        print('\nSave Files\n')
        self.seebeckfile.close()
    #end def
#end class
###############################################################################

#==============================================================================
if __name__=='__main__':
    runprogram = SeebeckProcessing("/Users/tobererlab1/Desktop/Skutt_0p010_PID")
#end if