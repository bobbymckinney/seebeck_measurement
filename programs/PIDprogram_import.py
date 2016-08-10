# -*- coding: utf-8 -*-
"""
Created on 26-02-2016
Bobby McKinney
PID initial program
"""
import omegacn7500
import time



def PID_Program_import(file,pid1,pid2):    
    # Define the ports for the PID

    datafile = open(file)
    data = datafile.readlines()
    times = []
    setpointsA = []
    setpointsB = []
    for d in data:
        times.append( float( d.split(',')[0] ) )
        setpointsA.append( float( d.split(',')[1] ) )
        setpointsB.append( float( d.split(',')[2] ) )
    #end for
    try:
        for i in range(len(times)):
            pattern = i // 8
            step = i % 8
            print 'Set pattern %d, step %d' % (pattern,step)
            while True:
                try:
                    time.sleep(0.1)
                    pid1.set_pattern_step_setpoint(pattern,step,setpointsA[i])
                    time.sleep(0.1)
                    pid1.set_pattern_step_time(pattern,step,times[i])
                    time.sleep(0.1)
                    pid2.set_pattern_step_setpoint(pattern,step,setpointsB[i])
                    time.sleep(0.1)
                    pid2.set_pattern_step_time(pattern,step,times[i])
                    break
                except IOError:
                    print IOError
                except ValueError:
                    print 'bad value, fix at end'
                    break
            #end while
        #end for
        #display pattern variables
    #end try
    except KeyboardInterrupt:
        print 'programming complete'
    #end except
#end def

def main():
    pid1 = omegacn7500.OmegaCN7500('/dev/cu.usbserial', 1) # Top heater
    pid2 = omegacn7500.OmegaCN7500('/dev/cu.usbserial', 2) # Bottom heater
    while True:
        try:
            choices1 = '\n1: 200C\n2: 225C\n3: 250C\n4: 275C\n5: 300C\n6: 325C\n7: 350C\n8: 375C\n9: 400C\n'
            choices2 = '10: 425C\n11: 450C\n12: 475C\n13: 500C\n14: 300C-continuous\n15: 400C-continuous\n16: 500C-continuous\n17: Other\n'
            profile = input('Which temperature profile would you like to choose?%s'%(choices1+choices2))
            if profile == 1:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/200C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 2:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/225C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 3:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/250C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 4:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/275C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 5:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/300C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 6:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/325C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 7:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/350C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 8:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/375C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 9:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/400C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 10:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/425C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 11:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/450C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 12:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/475C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 13:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/500C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 14:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/continuous300C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 15:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/continuous400C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 16:
                file = '/Users/tobererlab1/Dropbox/te_measurements/seebeck_measurement/programs/continuous500C_profile.csv'
                PID_Program_import(file,pid1,pid2)
                break
            elif profile == 17:
                file = raw_input('Please give your temperature profile csv filepath: ')
                PID_Program_import(file,pid1,pid2)
                break
            print 'try again' 
        except NameError:
            print 'try again'
    #end while

if __name__=='__main__':
    main()   