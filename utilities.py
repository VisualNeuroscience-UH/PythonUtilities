import zlib
import pickle
import numpy as np
from matplotlib import pyplot as plt
from scipy import sparse
import os
from cxsystem2.core.tools import write_to_file as wtf
from brian2.units import *
import datetime
import pdb

def getData(filename):
    fi = open(filename, 'rb')
    data_pickle = zlib.decompress(fi.read())
    data = pickle.loads(data_pickle)
    return data

def _getDistance(positions,index_position=None):
    '''Calculates distances between neurons. If index position is given, 
    only distances to this neuron is calculated. Without index position, 
    all distance pairs will be calculated.
    Assumes positions as a list or numpy array of complex coordinates'''
    
    positions_array = np.asarray(positions)
    assert len(positions_array) > 1, 'At least two positions necessary for distance'

    # Calculate distance btw one cell and all other cells
    def dist(index_position,other_positions):
        # Assumes arrays of complex numbers
        d = np.sqrt((np.real(index_position)-np.real(other_positions))**2 + 
            (np.imag(index_position)-np.imag(other_positions))**2)
        return d

    # Check whether index_position exists
    if index_position is not None:
        # Calculate distance between index neuron and other neurons
        distance = dist(index_position,positions_array)
    # If only two positions are given
    elif len(positions_array)==2:
        distance = dist(positions_array[0],positions_array[1])
    # Otherwise
    else:
        # Init result matrix
        distance = np.zeros([len(positions_array),len(positions_array)])

        # Loop index neuron positions
        for idx, index_position in enumerate(positions_array):
            ## Create vector array of other positions
            #other_positions = np.hstack([positions_array[:idx],positions_array[idx+1:]]) 
            # Calculate distance between index neuron and all neurons including itself
            distance[idx,:] = dist(index_position,positions_array)
           
    return distance

def _getNeuronIndex(data, neuron_group, position=0+0j):
    neuron_index=data['positions_all']['w_coord'][neuron_group].index(position)
    return neuron_index

def getLambda(D,MF):
    # Length constant according to Schwabe et al J Neurosci 2006
    # D is diameter of mean axonal length in mm along cx.
    # MF is magnification factor (2.3 mm/deg for V1 at 5 deg ecc; 0.45 mm/deg for MT at 5 deg)
    delta_x = 0.5 * D * MF**-1
    l = -1 * delta_x**-1 * np.log(0.05)
    return l

def _createPositions(distance_between_neurons, cx_radius, ndims=2, coordinate_system='w', zero_first=False):
    
    # Define grid. Put RF center to index 0.
    n_neurons_per_row = int(np.ceil((2 * cx_radius) / distance_between_neurons))
    # Check for even N neurons
    if not np.mod(n_neurons_per_row,2):
         n_neurons_per_row += 1
    center_position = 0+0j # assuming center at 0+0j
    
    if ndims==2:
        # Assuming circular grid, n rows = n columns
        n_neurons_per_column = n_neurons_per_row
        positions_real = np.linspace(-cx_radius,cx_radius,n_neurons_per_row)
        positions_imag = np.linspace(-cx_radius,cx_radius,n_neurons_per_column)
    elif ndims==1:
        positions_real = np.linspace(-cx_radius,cx_radius,n_neurons_per_row)
        #Place all cells to y=0
        positions_imag = 0
    else:
        raise NotImplementedError('Number of dimensions is not 1 or 2')
    
    
    positions_grid = np.meshgrid(positions_real,positions_imag)
    positions_grid[1] = positions_grid[1] * 1j
    positions_grid_np_array = positions_grid[0] + positions_grid[1]
    positions_grid_np_array_flat = positions_grid_np_array.flatten()

    # Cut circle according to cx_radius distance
    distances_to_center = _getDistance(positions_grid_np_array_flat, index_position=center_position)
    positions = positions_grid_np_array.flatten()[distances_to_center<=cx_radius]

    if zero_first:
        # Find center
        center_index_tuple=np.where(positions == center_position)
        assert len(center_index_tuple) == 1, 'Other than 1 values equal center value'
        center_index = int(center_index_tuple[0])
        positions_zero_first = np.hstack((positions[center_index],
                                        positions[:center_index],
                                        positions[center_index+1:]))
        positions=positions_zero_first

    if coordinate_system=='z':
        # magnification factor at 5 deg according to Schwabe 2006
        M=2.3
        positions_z = positions/M
        positions = positions_z
    elif coordinate_system=='w':
        pass
    else:
        raise NotImplementedError('Unknown coordinate system')

    positions_out=[(pos) for pos in positions] 

    # Return positions in complex coordinates
    return positions_out

def buildSchwabePositions(ndims=1,group_keys=None,group_values=None):
    
    # Three first groups are in V1 (161 neurons) and the fourth is in V5 (33)
    if group_keys is None or group_values is None:
        group_keys=['NG0_relay_vpm', 'NG1_SS_L2', 'NG2_MC_L2', 'NG3_SS_L6', 'NG4_L2_SS_autoconn_L2']
        group_values=[(0.23,18.4), (0.23,18.4), (0.23,18.4), (1.15,18.4), (0.23,18.4)]
        print("Using default group names and values")
    
    positions_w = {}
    positions_z = {}
    for group_key, group_value in zip(group_keys, group_values):
        positions_w[group_key] = _createPositions(group_value[0],group_value[1],ndims=ndims, coordinate_system='w') 
        positions_z[group_key] = _createPositions(group_value[0],group_value[1],ndims=ndims, coordinate_system='z') # Dummy, code needs
    coord_dict={'w_coord':positions_w, 'z_coord':positions_z}
    data_positions={'positions_all':coord_dict}
    return data_positions

'''def buildSchwabeConnections(data):

    # Replace id only connections
    connection_strengths = 7e-10
    data['relay_vpm__to__SS_L2_soma']['data'] = connection_strengths * sparse.csr_matrix(
                                                np.identity(np.asarray(data['positions_all']['w_coord']['NG1_SS_L2']).size))
    data['SS_L2__to__L2_SS_autoconn_L2_soma']['data'] = connection_strengths * sparse.csr_matrix(
                                                np.identity(np.asarray(data['positions_all']['w_coord']['NG1_SS_L2']).size))
    data['L2_SS_autoconn_L2__to__SS_L2_soma']['data'] = connection_strengths * sparse.csr_matrix(
                                                np.identity(np.asarray(data['positions_all']['w_coord']['NG1_SS_L2']).size))
    data['MC_L2__to__SS_L2_soma']['data'] = connection_strengths * sparse.csr_matrix(
                                                np.identity(np.asarray(data['positions_all']['w_coord']['NG1_SS_L2']).size))
    data['MC_L2__to__MC_L2_soma']['data'] = connection_strengths * sparse.csr_matrix(
                                                np.identity(np.asarray(data['positions_all']['w_coord']['NG2_MC_L2']).size))


    Add id to id + lambda connections
    data['SS_L4__to__SS_L4_soma']['data'] = data['SS_L4__to__SS_L4_soma']['data'] + \
                                                connection_strengths * sparse.csr_matrix(
                                                np.identity(np.asarray(data['positions_all']['w_coord']['NG1_SS_L4']).size))
    
    This covers both local as well as lateral excitation of inhibitory neurons. They have the same value in Schwabe 2006 model.
    data['SS_L2__to__MC_L2_soma']['data'] = data['SS_L2__to__MC_L2_soma']['data'] + \
                                                connection_strengths * sparse.csr_matrix(
                                                np.identity(np.asarray(data['positions_all']['w_coord']['NG2_MC_L2']).size))

    return data'''

def saveSchwabeData(data, base_filename,dir_name=None):
    filename = base_filename + '.gz'
    if dir_name is None:
        dir_name = os.getcwd()
    filenameWithPath = os.path.join(dir_name, filename)
    wtf(filenameWithPath, data)

def _newest(path='./',type='connections'):
    # type = {'connections','results'}
    files = [f for f in os.listdir(path) if type in f]
    paths = [os.path.join(path, basename) for basename in files]
    filename = max(paths, key=os.path.getctime)
    fullfile = os.path.join(path,filename)
    return fullfile

def showLatestConnections(path='./',filename=None, hist_from=None):

    if filename is None:
        filename = _newest(path,type='connections')
    else:
        filename = os.path.join(path, filename)
    print(filename)
    data = getData(filename)

    # Visualize
    # Extract connections from data dict
    list_of_connections = [n for n in data.keys() if '__to__' in n]
 
    # Pick histogram data
    if hist_from is None:
        hist_from = list_of_connections[-1]

    print(list_of_connections)
    n_images=len(list_of_connections)
    n_columns = 2
    n_rows = int(np.ceil(n_images/n_columns))
    fig, axs = plt.subplots(n_rows, n_columns)
    axs = axs.flat
    for ax, connection in zip(axs,list_of_connections):
        im = ax.imshow(data[connection]['data'].todense())
        ax.set_title(connection, fontsize=10)
        fig.colorbar(im, ax=ax)
    data4hist = np.squeeze(np.asarray(data[hist_from]['data'].todense().flatten()))
    data4hist_nozeros = np.ma.masked_equal(data4hist,0)
    axs[(n_rows * n_columns)-1].hist(data4hist_nozeros)
    plt.show()

def showLatestVm(path='./',filename=None):

    if filename is None:
        filename = _newest(path,type='results')
    print(filename)
    data = getData(filename)
    # Visualize
    # Extract connections from data dict
    list_of_results = [n for n in data['vm_all'].keys() if 'NG' in n]

    print(list_of_results)
    n_images=len(list_of_results)
    n_columns = 2
    n_rows = int(np.ceil(n_images/n_columns))

    t=data['vm_all'][list_of_results[0]]['t']
    time_interval=[2000, 4000]

    fig, axs = plt.subplots(n_rows, n_columns)
    axs = axs.flat

    for ax, results in zip(axs,list_of_results):
        N_monitored_neurons = data['vm_all'][results]['vm'].shape[1]
        N_neurons = len(data['positions_all']['w_coord'][results])
        # If all neurons are monitored, show center and it's neighborghs, otherwise, show all.
        if N_monitored_neurons == N_neurons: 
            # neuron_index_center=data['positions_all']['w_coord'][results].index(0+0j)
            neuron_index_center = _getNeuronIndex(data, results, position=0+0j)
            
            im = ax.plot(t[time_interval[0]:time_interval[1]], 
                        data['vm_all'][results]['vm'][time_interval[0]:time_interval[1],
                        neuron_index_center-1:neuron_index_center+2])
        else:
            im = ax.plot(t[time_interval[0]:time_interval[1]], 
                        data['vm_all'][results]['vm'][time_interval[0]:time_interval[1],:])
        ax.set_title(results, fontsize=10)

    plt.show()

def showLatestG(path='./',filename=None):

    if filename is None:
        filename = _newest(path,type='results')
    print(filename)
    data = getData(filename)
    # Visualize
    # Extract connections from data dict
    list_of_results_ge = [n for n in data['ge_soma_all'].keys() if 'NG' in n]
    list_of_results_gi = [n for n in data['gi_soma_all'].keys() if 'NG' in n]

    print(list_of_results_ge)
    n_images=len(list_of_results_ge)
    n_columns = 2
    n_rows = int(np.ceil(n_images/n_columns))

    t=data['ge_soma_all'][list_of_results_ge[0]]['t']
    time_interval=[2000, 4000]

    fig, axs = plt.subplots(n_rows, n_columns)
    axs = axs.flat

    for ax, results in zip(axs,list_of_results_ge):
        im = ax.plot(t[time_interval[0]:time_interval[1]], 
                     data['ge_soma_all'][results]['ge_soma'][time_interval[0]:time_interval[1],0:-1:20])
        ax.set_title(results + ' ge', fontsize=10)

    fig2, axs2 = plt.subplots(n_rows, n_columns)
    axs2 = axs2.flat

    for ax2, results2 in zip(axs2,list_of_results_gi):
        im = ax2.plot(t[time_interval[0]:time_interval[1]], 
                     data['gi_soma_all'][results2]['gi_soma'][time_interval[0]:time_interval[1],0:-1:20])
        ax2.set_title(results2 + ' gi', fontsize=10)

    plt.show()

def showLatestI(path='./',filename=None):

    if filename is None:
        filename = _newest(path,type='results')
    print(filename)
    data = getData(filename)
    # Visualize
    # Extract connections from data dict
    list_of_results_ge = [n for n in data['ge_soma_all'].keys() if 'NG' in n]
    list_of_results_gi = [n for n in data['gi_soma_all'].keys() if 'NG' in n]
    list_of_results_vm = [n for n in data['vm_all'].keys() if 'NG' in n]

    El = -65 * mV
    gl = 50 * nS
    Ee = 0 * mV
    Ei = -75 * mV

    print(list_of_results_ge)
    print(f'Assuming El = {El:6.4f} * mV, gl = {gl:6.4f} * nS, Ee = {Ee:6.4f} * mV, Ei = {Ei:6.4f} * mV\nDig from physiology df if u start messing with neuron types')

    n_images=len(list_of_results_ge)
    n_columns = 2
    n_rows = int(np.ceil(n_images/n_columns))

    t=data['ge_soma_all'][list_of_results_ge[0]]['t']
    time_interval=[2000, 4000]

    fig, axs = plt.subplots(n_rows, n_columns)
    axs = axs.flat

    for ax, results_ge, results_gi, results_vm in zip(  axs,list_of_results_ge, \
                                                        list_of_results_gi,list_of_results_vm):

        N_monitored_neurons = data['vm_all'][results_vm]['vm'].shape[1]
        N_neurons = len(data['positions_all']['w_coord'][results_vm])

        ge= data['ge_soma_all'][results_ge]['ge_soma']
        gi= data['gi_soma_all'][results_gi]['gi_soma']
        vm= data['vm_all'][results_vm]['vm']
        I_total = gl * (El - vm) + ge * (Ee - vm) + gi * (Ei - vm)

        if N_monitored_neurons == N_neurons: 
            # neuron_index_center=data['positions_all']['w_coord'][results_vm].index(0+0j)
            neuron_index_center = _getNeuronIndex(data, results_vm, position=0+0j)
            ax.plot(t[time_interval[0]:time_interval[1]], 
                        I_total[time_interval[0]:time_interval[1],
                        neuron_index_center])
        else:
            ax.plot(t[time_interval[0]:time_interval[1]], 
                        I_total[time_interval[0]:time_interval[1],:])

        ax.set_title(results_vm + ' I', fontsize=10)

        I_total_mean = np.mean(I_total[time_interval[0]:time_interval[1]] / namp)
        I_total_mean_str = f'mean I = {I_total_mean:6.2f} nAmp'
        ax.text(0.05, 0.95, I_total_mean_str, fontsize=10, verticalalignment='top', transform=ax.transAxes)

    plt.show()

def showLatestSpatial(path='./',filename=None,sum_length=None):

    if filename is None:
        filename = _newest(path,type='results')
    print(filename)
    data = getData(filename)

    # Visualize
    coords='w_coord'
    # Extract connections from data dict
    list_of_results = [n for n in data['spikes_all'].keys() if 'NG' in n]

    print(list_of_results)
    n_images=len(list_of_results)
    n_columns = 2
    ylims=np.array([-18.4,18.4])
    n_rows = int(np.ceil(n_images/n_columns))

    width_ratios = np.array([3,1,3,1])
    fig, axs = plt.subplots(n_rows, n_columns * 2, gridspec_kw={'width_ratios': width_ratios})
    axs = axs.flat
    # flat_list_of_results = [item for sublist in list_of_results for item in sublist]

    # Spikes
    for ax1, results in zip(axs[0:-1:2],list_of_results):
        # im = ax1.scatter(data['spikes_all'][results]['t'], data['spikes_all'][results]['i'],s=1)
        position_idxs=data['spikes_all'][results]['i']
        im = ax1.scatter(   data['spikes_all'][results]['t'], 
                            np.real(data['positions_all'][coords][results])[position_idxs],
                            s=1)
        ax1.set_ylim(ylims)
        ax1.set_title(results, fontsize=10)
    # Summary histograms
    for ax2, results in zip(axs[1:-1:2],list_of_results):
        # position_idxs=data['spikes_all'][results]['i']
        #Rearrange and sum neurons in sum_length bin width
        if sum_length is None:
            sum_length = 3 # How many neurons to sum together
        full_vector=data['spikes_all'][results]['count'].astype('float64')
        necessary_length = int(np.ceil(len(full_vector)/sum_length)) * sum_length
        n_zeros = necessary_length - len(full_vector)
        full_vector_padded = np.pad(full_vector, (0, n_zeros), 'constant', constant_values=(np.NaN, np.NaN))
        rearranged_data = np.reshape(full_vector_padded,[sum_length, int(necessary_length/sum_length) ], order='F')
        summed_rearranged_data = np.nansum(rearranged_data, axis=0)
        full_vector_pos = np.real(data['positions_all'][coords][results])
        full_vector_pos_padded = np.pad(full_vector_pos, (0, n_zeros), 'constant', constant_values=(np.NaN, np.NaN))
        rearranged_pos = np.reshape(full_vector_pos_padded,[sum_length, int(necessary_length/sum_length) ], order='F')
        mean_rearranged_pos = np. nanmean(rearranged_pos, axis=0)

        firing_frequency = summed_rearranged_data / (sum_length * data['runtime'])

        pos = mean_rearranged_pos
        im = ax2.barh(pos, firing_frequency, height=1.0)
        ax2.set_ylim(ylims)
        # ax2.axes.get_yaxis().set_visible(False)

    # Shut down last pair if uneven n images
    if np.mod(n_images,2):
        axs[-2].axis('off')
        axs[-1].axis('off')
    plt.show()

def showLatestASF(path='./',timestamp=None,sum_length=None):
    
    if timestamp is None:
        filename = _newest(path,type='results')
        today = str(datetime.date.today()).replace('-','')
        start_index = filename.find(today)
        end_index = start_index + 16
        timestamp = filename[start_index:end_index]

    # Get all files with the same timestamp
    # list all files with the timestamp
    all_files = os.listdir(path)
    files_correct_timestamp = [files for files in all_files if timestamp in files]
    # skip metadata and connections files, get other filenames
    result_files_for_ASF_step1 = [files for files in files_correct_timestamp if 'metadata' not in files]
    result_files_for_ASF = [files for files in result_files_for_ASF_step1 if 'connections' not in files]

    # Sort the result files to increasing center size
    # pick str btw 'act' and '-1.gz', eval the difference, multiply by -1 to get it positive
    filename_dict = {k:-1 * eval(k[k.find('act') + 3 : k.find('-1.gz')]) for k in result_files_for_ASF}
    # sort according to diff
    filename_dict_sorted = sorted(filename_dict,key=filename_dict.get)
    ASF_x_axis_values = sorted(filename_dict.values())
   
    coords='w_coord'
    if sum_length is None:
        sum_length = 3 # How many neurons to sum together

    # Get neuron group names and init ASF_dict
    data = getData(result_files_for_ASF[0])
    list_of_results = [n for n in data['spikes_all'].keys() if 'NG' in n]
    ASF_dict = {k:[] for k in list_of_results}

    # Loop for data
    for filename in filename_dict_sorted:
        print(f'Get {filename}')
        data = getData(filename)

        # For each neuron group, get spike frequencies for neurons of interest, accept sum_length
        for neuron_group in list_of_results:
            # Pick center idx
            center_index = _getNeuronIndex(data, neuron_group, position=0+0j)
            neuron_indices = np.arange(center_index - np.floor(sum_length/2), center_index + np.ceil(sum_length/2)).astype('int')
            # Select data, add to nd array
            full_vector=data['spikes_all'][neuron_group]['count'].astype('float64')
            firing_frequency = np.mean(full_vector[neuron_indices])
            ASF_dict[neuron_group].append(firing_frequency)
    
    # Visualize

    n_images=len(list_of_results)
    n_columns = 2
    # ylims=np.array([-18.4,18.4])
    n_rows = int(np.ceil(n_images/n_columns))

    # ASF is defined for center receptive field. I leave here the option to show the
    # spatial dimension in the second subplot, including eg the parameters of DoG fit
    # along space. This gives us reflection of the FB in case the HO model is not perfect.
    width_ratios = np.array([3,1,3,1])
    fig, axs = plt.subplots(n_rows, n_columns * 2, gridspec_kw={'width_ratios': width_ratios})
    axs = axs.flat
    # flat_list_of_results = [item for sublist in list_of_results for item in sublist]
    # pdb.set_trace()

    # Spikes
    for ax1, neuron_group in zip(axs[0:-1:2],list_of_results):
        ax1.plot(ASF_x_axis_values,ASF_dict[neuron_group])

    # for ax1, results in zip(axs[0:-1:2],list_of_results):
        # position_idxs=data['spikes_all'][results]['i']
        # im = ax1.scatter(   data['spikes_all'][results]['t'], 
        #                     np.real(data['positions_all'][coords][results])[position_idxs],
        #                     s=1)
        # ax1.set_ylim(ylims)
        ax1.set_title(neuron_group, fontsize=10)
    # # Summary histograms
    # for ax2, results in zip(axs[1:-1:2],list_of_results):
    #     # position_idxs=data['spikes_all'][results]['i']
    #     #Rearrange and sum neurons in sum_length bin width
    #     if sum_length is None:
    #         sum_length = 3 # How many neurons to sum together
    #     full_vector=data['spikes_all'][results]['count'].astype('float64')
    #     necessary_length = int(np.ceil(len(full_vector)/sum_length)) * sum_length
    #     n_zeros = necessary_length - len(full_vector)
    #     full_vector_padded = np.pad(full_vector, (0, n_zeros), 'constant', constant_values=(np.NaN, np.NaN))
    #     rearranged_data = np.reshape(full_vector_padded,[sum_length, int(necessary_length/sum_length) ], order='F')
    #     summed_rearranged_data = np.nansum(rearranged_data, axis=0)
    #     full_vector_pos = np.real(data['positions_all'][coords][results])
    #     full_vector_pos_padded = np.pad(full_vector_pos, (0, n_zeros), 'constant', constant_values=(np.NaN, np.NaN))
    #     rearranged_pos = np.reshape(full_vector_pos_padded,[sum_length, int(necessary_length/sum_length) ], order='F')
    #     mean_rearranged_pos = np. nanmean(rearranged_pos, axis=0)

    #     firing_frequency = summed_rearranged_data / (sum_length * data['runtime'])

    #     pos = mean_rearranged_pos
    #     im = ax2.barh(pos, firing_frequency, height=1.0)
    #     ax2.set_ylim(ylims)
    #     # ax2.axes.get_yaxis().set_visible(False)

    # Shut down last pair if uneven n images
    if np.mod(n_images,2):
        axs[-2].axis('off')
        axs[-1].axis('off')
    plt.show()

def createASFset(start_stim_radius=0.1,end_stim_radius=8,units='deg',Nsteps=5,show_positions=True):
    
    M=2.3 # M factor of macaque V1 at 5 deg ecc

    # Turn units to mm cortex
    if units == 'deg':
        start_stim_radius = start_stim_radius * M
        end_stim_radius = end_stim_radius * M
    else:
        assert units == 'mm', "Unknown units, aborting"
    
    # Name neuron group_keys
    group_keys=['NG0_relay_vpm', 'NG1_SS_L2', 'NG2_MC_L2', 'NG3_SS_L6', 'NG4_L2_SS_autoconn_L2']

    # Set outer radius of cells in mm (V1 widest, V5 somewhat smaller to see the edge effect)
    V1_outer_radius = 18.4
    V1_distance_btw_neurons = 0.23
    V5_outer_radius = 18.4
    V5_distance_btw_neurons = 1.15

    # Create positions (start, end, step) with buildSchwabePosisions
    input_radii = np.round( np.linspace(start_stim_radius, end_stim_radius, Nsteps),
                            decimals=1)

    # Create dictionary holding all input radii
    ASF_positions_dict={}
    for input_radius in input_radii:
        # Calculate rounded input radii for same positions as in V1
        # pdb.set_trace()
        input_radius_match_V1 = np.ceil(input_radius / V1_distance_btw_neurons) * V1_distance_btw_neurons
        group_values=[  (V1_distance_btw_neurons,input_radius_match_V1), 
                        (V1_distance_btw_neurons,V1_outer_radius), 
                        (V1_distance_btw_neurons,V1_outer_radius), 
                        (V5_distance_btw_neurons,V5_outer_radius), 
                        (V1_distance_btw_neurons,V1_outer_radius)]

        data_positions = buildSchwabePositions( ndims=1,group_keys=group_keys,
                                                group_values=group_values)

        key='in_radius_' + str(input_radius)
        ASF_positions_dict[key]=data_positions

        if show_positions:
            plt.figure()
            coords='z_coord' # ['w_coord' | 'z_coord']
            counter = 0
            for neuron_group in group_keys:
                points = data_positions['positions_all'][coords][neuron_group]
                plt.scatter(np.real(points),counter + np.imag(points),s=1,)
                plt.grid(color='k', linestyle='--',axis='x')
                counter += 1
            plt.show()

        # Save position files with compact names by calling saveSchwabeData
        saveSchwabeData(data_positions, key, dir_name='../connections')