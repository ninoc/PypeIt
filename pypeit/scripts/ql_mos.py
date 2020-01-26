#!/usr/bin/env python
#
# See top-level LICENSE file for Copyright information
#
# -*- coding: utf-8 -*-
"""
This script runs PypeIt on a set of MultiSlit images
"""
import argparse

from pypeit import msgs

import warnings

def parser(options=None):

    parser = argparse.ArgumentParser(description='Script to run PypeIt in QuickLook on a set of MOS files')
    parser.add_argument('spectrograph', type=str, help='Name of spectograph, e.g. shane_kast_blue')
    parser.add_argument('full_rawpath', type=str, help='Full path to the raw files')
    parser.add_argument('arc', type=str, help='Arc frame filename')
    parser.add_argument('flat', type=str, help='Flat frame filename')
    parser.add_argument('science', type=str, help='Science frame filename')
    parser.add_argument('-b', '--box_radius', type=float, help='Set the radius for the boxcar extraction (arcsec)')
    parser.add_argument('-d', '--det', type=int, default=1, help='Detector number')
    parser.add_argument("--ignore_headers", default=False, action="store_true",
                        help="Ignore bad headers?")
    parser.add_argument("--user_pixflat", type=str, help="Use a user-supplied pixel flat (e.g. keck_lris_blue)")

    if options is None:
        pargs = parser.parse_args()
    else:
        pargs = parser.parse_args(options)
    return pargs


def main(pargs):

    import os
    import numpy as np

    from IPython import embed

    from pypeit import pypeit
    from pypeit import pypeitsetup
    from pypeit.core import framematch

    spec = pargs.spectrograph

    # Config the run
    cfg_lines = ['[rdx]']
    cfg_lines += ['    spectrograph = {0}'.format(spec)]
    cfg_lines += ['    redux_path = {0}_A'.format(os.path.join(os.getcwd(),spec))]
    cfg_lines += ['    detnum = {0}'.format(pargs.det)]
    if pargs.ignore_headers:
        cfg_lines += ['    ignore_bad_headers = True']
    cfg_lines += ['[scienceframe]']
    cfg_lines += ['    [[process]]']
    cfg_lines += ['          cr_reject = False']
    if pargs.user_pixflat is not None:
        cfg_lines += ['[calibrations]']
        cfg_lines += ['    [[flatfield]]']
        cfg_lines += ['        frame = {0}'.format(pargs.user_pixflat)]
    cfg_lines += ['[scienceimage]']
    cfg_lines += ['    [[extraction]]']
    cfg_lines += ['         skip_optimal = True']
    if pargs.box_radius is not None: # Boxcar radius
        cfg_lines += ['    boxcar_radius = {0}'.format(pargs.box_radius)]
    cfg_lines += ['    [[findobj]]']
    cfg_lines += ['         skip_second_find = True']

    # Data files
    data_files = [os.path.join(pargs.full_rawpath, pargs.arc),
                  os.path.join(pargs.full_rawpath, pargs.flat),
                  os.path.join(pargs.full_rawpath,pargs.science)]

    # Setup
    ps = pypeitsetup.PypeItSetup(data_files, path='./', spectrograph_name=spec,
                                 cfg_lines=cfg_lines)
    ps.build_fitstbl()
    # TODO -- Get the type_bits from  'science'
    bm = framematch.FrameTypeBitMask()
    file_bits = np.zeros(3, dtype=bm.minimum_dtype())
    file_bits[0] = bm.turn_on(file_bits[0], ['arc', 'tilt'])
    file_bits[1] = bm.turn_on(file_bits[1],
                              ['pixelflat', 'trace'] if pargs.user_pixflat is None else 'trace')
    file_bits[2] = bm.turn_on(file_bits[2], 'science')

    # PypeItSetup sorts according to MJD
    #   Deal with this
    asrt = []
    for ifile in data_files:
        bfile = os.path.basename(ifile)
        idx = ps.fitstbl['filename'].data.tolist().index(bfile)
        asrt.append(idx)
    asrt = np.array(asrt)

    # Set bits
    ps.fitstbl.set_frame_types(file_bits[asrt])
    ps.fitstbl.set_combination_groups()
    # Extras
    ps.fitstbl['setup'] = 'A'

    # Write
    ofiles = ps.fitstbl.write_pypeit('', configs=['A'], write_bkg_pairs=True, cfg_lines=cfg_lines)
    if len(ofiles) > 1:
        msgs.error("Bad things happened..")

    # Instantiate the main pipeline reduction object
    pypeIt = pypeit.PypeIt(ofiles[0], verbosity=2,
                           reuse_masters=True, overwrite=True,
                           logname='mos.log', show=False)
    # Run
    pypeIt.reduce_all()
    msgs.info('Data reduction complete')
    # QA HTML
    msgs.info('Generating QA HTML')
    pypeIt.build_qa()

    return 0
