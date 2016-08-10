# -*- coding: utf-8 -*-
"""
Created on 26-02-2016
Bobby McKinney
PID initial program
"""
import omegacn7500

abort = 0

def PID_Program_Set():    
    # Define the ports for the PID
    pid1 = omegacn7500.OmegaCN7500('/dev/cu.usbserial', 1) # Top heater
    pid2 = omegacn7500.OmegaCN7500('/dev/cu.usbserial', 2) # Bottom heater
    try:
        print 'This program will let you set the setpoint and time for the heater PID controller\n'
        while True:
            pattern = input("What Pattern would you like to set? ")
            for step in range(8):
                print 'Set temperature setpoint and time for pattern %d, step %d for both top and bottom' % (pattern,step)
                while True:
                    try:
                        temp1 = input('Top Setpoint: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
                while True:
                    try:
                        time1 = input('Top Time: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
                while True:
                    try:
                        temp2 = input('Bottom Setpoint: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
                while True:
                    try:
                        time2 = input('Bottom Time: ')
                        break
                    except NameError:
                        print 'try again'
                #end while
            
                pid1.set_pattern_step_setpoint(pattern,step,temp1)
                pid1.set_pattern_step_time(pattern,step,time1)
                pid2.set_pattern_step_setpoint(pattern,step,temp2)
                pid2.set_pattern_step_time(pattern,step,time2)
            
                if step == 7:
                    print 'Set actual steps to complete for pattern %d' % (pattern)
                    while True:
                        try:
                            actualsteps1 = input('Top Actual Steps (0-7): ')
                            break
                        except NameError:
                            print 'try again'
                    #end while
                    while True:
                        try:
                            actualsteps2 = input('Bottom Actual Steps (0-7): ')
                            break
                        except NameError:
                            print 'try again'
                    #end while
                    pid1.set_pattern_actual_step(pattern, actualsteps1)
                    pid2.set_pattern_actual_step(pattern, actualsteps2)
                
                    print 'Set additional cycles to complete for pattern %d' % (pattern)
                    while True:
                        try:
                            additionalcycles1 = input('Top Additional Cycles: ')
                            break
                        except NameError:
                            print 'try again'
                    #end while
                    while True:
                        try:
                            additionalcycles2 = input('Bottom Additional Cycles: ')
                            break
                        except NameError:
                            print 'try again'
                    #end while
                    pid1.set_pattern_additional_cycles(pattern, additionalcycles1)
                    pid2.set_pattern_additional_cycles(pattern, additionalcycles2)
                
                    print 'Set pattern to link to for pattern %d (0-7, 8 for no link)' % (pattern)
                    while True:
                        try:
                            patternlink1 = input('Top Pattern Link: ')
                            break
                        except NameError:
                            print 'try again'
                    #end while
                    while True:
                        try:
                            patternlink1 = input('Bottom Pattern Link: ')
                            break
                        except NameError:
                            print 'try again'
                    #end while
                    pid1.set_pattern_link_topattern(pattern, patternlink1)
                    pid2.set_pattern_link_topattern(pattern, patternlink2)
                
                    print '\nHere are your pattern values for pattern %d for the Top' % (pattern)
                    print pid1.get_all_pattern_variables(pattern)
                    print '\n'
                    
                    print '\nHere are your pattern values for pattern %d for the Bottom' % (pattern)
                    print pid2.get_all_pattern_variables(pattern)
                    print '\n'
                
                
                    while True:
                        try:
                            setnext = raw_input('\nWould you like to set another pattern (y or n)? ')
                            break 
                        except NameError:
                            print 'try again'
                    #end while
                    if setnext != 'y':
                        abort = 1
                        break
                    #end if
                #end if
            #end for
            if abort == 1:
                break
        #end while
        print 'programming complete'
    except KeyboardInterrupt:
        print 'programming complete'
        
    
if __name__=='__main__':
    PID_Program_Set()    