# -*- coding: utf-8 -*-
"""
data for seebeck of copper taken from: Fundamentals of Thermoelectricity by Kamran Behnia
"""

import numpy as np # for linear fits

# for saving plots
import matplotlib.pyplot as plt


#==============================================================================
def main():
    file = open("copper_seebeck_data.txt")
    loadData = file.read()
    file.close()
    
    loadDataByLine = loadData.split('\n')
    Data = loadDataByLine[1:-1]
    
    temp = []
    seebeck = []
    
    for line in Data:
        point = line.split(',')
        temp.append(float(point[0]))
        seebeck.append(float(point[1]))
    #end for    

    coeffs = np.polyfit(temp, seebeck, 10).tolist()
    print coeffs
    
    # Create Plot:
    fig = plt.figure(figsize=(6,6),dpi=100) 
    ax = fig.add_subplot(111) 
    ax.grid() 
    ax.set_title("Copper Seebeck v. Temperature")
    ax.set_xlabel("T (K)")
    ax.set_ylabel("S (uV/K)")
    
    # Plot data points:
    ax.scatter(temp, seebeck, color='r', marker='.', label="Data")
     
    p = np.poly1d(coeffs)
    tp = np.linspace(min(temp), max(temp), 5000)
    
    ax.plot(tp, p(tp), '-', c='g', label="Fit")
    
    ax.legend(loc='upper left', fontsize='10')
    
    plt.show()
    fig.savefig("copper_seebeck_fit_plot.png")
    
    myfile = open("copper_seebeck_fit_equation.csv",'w')
    myfile.write('copper_seebeck\npoly fit results\n\n')
    myfile.write('temp range %f - %f\n\n' % (min(temp),max(temp)))
    myfile.write('deg,coeff\n')
    
    for x in range(len(coeffs)):
        myfile.write(str(x)+','+str(coeffs[-(x+1)])+'\n')
    #end for
    
    myfile.write('\n\ndata taken from: Fundamentals of Thermoelectricity by Kamran Behnia')
    myfile.close()
#end def


if __name__ == '__main__':
    main()
#end if