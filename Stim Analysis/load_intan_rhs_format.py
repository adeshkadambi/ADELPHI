#! /bin/env python
#
# Michael Gibson 17 July 2015
# Modified Zeke Arneodo Dec 2017
# Modified Adrian Foy Sep 2018

import sys, struct, math, os, time
import numpy as np

from intanutil.read_header import read_header
from intanutil.get_bytes_per_data_block import get_bytes_per_data_block
from intanutil.read_one_data_block import read_one_data_block
from intanutil.notch_filter import notch_filter
from intanutil.data_to_result import data_to_result



def read_data(filename):
    """Reads Intan Technologies RHD2000 data file generated by evaluation board GUI.

    Data are returned in a dictionary, for future extensibility.
    """
    tic = time.time()
    with open(filename, 'rb') as fid:
        filesize = os.path.getsize(filename)

        header = read_header(fid)
        # return header

        print('Found {} amplifier channel{}.'.format(header['num_amplifier_channels'],
                                                     plural(header['num_amplifier_channels'])))
        print('Found {} board ADC channel{}.'.format(header['num_board_adc_channels'],
                                                     plural(header['num_board_adc_channels'])))
        print('Found {} board DAC channel{}.'.format(header['num_board_dac_channels'],
                                                     plural(header['num_board_dac_channels'])))
        print('Found {} board digital input channel{}.'.format(header['num_board_dig_in_channels'],
                                                               plural(header['num_board_dig_in_channels'])))
        print('Found {} board digital output channel{}.'.format(header['num_board_dig_out_channels'],
                                                                plural(header['num_board_dig_out_channels'])))
        print('')

        # Determine how many samples the data file contains.
        bytes_per_block = get_bytes_per_data_block(header)
        print('{} bytes per data block'.format(bytes_per_block))
        # How many data blocks remain in this file?
        data_present = False
        bytes_remaining = filesize - fid.tell()
        if bytes_remaining > 0:
            data_present = True

        if bytes_remaining % bytes_per_block != 0:
            raise Exception('Something is wrong with file size : should have a whole number of data blocks')

        num_data_blocks = int(bytes_remaining / bytes_per_block)

        num_amplifier_samples = 128 * num_data_blocks
        num_board_adc_samples = 128 * num_data_blocks
        num_board_dac_samples = 128 * num_data_blocks
        num_board_dig_in_samples = 128 * num_data_blocks
        num_board_dig_out_samples = 128 * num_data_blocks

        record_time = num_amplifier_samples / header['sample_rate']

        if data_present:
            print('File contains {:0.3f} seconds of data.  Amplifiers were sampled at {:0.2f} kS/s.'.format(record_time,
                                                                                                            header[
                                                                                                                'sample_rate'] / 1000))
        else:
            print('Header file contains no data.  Amplifiers were sampled at {:0.2f} kS/s.'.format(
                header['sample_rate'] / 1000))

        if data_present:
            # Pre-allocate memory for data.
            print('')
            print('Allocating memory for data...')

            data = {}
            data['t'] = np.zeros(num_amplifier_samples, dtype=np.int)

            data['amplifier_data'] = np.zeros([header['num_amplifier_channels'], num_amplifier_samples], dtype=np.uint)

            if header['dc_amplifier_data_saved']:
                data['dc_amplifier_data'] = np.zeros([header['num_amplifier_channels'], num_amplifier_samples], dtype=np.uint) * header['dc_amplifier_data_saved']

            data['stim_data_raw'] = np.zeros([header['num_amplifier_channels'], num_amplifier_samples], dtype=np.int)
            data['stim_data'] = np.zeros([header['num_amplifier_channels'], num_amplifier_samples], dtype=np.int)

            data['board_adc_data'] = np.zeros([header['num_board_adc_channels'], num_board_adc_samples], dtype=np.uint)
            data['board_dac_data'] = np.zeros([header['num_board_dac_channels'], num_board_dac_samples], dtype=np.uint)

            # by default, this script interprets digital events (digital inputs, outputs, amp settle, compliance limit, and charge recovery) as booleans
            # if unsigned int values are preferred (0 for False, 1 for True), replace the 'dtype=np.bool' argument with 'dtype=np.uint' as shown
            # the commented line below illustrates this for digital input data; the same can be done for the other digital data types
            
            #data['board_dig_in_data'] = np.zeros([header['num_board_dig_in_channels'], num_board_dig_in_samples], dtype=np.uint)
            data['board_dig_in_data'] = np.zeros([header['num_board_dig_in_channels'], num_board_dig_in_samples], dtype=np.bool)
            data['board_dig_in_raw'] = np.zeros(num_board_dig_in_samples, dtype=np.uint)
            data['board_dig_out_data'] = np.zeros([header['num_board_dig_out_channels'], num_board_dig_out_samples], dtype=np.bool)
            data['board_dig_out_raw'] = np.zeros(num_board_dig_out_samples, dtype=np.uint)

            # Read sampled data from file.
            print('Reading data from file...')

            # Initialize indices used in looping
            indices = {}
            indices['amplifier'] = 0
            indices['aux_input'] = 0
            indices['board_adc'] = 0
            indices['board_dac'] = 0
            indices['board_dig_in'] = 0
            indices['board_dig_out'] = 0

            print_increment = 10
            percent_done = print_increment
            for i in (range(num_data_blocks)):
                read_one_data_block(data, header, indices, fid)
                # Increment all indices indices in 128
                indices = {k: v + 128 for k, v in indices.items()}

                fraction_done = 100 * (1.0 * i / num_data_blocks)
                if fraction_done >= percent_done:
                    print('{}% done...'.format(percent_done))
                    percent_done = percent_done + print_increment

            # Make sure we have read exactly the right amount of data.
            bytes_remaining = filesize - fid.tell()
            if bytes_remaining != 0: raise Exception('Error: End of file not reached.')

    # end of reading data file.
    # return data

    if (data_present):
        print('Parsing data...')

        # Extract digital input channels to separate variables.
        for i in range(header['num_board_dig_in_channels']):
            data['board_dig_in_data'][i, :] = np.not_equal(np.bitwise_and(data['board_dig_in_raw'],
                                                                          (1 << header['board_dig_in_channels'][i][
                                                                              'native_order'])), 0)

        # Extract digital output channels to separate variables.
        for i in range(header['num_board_dig_out_channels']):
            data['board_dig_out_data'][i, :] = np.not_equal(np.bitwise_and(data['board_dig_out_raw'],
                                                                           (1 << header['board_dig_out_channels'][i][
                                                                               'native_order'])), 0)

        # Extract stimulation data
        data['compliance_limit_data'] = np.bitwise_and(data['stim_data_raw'], 32768) >= 1 # get 2^15 bit, interpret as True or False
        data['charge_recovery_data'] = np.bitwise_and(data['stim_data_raw'], 16384) >= 1 # get 2^14 bit, interpret as True or False
        data['amp_settle_data'] = np.bitwise_and(data['stim_data_raw'], 8192) >= 1 # get 2^13 bit, interpret as True or False
        data['stim_polarity'] = 1 - (2*(np.bitwise_and(data['stim_data_raw'], 256) >> 8)) # get 2^8 bit, interpret as +1 for 0_bit or -1 for 1_bit
        
        curr_amp = np.bitwise_and(data['stim_data_raw'], 255) # get least-significant 8 bits corresponding to the current amplitude
        data['stim_data'] = curr_amp * data['stim_polarity'] # multiply current amplitude by the correct sign

        # # Scale voltage levels appropriately.
        data['amplifier_data'] = np.multiply(0.195,
                                             (
                                             data['amplifier_data'].astype(np.int32) - 32768))  # units = microvolts
        data['stim_data'] = np.multiply(header['stim_step_size'], data['stim_data'] / 1.0e-6)

        if header['dc_amplifier_data_saved']:
            data['dc_amplifier_data'] = np.multiply(-0.01923,
                                                    (data['dc_amplifier_data'].astype(
                                                        np.int32) - 512))  # units = volts

        data['board_adc_data'] = np.multiply(0.0003125, (data['board_adc_data'].astype(np.int32) - 32768)) # units = volts
        data['board_dac_data'] = np.multiply(0.0003125, (data['board_dac_data'].astype(np.int32) - 32768)) # units = volts

        # Check for gaps in timestamps.
        num_gaps = np.sum(np.not_equal(data['t'][1:] - data['t'][:-1], 1))
        if num_gaps == 0:
            print('No missing timestamps in data.')
        else:
            print('Warning: {0} gaps in timestamp data found.  Time scale will not be uniform!'.format(num_gaps))

        # Scale time steps (units = seconds).
        data['t'] = data['t'] / header['sample_rate']

        # If the software notch filter was selected during the recording, apply the
        # same notch filter to amplifier data here.
        if header['notch_filter_frequency'] > 0:
            print_increment = 10
            percent_done = print_increment
            for i in range(header['num_amplifier_channels']):
                data['amplifier_data'][i, :] = notch_filter(data['amplifier_data'][i, :], header['sample_rate'],
                                                            header['notch_filter_frequency'], 10)
                if fraction_done >= percent_done:
                    print('{}% done...'.format(percent_done))
                    percent_done = percent_done + print_increment
    else:
        data = []

    # Move variables to result struct.
    result = data_to_result(header, data, data_present)

    print('Done!  Elapsed time: {0:0.1f} seconds'.format(time.time() - tic))
    
    return result


def plural(n):
    """Utility function to optionally pluralize words based on the value of n.
    """

    if n == 1:
        return ''
    else:
        return 's'


if __name__ == '__main__':
    a = read_data(sys.argv[1])
    #print(a)
