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
    def __init__(self, directory, fileName):
        self.directory = directory
        
        filePath = directory + '/'+ fileName
        ttempA, tempA, ttempB, tempB, tVlow, Vlow, tVhigh, Vhigh, tVhigh2, Vhigh2, tVlow2, Vlow2, ttempB2, tempB2, ttempA2, tempA2 = extract_Data(filePath)
        
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
        Vlow_int = self.interpolate(tVlow, Vlow)
        Vlow2_int = self.interpolate(tVlow2, Vlow2)
        for x in xrange(len(Vlow_int)):
            Vlow_int[x] = (Vlow_int[x] + Vlow2_int[x])/2
    
        self.Vlow_int_corrected = self.voltage_Correction(Vlow_int,'low')
        
        Vhigh_int = self.interpolate(tVhigh, Vhigh)
        Vhigh2_int = self.interpolate(tVhigh2, Vhigh2)
        for x in xrange(len(Vhigh_int)):
            Vhigh_int[x] = (Vhigh_int[x] + Vhigh2_int[x])/2
    
        self.Vhigh_int_corrected = self.voltage_Correction(Vhigh_int,'high')
        
        print('calculate seebeck')
        # Complete linear fits to the data to find Seebeck coefficients:
        low_seebeck, high_seebeck = self.calculate_seebeck()
        print "low_seebeck: ",low_seebeck
        print "high_seebeck: ", high_seebeck
        
        print('extracting data from fits')
        # Extract out the data from the fits in order to write to file later:
        self.mlow, self.blow, self.rlow = self.extract_seebeck_elements(low_seebeck)
        self.mhigh, self.bhigh, self.rhigh = self.extract_seebeck_elements(high_seebeck)
        
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
    def voltage_Correction(self, raw_data, side):
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
            v_corrected[x] = self.alphacalc(avgT_Kelvin[x],side)*self.dT[x] - raw_data[x]
        
        return v_corrected
        
    #end def
        
    #--------------------------------------------------------------------------
    def alphacalc(self, x, side):
        ''' x = avgT 
            alpha in uV/K
        '''
        
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
    def calculate_seebeck(self):
        '''
        Calculates Seebeck for each measurement by finding the slope of a
        linear fit to the corrected voltage and dT.
        '''
        x = self.dT
        y_Vlow = self.Vlow_int_corrected
        y_Vhigh = self.Vhigh_int_corrected
        
        Vlow_fit = self.polyfit(x,y_Vlow,1)
        Vhigh_fit = self.polyfit(x,y_Vhigh, 1)
        
        self.create_plot(x, y_Vlow, Vlow_fit, title='low seebeck plot')
        self.create_plot(x, y_Vhigh, Vhigh_fit, title='high seebeck plot')

        
        return Vlow_fit, Vhigh_fit
        
    #end def
            
    #--------------------------------------------------------------------------
    def polyfit(self, x, y, degree):
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
    
        return results
    
    #end def
    
    #--------------------------------------------------------------------------
    def create_plot(self, x, y, fit, title):
        
        dpi = 400
        
        plt.ioff()
        
        # Create Plot:
        fig = plt.figure(dpi=dpi) 
        ax = fig.add_subplot(111) 
        ax.grid() 
        ax.set_title(title)
        ax.set_xlabel("dT (K)")
        ax.set_ylabel("dV (uV)")
        
        # Plot data points:
        ax.scatter(x, y, color='r', marker='.', label="Voltage")
        
        # Overlay linear fits:
        coeffs = fit['polynomial']
        p = np.poly1d(coeffs)
        xp = np.linspace(min(x), max(x), 5000)
        eq = 'dV = %.2f*(dT) + %.2f' % (coeffs[0], coeffs[1])
        ax.plot(xp, p(xp), '-', c='g', label="Voltage Fit\n %s" % eq)
        
        ax.legend(loc='upper left', fontsize='10')
        
        # Save:
        
        fig.savefig('%s.png' % (self.directory +'/'+ title) , dpi=dpi)
        
        plt.close()
    #end def
    
    #--------------------------------------------------------------------------
    def extract_seebeck_elements(self, definitions):
        '''
        Extracts the data from the Seebeck fits in order to write to file later.
        
        definitions - ouput of self.calculate_seebeck()
        '''
        
        m = definitions['polynomial'][0]
        b = definitions['polynomial'][1]
        r = definitions['r-squared']
        
        return m, b, r
    
    #end def
    
    #--------------------------------------------------------------------------
    def return_output(self):
        return self.t, self.avgT, self.dT, self.Vlow_int_corrected, self.Vhigh_int_corrected
    #end def
        
    #--------------------------------------------------------------------------
    def return_seebeck(self):
        # temps are the same for both
        temp = sum(self.avgT)/len(self.avgT)
        return temp, self.mlow, self.blow, self.rlow, self.mhigh, self.bhigh, self.rhigh
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
    tVlow = [None]*length
    Vlow = [None]*length
    tVhigh = [None]*length
    Vhigh = [None]*length

    tVhigh2 = [None]*length
    Vhigh2 = [None]*length
    tVlow2 = [None]*length
    Vlow2 = [None]*length
    ttempB2 = [None]*length
    tempB2 = [None]*length
    ttempA2 = [None]*length
    tempA2 = [None]*length  
    
    print('Successfully loaded data by line')
    
    for x in xrange(length):
        line = numericData[x].split(',')
        
        ttempA[x] = float(line[0])
        tempA[x] = float(line[1])
        ttempB[x] = float(line[2])
        tempB[x] = float(line[3])
        tVlow[x] = float(line[4])
        Vlow[x] = float(line[5])
        tVhigh[x] = float(line[6])
        Vhigh[x] = float(line[7])

        tVhigh2[x] = float(line[8])
        Vhigh2[x] = float(line[9])
        tVlow2[x] = float(line[10])
        Vlow2[x] = float(line[11])
        ttempB2[x] = float(line[12])
        tempB2[x] = float(line[13])
        ttempA2[x] = float(line[14])
        tempA2[x] = float(line[15])
    #end for
    
    print('Successfully split each line of data')
    return ttempA, tempA, ttempB, tempB, tVlow, Vlow, tVhigh, Vhigh, tVhigh2, Vhigh2, tVlow2, Vlow2, ttempB2, tempB2, ttempA2, tempA2
              
#end def
            
#--------------------------------------------------------------------------
def create_processed_files(directory, fileName):
    '''
    Writes the output from the Process_Data object into seperate files.
    '''
    
    # Make a new folder:
    
    print 'start processing'
    print 'directory: '+ directory
    print 'fileName: ' + fileName
    Post_Process = Process_Data(directory, fileName)

    print('data processed')
    
    ### Write processed data to a new file:
    outFile = directory + '/Processed_Data.csv'
    file = outFile # creates a data file
    myfile = open(outFile, 'w') # opens file for writing/overwriting
    myfile.write('Time (s),Average T (C),dT (K),Low V Corrected (uV),High V Corrected (uV)\n')
    
    time, avgT, dT, Vlow, Vhigh = Post_Process.return_output()
    
    for x in xrange(len(time)):
        myfile.write('%.2f,%f,%f,%f,%f\n' % (time[x], avgT[x], dT[x], Vlow[x], Vhigh[x]))
    
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
    
    myfile.write('%f,%f,%f,%f,,%f,%f,%f,%f\n' % (temp, low_m, low_b, low_r, temp, high_m, high_b, high_r))
    
    
    myfile.close()
    
    
#end def
        
#==============================================================================

def main():
    inFile = 'Data.csv'
    directory = '../Google\ Drive/rwm-tobererlab/Seebeck Data 2015-05-25 20.03.24'
    
    create_processed_files(directory, inFile, "k-type")
    
#end def

if __name__ == '__main__':
    main()
#end if