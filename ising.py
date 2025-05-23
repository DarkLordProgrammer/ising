import sys
import os
import time
import csv
import logging
# import click
import numpy as np
# import logging
import matplotlib.pyplot as plt
import multiprocessing as mp
# from IsingLattice import IsingLattice as IsingLattice_c
from sys import exit, argv
# from pandas import DataFrame
# from tqdm import tqdm #fancy progress bar generator
# from ising_c import run_ising #import run_ising function from ising.py

# conditionally import python and C++ version of IsingLattice
has_cpp = False
from IsingLattice_python import IsingLattice as IsingLattice_py
if os.path.isfile('ising_lattice_lib.so'):
    has_cpp = True
    from IsingLattice_cpp    import IsingLattice as IsingLattice_cpp

## main program
def make_B_generator(inp, t_final=None):
    """Return a generator that makes values of B (magetic field in each step)
    note: you *should* play with this function
    
    default implementation: always return 0
    """
    n_slope = inp['n_steps'] - inp['n_burnin'] - inp['n_analyze']
    if n_slope < 0:
        print('fatal error: n_steps - n_burnin - n_slope < 0')
        print('terminating program')
        exit(2)

    # get linearly decreasing values from B to 0
    for val in np.linspace(start=inp['B'], stop=0, num=n_slope):
        yield val

    for val in range(inp['n_burnin']):
        yield 0

    for val in range(inp['n_analyze']):
        yield 0

def make_T_generator(inp, t_final):
    """Return a generator that makes values of T (temperature in each step)
    note: you *should* play with this function
    
    default implementation: 
        start at T=t_top, and linearly decrease temperature to t_final
        hold at t_final for n_burnin
        hold at t_final for n_analyze
    """
    n_slope = inp['n_steps'] - inp['n_burnin'] - inp['n_analyze']
    if n_slope < 0:
        print('fatal error: n_steps - n_burnin - n_slope < 0')
        print('terminating program')
        exit(2)

    # get linearly decreasing values from t_top to t_final
    for val in np.linspace(start=inp['t_top'], stop=t_final, num=n_slope):
        yield val

    for val in range(inp['n_burnin']):
        yield t_final

    for val in range(inp['n_analyze']):
        yield t_final

def set_input(cmd_line_args):
    """Parse command-line parameters into an input dictionary.
    use default values

    input:   sys.argv
             use syntax of keyword:value on command line
    return:  dict[key] = value
    note:    Any value which can be turned into a number will be a float 
             if it has a '.', otherwise it will be a float.

    """

    inp = dict()
    inp['t_min']      = 2.15   # minimum temperature
    inp['t_max']      = 2.5  # maximum temperature
    inp['t_step']     = 0.05    # step size from min to max temperature
    inp['t_top']      = 4.0    # start temperature (arbitrary; feel free to change)
    inp['N']          = 10     # sqrt(lattice size) (i.e. lattice = N^2 points
    n_anneal = 2000
    inp['n_analyze']  = 5000  # number of lattice steps at end of simulation calculated for averages and std.dev.
    inp['n_burnin']   =  2000  # optional parameter, used as naive default
    inp['n_steps']    = n_anneal + inp['n_analyze'] + inp['n_burnin']  # number of lattice steps in simulation    

    # inp['J']          = 1.0    # **great** default value -- spin-spin interaction strength
    inp['B']          = 0    # magnetic field strength
    inp['flip_perc']  = 0.1    # ratio of sites examined to flip in each step
    inp['dir_out']    = 'data_debugging' # output directory for file output
    inp['plots']      = True  # whether or not plots are generated

    inp['print_last_spin']  = False # print the last spin matrix to file                           
    inp['print_inp']  = False  # temperature option
    inp['use_cpp']    = False   # use 1 for True and 0 for False

    inp['date_output'] = False
    inp['file_prefix'] = ''
    inp['multiprocess'] = False
    inp['skip_prog_print'] = False
    

    for x in cmd_line_args[1:]:
        if ':' in x:
            try:
                key, val = x.split(':')
                try:
                    if '.' in val:
                        inp[key] = float(val)
                        print('%-20s'%('inp["%s"]'%key),'set to float  ',inp[key])
                    elif val.lower() == 'false' or val.lower() == 'f':
                        inp[key] = False
                    elif val.lower() == 'true' or val.lower() == 't':
                        inp[key] = True
                    else:
                        inp[key] = int(val)
                        print('%-20s'%('inp["%s"]'%key),'set to int    ',inp[key])
                except:
                    inp[key] = val
                    print('%-20s'%('inp["%s"]'%key),'set to string ',inp[key])
            except:
                print('warning: input "%s" not added to arguments'%x)
        else:
            print('ignoring command line input: %s'%x)

    if inp['print_inp']:
        print('Printed list of input keys:')
        for key in sorted(inp.keys()):
            print('%-20s'%key,' ',inp[key])
    return inp

class check_progress(object):
    """A class that will print a simple status bar of percentage of work done"""
    def __init__(self, inp, T, skip_progress=False):
        self.skip_print = skip_progress
        if self.skip_print:
            return

        self.start_time = time.time()
        self.n_steps = inp['n_steps']
        self.n_check = 1000
        if 'check_per_steps' in inp:
            self.n_check = inp['check_per_steps']
        self.fmt_print = ('%ix%i (T=%.2f) steps: %%7i/%7i, %%5.1f%%%%  '
                'run time: %%8s  est.time-to-go: %%8s'%
                (inp['N'], inp['N'], T, self.n_steps))
        self.n_called = -1 # will progress untill n_called = n_steps
        self.check()
        # print(self.fmt_print)

        # if False:
        #     print('%ix%i IsingLattice. Finished %10i / %10i steps (%4.1f%%). '
        #         'Started '+str(time.strftime('%m-%d %H:%M:%S')))
            # dir_out += str(time.strftime("_%Y%m%d-%H%M%S"))
    def check(self, final=False):
        if self.skip_print:
            return

        self.n_called += 1

        if not self.n_called % 1000 == 0 and not final:
            return
        ratio = float(self.n_called) / self.n_steps
        if ratio == 0:
            time_pass_str = '00:00:00'
            est_str = 'n/a'
        else:
            time_pass = time.time() - self.start_time 
            time_pass_str = time.strftime('%H:%M:%S', time.gmtime(time_pass));
            est_time  = (1-ratio)*time_pass/ratio
            # print('est_time ', est_time)
            est_str = time.strftime('%H:%M:%S', time.gmtime(est_time))
        if final:
            print(self.fmt_print%(self.n_called, ratio*100., time_pass_str, 'done!'))
        else:
            print(self.fmt_print%(self.n_called, ratio*100., time_pass_str, est_str), end='\r')

        
# def check_progress(inp):
#     '''Print the progress of the plot'''
#     pass

def run_ising_lattice(inp, T_final, skip_print=False):
    '''Run a 2-D Ising model on a lattice.
    Return three objects (each a numpy.array, which you can treat
    as identical to a numpy.array)
        M_avg:       the average magnetization of each site for each n_analyze step
        E_avg:       '.........' energy        '..................................'
        correlation: an (N/2-1) array of the correlation function values at the final data frame

        Note that this will use the generators from functions:
        (1) make_T_generator
        (2) make_B_generator
    '''

    time_start = time.time()

    lattice = None
    if inp['use_cpp'] and has_cpp:
        lattice = IsingLattice_cpp(inp['N'], inp['flip_perc'])
    elif inp['use_cpp'] and not has_cpp:
        print('Warning: although use_cpp is set to 1, '
        ' the shared library IsingLattice.so is not present.\n '
        ' Therefore, the python implementation of Ising will be used.')
        lattice = IsingLattice_py(inp['N'],inp['flip_perc'])
    else:
        lattice = IsingLattice_py(inp['N'],inp['flip_perc'])

    # Make the run loop
    try: # try loop that can be interrupted by the user
        #first loop through all steps up to n_analyze
        T_generator = make_T_generator(inp, T_final)
        B_generator = make_B_generator(inp, T_final)
        n_prior = inp['n_steps'] - inp['n_analyze']

        progress = check_progress(inp, T_final, skip_print)

        for T, B, step in zip(T_generator, B_generator, range(n_prior)):
            lattice.step(T,B)
            progress.check()

        # loop through the analyze section of generators
        E_avg = []
        M_avg = []
        '''
        List of spin autocorrelations lists
        R[i][j] where i is the step index (i=0 being the first step in the analyze stage),
        j is the offset index (j=0 being d=1)
        Note T_final is a parameter of this whole method, which is called multiple times per trial
        '''
        R = []
        
        for T, B, step in zip(T_generator, B_generator, range(inp['n_analyze'])):
            lattice.step(T,B)
            E_avg.append(lattice.get_E())
            M_avg.append(lattice.get_M())
            R.append(np.array([entry[1] for entry in lattice.calc_auto_correlation()]))
            progress.check()
        progress.check(True)
        if inp['print_last_spin']:            
            last_spin_matrix = lattice.get_numpy_spin_matrix()
        else:
            last_spin_matrix = None

        lattice.free_memory()
        return (
            np.array(E_avg),
            np.array(M_avg),
            np.array(R),
            last_spin_matrix
        )

    except KeyboardInterrupt:
        try:
            lattice.free_memory()
        except:
            pass
        print("\n\nProgram terminated by keyboard. Good Bye!")
        sys.exit()

def plot_graphs(data): #T,E_mean,E_std,M_mean,M_std): #plot graphs at end
    dat = np.array(data)
    # print('data: ', dat)
    # print('x: ', dat[:,1])
    # x = dat[:,1][0]
    # print('xlist: ', x)

    plt.figure(1)
    # plt.ylim(0,1)
    plt.errorbar(dat[:,0], dat[:,1], yerr=dat[:,2], fmt='o')
    plt.xlabel('Temperature')
    plt.ylabel('Average Site Energy')
    plt.figure(2)
    plt.errorbar(dat[:,0], np.absolute(dat[:,3]), yerr=dat[:,4], uplims=True, lolims=True,fmt='o')
    plt.xlabel('Temperature')
    plt.ylabel('Average Site Magnetization')
    plt.show()

def get_filenames(inp): #make data folder if doesn't exist, then specify filename
    '''Generate the output file names for the EM (energy and megnetism) and SC (spin correlation) files'''
    try:
        dir_out = inp['dir_out']
        prefix  = inp['file_prefix']
        if inp['date_output']:
            dir_out += str(time.strftime("_%Y%m%d-%H%M%S"))

        if not os.path.isdir(dir_out):
            os.makedirs(dir_out)

        # file name = [file_prefix]##_EM_v#.csv if only one temperature (example: runA_4.20_EM_v0.csv)
        #             [file_prefix]##T##_EM_v#.csv if there are two temperatures (example: runA_4.2T5.3_EM_v0.csv) 
        # the other file name is identical, but with "SC" (for spin correlation)) instead of EM
        if inp['t_max'] <= inp['t_min']:
            t_name = '%.2f'%inp['t_min']
        else:
            t_name = '%.2fT%.2f'%(inp['t_min'],inp['t_max'])

        # print('%s%s_SC_v%i.csv'%(prefix,t_name,v))
        v = 0
        while (os.path.isfile( os.path.join(dir_out, '%s%s_EM_v%i.csv'%(prefix,t_name,v))) or
               os.path.isfile( os.path.join(dir_out, '%s%s_SC_v%i.csv'%(prefix,t_name,v)))):
            v += 1

        return ( os.path.join(dir_out, '%s%s_EM_v%i.csv'%(prefix,t_name,v)),
                 os.path.join(dir_out, '%s%s_SC_v%i.csv'%(prefix,t_name,v)),
                 os.path.join(dir_out, '%s%s_LS_v%i.csv'%(prefix,t_name,v)) )

    except:
        print ('fatal: Failed to make output file names')
        sys.exit()

def print_results(inp, data, corr, last_spins_mats=[None]):
    data_filename, corr_filename, last_spins_mats_filename = get_filenames(inp)
    with open(data_filename,'w') as f_out:
        writer = csv.writer(f_out, delimiter=',', lineterminator='\n')
        writer.writerow(['N', 'n_steps', 'n_analyze', 'flip_perc'])
        writer.writerow([inp['N'], inp['n_steps'], inp['n_analyze'], inp['flip_perc']])
        writer.writerow([])
        writer.writerow(['Temp','E_mean','E_std','M_mean','M_std','M_abs_mean','M_abs_std'])
        for entry in data:
            writer.writerow(entry)
        # for t, e_mean, e_std, m_mean, m_std in zip(T, E_mean, E_std, M_mean, M_std):
        #     writer.writerow([t, e_mean, e_std, m_mean, m_std])

    with open(corr_filename,'w') as f_out:
        writer = csv.writer(f_out, delimiter=',', lineterminator='\n')
        writer.writerow(['N', 'n_steps', 'n_analyze', 'flip_perc'])
        writer.writerow([inp['N'], inp['n_steps'], inp['n_analyze'], inp['flip_perc']])
        writer.writerow([])
        writer.writerow(['Temp']+[R_header(i)
                                      for i in range(1,len(corr[0][1])+1)
                                      for R_header in (lambda x: f"R_mean_d={x}", lambda x: f"R_std_d={x}")]) 
        #Offsets calculated from the length of autocorrelation list for first temperature
        for entry in corr:    
            R_data = [R(d) for d in range(len(entry[1]))
                      for R in (lambda x: entry[1][x], lambda x: entry[2][x])]   
            row_data = [entry[0]] + R_data
            writer.writerow(row_data)

    if last_spins_mats[0] is not None:
        with open(last_spins_mats_filename,'w') as f_out:
            writer = csv.writer(f_out, delimiter=',', lineterminator='\n')
            writer.writerow(['N', 'n_steps', 'n_analyze', 'flip_perc', 'T'])
            writer.writerow([inp['N'], inp['n_steps'], inp['n_analyze'], inp['flip_perc'], inp['t_min']])
            writer.writerow([])
            for row in last_spins_mats[0]: #Write out the T = t_min spin matrix rowwise
                writer.writerow(row)

def run_indexed_process( inp, T, data_listener):
# def run_simulation(
#         temp, n, num_steps, num_burnin, num_analysis, flip_prop, j, b, data_filename, corr_filename, data_listener, corr_listener):
    print("Starting Temp {0}".format(round(T,3)))
    try:
        E, M, R, last_spin_matrix = run_ising_lattice(inp, T, skip_print=True) #Lists of microstate values for the analyze stage
        E_mean = np.mean(E)
        E_std = np.std(E)
        M_mean = np.mean(M)
        M_std = np.std(M)
 
        '''
        Each element appended to corr is for a given final temperature temp as part of a trial
        that scans temp. For each final temperature, R_mean[i] and R_std[i] are the average and
        standard deviation of the autocorrelation with offset d = i+1 as computed in the last
        n_analyze steps Averaging R over axis 0 averages with respect to the steps.
        Indexing at 0 is because of numpy convention that an array is returned.
        '''
        R_mean = np.mean(R,axis=0)
        R_std = np.std(R,axis=0)
        
        data_listener.put(([T,E_mean,E_std, M_mean, M_std], [T,R_mean,R_std]))
        # corr_listener.put([T,]+[x[1] for x in C])
        print("Finished Temp {0}".format(round(T,3)))
        return True

    except KeyboardInterrupt:
        print("\n\nProgram Terminated. Good Bye!")
        data_listener.put('kill')
        # corr_listener.put('kill')
        sys.exit()

    except:
        logging.error("Temp="+str(round(T,3))+": Simulation Failed. No Data Written")
        return False

def listener(queue, inp, data):
    '''listen for messages on the queue
    appends messages to data'''
    # f = open(fn, 'a') 
    # writer = csv.writer(f, delimiter=',', lineterminator='\n')
    while True:
        message = queue.get()
        # print('message: ', message)
        if message == 'kill':
            data['data'].sort()
            data['corr'].sort()
            print_results(inp, data['data'], data['corr'])
            print ('Closing listener')
            # print('killing')
            break
        data['data'].append(message[0])
        data['corr'].append(message[1])
        # print('--------\n',data)

def make_T_array(inp):
    if inp['t_max'] <= inp['t_min']:
        return [inp['t_min'],]
    else:
        return np.arange(inp['t_min'], inp['t_max'], inp['t_step'])


def run_multi_core(inp):
    print("\n2D Ising Model Simulation; multi-core\n")
    T_array = make_T_array(inp)

    #must use Manager queue here, or will not work
    manager = mp.Manager()
    data_listener = manager.Queue()
    # corr_listener = manager.Queue()    
    pool = mp.Pool(mp.cpu_count())

    # arrays of results:
    data = {'data':[], 'corr':[]}
    # corr = []

    #put listener to work first
    data_watcher = pool.apply_async(listener, args=(data_listener, inp, data,))
    # corr_watcher = pool.apply_async(listener, args=(corr_listener, inp, corr,))

    #fire off workers 
    jobs = [pool.apply_async(run_indexed_process,args=(inp,T, data_listener)) for T in T_array]

    # collect results from the workers through the pool result queue   
    [job.get() for job in jobs]
    data_listener.put('kill')
    pool.close()

def run_single_core(inp):
    print("\n2D Ising Model Simulation; single core\n")
    # sequentially run through the desired temperatures and collect the output for each temperature
    data = []
    corr = []
    last_spin_mats = []
    for temp in make_T_array(inp):
        E, M, R, last_spin_matrix = run_ising_lattice(inp, temp, skip_print=inp['skip_prog_print'])
        E_mean = np.mean(E)
        E_std = np.std(E)
        M_mean = np.mean(M)
        M_std = np.std(M)
        M_abs_mean = np.mean(np.abs(M))
        M_abs_std = np.std(np.abs(M))   
    
        '''
        Each element appended to corr is for a given final temperature temp as part of a trial
        that scans temp. For each final temperature, R_mean[i] and R_std[i] are the average and
        standard deviation of the autocorrelation with offset d = i+1 as computed in the last
        n_analyze steps Averaging R over axis 0 averages with respect to the steps.
        Indexing at 0 is because of numpy convention that an array is returned.
        '''
        R_mean = np.mean(R,axis=0)
        R_std = np.std(R,axis=0)

        data.append( (temp, E_mean, E_std, M_mean, M_std, M_abs_mean, M_abs_std) )
        corr.append( (temp, R_mean, R_std) )    
        last_spin_mats.append(last_spin_matrix)

    print_results(inp, data, corr, last_spin_mats)

    if inp['plots']:
        plot_graphs(data)


if __name__ == "__main__":
    """Main program: run Ising Lattice here"""
    inp = set_input(argv)
    if inp['multiprocess']:
        run_multi_core(inp)
    if not inp['multiprocess']:
        run_single_core(inp)
