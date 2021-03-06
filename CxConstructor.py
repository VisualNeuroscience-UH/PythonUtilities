# -*- coding: utf-8 -*-
'''
Construct macaque visual cortex model using existing configuration files.

This module input your definitions MyConstructor
and constructs model of macaque V1. It makes a query to neuroinfo csv data 
and tables from Vanni et al Cerebral Cortex 2020. It uses these data to create
cell groups and connections into anatomical and physiological csv files
for CxSystem2 package.

Classes
    Config: This class contains general utility methods. 
    Area:   This class contains area-level data and methods
    Group:  Neuron group level data and methods
    Connections:    Generate synapses object, which includes the new anatomy df with connections. Use ni csv data.
'''

import numpy as np
from matplotlib import pyplot as plt
import os
import pandas as pd

from cxsystem2.core.tools import  read_config_file

import pdb


###############################################
##### GLOBAL CONSTANTS FOR CXCONSTRUCTOR ######
###############################################

# System-dependent constant paths
ROOT_PATH = r'C:\Users\Simo\Laskenta\Git_Repos\CxConstructor\MacV1Buildup'
PATH_TO_TABLES = os.path.join(ROOT_PATH, 'tables')
PATH_TO_NI_CSV = os.path.join(ROOT_PATH, 'ni_csv_copy')
PATH_TO_CONFIG_FILES = os.path.join(ROOT_PATH, 'config_files')

# Constant filenames
TABLE1_DATA_FILENAME = 'table1_data.csv'
TABLE2_DATA_FILENAME = 'table2_data.csv'
LAYER_NAME_MAP_FILENAME = 'layer_name_mapping_V1.xlsx'
NEURON_COMPARTMENT_FILENAME = 'PC_apical_dendrites.xlsx'
NEURON_GROUP_EPHYS_TEMPLATE_FILENAME = 'neuron_group_ephys_templates.xlsx'
LOCAL_EXCITATORY_CONNECTION_FILENAME = 'connections_local_excitatory.csv'
LOCAL_INHIBITORY_CONNECTION_FILENAME = 'connections_local_inhibitory.csv'
POST_SYN_COMPARTMENTS = 'post_syn_compartments.xlsx'
POST_SYN_TARGET_CELLTYPES = 'post_syn_target_celltypes.xlsx'

# Constant values
N_MAX_NEW_CONNECTIONS = 1000
N_SYNAPSES_PER_CONNECTION = 1
SYNAPSE_TYPE = 'Depressing'
_CELLTYPES = np.array(['PC', 'SS', 'BC', 'MC', 'L1i', 'VPM', 'HH_I', 'HH_E', 'NDNEURON']) # Copied from CxSystem2\cxsystem2\core\physiology_reference.py class NeuronReference

INPUT_LAYER_IDX = 0
INPUT_LAYER_TARGET_LAYER = 'L4C'
INPUT_CONNECTION_PROBABILITY = 1.0


##############################################
################# MAIN CODE ##################
##############################################


class Config:

    '''
    This class contains general objects, concerning all areas and connections. It is here for general data and methods.
    '''    
    
    @classmethod
    def get_data_from_anat_config_df(cls, anat_df, datatype='G'):

        # Get and set column names for neuron groups
        data_columns = anat_df.loc[anat_df.groupby([0]).get_group(datatype).index[0]-1,:].values
        neuron_groups_df = anat_df.groupby([0]).get_group(datatype)
        neuron_groups_df.columns = data_columns

        return neuron_groups_df, data_columns

    @classmethod
    def get_neuron_types(cls):
        neuron_types_df = cls.read_data_from_tables(PATH_TO_TABLES, NEURON_GROUP_EPHYS_TEMPLATE_FILENAME)
        # Pack to easily searchable dataframes

        cutoff_index = neuron_types_df.loc[neuron_types_df.iloc[:,0]=='CompartmentalNeurons'].index.values[0]
        PointNeurons_df = neuron_types_df.iloc[:cutoff_index - 1, :]
        CompartmentalNeurons_df = neuron_types_df.iloc[cutoff_index + 1:, :]
        new_header = CompartmentalNeurons_df.iloc[0]
        CompartmentalNeurons_df = CompartmentalNeurons_df[1:]
        CompartmentalNeurons_df.columns = new_header

        return PointNeurons_df, CompartmentalNeurons_df

    @classmethod
    def read_data_from_tables(cls, path, filename):
        fullpath = os.path.join(path, filename)
        filenameroot, file_extension = os.path.splitext(filename)
        if file_extension=='.csv':
            df = pd.read_csv(fullpath)
        elif file_extension=='.json':
                df = pd.read_json(fullpath)
        elif file_extension=='.xlsx':
                df = pd.read_excel(fullpath)
        else:
            raise NotImplementedError('Unexpected filename extension')

        return df

    @classmethod
    def get_neuroinformatics_data(cls, table_filename, set_index=None):
        table_df = cls.read_data_from_tables(PATH_TO_TABLES, table_filename)
        table_df = table_df.set_index(set_index) 
        return table_df

    @staticmethod
    def pd_string_value2list_of_strings(string_containing_list):
        list_of_strings = string_containing_list.values.tolist()[0].split(',')
        # strip spaces
        list_of_strings = [i.replace(' ','') for i in list_of_strings]
        return list_of_strings

    @staticmethod
    def write_config_files(config_dataframe_df, filename_in, csv=False, json=False, xlsx=False):

        assert csv or json or xlsx, 'Come on, you need at least one type active to write something'

        filename, file_extension = os.path.splitext(filename_in)

        if csv:
            config_dataframe_df.to_csv(os.path.join(PATH_TO_CONFIG_FILES,filename + '.csv'), header=False, index=False)
        if xlsx:
            config_dataframe_df.to_excel(os.path.join(PATH_TO_CONFIG_FILES,filename + '.xlsx'), header=False, index=False)
        if json:
            config_dataframe_df.to_json(os.path.join(PATH_TO_CONFIG_FILES,filename + '.json'))
    

class Area(Config):
    '''
    This class contains area-level data and methods.
    '''

    def __init__(self, area_name='V1', requestedVFradius=.1, center_ecc=5, requested_layers=['L1', 'L23', 'L4A','L4B', 'L4CA', 'L4CB','L5','L6']):
        
        self.area_name=area_name
        self.requestedVFradius=requestedVFradius
        self.center_ecc=center_ecc
        self.requested_layers=requested_layers

        # Read connection table sublayer to Table2 layer mapping. Contains assumed proportions for Ncells/sublayer
        layer_name_mapping_df_orig = self.read_data_from_tables(PATH_TO_TABLES, LAYER_NAME_MAP_FILENAME)
        # Drop comments
        layer_name_mapping_df_orig = layer_name_mapping_df_orig.drop(columns='comments')
        self.layer_name_mapping_df_orig = layer_name_mapping_df_orig
        self.PC_apical_dendrites = self.read_data_from_tables(PATH_TO_TABLES, NEURON_COMPARTMENT_FILENAME)

        # Check layer names for validity: are they mapped in the sublayer to layer mapping file
        # valid_layers = layer_name_mapping_df_orig['allowed_requested_layers'].tolist()
        layer_name_mapping_df_orig_search_columns = ['down_mapping1', 'down_mapping2', 'down_mapping3', 'csv_layers']

        valid_layers = self.get_valid_layer_names(   layer_name_mapping_df_orig, 
                                                layer_name_mapping_df_orig_search_columns)
        assert set(requested_layers) - set(valid_layers) == set(), f'Invalid layer names, valid layer names are {valid_layers}'
        self.valid_layers = valid_layers

        # Map requested_layers to layer_name_mapping_df_groups. Calculate proportions for groups  
        self.layer_name_mapping_df_groups, self.layer_name_mapping_df_full = \
                                        self.map_requested_layers2valid_layers(
                                        requested_layers, layer_name_mapping_df_orig, 
                                        layer_name_mapping_df_orig_search_columns)

        # Create dictionaries both from layer idx to layer name and layer name to layer idx
        self.layerIdx2layerNames_dict = dict(set(zip(self.layer_name_mapping_df_groups['layer_idx'], self.layer_name_mapping_df_groups['requested_layers'])))
        self.layerNames2layerIdx_dict = dict(map(reversed, self.layerIdx2layerNames_dict.items()))

        if area_name=='V1':
            # Get proportion V1 of total V1
            #Requested V1 area in mm2
            V1area = self._VFradius2V1area(requestedVFradius, center_ecc)

            # Get V1 proportion for simulation so that we can get N cells from the total N cells in V1 layers in Table 2
            V1total_area = self.table1_df.loc['mean','V1']
            self.area_proportion = V1area / V1total_area
        else:
            self.area_proportion = 1 # Not implemented yet for other areas

    def map_requested_layers2valid_layers(self, requested_layers, layer_name_mapping_df_orig, search_columns):
        '''
        Map requested_layers to layer_name_mapping_df_groups. Calculate proportions for groups.
        Return df with one layer per requested layer with proportions calculated
        '''
        # Calculate proportions
        # Loop through requested layers
        # Loop through layer_name_mapping_df_orig
        # Is requested layer in down_mapping1, down_mapping2, down_mapping3 or in csv_layers columns?
        # Check if this csv_layer is already accounted for: 
        #   is any down mapping column names already in picked csv list?
        # If yes, discard this layer and continue
        # If no, append corresponding rows to layer_name_mapping_df
        # mark this csv_layer picked for layer_name_mapping_df
        layer_name_mapping_df = pd.DataFrame(columns=layer_name_mapping_df_orig.columns)

        # Add columns for layer idx and requested layers
        layer_name_mapping_df = layer_name_mapping_df.join(pd.DataFrame(columns=['layer_idx']))
        layer_name_mapping_df = layer_name_mapping_df.join(pd.DataFrame(columns=['requested_layers']))
        layer_name_mapping_df_full = layer_name_mapping_df

        # Loop through requested layers
        for current_layer_requested_idx, current_layer_requested in enumerate(requested_layers):

            # Loop through layer_name_mapping_df_orig
            for index, row in layer_name_mapping_df_orig.iterrows():
                
                # Is requested layer in this row's search_columns?
                if current_layer_requested in row[search_columns].values:
                    
                    # Check if current csv_layer is already accounted for: 
                    #   are any of the down mapping column names (row) of the current row 
                    #   already in the csv_layers column of the layer_name_mapping_df?

                    #   if set does not change (no matching names in the csv_layers column), 
                    #   append row to layer_name_mapping_df, otherwise continue
                    if (set(row[search_columns].values) - set(layer_name_mapping_df['csv_layers'].values)) == set(row[search_columns].values):
                        layer_name_mapping_df = layer_name_mapping_df.append(row)
                        # Add layer_idx to last row
                        layer_name_mapping_df.loc[index,'layer_idx'] = current_layer_requested_idx + 1
                        layer_name_mapping_df.loc[index,'requested_layers'] = current_layer_requested
                
                    # All layers are included in full for full csv mapping
                    layer_name_mapping_df_full = layer_name_mapping_df_full.append(row)
                    layer_name_mapping_df_full.loc[index,'layer_idx'] = current_layer_requested_idx + 1
                    layer_name_mapping_df_full.loc[index,'requested_layers'] = current_layer_requested

        # Set layer_idx to integer type
        layer_name_mapping_df['layer_idx'] = layer_name_mapping_df['layer_idx'].astype('int32')
        layer_name_mapping_df_full['layer_idx'] = layer_name_mapping_df_full['layer_idx'].astype('int32')

        # # Add proportions to layer_name_mapping_df_full
        # # layer_name_mapping_df_full = layer_name_mapping_df_full.join(pd.DataFrame(columns=['sub_proportion']))

        # layer_name_mapping_df_full['sub_proportion'] = layer_name_mapping_df_orig['sub_proportion']

        # Check that sums of cells do not exceed table2 counts
        # assert layer_name_mapping_df['sub_proportion'].sum(axis=0) <= current_layer_requested_idx + 1, 'Sums of cells will exceed table2 counts'

        return layer_name_mapping_df, layer_name_mapping_df_full

    def get_valid_layer_names(self, layer_name_mapping_df_orig, columns_for_search):
        '''
        Search layer_name_mapping_V1 through columns csv_layers, and down_mapping1-3.
        Any unique name is valid for request
        '''

        valid_layers = pd.unique(layer_name_mapping_df_orig[columns_for_search].values.ravel('K'))
        return valid_layers

    def _VFradius2V1area(self, radius, center_ecc):
        '''
        Input radius in degrees, output area in mm2
        '''
        a=1
        # Assuming M = 1/(0.077 + 0.082 × E) mm/deg Tootell 1982 Science (valid < 10 deg ecc), we get at center_ecc deg
        M = 1/(0.077 + (0.082 * center_ecc))
        # Taking 1/M = a/k + 1/k * E, we get at center_ecc deg
        k = (a + center_ecc) * M

        cx_min_mm = k * np.log(a + center_ecc - radius)
        cx_max_mm = k * np.log(a + center_ecc + radius)

        # To avoid integrating complex logarithm, we take circular patch of cx, with radius of (cx_max_mm - cx_min_mm) / 2
        radius_in_mm = (cx_max_mm - cx_min_mm) / 2
        V1area = np.pi * np.power(radius_in_mm,2)
        return V1area


class Groups(Config):
    '''
    Neuron group level data and methods
    '''

    def __init__(   self, area_object, requested_cell_types_and_proportions, cell_type_data_source, 
                    cell_type_data_folder_name, cell_type_data_file_name, monitors, bg_inputs):
        
        self.area_object = area_object
        self.requested_cell_types_and_proportions = requested_cell_types_and_proportions

        self.monitors =  monitors
        self.bg_inputs = bg_inputs
        self.requested_cell_types = self.get_requested_cell_types(requested_cell_types_and_proportions)

        # Unpack for init
        inhibitory_types = requested_cell_types_and_proportions['inhibitory_types']
        inhibitory_proportions = requested_cell_types_and_proportions['inhibitory_proportions']
        excitatory_types = requested_cell_types_and_proportions['excitatory_types']
        excitatory_proportions = requested_cell_types_and_proportions['excitatory_proportions']
        requested_layers = area_object.requested_layers

        # Get proportions of inhibitory and excitatory neurons in each layer
        # Valid EIflag 'Glutamatergic' and 'GABAergic'
        self.inhibitory_proportions_df = self.get_proportions_df(   'GABAergic',inhibitory_proportions, inhibitory_types, requested_layers, 
                                                                    cell_type_data_source, cell_type_data_folder_name, cell_type_data_file_name)
        
        self.excitatory_proportions_df = self.get_proportions_df(   'Glutamatergic',excitatory_proportions, excitatory_types, requested_layers, 
                                                                    cell_type_data_source, cell_type_data_folder_name, cell_type_data_file_name)

        
        # Map cell groups to requested layers
        # Choose layer mappings according to requested layers. 
        # TODO If an entry has two values separated by ";", the two values must be averaged

        self.layer_mapping_df = area_object.layer_name_mapping_df_groups

        # Get df with neuron groups for anatomy df, return new df to object
        self.anatomy_config_df_new = self.generate_cell_groups(area_object, requested_cell_types_and_proportions)
        self.physiology_df_with_subgroups = self.spawn_subgroup_physiology()

    def get_requested_cell_types(self, requested_cell_types_and_proportions):  
        '''
        Get cell types mapped to general type names (eg PC instead of PC1) for mapping to data tables
        '''
        requested_cell_types_orig = requested_cell_types_and_proportions['excitatory_types'] + requested_cell_types_and_proportions['inhibitory_types']
        requested_cell_types_noPC1 = ['PC' if x=='PC1' else x for x in requested_cell_types_orig]
        requested_cell_types = ['PC' if x=='PC2' else x for x in requested_cell_types_noPC1]
        return requested_cell_types

    def spawn_subgroup_physiology(self):
        '''
        Spawn subtypes physiology

        Read canonical types from excel
        Read example physiol.csv to df
        Strip old subtypes from physiol df
        Get unique subtypes from anatomy_config_df_new
        Add subtypes one-by-one to physiol df
        Return physiol df
        '''
        # Unpack for current method
        physiology_df = self.physiology_config_df
        anatomy_config_df_new = self.anatomy_config_df_new
        existing_neuron_groups, cell_group_columns = self.get_data_from_anat_config_df(anatomy_config_df_new, 'G') 
        PointNeurons_df, CompartmentalNeurons_df = self.get_neuron_types()
        
        assert '### NEURON GROUP PARAMETERS ###' in physiology_df[0].values, \
            '''Sorry but you need to mark the cut point (start of neuron subgroup ephys properties) 
            in the physiology configuration file with "### NEURON GROUP PARAMETERS ###", because 
            the guy who programmed me is dead-lazy'''
        cutoff_index = physiology_df.loc[physiology_df[0]=='### NEURON GROUP PARAMETERS ###'].index.values[0]

        # Sniff physiology_df for input group, assuming INPUTGROUPNAME,,,\,,, in the csv file
        df_to_sniff = physiology_df.loc[cutoff_index:]
        empty_rows_following_cutoff = df_to_sniff[df_to_sniff.isnull().all(axis=1)].index.values - cutoff_index
        if empty_rows_following_cutoff[0] == 2:
            input_group = df_to_sniff.iloc[1:2,0].values[0]
            assert isinstance(input_group, str), f'Not typical input group expression in physiology config at line {cutoff_index + 1}, aborting...'
            print(f"Warning: Adding assumed input group {input_group}")
            physiology_df_stub = physiology_df.loc[:cutoff_index + 2]
            # Flag input group to Config class object for later use
            Config.input_group = 1
        else:
            physiology_df_stub = physiology_df.loc[:cutoff_index]

        unique_subtypes = existing_neuron_groups['neuron_subtype'].unique()
        collect_subtype_dataframes_list = []

        for neuron_subtype in unique_subtypes:
            # Get matching type
            neuron_type = existing_neuron_groups.groupby(['neuron_subtype']).get_group(neuron_subtype)['neuron_type'].values[0]

            if neuron_type in PointNeurons_df.columns: 
                keys = PointNeurons_df['Key']
                values = PointNeurons_df[neuron_type]
            elif neuron_type in CompartmentalNeurons_df.columns:
                keys = CompartmentalNeurons_df['Key']
                # values = CompartmentalNeurons_df[neuron_type]
                values = self._get_compartmental_values(keys, CompartmentalNeurons_df[neuron_type], neuron_subtype)
            elif neuron_type.startswith('PC'):
                keys = CompartmentalNeurons_df['Key']
                # values = CompartmentalNeurons_df['PC']
                values = self._get_compartmental_values(keys, CompartmentalNeurons_df['PC'], neuron_subtype)
            else:
                raise NotImplementedError('neuron_type not recognized, requested types do not match neuron_group_ephys_templates? Aborting...')

            # Create subtype df
            data = [[neuron_subtype], keys.values.tolist(), values.values.tolist()]
            subtype_ephys_df = pd.DataFrame(data).T
            # Append empty row to the end of df
            subtype_ephys_df = subtype_ephys_df.append(pd.Series(), ignore_index=True)
            # => append to list
            collect_subtype_dataframes_list.append(subtype_ephys_df)
        all_subtype_ephys_df = pd.concat(collect_subtype_dataframes_list,ignore_index=True)    
        # Append to physiology_df_stub
        physiology_df_with_subgroups = pd.concat([physiology_df_stub, all_subtype_ephys_df],ignore_index=True)

        return physiology_df_with_subgroups

    def _get_compartmental_values(self, keys, values, neuron_subtype):
        # Set Area_total, fract_areas and Ra to match PC subtype
        neuron_subtype_layer = neuron_subtype[:neuron_subtype.find('_')]
        neuron_type = neuron_subtype[neuron_subtype.find('_') + 1:]
        # pc_ad_map_df = self.area_object.PC_apical_dendrites.set_index(keys='layer')

        ad_source_layer_idx, ad_target_layer_idx = self.pc_apical_dendrite2layer_idx(neuron_subtype_layer, neuron_type)

        # Example of PC with ad comp 0, 1 and 2
        # fract_areas = {2: array([0.58, 0.052, 0.20, 0.15, 0.020])}
        # Ra = [100,100,150,150,150] * Mohm # There is probably one comp too much here
        # Area_tot_pyram = 10913.2817103 * um**2 rounded to 11000

        # Get constants
        R_basal2soma = 100
        R_apical = 150
        Area_tot_pyram_3ad = 11000 # for 3 ad compartment of size fa_bsa[-1]
        fa_bsa = np.array([0.55, 0.05, 0.2]) # fract_areas_basal_soma_apical

        n_nonsoma_ad_comps = ad_source_layer_idx - ad_target_layer_idx 
        N_comps = 3 + n_nonsoma_ad_comps # basal, soma, apical0 + apical dendrite compartments outside soma layer
        fa_ad = np.repeat(fa_bsa[-1], n_nonsoma_ad_comps)
        fa_bsa_full = np.append(fa_bsa,fa_ad)
        fa_bsa_full = fa_bsa_full / np.sum(fa_bsa_full) # normalize sum to 1, keeping ratio of one_ad_comp / (soma+basal) constant
        n_total_apical_comps = 1 + n_nonsoma_ad_comps
        array_string = ", ".join([str(round(i,2)) for i in fa_bsa_full])
        fract_areas =   '{' + \
                        f'{n_nonsoma_ad_comps}: array([{array_string}])' + \
                        '}'
        Ra_ad = np.repeat(R_apical, n_total_apical_comps)
        Ra_string = ", ".join([str(round(i,0)) for i in Ra_ad])
        Ra = f'[{R_basal2soma}, {Ra_string} ] * Mohm'

        # Area_total_pyram
        at_b = fa_bsa[0] * Area_tot_pyram_3ad
        at_s = fa_bsa[1] * Area_tot_pyram_3ad
        at_ad = fa_bsa[-1] * Area_tot_pyram_3ad
        at_full = at_b + at_s + (at_ad * n_total_apical_comps)
        Area_tot_pyram = f'{at_full} * um**2'
        
        # Set rea_tot_pyram, fract_areas and Ra
        values_new = values

        fract_areas_index = keys=='fract_areas'
        Ra_index = keys=='Ra'
        Area_tot_pyram_index = keys=='Area_tot_pyram'

        values_new = values_new.mask(fract_areas_index,other = fract_areas)
        values_new = values_new.mask(Ra_index,other = Ra)
        values_new = values_new.mask(Area_tot_pyram_index,other = Area_tot_pyram)

        return values_new

    def generate_cell_groups(self, area_object, requested_cell_types_and_proportions):
        '''
        Generate_cell_groups function
        For each layer in macaque V1, set the neuron groups, types and numbers
            -calculate the number of cell groups
            -generate df for holding the neuron groups
                -get starting neuron group idx and line number of insert from anatomy csv
            -map the Table2 data into cell groups
            -return df with neuron group rows for anatomy csv 
        '''
        # Unpacking for current method
        table2_df = self.table2_df
        anatomy_config_df = self.anatomy_config_df
        area_proportion = area_object.area_proportion
        requested_layers = area_object.requested_layers
        PC_apical_dendrites = self.read_data_from_tables(PATH_TO_TABLES, NEURON_COMPARTMENT_FILENAME)
        inhibitory_proportions_df = self.inhibitory_proportions_df
        excitatory_proportions_df = self.excitatory_proportions_df

        monitors = self.monitors
        background_input = self.bg_inputs
        layer_mapping_df = self.layer_mapping_df 


        # Get and set column names for neuron groups
        existing_neuron_groups, cell_group_columns = self.get_data_from_anat_config_df(anatomy_config_df, 'G')

        # Get starting index for cell groups and row indices for anat df
        if self.replace_existing_cell_groups:
            start_cell_group_index = 1 # Reserve 0 for input group
            start_index = anatomy_config_df.groupby([0]).get_group('G').index[0]
        else:
            start_cell_group_index = int(existing_neuron_groups['idx'].values[-1]) + 1
            start_index = anatomy_config_df.groupby([0]).get_group('G').index[-1] + 1

        # Count number of new groups, ie number of new rows
        index_excitatory_s = excitatory_proportions_df.fillna(0).astype(bool).sum()
        index_inhibitory_s = inhibitory_proportions_df.fillna(0).astype(bool).sum()
        N_rows =  index_excitatory_s.sum() + index_inhibitory_s.sum()
        
        # Generate df for holding the neuron groups. Add indices here to preallocate memory
        indices = start_index + np.arange(N_rows)      
        NG_df = pd.DataFrame(columns=cell_group_columns, index=indices)
        
        # Now we go for the cell groups. First let's set the identical values
        NG_df.row_type = 'G'
        NG_df.idx = np.arange(start_cell_group_index, start_cell_group_index + N_rows)
        NG_df.net_center = NG_df.noise_sigma = NG_df.gemean = NG_df.gestd = NG_df.gimean = NG_df.gistd = '--'
        NG_df.monitors = monitors

        # Add one layer at a time starting from L1
        current_group_index = start_index

        for layer in requested_layers:
            current_layer_proportion_inhibitory = self.calc_proportion_inhibitory(layer, table2_df, layer_mapping_df)
            current_layer_N_neurons_area = self.calc_N_neurons(layer, table2_df, layer_mapping_df)
            current_layer_N_excitatory_neurons = (1 - current_layer_proportion_inhibitory) * area_proportion * current_layer_N_neurons_area
            current_layer_N_inhibitory_neurons = current_layer_proportion_inhibitory * area_proportion * current_layer_N_neurons_area
            layer_idx = self.layer_name_to_idx_mapping(layer)

            # Add excitatory cell groups
            for current_group in excitatory_proportions_df.index.values:
                # Jump to next group if proportion is 0
                if excitatory_proportions_df.loc[current_group][layer]==0:
                    continue
                # go through all columns which require individual values. 
                NG_df.loc[current_group_index,'number_of_neurons'] =  np.round(excitatory_proportions_df.loc[current_group][layer] * current_layer_N_excitatory_neurons)
                if current_group in _CELLTYPES:
                    NG_df.loc[current_group_index,'neuron_type'] = current_group
                else:
                    for this_type in _CELLTYPES:
                        if current_group.startswith(this_type):
                            NG_df.loc[current_group_index,'neuron_type'] = this_type
                # Use layers as neuron subtype prefixes
                NG_df.loc[current_group_index,'neuron_subtype'] = layer + '_' + current_group

                # For PC, map apical dendrite extent from table to layer index
                if current_group.startswith('PC'):

                    ad_source_layer_idx, ad_target_layer_idx = self.pc_apical_dendrite2layer_idx(layer, current_group)

                    # Write layer_idx string
                    NG_df.loc[current_group_index,'layer_idx'] =  '[' + str(ad_source_layer_idx) + '->' + str(ad_target_layer_idx) + ']'
                else: 
                    NG_df.loc[current_group_index,'layer_idx'] =  layer_idx

                NG_df.loc[current_group_index,'n_background_inputs'] = background_input['n_background_inputs_for_excitatory_neurons']
                NG_df.loc[current_group_index,'n_background_inhibition'] = background_input['n_background_inhibition_for_excitatory_neurons']
                current_group_index += 1

            # Add inhibitory cell groups
            for current_group in inhibitory_proportions_df.index.values:
                # Jump to next group if proportion is 0

                if inhibitory_proportions_df.loc[current_group][layer]==0:
                    continue
                # go through all columns which require individual values
                NG_df.loc[current_group_index,'number_of_neurons'] =  np.round(inhibitory_proportions_df.loc[current_group][layer] * current_layer_N_inhibitory_neurons)
                NG_df.loc[current_group_index,'neuron_type'] = current_group
                NG_df.loc[current_group_index,'neuron_subtype'] = layer + '_' + current_group
                
                NG_df.loc[current_group_index,'layer_idx'] =  layer_idx

                NG_df.loc[current_group_index,'n_background_inputs'] = background_input['n_background_inputs_for_inhibitory_neurons']
                NG_df.loc[current_group_index,'n_background_inhibition'] = background_input['n_background_inhibition_for_inhibitory_neurons']
                current_group_index += 1

        assert current_group_index == indices[-1] + 1, 'oh-ou'

        # Add to anatomy df

        # Change column names
        NG_df.columns = anatomy_config_df.columns

        # Get end of cell groups index for slicing original anat df
        end_index = anatomy_config_df.groupby([0]).get_group('G').index[-1] + 1
        anatomy_config_df_beginning = anatomy_config_df.iloc[:start_index,:] 
        anatomy_config_df_end = anatomy_config_df.iloc[end_index:,:] 
        anatomy_config_df_new = pd.concat([anatomy_config_df_beginning, NG_df, anatomy_config_df_end], ignore_index=True)

        return anatomy_config_df_new

    def pc_apical_dendrite2layer_idx(self, layer, current_group):
        '''
        Map apical dendrite expression, eg [L5->L1] to source and target layer idx according to existing layers
        '''
        pc_ad_map_df = self.area_object.PC_apical_dendrites.set_index(keys='layer')
        # Map current layer to df index. Find correct row from pc_ad_map_df
        assert layer in pc_ad_map_df.index.values, 'Requested layer not found in PC apical dendrite map. Create matching entry to PC_apical_dendrites.xlsx'
        pc_ad_map_df_row_s = pc_ad_map_df.loc[layer]
        # Map current group to PC1 or PC2
        if current_group is 'PC':
            ad_group = 'PC1'
        else: 
            assert current_group in pc_ad_map_df_row_s.index.values, 'PC group name not found in PC_apical_dendrites.xlsx for current layer'
            ad_group = current_group

        # Map ad source and target to corresponding layer indices
        ad_string = pc_ad_map_df_row_s.loc[ad_group]
        ad_source_layer_name = ad_string[ad_string.find('[') + 1 : ad_string.find('->')]
        ad_source_layer_idx = self.layer_name_to_idx_mapping(ad_source_layer_name)
        ad_target_layer_name = ad_string[ad_string.find('->') + 2 : ad_string.find(']')]
        ad_target_layer_idx = self.layer_name_to_idx_mapping(ad_target_layer_name)

        return ad_source_layer_idx, ad_target_layer_idx

    def layer_name_to_idx_mapping(self, layer_in):
        assert layer_in in self.layer_mapping_df['requested_layers'].values, 'Current layer not among requested layers'
        layer_idx = self.layer_mapping_df.loc[self.layer_mapping_df['requested_layers'] == layer_in, 'layer_idx'].values[0]
        return layer_idx

    def calc_N_neurons(self, current_layer, table2_df, layer_mapping_df):
        # When more or less than than one layer maps to requested layer, one cannot directly query table 2
        # Instead you need to sum according to sub_proportion
        # from layer_mapping_df, choose current_layer rows in requested_layer_column
        # TODO Less than one layer not implemented yet

        table2to_sub_proportions_df = layer_mapping_df.loc[layer_mapping_df['requested_layers'] == 
                                        current_layer, ['table2_df', 'sub_proportion']]

        # Calculate sum, 
        # sigma_i(sub_proportion_i * n_neurons_i) * 1e6

        sum_neurons = 0
        for idx, table2_requested_layer in enumerate(table2to_sub_proportions_df['table2_df'].values):
            sum_neurons += table2to_sub_proportions_df.loc[:,'sub_proportion'].values[idx] * \
                                table2_df.loc[table2_requested_layer,'n_neurons_10e6'] 

        # Scale
        sum_neurons_scaled = sum_neurons * 1e6

        return sum_neurons_scaled

    def calc_proportion_inhibitory(self, current_layer, table2_df, layer_mapping_df):
        # When more or less than than one layer maps to requested layer, one cannot directly query table 2
        # Instead you need to average according to sub_proportion
        # from layer_mapping_df, choose current_layer rows in requested_layer_column
        # TODO Less than one layer not implemented yet

        table2to_sub_proportions_df = layer_mapping_df.loc[layer_mapping_df['requested_layers'] == 
                                        current_layer, ['table2_df', 'sub_proportion']]

        # Calculate weighed average, 
        # sigma_i(sub_proportion_i * n_neurons_i * percent_inhibitory_i)/sigma_i(sub_proportion_i * n_neurons_i)

        useful_numerator = 0
        useful_denominator = 0
        for idx, table2_requested_layer in enumerate(table2to_sub_proportions_df['table2_df'].values):
            useful_numerator += table2to_sub_proportions_df.loc[:,'sub_proportion'].values[idx] * \
                                table2_df.loc[table2_requested_layer,'n_neurons_10e6'] * \
                                table2_df.loc[table2_requested_layer,'percent_inhibitory']
            useful_denominator +=   table2to_sub_proportions_df.loc[:,'sub_proportion'].values[idx] * \
                                    table2_df.loc[table2_requested_layer,'n_neurons_10e6']
        percentage_inhibitory = useful_numerator / useful_denominator

        # From percentage to proportion
        proportion_inhibitory = percentage_inhibitory / 100

        return proportion_inhibitory

    def drop_unused_cell_types(self, proportions_df, types):
            unused_types_set = set(proportions_df.index) - set(types)
            proportions_df_clean = proportions_df.drop(unused_types_set, axis=0)
            # rescale to sum 1 after dropping the unused types
            proportions_df = proportions_df_clean / proportions_df_clean.sum(axis=0)
            return proportions_df

    def get_markram_cell_type_proportions(self, cell_type_df, EIflag):
        # This diverges according to EI flag because excitatory is not implemented currently
        
        if EIflag=='Glutamatergic':
            # This can be fixed later. Now it gives proportions of cell types as 1/N types
            excitatory_proportions_df = self.get_empty_cell_type_proportions(self.area_object.requested_layers, self.requested_cell_types_and_proportions['excitatory_types'])
            return excitatory_proportions_df

        elif EIflag=='GABAergic':
            # Get cell type proportions from Markram rat somatosensory cx data
            n_neurons_per_type = cell_type_df.loc['No. of neurons per morphological types',:]
            type_mapping = {
                'SST' : ['MC'],
                'PVALB' : ['NBC','LBC'],
                'VIP' : ['SBC','BP','DBC']}
            layers_for_cell_count = cell_type_df.columns.values
            type_count = {}
            inhibitory_proportions_df = pd.DataFrame(index=type_mapping.keys())

            # calculate sum of inhibitory SST, PV and VIP cells
            for layer_for_count in layers_for_cell_count:
                cell_count_dict = n_neurons_per_type[layer_for_count]
                layer_string_to_add = layer_for_count + '_'
                for current_type in type_mapping.keys():
                    n_neurons_for_current_type = 0
                    subtypes_list = type_mapping[current_type]
                    for current_subtype in subtypes_list:
                        try:
                            n_neurons_for_current_subtype = cell_count_dict[layer_string_to_add + current_subtype]
                            n_neurons_for_current_type += n_neurons_for_current_subtype
                        except KeyError:
                            continue
                    type_count[current_type] = n_neurons_for_current_type

                # get proportions of the three types in different layers
                type_count_array = np.fromiter(type_count.values(), dtype=float)
                proportions = type_count_array/sum(type_count_array)
                inhibitory_proportions_df[layer_for_count] = pd.Series(proportions, index=type_mapping.keys())
            return inhibitory_proportions_df

    def get_allen_cell_type_proportions(self, cell_type_allen_df_raw, EIflag):
        # Valid EIflag 'Glutamatergic' and 'GABAergic'

        # Select appropriate classifying parameters from df
        cell_type_allen_relevant_columns_df = cell_type_allen_df_raw[['region_label', 'class_label', 'subclass_label', 'cortical_layer_label']]
        cell_type_allen_V1_df = cell_type_allen_relevant_columns_df.loc[cell_type_allen_relevant_columns_df['region_label'] == 'V1C']
        cell_type_allen_df = cell_type_allen_V1_df.drop(columns=['region_label'])
        
        grouped = cell_type_allen_df.groupby(['class_label', 'cortical_layer_label'])
        allen_layers = cell_type_allen_df['cortical_layer_label'].unique()

        # Prepare for getting unique cell types from Allen data
        cell_type_allen_df_for_unique_types = cell_type_allen_df.drop('cortical_layer_label', axis=1)
        grouped_for_unique_types = cell_type_allen_df_for_unique_types.groupby(['class_label'])

        # Neuron proportions
        # Get unique types
        types=grouped_for_unique_types.get_group(EIflag)['subclass_label'].unique()
        proportions_df = pd.DataFrame(index=types)

        for layer_for_count in allen_layers:
            neurons_by_layer = grouped.get_group((EIflag,layer_for_count))
            proportions = neurons_by_layer['subclass_label'].value_counts(normalize=True)
            proportions_df[layer_for_count] = proportions

        return proportions_df

    def get_empty_cell_type_proportions(self, requested_layers, requested_types):
        '''
        Create cell type proportions from N cell types when they are not defined by user or pre-existing data
        '''
        N_types = len(requested_types)
        proportions = 1/N_types
        proportions_df = pd.DataFrame(index=requested_types, columns=requested_layers).fillna(proportions)

        return proportions_df

    def get_proportions_df(self, EIflag, proportions, types, requested_layers, cell_type_data_source, cell_type_data_folder_name, cell_type_data_file_name):
        'Get excitatory and inhibitory cell type proportions'

        assert set(proportions.keys()) == set(requested_layers) or len(proportions) == 0, \
            'f{EIflag} cell group proportions do not match requested layers, aborting...'

        if proportions: # If manually given, executes this end continues
            proportions_df =  pd.DataFrame(data=proportions, index=types)

        elif cell_type_data_source: # If given
            fullpath = os.path.join(PATH_TO_TABLES, cell_type_data_folder_name)
            cell_type_df = self.read_data_from_tables(fullpath, cell_type_data_file_name)

            if cell_type_data_source=='HBP' or cell_type_data_source=='Markram':
                proportions_df = self.get_markram_cell_type_proportions(cell_type_df, EIflag)

            elif cell_type_data_source=='Allen':
                # Valid EIflag 'Glutamatergic' and 'GABAergic'
                proportions_df = self.get_allen_cell_type_proportions(cell_type_df, EIflag)

            proportions_df = self.drop_unused_cell_types(proportions_df, types)

        # If no proportions is defined manually and no data source is given, fill proportions with 1/N cell types
        elif not cell_type_data_source: 
            proportions_df = self.get_empty_cell_type_proportions(requested_layers, types)
                
        return proportions_df


class Connections(Config):
    '''
    Generate synapses object, which includes the new anatomy df with connections
    '''

    def __init__(self, area_object, group_object, use_all_csv_data):

        # TÄHÄN JÄIT: KYTKE INPUT MUIHIN RYHMIIN; SIIRRÄ COMP GLOBAALIT YLÖS; HARKITSE SIISTIMISTÄ
        
        # Read data from files.
        # Read ni csv into dataframe
        exc_df = self.read_data_from_tables(PATH_TO_NI_CSV, LOCAL_EXCITATORY_CONNECTION_FILENAME)
        inh_df = self.read_data_from_tables(PATH_TO_NI_CSV, LOCAL_INHIBITORY_CONNECTION_FILENAME)
        self.post_syn_comp_df = self.read_data_from_tables(PATH_TO_TABLES, POST_SYN_COMPARTMENTS)
        self.post_syn_type_df = self.read_data_from_tables(PATH_TO_TABLES, POST_SYN_TARGET_CELLTYPES)
        
        area_name = area_object.area_name
        requested_layers = area_object.requested_layers
        # layer_mapping_df = group_object.layer_mapping_df
        # layer_name_mapping_df_orig = area_object.layer_name_mapping_df_orig
        layer_name_mapping_df_groups = area_object.layer_name_mapping_df_groups
        layer_name_mapping_df_full = area_object.layer_name_mapping_df_full


        self.anatomy_config_df_new_groups = group_object.anatomy_config_df_new
        
        # Map exc_df and inh_df to valid format inhibitory and excitatory connections in each layer
        self.excitatory_connections_df = self.get_local_connection_df(exc_df, area_name, 
                                            layer_name_mapping_df_full, layer_name_mapping_df_groups)

        self.inhibitory_connections_df = self.get_local_connection_df(inh_df, area_name, 
                                            layer_name_mapping_df_full, layer_name_mapping_df_groups)

        # Generate connections
        self.anatomy_config_df_new_groups_new_synapses = self.generate_synapses(area_object, group_object)

    def generate_synapses(self, area_object, group_object):
        '''
        generate_synapses function
        -for each origin and target group, set receptor,pre_syn_idx,post_syn_idx by layer and compartment,syn_type,p,n,
        -return df with receptor,pre_syn_idx,post_syn_idx,syn_type,p,n, 

        '''

        # Unpack for this method
        layer_mapping_df = area_object.layer_name_mapping_df_groups
        layerIdx2layerNames_dict = area_object.layerIdx2layerNames_dict
        layerNames2layerIdx_dict = area_object.layerNames2layerIdx_dict
        requested_cell_types = group_object.requested_cell_types
        excitatory_proportions_df = group_object.excitatory_proportions_df
        inhibitory_proportions_df = group_object.inhibitory_proportions_df

        replace_existing_cell_groups = self.replace_existing_cell_groups
        excitatory_connections_df = self.excitatory_connections_df 
        inhibitory_connections_df = self.inhibitory_connections_df 
        anatomy_config_df_new_groups = self.anatomy_config_df_new_groups

        # Get and set column names for connections
        existing_connection, connection_columns = self.get_data_from_anat_config_df(self.anatomy_config_df, 'S')

        # Get starting index for connections and row indices for anat df
        if self.replace_existing_cell_groups:
            start_index = anatomy_config_df_new_groups.groupby([0]).get_group('S').index[0]
        else:
            start_index = anatomy_config_df_new_groups.groupby([0]).get_group('S').index[-1] + 1

        # N_rows = self._get_n_connection_rows(group_object, excitatory_connections_df, inhibitory_connections_df, excitatory_proportions_df, inhibitory_proportions_df, layerNames2layerIdx_dict)
        N_rows = N_MAX_NEW_CONNECTIONS

        self.post_syn_comp_df # rules for connecting synapses to postsyn PC compartments
        
        # Generate df for holding the connections. Add indices here to preallocate memory
        indices = start_index + np.arange(N_rows)      
        syn_df = pd.DataFrame(columns=connection_columns, index=indices)

        # Now we go for the cell groups. First let's set the identical values
        syn_df.row_type = 'S'
        syn_df.syn_type = SYNAPSE_TYPE
        syn_df.n = N_SYNAPSES_PER_CONNECTION
        syn_df.monitors = syn_df.custom_weight = '--'
        syn_df.load_connection = syn_df.save_connection = 0

        # Get neuron groups for their index search below
        existing_neuron_groups_df, cell_group_columns = self.get_data_from_anat_config_df(anatomy_config_df_new_groups, 'G')

        # Add one layer at a time starting from L1
        current_connection_index = start_index
        
        # Set 'receptor', 'pre_syn_idx', 'post_syn_idx', 'p'

        # Input connections
        if Config.input_group == 1:
            # define connections_df for the input group
            input_layer_idx = INPUT_LAYER_IDX
            input_layer_target_layer = layerNames2layerIdx_dict[INPUT_LAYER_TARGET_LAYER] 
            input_connection_probability = INPUT_CONNECTION_PROBABILITY
            input_connections_dict = {  'FromLayer':input_layer_idx,
                                        'ToLayer':input_layer_target_layer,
                                        'p':input_connection_probability}
            input_connections_df = pd.DataFrame(input_connections_dict, index=np.arange(1))
            in_type = excitatory_proportions_df.index[0] # get first neuron type as in type
            primary_proportion_df = excitatory_proportions_df
            primary_proportion_df.loc[in_type,'IN'] = 1
            layerIdx2layerNames_dict[0] = 'IN'
            # Prepend existing_neuron_groups_df with index 'INPUT', column 'neuron_subtype'='IN_SS'; 'layer_idx' = 0
            top_row_df = pd.DataFrame(columns=existing_neuron_groups_df.columns, index=['INPUT'])
            top_row_df['idx'] = [0] # group index
            top_row_df['neuron_type'] = [in_type] 
            top_row_df['neuron_subtype'] = [f'IN_{in_type}'] 
            top_row_df['layer_idx'] = [INPUT_LAYER_IDX]
            prepended_neuron_groups_df = pd.concat([top_row_df, existing_neuron_groups_df])

            syn_df, current_connection_index = self._set_connection_parameters(syn_df, 
                prepended_neuron_groups_df, input_connections_df, primary_proportion_df,  
                inhibitory_proportions_df, current_connection_index, layerIdx2layerNames_dict, 
                layerNames2layerIdx_dict, requested_cell_types, receptor_type='ge')

        # Excitatory connections
        syn_df, current_connection_index = self._set_connection_parameters(syn_df, 
            existing_neuron_groups_df, excitatory_connections_df, excitatory_proportions_df,  
            inhibitory_proportions_df, current_connection_index, layerIdx2layerNames_dict, 
            layerNames2layerIdx_dict, requested_cell_types, receptor_type='ge')
        
        # Inhibitory connections
        syn_df, current_connection_index = self._set_connection_parameters(syn_df, 
            existing_neuron_groups_df, inhibitory_connections_df, excitatory_proportions_df,  
            inhibitory_proportions_df, current_connection_index, layerIdx2layerNames_dict, 
            layerNames2layerIdx_dict, requested_cell_types, receptor_type='gi')

        # Cut extra rows
        assert current_connection_index < N_MAX_NEW_CONNECTIONS + start_index,\
            f'''Increase constant N_MAX_NEW_CONNECTIONS, now {N_MAX_NEW_CONNECTIONS} but you have {current_connection_index-start_index} connections'''
        syn_df = syn_df.loc[:current_connection_index - 1,:]

        # Sort to 1-source neuron group, 2-E,I
        # Because neuron groups are numbered from layer 1 downwards, E first, we get
        # sorted as source layer E -> target neuron group  E, I -> source layer I -> target neuron group E, I
        syn_df = syn_df.sort_values(by=['pre_syn_idx', 'receptor'])

        # Change column names
        syn_df.columns = anatomy_config_df_new_groups.columns
        
        # Get anat config df first new connection index
        anatomy_config_df_beginning = anatomy_config_df_new_groups.iloc[:start_index,:] 
        
        # Concatenate, ignore sorted syn_df index
        anatomy_config_df_new = pd.concat([anatomy_config_df_beginning, syn_df], ignore_index=True)

        return anatomy_config_df_new

    def _set_connection_parameters(self, syn_df, existing_neuron_groups_df, connections_df, 
            excitatory_proportions_df, inhibitory_proportions_df, current_connection_index, 
            layerIdx2layerNames_dict, layerNames2layerIdx_dict, requested_cell_types, 
            receptor_type=None):
        
        post_syn_comp_df_requested_cell_types =  self.post_syn_comp_df.loc[ 
            self.post_syn_comp_df['Presynaptic Cell Types'].isin(requested_cell_types)]
        post_syn_type_df_requested_cell_types =  self.post_syn_type_df.loc[ 
            self.post_syn_type_df['Presynaptic Cell Types'].isin(requested_cell_types)]

        receptor = receptor_type

        for conn_idx in connections_df.index.values:

            pre_layer = layerIdx2layerNames_dict[connections_df.loc[conn_idx,'FromLayer']]
            post_layer_idx = connections_df.loc[conn_idx,'ToLayer']
            post_layer = layerIdx2layerNames_dict[post_layer_idx]
            probability = connections_df.loc[conn_idx,'p']

            #Create logic for switching between e and i proportions
            if receptor == 'ge':
                primary_proportion = excitatory_proportions_df
            elif receptor == 'gi':
                primary_proportion = inhibitory_proportions_df

            for current_pre_type in  \
                primary_proportion.index[primary_proportion[pre_layer].fillna(0).astype(bool).values].values: 
                # Get pre group idx
                pre_neuron_subtype = pre_layer + '_' + current_pre_type

                '''
                In addition to neuron groups in the current post_layer, PC groups below this layer 
                may have their apical dendrites here. Postsynaptic connections may go to PC soma, apical or  
                basal dendrite in this layer or to apical dendrites crossing this layer. Thus we need to
                add all PC groups with crossing apical dendrites to post neuron groups
                Pseudocode:
                Expand existing_neuron_groups_df PC layer idx from  [7->1] to array of 1,2,3,4,5,6,7 for search of corresponding post syn layer
                Associate matching compartments with indices to PC apical dendrite
                Get matching compartments of all PC groups at the current post_layer.

                Coding of post_syn_idx for PCs:
                1[C]0ba : 1 is NG idx, [C] is compartmental flag, 0 is layer idx starting from NG home layer upwards, 
                home layer = 0. a is apical d, b is basal d, s is soma.

                So you need NG idx for all postsyn groups and postsyn compartment idx for PC neurons. 
                Then you need to map exc conn to ba and inh conn to s at soma layer
                '''

                # Get neuron_subtype list of PC groups whose apical dendrites extend to this post_layer_idx
                pc_groups_list, pc_groups_comp_list = self._get_pc_groups(existing_neuron_groups_df[['neuron_type', 'neuron_subtype', 'layer_idx']], post_layer_idx)
                exc_groups_list = excitatory_proportions_df.index[excitatory_proportions_df[post_layer].fillna(0).astype(bool).values].values.tolist()
                point_exc_groups_list = [g for g in exc_groups_list if not g.startswith('PC')]
                inh_groups_list = inhibitory_proportions_df.index[inhibitory_proportions_df[post_layer].fillna(0).astype(bool).values].values.tolist()
                all_post_types_in_current_post_layer = point_exc_groups_list + pc_groups_list + inh_groups_list

                for current_post_type in all_post_types_in_current_post_layer:

                    # init weight_pretype2posttype, weight_pretype2postcomp
                    weight_pretype2posttype = 1
                    weight_pretype2postcomp = 1

                    pre_type = current_pre_type
                    post_type = current_post_type

                    if pre_type.startswith('PC'): 
                        pre_type = 'PC' # Truncate for main type
                    if post_type.startswith('PC') or \
                        post_type.startswith('L') and '_PC' in post_type: 
                        post_type = 'PC' # Truncate for main type

                    # Check if pre type contacts post type, if yes get weight multiplier, otherwise continue
                    allowed_types_s = post_syn_type_df_requested_cell_types.loc[
                        post_syn_type_df_requested_cell_types['Presynaptic Cell Types'] == 
                        pre_type,'Postsynaptic Cell Types']
                        
                    allowed_types_list = self.pd_string_value2list_of_strings(allowed_types_s)

                    if not post_type in allowed_types_list:
                        continue 
                    else:
                        #Find which index of list contains the post type
                        matching_idx = allowed_types_list.index(post_type)
                        # Get multiplier
                    allowed_weights = post_syn_type_df_requested_cell_types.loc[
                        post_syn_type_df_requested_cell_types['Presynaptic Cell Types'] == 
                        pre_type,'Postsynaptic Cell Weights'] 
                    allowed_weights_list = self.pd_string_value2list_of_strings(allowed_weights) 
                    weight_pretype2posttype = np.float(allowed_weights_list[matching_idx])

                    if post_type == 'PC':
                        postsyn_ad = ''
                        comp_name = ''
                        # weight_pretype2postcomp = 0
                        ng_idx = str(existing_neuron_groups_df.loc[existing_neuron_groups_df['neuron_subtype'] == current_post_type, 'idx'].values[0])
                        comp_idx = self._get_comp_idx(current_post_type, post_layer, layerNames2layerIdx_dict)
                        # Get post comp connection weight for current pre type, continue if zero
                        current_pre_type_post_comp_distribution = post_syn_comp_df_requested_cell_types.loc[
                            post_syn_comp_df_requested_cell_types['Presynaptic Cell Types']==pre_type, 'Distribution']
                        current_pre_type_post_comp_distribution_list = self.pd_string_value2list_of_strings(current_pre_type_post_comp_distribution)
                        # Get postsyn ad (apicalProx, apicalDist)
                        postsyn_ad = pc_groups_comp_list[pc_groups_list.index(current_post_type)]

                        if postsyn_ad == 'soma':
                            # Get soma indexes
                            values = np.array([float(i) for i in current_pre_type_post_comp_distribution_list[:3]])
                            comp_index = values > 0
                            letters = np.array(['b', 's', 'a'])
                            comp_name = ''.join(letters[comp_index])
                            weight_pretype2postcomp = values[comp_index]
                        elif postsyn_ad == 'apicalProx':
                            comp_index = 3
                            weight_pretype2postcomp = np.float(current_pre_type_post_comp_distribution_list[comp_index])
                        elif postsyn_ad == 'apicalDist':
                            comp_index = 4
                            weight_pretype2postcomp = np.float(current_pre_type_post_comp_distribution_list[comp_index])
                        else:
                            raise NotImplementedError('postsyn_ad not caught at _set_connection_parameters')
                        
                        # If current pre type does not have contact with current PC compartment
                        if not np.any(weight_pretype2postcomp):
                            continue

                        post_syn_idx_pc_string = ng_idx + '[C]' + comp_idx + comp_name
                    else:
                        post_syn_idx_pc_string = existing_neuron_groups_df.loc[existing_neuron_groups_df['neuron_subtype'] == post_layer + '_' + current_post_type, 'idx'].values[0]
 
                    syn_df.loc[current_connection_index,'receptor'] = receptor
                    syn_df.loc[current_connection_index,'pre_syn_idx'] = \
                        existing_neuron_groups_df.loc[existing_neuron_groups_df['neuron_subtype'] == pre_neuron_subtype, 'idx'].values[0]
                    
                    syn_df.loc[current_connection_index,'post_syn_idx'] = post_syn_idx_pc_string
                    probability_value = probability * weight_pretype2posttype * weight_pretype2postcomp

                    if probability_value.size > 1:
                        n_times = probability_value.size
                        probability_value = np.array2string(probability_value, separator='+')[1:-1]
                        syn_df.loc[current_connection_index,'n'] = '+'.join(str(N_SYNAPSES_PER_CONNECTION) * n_times)

                    syn_df.loc[current_connection_index,'p'] = probability_value
                    current_connection_index += 1
                    
        return syn_df, current_connection_index

    def _get_comp_idx(self, current_post_type, post_syn_layer, layerNames2layerIdx_dict):
        # To resolve comp_idx, we need to know where is postsyn PC soma compared to current post syn layer
        postsyn_pc_soma_layer_name = current_post_type[:current_post_type.find('_')]
        postsyn_pc_soma_layer_idx = layerNames2layerIdx_dict[postsyn_pc_soma_layer_name]
        current_post_syn_layer_idx = layerNames2layerIdx_dict[post_syn_layer]
        comp_idx = str(postsyn_pc_soma_layer_idx - current_post_syn_layer_idx)
        return comp_idx

    def _get_pc_groups(self, groups_df, post_layer_idx):
        # Get neuron_subtype list of PC groups whose apical dendrites extend to this post_layer_idx
        pc_groups_df = groups_df[groups_df['neuron_type'].str.startswith('PC')]
        def applyme(my_string):
            # From example '[7->1]' to array([6,5,4,3,2,1])
            return eval('np.arange(int(my_string[my_string.find("[")+1]), int(my_string[my_string.find("->")+2]) - 1, -1)')
        pc_groups_expand_df = pc_groups_df.copy()
        pc_groups_expand_df['layer_idx'] = pc_groups_df['layer_idx'].apply(applyme)
        pc_groups_list = []
        pc_groups_comp_list = []
        for foo, row in pc_groups_expand_df.iterrows():
            if post_layer_idx in row['layer_idx']:
                pc_groups_list.append(row['neuron_subtype'])
            if post_layer_idx == row['layer_idx'][-1]:
                pc_groups_comp_list.append('apicalDist')
            elif post_layer_idx in row['layer_idx'][1:-1]:
                pc_groups_comp_list.append('apicalProx')
            elif post_layer_idx == row['layer_idx'][0]:
                pc_groups_comp_list.append('soma')
        return pc_groups_list, pc_groups_comp_list

    def get_local_connection_df(self, ni_df, area_name, layer_name_mapping_df_full, 
                                layer_name_mapping_df_groups):
        '''
        Turn neuroinformatics connection df to useful connection_df

        Select area
        Turn layer names in csv into requested layer names

        Three categories of csv connections. 
        1) requested layer names found: Use directly csv layer name
        2) requested layer names not found: Down-map from requested layer to csv         
        3) do not use if flag use_all_csv_data = False

        Create map from D, M, S to connection probabilities. Allows use of proportions
        Separate proportions for the pre- and postsynaptic side, multiply for final connections

        '''

        use_all_csv_data = self.use_all_csv_data

        # Select area
        connection_df_ni_names = ni_df.groupby(['FromArea']).get_group(area_name)

        # Drop unnecessary area columns
        connection_df_ni_names = connection_df_ni_names.drop(columns=['FromArea', 'ToArea'])

        # Strip references
        connection_df_ni_names = connection_df_ni_names.drop(columns=['References'])
        
        # Duplicate csv layer names for proportion columns
        connection_df_ni_names['FL_proportions'] = connection_df_ni_names['FromLayer']
        connection_df_ni_names['TL_proportions'] = connection_df_ni_names['ToLayer']

        if use_all_csv_data:
            # layer_name_mapping_df_groups maps requested layer names, layer idx and csv layer names
            csv2idx_dict = dict(zip(layer_name_mapping_df_full.csv_layers, 
                                    layer_name_mapping_df_full.layer_idx))
            csv2proportion_dict = dict(zip(layer_name_mapping_df_full.csv_layers, 
                                    layer_name_mapping_df_full.sub_proportion))
        else:
            csv2idx_dict = dict(zip(layer_name_mapping_df_groups.csv_layers, 
                                    layer_name_mapping_df_groups.layer_idx))
            csv2proportion_dict = dict(zip(layer_name_mapping_df_groups.csv_layers, 
                                    layer_name_mapping_df_groups.sub_proportion))

        # Replace csv layer names with idx. The FL_proportions and TL_proportions indicate
        # relative layer thickness in comparison to Table 2 layers.
        connection_df_ni_names['FromLayer'] = connection_df_ni_names['FromLayer'].replace(csv2idx_dict)
        connection_df_ni_names['ToLayer'] = connection_df_ni_names['ToLayer'].replace(csv2idx_dict)
        connection_df_ni_names['FL_proportions'] = \
            connection_df_ni_names['FL_proportions'].replace(csv2proportion_dict)
        connection_df_ni_names['TL_proportions'] = \
            connection_df_ni_names['TL_proportions'].replace(csv2proportion_dict)

        # Now we just skip the rows not matching either pre- or postsynaptic layers
        layer_idxs = layer_name_mapping_df_groups.layer_idx.unique()
        connection_df_ni_names = connection_df_ni_names.loc[connection_df_ni_names['FromLayer'].isin(layer_idxs)]
        connection_df_ni_names = connection_df_ni_names.loc[connection_df_ni_names['ToLayer'].isin(layer_idxs)]


        '''
        ***Mapping from connection strength to connection probability***

        Create map from D, M, S to connection probabilities. Allows use of proportions
        In brian2 the synaptic p (probability of connection) parameter provides the 
        N connections / (NcellsG1 * NcellsG2), ie the number of connections from all possible pairs.
        The brian2 n-parameter multiplies each existing connection with integer number.
        
        The connection strength is the proportion of axonal sprouting/labelled cells in particular layer.
        We map connection strength value to numerical weight:
        D, dominant = 0.5 - 1, mean 0.75
        M, median = 0.1 - 0.5, mean 0.3
        S, sparse = eps - 0.1, mean 0.05        
        
        Local connections
        Intracellular tagging, shows single neuron structure. 
        We get:
        p = sw * (lw/0.5) * tw * apc
        p: probability of connections between any two cells (brian parameter). 
        sw: source group weight. N efferent synapses for this neuron group / mean N efferent synapses in cortical neurons
        lw: layer weight. The connection strength parameter from ni paper. The proportion of axonal sprouting in particular layer
        tw: target group weight. N presynaptic terminals from this neuron group / mean N presynaptic terminals from any neuron group
        tw 0 means avoidance of the postsynaptic group. tw 1 means Peter's rule
        apc: average probability of connection between two neurons, when efferent axon and afferent cell soma are in the same layer

        N pre and postsynaptic cells is already accounted for in NeuronGroups.
        sw, lw/0.5 and tw are all mean 1

        Because we do not know sw or tw for our neuron groups, this becomes
        p = (lw/0.5) * apc


       ***Weighing sublayers from ni cvs to probability***

        When we have multiple sublayers, we need to weigh the p value according estimated relative 
        sublayer thickness which we assume relates to the proportion of neurons in the sublayer from 
        all neurons in the layer. Eg for source sublayer1 to target sublayer1 connection , the p_partial value is
        p1 =  p_s1_t1 * sst1 * tst1
        p_s1_t1: probability of connection between source and target sublayers
        sst1: source sublayer thickness
        tst1: target sublayer thickness
        
        
        ***Scaling total p value according to included total sublayer thicknesses***
        
        The total p value for connecting two neuron groups becomes
        p_total = p1 + p2 + ... pN, where the partial p values indicate connection probabilities between each sublayer.
 
        Finally, include scaling by total proportions over all included sublayers. Full layer gives one and
        if u add sublayers A and B they include 0.5 each and BL and IB again 0.4 and 0.6 which sums to over 1.

        source scaling factor ssf = sst1 + sst2 + ... + sstN
        target scaling factor tsf = tst1 + tst2 + ... + tstN
        
        Final p value:

        p = p_total * 2 / (ssf + tsf)
        '''

        # Calculate partial p values for each sublayer to sublayer connection
        cw2p_dict = dict(zip(['D', 'M', 'S'],[0.75, 0.3, 0.05]))
        apc = 0.1
        sw = tw = 1
        connection_df_ni_names['Strength'] = connection_df_ni_names['Strength'].replace(cw2p_dict)
        connection_df_ni_names['p_partial'] = \
            sw * (connection_df_ni_names['Strength'] / 0.5) * tw * apc * \
            connection_df_ni_names['FL_proportions'] * connection_df_ni_names['TL_proportions']
            
        # Scale each unique set of partial connections to total FL_portion + TL_portion = 2
        # Change appropriate columns' data types to float. Mixed integers seemed to make these "objects"
        connection_df_ni_names = connection_df_ni_names.astype({'FL_proportions': 'float', 'TL_proportions': 'float', 'p_partial': 'float'})        
        
        # Group according to unique connections and sum all float columns
        connection_df_ni_names_unique = connection_df_ni_names.groupby(['FromLayer','ToLayer']).sum()
        connection_df_ni_names_unique = connection_df_ni_names_unique.reset_index()

        # I am not a perfectionist but I work with a mathematician and want to be exact, thus
        connection_df_ni_names_unique = connection_df_ni_names_unique.rename(columns={'p_partial':'p_total'})
        
        # Scale to final p value
        connection_df_ni_names_unique['p'] = (connection_df_ni_names_unique['p_total'] * 2) / \
            (connection_df_ni_names_unique['FL_proportions'] + connection_df_ni_names_unique['TL_proportions'])
        
        return connection_df_ni_names_unique


###############################################
########## END OF CXCONSTRUCTOR CODE ##########
###############################################

if __name__ == "__main__":
    '''
    Start of user input
    Copy and comment/uncomment examples/your own versions by need. If python gives exception, look first your own syntax below.
    '''

    area_name='V1' # Don't change this.
    requestedVFradius=.1 # Increasing this rapidly makes much more cells and increases the computational cost
    center_ecc=5 # Don't change this. This might be later replaced by 2D coordinates

    '''
    The proportion of inhibitory and excitatory neurons in distinct V1 layers will come from our review Table2.
    Below, you provide inhibitory and excitatory cell types and proportions when you have more than one type for each.
    Cell types are mandatory, and their names must match both Allen/HBP data table if these are used and physiology file cell type names
    Inhibitory and excitatory cell type proportions layerwise come either from  Allen/HBP data, 
    or you can define them by hand below. If left empty, 1/N cell types will be used for each layer.

    Later in an advanced version of the system, you can use the considerations below:
    Inhibitory neurons are divided into three groups in each layer, except in L1. In L1 we have limited data. The inh neurons will
    for sure be structurally simple. Whether we need a separate cell type for L1 is an open question. We could use the LAMP5 molecular marker as L1I 
    neuron, but then we need to assing its proportion in other layers with no idea of its structure. See Tasic_2018_Nature
    One limitation is that we are using Allen molecular types to get quantities of our limited set of structural types.
    inhibitory_types = ['SST', 'VIP', 'PVALB'] # This is a good guess, and take these proportions from Allen data

    For excitatory neurons we do not have HBP/Allen data to start with because only structural types currently implementd in CxSystem are 
    pyramidal cells (PC) with apical dendrites and spiny stellate (SS) cells which are point-like.
    Each PC group in layers L2 to L6 are divided into two. The first has apical dendrite extending to L1 and the second to L23 (L4-5, or L4C (L6)
    see Lund_1991_JCompNeurol, Callaway_1996_VisNeurosci, Nassi_2007_Neuron, Nhan_2012_JCompNeurol, Wiser_1996_Jneurosci, Briggs_2016_Neuron

    '''
    # requested_layers=['L1', 'L23', 'L4A','L4B', 'L4CA', 'L4CB','L5','L6'] # You should be able start from L4CA or B alone for testing
    requested_layers=['L1', 'L23', 'L4A','L4B', 'L4CA','L5','L6'] # You should be able start from L4CA or B alone for testing
    # requested_layers=['L23', 'L4CA', 'L5','L6'] # You should be able start from L4CA or B alone for testing
    # requested_layers=['L23', 'L4CA', 'L5','L6'] # You should be able start from L4CA or B alone for testing
 
    # Here are some examples
    inhibitory_types = ['MC', 'BC']
    # inhibitory_types = ['BC']
    # inhibitory_proportions={} # Leaving this empty will produce 1/N types proportions for each layer if cell_type_data_source = ''
    # inhibitory_proportions = {  
    # 'L23': [.5, .5], 
    # 'L4CA': [1, 0],
    # 'L5': [.5, .5], 
    # 'L6': [.5, .5]}
    
    inhibitory_proportions = {  
    'L1': [1, 0], 
    'L23': [.5, .5], 
    'L4A': [.5, .5], 
    'L4B': [.5, .5], 
    'L4CA': [1, 0],
    'L5': [.5, .5], 
    'L6': [.5, .5]}

    # Excitatory proportions are given by hand here. 
    # The list length for each layer must match the N types and should sum to approximately 1.
    # The layers must match the requested layers
    # excitatory_types = ['SS', 'PC1', 'PC2']
    # excitatory_types = ['SS','PC1'] # IT is one of th Allen excitatory types. SS = spiny stellate and this should exist in all physiological files
    excitatory_types = ['SS'] # IT is one of th Allen excitatory types. SS = spiny stellate and this should exist in all physiological files
    excitatory_proportions = {} # Leaving this empty will produce 1/N types proportions for each layer if cell_type_data_source = ''
    # excitatory_proportions = {  
    # 'L1': [1, 0], 
    # 'L23': [0, 1], 
    # 'L4A': [.5, .5], 
    # 'L4B': [.5, .5], 
    # 'L4C': [1, 0],
    # 'L5': [0, 1], 
    # 'L6': [.1, .9]}

    # Read in anat csv to start with. Check for config_files folder for valid inputs.
    # If replace_existing_cell_groups flag is False, your groups will be added to current groups. This allows building system stepwise
    replace_existing_cell_groups = True # 
    anatomy_config_file_name = 'pytest_anatomy_config.csv'
    physiology_config_file_name = 'pytest_physiology_config.csv' # anatomy and physiology filenames sometimes diverge

    # Own additional data files
    neuron_group_ephys_templates_filename = 'neuron_group_ephys_templates.xlsx'

    # Activate correct selection. These data provide proportions of distinct cell groups in each layer.
    # Markram data, rat S1
    # cell_type_data_source = 'HBP'
    
    # # Allen data, human V1
    # cell_type_data_source = 'Allen'

    # No data source. Use this eg for single excitatory and single inhibitory types. 
    cell_type_data_source = ''

    request_monitors = '[Sp]'
    n_background_inputs_for_excitatory_neurons = 630
    n_background_inhibition_for_excitatory_neurons = 290    
    n_background_inputs_for_inhibitory_neurons = 500
    n_background_inhibition_for_inhibitory_neurons = 180    

    # Connections. You can use only a subset of layers in ni csv data matching your requested layers or alternatively
    # you can use all csv data, including the sublayers and CO compartments.
    use_all_csv_data = True
    

    '''
    End of user input
    '''

    if cell_type_data_source == 'HBP':
        cell_type_data_folder_name='hbp_data'; cell_type_data_file_name='layer_download.json'
    elif cell_type_data_source == 'Allen':
        cell_type_data_folder_name='allen_data'; cell_type_data_file_name='sample_annotations.csv'
    elif cell_type_data_source == '':
        cell_type_data_folder_name=''; cell_type_data_file_name=''

    # Packing of variables for brevity
    requested_cell_types_and_proportions = {
        'inhibitory_types':inhibitory_types, 
        'inhibitory_proportions':inhibitory_proportions, 
        'excitatory_types':excitatory_types,
        'excitatory_proportions':excitatory_proportions}
    requested_background_input = {
        'n_background_inputs_for_excitatory_neurons':n_background_inputs_for_excitatory_neurons,
        'n_background_inhibition_for_excitatory_neurons':n_background_inhibition_for_excitatory_neurons,
        'n_background_inputs_for_inhibitory_neurons':n_background_inputs_for_inhibitory_neurons,
        'n_background_inhibition_for_inhibitory_neurons':n_background_inhibition_for_inhibitory_neurons}

    # Set Config class variables
    Config.anatomy_config_df = read_config_file(os.path.join(PATH_TO_CONFIG_FILES,anatomy_config_file_name))
    Config.physiology_config_df = read_config_file(os.path.join(PATH_TO_CONFIG_FILES,physiology_config_file_name))  
    Config.replace_existing_cell_groups = replace_existing_cell_groups  
    Config.table1_df = Config.get_neuroinformatics_data(TABLE1_DATA_FILENAME, set_index='stat')
    Config.table2_df = Config.get_neuroinformatics_data(TABLE2_DATA_FILENAME, set_index='layer')
    Config.use_all_csv_data = use_all_csv_data

    V1 = Area(area_name=area_name, requestedVFradius=requestedVFradius, center_ecc=center_ecc, requested_layers=requested_layers)

    # Add anatomy and physiology config files to start with
    group_object = Groups(V1, requested_cell_types_and_proportions, cell_type_data_source, cell_type_data_folder_name, 
                cell_type_data_file_name, request_monitors,requested_background_input)
    
    Conn_new = Connections(V1, group_object, use_all_csv_data)

    # Write anatomy out
    Config.write_config_files(Config.anatomy_config_df, anatomy_config_file_name, xlsx=True) # Original as excel file
    Config.write_config_files(Conn_new.anatomy_config_df_new_groups_new_synapses, anatomy_config_file_name[:-4] + '_cxc', csv=True, xlsx=True)
    
    # Write physiology out
    Config.write_config_files(Config.physiology_config_df, physiology_config_file_name, xlsx=True) # Original as excel file
    Config.write_config_files(group_object.physiology_df_with_subgroups, physiology_config_file_name[:-4] + '_cxc', csv=True, xlsx=True)
