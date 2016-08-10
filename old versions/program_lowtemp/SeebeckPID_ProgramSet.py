# -*- coding: utf-8 -*-
"""
Created on 26-02-2016
Bobby McKinney
PID initial program
"""
import omegacn7500


def PID_Program_Set():    
    # Define the ports for the PID
    pid1 = omegacn7500.OmegaCN7500('/dev/cu.usbserial', 1) # Top heater
    pid2 = omegacn7500.OmegaCN7500('/dev/cu.usbserial', 2) # Bottom heater
    try:
        print 'This program will let you set the setpoint and time for both PID controllers\n'
        for i in range(64):
            pattern = i // 8
            step = i % 8
            print 'Set temperature setpoint and time for pattern %d, step %d' % (pattern,step)
            while True:
                try:
                    temp1 = input('Setpoint PIDA: ')
                    break
                except NameError:
                    print 'try again'
            #end while
            while True:
                try:
                    temp2 = input('Setpoint PIDB: ')
                    break
                except NameError:
                    print 'try again'
            #end while
            while True:
                try:
                    time = input('Time: ')
                    break
                except NameError:
                    print 'try again'
            #end while
            pid1.set_pattern_step_setpoint(pattern,step,temp1)
            pid1.set_pattern_step_time(pattern,step,time)
            
            pid2.set_pattern_step_setpoint(pattern,step,temp2)
            pid2.set_pattern_step_time(pattern,step,time)
            
            if step == 7:
                print 'Set actual steps to complete for pattern %d' % (pattern)
                while True:
                    try:
                        actualsteps1 = input('Actual Steps PIDA: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
                while True:
                    try:
                        actualsteps2 = input('Actual Steps PIDB: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
                pid1.set_pattern_actual_step(pattern, actualsteps1)
                pid2.set_pattern_actual_step(pattern, actualsteps2)
                
                print 'Set additional cycles to complete for pattern %d' % (pattern)
                while True:
                    try:
                        additionalcycles1 = input('Additional Cycles PIDA: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
                while True:
                    try:
                        additionalcycles2 = input('Additional Cycles PIDB: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
                pid1.set_pattern_additional_cycles(pattern, additionalcycles1)
                pid2.set_pattern_additional_cycles(pattern, additionalcycles2)
                
                print 'Set pattern to link to for pattern %d (8 for no linking)' % (pattern)
                while True:
                    try:
                        patternlink1 = input('Pattern Link PIDA: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
                while True:
                    try:
                        patternlink2 = input('Pattern Link PIDB: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
                pid1.set_pattern_link_topattern(pattern, patternlink1)
                pid2.set_pattern_link_topattern(pattern, patternlink2)
                
                print '\nHere are your pattern values for PIDA for pattern %d' % (pattern)
                print pid1.get_all_pattern_variables(pattern)
                print '\n'
                
                print '\nHere are your pattern values for PIDB for pattern %d' % (pattern)
                print pid2.get_all_pattern_variables(pattern)
                print '\n'
                
            #end if
        #end for
    except KeyboardInterrupt:
        print 'programming complete'
    
if __name__=='__main__':
    PID_Program_Set()    