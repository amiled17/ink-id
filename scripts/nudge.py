'''
nudge.py
create a nudged version of the volume, increasing values at ink points
'''

__author__ = "Jack Bandy"
__email__ = "jgba225@g.uky.edu"

import numpy as np
import tifffile as tiff
import os
import matplotlib.pyplot as plt
from scipy.signal import argrelmax
from scipy.stats import norm

truth_mask = tiff.imread('/home/jack/devel/volcart/predictions/3dcnn/Quadrant Experiment/new.tif')
vol = np.load('/home/jack/devel/volcart/small-fragment-data/volume.npy')
output_dir = '/home/jack/devel/volcart/small-fragment-data/nudge-'
output = np.zeros(vol.shape, dtype=np.uint16)
before = np.zeros(truth_mask.shape, dtype=np.uint16)
after = np.zeros(truth_mask.shape, dtype=np.uint16)
cap = np.iinfo(vol.dtype).max
vol_min = np.min(np.where(vol > 0, vol, cap))
vol_max = np.max(vol)
vol_range = (vol_max - vol_min)
truth_value = np.max(truth_mask)


# parameters
loc = 0
scale = 4 # how much to stretch the curve, lower = taller curve, higher = shorter/wider
increase_percentages = np.array([ 8,])
increase_decimals = increase_percentages / 100
neigh = 4
thresh = 20500
reach_in = 10
reach_back = 4
span = max(reach_in, reach_back)
show_demo = False
shown_demo = True # set to False to display a sample graph


# create the distribution array
distribute = [0.0] * (span+1)
for i in range(len(distribute)):
    # the initial distribution
    distribute[i] = norm.pdf(i, loc, scale)



for increase in increase_decimals:
    # re-initialize everything
    vol = np.load('/home/jack/devel/volcart/small-fragment-data/volume.npy')
    outvol = np.copy(vol)
    before = np.zeros(truth_mask.shape, dtype=np.uint16)
    after = np.zeros(truth_mask.shape, dtype=np.uint16)

    target_increase = increase * vol_range
    increase_parameter = (target_increase / distribute[0])
    # for example if the target increase is 1.0% (.010),
    # target_increase = 65535*.01 = 655.35
    # increase_parameter = 655.35 / .19 = 3285


    # main loop
    for i in range(neigh, vol.shape[0] - neigh):
        for j in range(neigh, vol.shape[1] - neigh):
            vector = vol[i,j]
            truth_weight = np.mean(truth_mask[i-neigh:i+neigh, j-neigh:j+neigh]) / truth_value

            # set everything below threshold to 0
            thresh_vect = np.where(vector > thresh, vector, 0)
            try:
                peak = argrelmax(thresh_vect)[0][0]
                before[i,j] = vector[peak]

                # nudge each point around the peak
                for x in range(peak - reach_back, peak):
                    diff = abs(peak - x)
                    proportion = float(diff) / float(reach_back)
                    aligned_index = int(proportion * span)
                    dist_weight = distribute[aligned_index]
                    vector[x] += int(increase_parameter * truth_weight * dist_weight)
                for x in range(peak, peak + reach_in):
                    diff = abs(peak - x)
                    dist_weight = distribute[diff]
                    vector[x] += int(increase_parameter * truth_weight * dist_weight)


                outvol[i,j] = vector
                after[i,j] = vector[peak]
                if show_demo and not shown_demo and truth_weight > .9:
                    xs = np.arange(vol.shape[2])
                    plt.plot(thresh_vect, color='b')
                    plt.plot(vector, color='g')
                    plt.show()
                    shown_demo = True

            except IndexError:
                # for when no argrelmax exists
                pass

        #progress update
        if (i % int((vol.shape[0] - neigh) / 10) == 0):
            print("finished rows 0 to {} out of {} for increase {}".format(
                i, vol.shape[0] - neigh, increase))

    # output
    current_output_dir = (output_dir + "{:.2f}%".format(increase * 100) + "/")
    try:
        os.mkdir(current_output_dir)
    except Exception:
        pass

    # 1: save the volume and surface images
    np.save(current_output_dir+"volume-nudged-{:.2f}%".format(
        increase*100), outvol)
    tiff.imsave(current_output_dir+"values-before-nudge-{:.2f}%.tif".format(
        increase*100), before)
    tiff.imsave(current_output_dir+"values-after-nudged-{:.2f}%.tif".format(
        increase*100), after)

    # 2: save the slices
    slice_dir = current_output_dir + "/slices/"
    try:
        os.mkdir(slice_dir)
    except Exception:
        pass

    for sl in range(outvol.shape[0]):
        zeros = len(str(sl))
        tiff.imsave(slice_dir+"slice" + "0000"[:4-zeros] + str(sl), outvol[sl])

    # 3: save the planet
    #TODO
