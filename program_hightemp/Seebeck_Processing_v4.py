# -*- coding: utf-8 -*-
"""
Created on Fri Jul 18 16:07:35 2014

@author: Benjamin Kostreva (benkostr@gmail.com)

__Title__

Description:
    Interpolates all of the data from the Seebeck files and calculates dT and
    corrected voltages.
    
Comments:
    - The linear interpolation calculates what the data in between time stamps
      should be.
      
Edited by Bobby McKinney 2015-01-12
"""

import numpy as np # for linear fits

# for saving plots
import matplotlib.pyplot as plt

# for creating new folders
import os

###############################################################################
class Process_Data:
    ''' Interpolates the data in order to get a common timestamp and outputs
        time, dT, lowV, highV corrected lists with common timestamps on each 
        line.
    '''
    #--------------------------------------------------------------------------
    def __init__(self, directory, fileName, tc_type):
        self.directory = directory
        
        filePath = directory + '/'+ fileName
        ttempA, tempA, ttempB, tempB, thighV, highV, tlowV, lowV, tlowV2, lowV2, thighV2, highV2, ttempB2, tempB2, ttempA2, tempA2, self.indicator = extract_Data(filePath)
        
        print('extracted data from raw file')
        
        self.ttempA = ttempA # first time stamp in a line
        self.ttempA2 = ttempA2 # last time stamp in a line
        
        # This will be the common time stamp for each line after interpolation:
        self.t = [None]*(len(ttempA)-1)
        for x in xrange(1, len(ttempA)):
            self.t[x-1] = (self.ttempA[x] + self.ttempA2[x-1])/2
        
        print('find dT')
        # Finding dT (after interpolation, at common time):
        tempA_int = self.interpolate(ttempA, tempA)
        tempA2_int = self.interpolate(ttempA2, tempA2)
        for x in xrange(len(tempA_int)):
            tempA_int[x] = (tempA_int[x] + tempA2_int[x])/2 
        tempB_int = self.interpolate(ttempB, tempB)
        tempB2_int = self.interpolate(ttempB2, tempB2)
        for x in xrange(len(tempA_int)):
            tempB_int[x] = (tempB_int[x] + tempB2_int[x])/2
        self.dT = [None]*len(tempA_int)
        for x in xrange(len(tempA_int)):
            self.dT[x] = tempA_int[x] - tempB_int[x]
            
        # Finding avg T:
        self.avgT = [None]*len(tempA_int)
        for x in xrange(len(tempA_int)):
            self.avgT[x] = (tempA_int[x] + tempB_int[x])/2
        
        print('find corrected voltage')
        # Voltage Corrections (after interpolation, at common time):
        highV_int = self.interpolate(thighV, highV)
        highV2_int = self.interpolate(thighV2, highV2)
        for x in xrange(len(highV_int)):
            highV_int[x] = (highV_int[x] + highV2_int[x])/2
        lowV_int = self.interpolate(tlowV, lowV)
        lowV2_int = self.interpolate(tlowV2, lowV2)
        for x in xrange(len(lowV_int)):
            lowV_int[x] = (lowV_int[x] + lowV2_int[x])/2
        self.highV_int_corrected = self.voltage_Correction(highV_int, 'high', tc_type)
        self.lowV_int_corrected = self.voltage_Correction(lowV_int, 'low', tc_type)
        
        print('calculate seebeck')
        # Complete linear fits to the data to find Seebeck coefficients:
        low_seebeck, high_seebeck = self.calculate_seebeck(self.extract_measurements())
        
        print('extracting data from fits')
        # Extract out the data from the fits in order to write to file later:
        temp, self.high_m, self.high_b, self.high_r = self.extract_seebeck_elements(high_seebeck)
        self.temp, self.low_m, self.low_b, self.low_r = self.extract_seebeck_elements(low_seebeck)
        
    #end init
        
    #--------------------------------------------------------------------------
    def interpolate(self, tdata, data):
        ''' Interpolates the data in order to achieve a single time-stamp
            on each data line.
        '''
        y0 = data[0]
        t0 = tdata[0]
        
        y = [None]*(len(data)-1)
        
        for x in xrange(1, len(data)):
            y1 = data[x]
            t1 = tdata[x]
            
            t_term = (self.t[x-1] - t0)/(t1 - t0)
            # Linear interpolation:
            y[x-1] = y0*(1 - t_term) + y1*t_term
            
            y0 = data[x]
            t0 = data[x]
        #end for
            
        return y
        
    #end def
        
    #--------------------------------------------------------------------------
    def voltage_Correction(self, raw_data, side, tc_type):
        ''' raw_data must be in uV, corrects the voltage measurements from the
            thermocouples
        '''
        
        # Kelvin conversion for polynomial correction.
        avgT_Kelvin = [None]*len(self.avgT)
        for x in xrange(len(self.avgT)):
            avgT_Kelvin[x] = self.avgT[x] + 273.15
        
        # Correction for effect from Thermocouple Seebeck
        v_corrected = [None]*len(avgT_Kelvin)
        for x in xrange(len(avgT_Kelvin)):
            v_corrected[x] = self.alphacalc(avgT_Kelvin[x], side, tc_type)*self.dT[x] - raw_data[x]
        
        return v_corrected
        
    #end def
        
    #--------------------------------------------------------------------------
    def alphacalc(self, x, side, tc_type):
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
    def extract_measurements(self):
        '''
        Returns a list of lists with elements [line number, 'Start'/'Stop' , Temperature]
        for each subsequent measurement.
        '''
        # Extract a list of just 'Start' and 'Stop' (and 'Left' (Equilibrium) if applicable):
        h = [None]*len(self.avgT)
        for x in xrange(len(self.avgT)):
            h[x] = self.indicator[x][:-11]
        h = ','.join(h)
        h = ''.join(h.split())
        h = h.split(',')
        h = [x for x in h if x]
        
        
        # Get number of Measurements:
        num = 0
        for x in xrange(len(h)-1):
            if h[x] == 'Start':
                # if the indicator says stop (or stop is overlapped by another start):
                if h[x+1] == 'Stop' or h[x+1] == 'Start':
                    num = num + 1
        if h[-1] == 'Start':
            num = num + 1
            
        num = num*2 # Both start and stop
        
        
        # Create a list that records the beginning and end of each measurement:
        measurement_indicator = [[None,None,None]]*num # [line num, 'Start/Stop', temp]
        s = -1 # iterator for each element of h
        n = 0 # iterator to create the elements of measurement_indicator
        overlap_indicator = 0 # in case a 'Start' overlaps a 'Stop'
        for x in xrange(len(self.avgT)):
            if self.indicator[x] == 'Start Oscillation':
                s = s + 1 # next element of h
                if h[s] == 'Start':
                    if overlap_indicator == 1:
                        # if 'Start' overlaps a 'Stop':
                        measurement_indicator[n] = [x,'Stop',self.avgT[x]]
                        n = n + 1
                        overlap_indicator = 0
                    #end if
                    try:
                        if h[s+1] == 'Stop' or h[s+1] == 'Start':
                            measurement_indicator[n] = [x,'Start',self.avgT[x]]
                            n = n + 1
                            if h[s+1] == 'Start':
                                overlap_indicator = 1
                    #end try
                    except IndexError:
                        # if h[s+1] is out of range, i.e. this is the last 'Start':
                        measurement_indicator[n] = [x,'Start',self.avgT[x]]
                    #end except
                #end if
            #end if
            elif self.indicator[x] == 'Stop Oscillation':
                measurement_indicator[n] = [x,'Stop',self.avgT[x]]
                n = n + 1
                # goes to the next element of h:
                s = s + 1
            #end elif
            elif  self.indicator[x] == 'Left Equilibrium':
                # goes to the next element of h:
                s = s + 1
            #end elif
        #end for
        
        # If we hit the end of the data and there wasn't a 'Stop' indicator:
        if measurement_indicator[-1] == [None,None,None]:
            last_elem = len(self.avgT)-1
            measurement_indicator[-1] = [last_elem,'Stop',self.avgT[last_elem]]
        #end if
            
            
        return measurement_indicator
        
    #end def
        
    #--------------------------------------------------------------------------
    def calculate_seebeck(self, measurement_indicator):
        '''
        Calculates Seebeck for each measurement by finding the slope of a
        linear fit to the corrected voltage and dT.
        
        measurement_indicator - list of lists of form [line number, 'Start'/'Stop' , Temperature]
        '''
        self.dT
        self.highV_int_corrected
        self.lowV_int_corrected
        
        # number of measurements:
        num = len(measurement_indicator)/2
        
        measurement_range = [[None,None,None]]*num # start, stop (indexes), temp
        n = 0 # index for this list
        for i in xrange(len(measurement_indicator)-1):
            #if 'Start':
            if measurement_indicator[i][1] == 'Start':
                m1 = measurement_indicator[i] # Start
                m2 = measurement_indicator[i+1] # Stop
                low = m1[0]
                high = m2[0]
                temp = np.average(self.avgT[low:high+1])
                measurement_range[n] = [low, high, temp]
                n = n + 1
        
        
        self.plot_number = 0 # for creating multiple plots without overwriting
        lowV_fit = [None]*len(measurement_range)
        highV_fit = [None]*len(measurement_range)
        for i in xrange(len(measurement_range)):
            low = measurement_range[i][0]
            high = measurement_range[i][1]
            temp = measurement_range[i][2]
            
            x = self.dT[low:high+1]
            y_lowV = self.lowV_int_corrected[low-1:high]
            y_highV = self.highV_int_corrected[low-1:high]
            
            lowV_fit[i] = self.polyfit(x,y_lowV,1,temp)
            highV_fit[i] = self.polyfit(x,y_highV,1,temp)
            
            #celsius = u"\u2103"
            celsius = 'C'
            
            self.create_plot(x, y_lowV, y_highV, lowV_fit[i], highV_fit[i], title='%.2f %s' % (temp, celsius) )
        
        return lowV_fit, highV_fit
        
    #end def
            
    #--------------------------------------------------------------------------
    def polyfit(self, x, y, degree, temp):
        '''
        Returns the polynomial fit for x and y of degree degree along with the
        r^2 and the temperature, all in dictionary form.
        '''
        results = {}
    
        coeffs = np.polyfit(x, y, degree)
    
        # Polynomial Coefficients
        results['polynomial'] = coeffs.tolist()
        
        # Calculate coefficient of determination (r-squared):
        p = np.poly1d(coeffs)
        # fitted values:
        yhat = p(x)                      # or [p(z) for z in x]
        # mean of values:
        ybar = np.sum(y)/len(y)          # or sum(y)/len(y)
        # regression sum of squares:
        ssreg = np.sum((yhat-ybar)**2)   # or sum([ (yihat - ybar)**2 for yihat in yhat])
        # total sum of squares:
        sstot = np.sum((y - ybar)**2)    # or sum([ (yi - ybar)**2 for yi in y])
        results['r-squared'] = ssreg / sstot
        
        results['temperature'] = temp
    
        return results
    
    #end def
    
    #--------------------------------------------------------------------------
    def create_plot(self, x, ylow, yhigh, fitLow, fitHigh, title):
        self.plot_number += 1
        dpi = 400
        
        plt.ioff()
        
        # Create Plot:
        fig = plt.figure(self.plot_number, dpi=dpi) 
        ax = fig.add_subplot(111) 
        ax.grid() 
        ax.set_title(title)
        ax.set_xlabel("dT (K)")
        ax.set_ylabel("dV (uV)")
        
        # Plot data points:
        ax.scatter(x, ylow, color='r', marker='.', label="Low Voltage")
        ax.scatter(x, yhigh, color='b', marker='.', label="High Voltage")
        
        # Overlay linear fits:
        coeffsLow = fitLow['polynomial']
        coeffsHigh = fitHigh['polynomial']
        p_low = np.poly1d(coeffsLow)
        p_high = np.poly1d(coeffsHigh)
        xp = np.linspace(min(x), max(x), 5000)
        low_eq = 'dV = %.2f*(dT) + %.2f' % (coeffsLow[0], coeffsLow[1])
        high_eq = 'dV = %.2f*(dT) + %.2f' % (coeffsHigh[0], coeffsHigh[1])
        ax.plot(xp, p_low(xp), '-', c='#FF9900', label="Low Voltage Fit\n %s" % low_eq)
        ax.plot(xp, p_high(xp), '-', c='g', label="High Voltage Fit\n %s" % high_eq)
        
        ax.legend(loc='upper left', fontsize='10')
        
        # Save:
        plot_folder = self.directory + '/Seebeck Plots/'
        if not os.path.exists(plot_folder):
            os.makedirs(plot_folder)
        
        fig.savefig('%s.png' % (plot_folder + title) , dpi=dpi)
        
        plt.close()
    #end def
    
    #--------------------------------------------------------------------------
    def extract_seebeck_elements(self, definitions):
        '''
        Extracts the data from the Seebeck fits in order to write to file later.
        
        definitions - ouput of self.calculate_seebeck()
        '''
        length = len(definitions)
        
        temp = [None]*length # Temperature
        m = [None]*length # Slope (Seebeck)
        b = [None]*length # offset
        r = [None]*length # r-squared
        
        for x in xrange(length):
            temp[x] = definitions[x]['temperature']
            m[x] = definitions[x]['polynomial'][0]
            b[x] = definitions[x]['polynomial'][1]
            r[x] = definitions[x]['r-squared']
        
        return temp, m, b, r
    
    #end def
    
    #--------------------------------------------------------------------------
    def return_output(self):
        return self.t, self.avgT, self.dT, self.lowV_int_corrected, self.highV_int_corrected, self.indicator
    #end def
        
    #--------------------------------------------------------------------------
    def return_seebeck(self):
        # temps are the same for both
        return self.temp, self.low_m, self.low_b, self.low_r, self.high_m, self.high_b, self.high_r
    #end def
        
    

#end class
###############################################################################

#--------------------------------------------------------------------------
def extract_Data(filePath):
    
    f = open(filePath)
    loadData = f.read()
    f.close()
    
    loadDataByLine = loadData.split('\n')
    numericData = loadDataByLine[5:]
    
    # Create lists that are one less than the total number of lines...
    #   this stops any errors from an incomplete line at the end. :
    length = len(numericData)-2
    ttempA = [None]*length
    tempA = [None]*length
    ttempB = [None]*length
    tempB = [None]*length
    thighV = [None]*length
    highV = [None]*length
    tlowV = [None]*length
    lowV = [None]*length  
    tlowV2 = [None]*length
    lowV2 = [None]*length
    thighV2 = [None]*length
    highV2 = [None]*length
    ttempB2 = [None]*length
    tempB2 = [None]*length
    ttempA2 = [None]*length
    tempA2 = [None]*length  
    indicator = [None]*length
    
    print('Successfully loaded data by line')
    
    for x in xrange(length):
        line = numericData[x].split(',')
        
        ttempA[x] = float(line[0])
        tempA[x] = float(line[1])
        ttempB[x] = float(line[2])
        tempB[x] = float(line[3])
        thighV[x] = float(line[4])
        highV[x] = float(line[5])
        tlowV[x] = float(line[6])
        lowV[x] = float(line[7])  
              
        tlowV2[x] = float(line[8])
        lowV2[x] = float(line[9])
        thighV2[x] = float(line[10])
        highV2[x] = float(line[11])
        ttempB2[x] = float(line[12])
        tempB2[x] = float(line[13])
        ttempA2[x] = float(line[14])
        tempA2[x] = float(line[15])
        
        indicator[x] = line[16]
    #end for
    
    print('Successfully split each line of data')
    return ttempA, tempA, ttempB, tempB, thighV, highV, tlowV, lowV, tlowV2, lowV2, thighV2, highV2, ttempB2, tempB2, ttempA2, tempA2, indicator
              
#end def
            
#--------------------------------------------------------------------------
def create_processed_files(directory, fileName, tc_type):
    '''
    Writes the output from the Process_Data object into seperate files.
    '''
    
    # Make a new folder:
    
    print 'start processing'
    print 'directory: '+ directory
    print 'fileName: ' + fileName
    print 'tc_type: '+ tc_type
    Post_Process = Process_Data(directory, fileName, tc_type)

    print('data processed')
    
    ### Write processed data to a new file:
    outFile = directory + '/Processed_Data.csv'
    file = outFile # creates a data file
    myfile = open(outFile, 'w') # opens file for writing/overwriting
    myfile.write('Time (s),Average T (C),dT (K),Low V Corrected (uV),High V Corrected (uV)\n')
    
    time, avgT, dT, lowV, highV, indicator = Post_Process.return_output()
    
    for x in xrange(len(time)):
        myfile.write('%.2f,%f,%f,%f,%f,%s\n' % (time[x], avgT[x], dT[x], lowV[x], highV[x], indicator[x]))
    
    myfile.close()
    
    
    ### Write linear fits and calculated Seebeck coefficients to a new file:
    seebeck_file = directory + '/Seebeck.csv'
    file = seebeck_file
    myfile = open(seebeck_file, 'w')
    myfile.write('Linear Fit: seebeck*x + offset\n')
    myfile.write('\n')
    myfile.write('Low (i.e. Alumel):,,,,,High (i.e. Chromel):\n')
    table_header = 'Temp (C),Seebeck (uV/K),offset,r^2'
    myfile.write('%s,,%s\n' % (table_header,table_header))
    
    temp, low_m, low_b, low_r, high_m, high_b, high_r = Post_Process.return_seebeck()
    
    for x in xrange(len(temp)):
        myfile.write('%f,%f,%f,%f,,%f,%f,%f,%f\n' % (temp[x], low_m[x], low_b[x], low_r[x], temp[x], high_m[x], high_b[x], high_r[x]))
    
    myfile.close()
    
    
#end def
        
#==============================================================================

def main():
    inFile = 'Data.csv'
    directory = '../Google\ Drive/rwm-tobererlab/Seebeck Data 2015-05-25 20.03.24/'
    
    create_processed_files(directory, inFile, "k-type")
    
#end def

if __name__ == '__main__':
    main()
#end if