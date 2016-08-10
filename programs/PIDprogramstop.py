# -*- coding: utf-8 -*-
"""
Created on 26-02-2016
Bobby McKinney
PID initial program
"""
import omegacn7500
import time

def PIDstop(pid1,pid2,pid3,pid4):
    time.sleep(0.1)
    while True:
        try:
            pid1.stop()
            print 'PID 1 stopped'
            break 
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            pid2.stop()
            print 'PID 2 stopped'
            break 
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 1 (sample) temperature: %.2f C' %(pid1.get_pv())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 3 (block) temperature: %.2f C' %(pid3.get_pv())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 1 setpoint: %.2f C' %(pid1.get_setpoint())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 2 (sample) temperature: %.2f C' %(pid2.get_pv())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 4 (block) temperature: %.2f C' %(pid4.get_pv())
            break
        except IOError:
            print IOError
    #end while
    time.sleep(0.1)
    while True:
        try:
            print 'PID 2 setpoint: %.2f C' %(pid2.get_setpoint())
            break
        except IOError:
            print IOError
    #end while
#end def

if __name__=='__main__':
    pid1 = omegacn7500.OmegaCN7500('/dev/cu.usbserial',1)
    pid2 = omegacn7500.OmegaCN7500('/dev/cu.usbserial',2)
    pid3 = omegacn7500.OmegaCN7500('/dev/cu.usbserial',3)
    pid4 = omegacn7500.OmegaCN7500('/dev/cu.usbserial',4)
    PIDstop(pid1,pid2,pid3,pid4)   