import argparse
import functools
import math
import numpy as np
import os

import torch

import inkid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', help='Directory to hold output subvolumes')
    parser.add_argument('--input-set', metavar='path', nargs='*', help='input dataset(s)', default=[])
    parser.add_argument('--number', '-n', metavar='N', default=4, type=int,
                        help='number of subvolumes to keep')
    parser.add_argument('--ink', action='store_true', help='Restrict to points on ink areas')
    parser.add_argument('--no-ink', action='store_true', help='Restrict to points not on ink areas')
    parser.add_argument('--concat-subvolumes', action='store_true',
                        help='Create one set of slices containing all subvolumes')
    inkid.ops.add_subvolume_args(parser)

    # Data organization/augmentation
    parser.add_argument('--jitter-max', metavar='n', type=int)
    parser.add_argument('--augmentation', action='store_true', dest='augmentation')
    parser.add_argument('--no-augmentation', action='store_false', dest='augmentation')

    # Data region
    parser.add_argument('--leave-out-nth-source', metavar='num', default=None, type=int,
                        help='index of data source to remove from input dataset')

    args = parser.parse_args()

    # Make sure some sort of input is provided, else there is nothing to do
    if len(args.input_set) == 0:
        raise ValueError('Some --input-set must be specified.')

    input_ds = inkid.data.Dataset(args.input_set)

    os.makedirs(args.output, exist_ok=True)

    # If k-fold job, remove nth region from training and put in prediction/validation sets
    if args.leave_out_nth_source is not None:
        nth_region_path: str = input_ds.regions()[args.leave_out_nth_source].path
        input_ds.remove_source(nth_region_path)

    subvolume_args = dict(
        shape_voxels=args.subvolume_shape_voxels,
        shape_microns=args.subvolume_shape_microns,
        out_of_bounds='all_zeros',
        move_along_normal=args.move_along_normal,
        method=args.subvolume_method,
        normalize=args.normalize_subvolumes,
        augment_subvolume=args.augmentation,
        jitter_max=args.jitter_max,
    )

    input_ds.set_for_all_sources('feature_type', 'subvolume_3dcnn')
    input_ds.set_for_all_sources('feature_args', subvolume_args)

    seed = 42
    np.random.seed(seed)
    torch.manual_seed(seed)

    input_dl = None
    if len(input_ds) > 0:
        input_dl = torch.utils.data.DataLoader(input_ds, shuffle=True)

    square_side_length = math.ceil(math.sqrt(args.number))
    pad = 20
    padded_shape_voxels = [i + pad * 2 for i in args.subvolume_shape_voxels]
    concatenated_shape = [padded_shape_voxels[0],
                          padded_shape_voxels[1] * square_side_length,
                          padded_shape_voxels[2] * square_side_length]
    concatenated_subvolumes = np.zeros(concatenated_shape)

    counter = 0
    for _, subvolume in input_dl:
        if counter >= args.number:
            break
        subvolume = subvolume.numpy()[0][0]
        if args.concat_subvolumes:
            concat_x = (counter // square_side_length) * padded_shape_voxels[2]
            concat_y = (counter % square_side_length) * padded_shape_voxels[1]
            subvolume = np.pad(subvolume, pad)
            concatenated_subvolumes[0:padded_shape_voxels[0],
                                    concat_y:concat_y + padded_shape_voxels[1],
                                    concat_x:concat_x + padded_shape_voxels[2]] = subvolume
        else:
            inkid.ops.save_volume_to_image_stack(subvolume, os.path.join(args.output, str(counter)))
        counter += 1

    if args.concat_subvolumes:
        inkid.ops.save_volume_to_image_stack(concatenated_subvolumes, args.output)


if __name__ == '__main__':
    main()
