""" Module for Keck/NIRSPEC specific codes
"""
from __future__ import absolute_import, division, print_function

try:
    basestring
except NameError:  # For Python 3
    basestring = str

import glob

import numpy as np
from astropy.io import fits

from pypit import msgs
from pypit import ardebug as debugger
from. import spectroclass

class KeckNIRSPECSpectrograph(spectroclass.Spectrograph):
    """
    Child to handle Keck/LRIS specific code
    """
    def __init__(self):
        # Get it started
        super(KeckNIRSPECSpectrograph, self).__init__()
        self.spectrograph = 'keck_nirspec'
        self.detector = [
                # Detector 1
                DetectorPar(dataext=0, dispaxis=0, xgap=0., ygap=0., ysize=1., platescale=0.193,
                            darkcurr=0.8, saturation=65535., nonlinear=0.76, numamplifiers=1,
                            gain=5.8, ronoise=23)
            ]

    def bpm(self, shape=None, **null_kwargs):
        """ Generate a BPM

        Parameters
        ----------
        shape : tuple, REQUIRED

        Returns
        -------
        badpix : ndarray

        """
        # Edges of the detector are junk
        msgs.info("Custom bad pixel mask for NIRSPEC")
        self.bpm = np.zeros((self.shape[0], self.shape[1]))
        self.bpm[:, :20] = 1.
        self.bpm[:, 1000:] = 1.

    def setup_arcparam(self, arcparam, fitstbl=None, arc_idx=None,
                       msarc_shape=None, **null_kwargs):
        """

        Args:
            arcparam:
            disperser:
            fitstbl:
            arc_idx:
            msarc_shape:
            **null_kwargs:

        Returns:

        """
        arcparam['lamps'] = ['OH_R24000']
        if fitstbl['filter1'][arc_idx] == 'NIRSPEC-1':
            arcparam['n_first'] = 2  # Too much curvature for 1st order
            arcparam['disp'] = 2.1093  # Ang per pixel for Low-Res, NIRSPEC-1 filter
            arcparam['b1'] = 1. / arcparam['disp'] / msarc_shape[0]
            arcparam['wvmnx'][0] = 9400.  # Min wavelength
            arcparam['wvmnx'][1] = 11300.  # Max wavelength
            arcparam['wv_cen'] = 10000.  # Central wavelength

