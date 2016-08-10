# -*- coding: utf-8 -*-
"""
Created on 26-04-2016
Bobby McKinney
PID initial program
"""
import os
import time
import matplotlib.pyplot as plt

def TypeKimport():
    fileAl = open('Alumel_Seebeck.csv','r')
    dataAl = fileAl.readlines()
    fileAl.close()
    dataAl.pop(0)
    tempAl = []
    seebeckAl = []
    for line in dataAl:
        tempAl.append(float(line.split(',')[0]))
        seebeckAl.append(float(line.split(',')[1]))
    #end for
    
    fileCh = open('Chromel_Seebeck.csv','r')
    dataCh = fileCh.readlines()
    fileCh.close()
    dataCh.pop(0)
    tempCh = []
    seebeckCh = []
    for line in dataCh:
        tempCh.append(float(line.split(',')[0]))
        seebeckCh.append(float(line.split(',')[1]))
    #end for

    return tempAl,seebeckAl,tempCh,seebeckCh


if __name__=='__main__':
    tAl,sAl,tCh,sCh = TypeKimport()
    line_alumel, = plt.plot(tAl,sAl,'r-',label = 'Alumel')
    line_chromel, = plt.plot(tCh,sCh,'b-', label = 'Chromel')
    plt.xlabel('Temperature (C)')
    plt.ylabel('Seebeck (uV/K)')
    plt.legend()
    plt.grid('on')
    plt.show()
    