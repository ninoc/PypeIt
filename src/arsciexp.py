import sys
import pdb
import numpy as np
# Import PYPIT routines
from astropy.time import Time
import datetime
from matplotlib.backends.backend_pdf import PdfPages
import artrace
import arsort
import arload
import arcomb
import armsgs
import arproc

# Logging
msgs = armsgs.get_logger()

class ScienceExposure:

    def __init__(self, snum, argflag, spect, fitsdict):
        """
        A Science Exposure class that carries all information for a given science exposure
        """

        #############################
        # Set some universal parameters
        self._argflag = argflag   # Arguments and Flags
        self._spect = spect       # Spectrograph information
        self._transpose = False   # Determine if the frames need to be transposed

        # Set indices used for frame combination
        self._idx_sci = spect['science']['index'][snum]
        self._idx_arcs = spect['arc']['index'][snum]
        self._idx_trace = spect['trace']['index'][snum]
        if self._argflag['reduce']['usebias'] == 'bias': self._idx_bias = spect['bias']['index'][snum]
        elif self._argflag['reduce']['usebias'] == 'dark':  self._idx_bias = spect['dark']['index'][snum]
        else: self._idx_bias = []
        if self._argflag['reduce']['usetrace'] == 'trace': self._idx_trace = self._spect['trace']['index'][snum]
        elif self._argflag['reduce']['usetrace'] == 'blzflat': self._idx_trace = self._spect['blzflat']['index'][snum]
        else: self._idx_trace = []
        if self._argflag['reduce']['useflat'] == 'pixflat': self._idx_flat = self._spect['pixflat']['index'][snum]
        elif self._argflag['reduce']['useflat'] == 'blzflat': self._idx_flat = self._spect['blzflat']['index'][snum]
        else: self._idx_flat = []

        # Set the base name and extract other names that will be used for output files
        self._basename = ""
        self.SetBaseName(fitsdict)
        self._target_name = fitsdict['target'][self._idx_sci[0]].replace(" ", "")

        # Initialize the QA for this science exposure
        qafn = "{0:s}/QA_{1:s}.pdf".format(self._argflag['run']['plotsdir'], self._basename)
        self._qa = PdfPages(qafn)

        # Initialize Variables
        ndet = spect['mosaic']['ndet']
        self._nonlinear = [self._spect['det'][det-1]['saturation']*self._spect['det'][det-1]['nonlinear']
                           for det in xrange(ndet)]
        self._dispaxis = None  # Which direction is the predominant spectral (dispersion) axis
        self._nspec    = [None for all in xrange(ndet)]   # Number of spectral pixels
        self._nspat    = [None for all in xrange(ndet)]   # Number of spatial pixels
        self._ampsec   = [None for all in xrange(ndet)]   # Locations of the amplifiers on each detector
        self._pixlocn  = [None for all in xrange(ndet)]   # Physical locations of each pixel on the detector
        self._lordloc  = [None for all in xrange(ndet)]   # Array of slit traces (left side) in physical pixel coordinates
        self._rordloc  = [None for all in xrange(ndet)]   # Array of slit traces (left side) in physical pixel coordinates
        self._pixcen   = [None for all in xrange(ndet)]   # Central slit traces in apparent pixel coordinates
        self._pixwid   = [None for all in xrange(ndet)]   # Width of slit (at each row) in apparent pixel coordinates
        self._lordpix  = [None for all in xrange(ndet)]   # Array of slit traces (left side) in apparent pixel coordinates
        self._rordpix  = [None for all in xrange(ndet)]   # Array of slit traces (right side) in apparent pixel coordinates
        self._tilts    = [None for all in xrange(ndet)]   # Array of spectral tilts at each position on the detector
        self._satmask  = [None for all in xrange(ndet)]   # Array of Arc saturation streaks
        self._arcparam = [None for all in xrange(ndet)]   #
        self._wvcalib  = [None for all in xrange(ndet)]   #
        self._resnarr  = [None for all in xrange(ndet)]   # Resolution array
        # Initialize the Master Calibration frames
        self._bpix = [None for all in xrange(ndet)]          # Bad Pixel Mask
        self._msarc = [None for all in xrange(ndet)]         # Master Arc
        self._msbias = [None for all in xrange(ndet)]        # Master Bias
        self._mstrace = [None for all in xrange(ndet)]       # Master Trace
        self._mspixflat = [None for all in xrange(ndet)]     # Master pixel flat
        self._mspixflatnrm = [None for all in xrange(ndet)]  # Normalized Master pixel flat
        self._msblaze = [None for all in xrange(ndet)]       # Blaze function
        # Initialize the Master Calibration frame names
        self._msarc_name = [None for all in xrange(ndet)]      # Master Arc Name
        self._msbias_name = [None for all in xrange(ndet)]     # Master Bias Name
        self._mstrace_name = [None for all in xrange(ndet)]    # Master Trace Name
        self._mspixflat_name = [None for all in xrange(ndet)]  # Master Pixel Flat Name
        # Initialize the science, variance, and background frames
        self._sciframe = [None for all in xrange(ndet)]
        self._varframe = [None for all in xrange(ndet)]
        self._bgframe  = [None for all in xrange(ndet)]
        # Initialize some extraction products
        self._ext_boxcar = [None for all in xrange(ndet)]
        self._ext_optimal = [None for all in xrange(ndet)]
        return

    def SetBaseName(self, fitsdict):
        """
        Set the base name that is used for all outputs

        Parameters
        ----------
        fitsdict : dict
          Contains relevant information from fits header files
        """
        scidx = self._idx_sci[0]
        if "T" in fitsdict['date'][scidx]:
            tbname = fitsdict['date'][scidx]
        else:
            # Not ideal, but convert MJD into a date+time
            timval = Time(fitsdict['time'][scidx]/24.0, scale='tt', format='mjd')
            tbname = timval.isot
        tval = datetime.datetime.strptime(tbname, '%Y-%m-%dT%H:%M:%S.%f')
        self._basename = datetime.datetime.strftime(tval, '%Y%b%dT') + tbname.split("T")[1]
        return

    ###################################
    # Reduction procedures
    ###################################

    def BadPixelMask(self, det):
        """
        Generate Bad Pixel Mask for a given detector

        Parameters
        ----------
        det : int
          Index of the detector

        Returns
        -------
        boolean : bool
          Should other ScienceExposure classes be updated?
        """
        if self._argflag['reduce']['badpix']:
            msgs.info("Preparing a bad pixel mask")
            # Get all of the bias frames for this science frame
            if len(self._idx_bias) == 0:
                msgs.warn("No bias frames available to determine bad pixel mask")
                msgs.info("Not preparing a bad pixel mask")
                #self._bpix = None
                return False
            # Load the Bias frames
            bpix = arproc.badpix(self, det, self.GetMasterFrame('bias', det))
        else:
            msgs.info("Not preparing a bad pixel mask")
            return False
        self.SetFrame(self._bpix, bpix, det)
        del bpix
        return True

    def GetDispersionDirection(self, fitsdict, det):
        """
        Set the dispersion axis. If necessary, transpose frames and adjust information as needed

        Parameters
        ----------
        fitsdict : dict
          Contains relevant information from fits header files
        det : int
          Index of the detector

        Returns
        -------
        fitsdict : dict
          Updates to the input fitsdict
        """
        if self._argflag['trace']['disp']['direction'] is None:
            self._dispaxis = artrace.dispdir(self._msarc[det-1], dispwin=self._argflag['trace']['disp']['window'], mode=0)
        elif self._argflag['trace']['disp']['direction'] in [0, 1]:
            self._dispaxis = int(self._argflag['trace']['disp']['direction'])
        else:
            msgs.error("The argument for the dispersion direction (trace+disp+direction)"+msgs.newline() +
                       "must be either:"+msgs.newline()+"  0 if the dispersion axis is predominantly along a row" +
                       msgs.newline() + "  1 if the dispersion axis is predominantly along a column")
        # Perform a check to warn the user if the longest axis is not equal to the dispersion direction
        if self._msarc[det-1].shape[0] > self._msarc[det-1].shape[1]:
            if self._dispaxis == 1: msgs.warn("The dispersion axis is set to the shorter axis, is this correct?")
        else:
            if self._dispaxis == 0: msgs.warn("The dispersion axis is set to the shorter axis, is this correct?")

        ###############
        # Change dispersion direction and files if necessary
        # The code is programmed assuming dispaxis=0
        if self._dispaxis == 1:
            msgs.info("Transposing frames and keywords")
            # Flip the transpose switch
            self._transpose = True
            # Transpose the master bias frame
            #pdb.set_trace()
            if self._msbias[det-1] is not None:
                if type(self._msbias[det-1]) is str: pass  # Overscan sub - change the oscansec parameters below
                elif type(self._msbias[det-1]) is np.ndarray: self.SetMasterFrame(self._msbias[det-1].T, 'bias', det)
            # Transpose the master arc, and save it
            self.SetMasterFrame(self._msarc[det-1].T, 'arc', det)
            # Transpose the bad pixel mask
            if self._bpix[det-1] is not None:
                self.SetFrame(self._bpix, self._bpix[det-1].T, det)
            # Transpose the amplifier sections frame
            self.SetFrame(self._ampsec, self._ampsec[det-1].T, det)
            # Update the keywords of the fits files
            for i in xrange(len(fitsdict['naxis0'])):
                temp = fitsdict['naxis0'][i]
                fitsdict['naxis0'][i] = fitsdict['naxis1'][i]
                fitsdict['naxis1'][i] = temp
            # Change the user-specified (x,y) pixel sizes
            tmp = self._spect['det'][det-1]['xgap']
            self._spect['det'][det-1]['xgap'] = self._spect['det'][det-1]['ygap']
            self._spect['det'][det-1]['ygap'] = tmp
            self._spect['det'][det-1]['ysize'] = 1.0/self._spect['det'][det-1]['ysize']
            # Update the amplifier/data/overscan sections
            for i in xrange(self._spect['det'][det-1]['numamplifiers']):
                # Flip the order of the sections
                self._spect['det'][det-1]['ampsec{0:02d}'.format(i+1)] = self._spect['det'][det-1]['ampsec{0:02d}'.format(i+1)][::-1]
                self._spect['det'][det-1]['datasec{0:02d}'.format(i+1)] = self._spect['det'][det-1]['datasec{0:02d}'.format(i+1)][::-1]
                self._spect['det'][det-1]['oscansec{0:02d}'.format(i+1)] = self._spect['det'][det-1]['oscansec{0:02d}'.format(i+1)][::-1]
            # Change the user-specified (x,y) pixel sizes
            msgs.work("Transpose gain and readnoise frames")
            # Set the new dispersion axis
            self._dispaxis = 0
        # Set the number of spectral and spatial pixels
        self._nspec[det-1], self._nspat[det-1] = self._msarc[det-1].shape
        return fitsdict

    def GetPixelLocations(self, det):
        """
        Generate or load the physical location of each pixel

        Parameters
        ----------
        det : int
          Index of the detector
        """
        if self._argflag['reduce']['locations'] is None:
            self.SetFrame(self._pixlocn, artrace.gen_pixloc(self, self._mstrace[det-1], det, gen=True), det)
        elif self._argflag['reduce']['locations'] in ["mstrace"]:
            self.SetFrame(self._pixlocn, artrace.gen_pixloc(self._spect, self._mstrace[det-1], det, gen=False), det)
        else:
            mname = self._argflag['run']['masterdir']+'/'+self._argflag['reduce']['locations']
            self.SetFrame(self._pixlocn, arload.load_master(mname, frametype=None), det)
        return

    def MasterArc(self, fitsdict, det):
        """
        Generate Master Arc frame for a given detector

        Parameters
        ----------
        fitsdict : dict
          Contains relevant information from fits header files
        det : int
          Index of the detector

        Returns
        -------
        boolean : bool
          Should other ScienceExposure classes be updated?
        """

        if self._msarc[det-1] is not None:
            msgs.info("An identical master arc frame already exists")
            return False
        if self._argflag['reduce']['usearc'] in ['arc']:
            msgs.info("Preparing a master arc frame")
            ind = self._idx_arcs
            # Load the arc frames
            frames = arload.load_frames(self, fitsdict, ind, det, frametype='arc', msbias=self._msbias[det-1])
            if self._argflag['reduce']['arcmatch'] > 0.0:
                sframes = arsort.match_frames(frames, self._argflag['reduce']['arcmatch'], msgs, frametype='arc',
                                              satlevel=self._spect['det']['saturation']*self._spect['det']['nonlinear'])
                subframes = np.zeros((frames.shape[0], frames.shape[1], len(sframes)))
                numarr = np.array([])
                for i in xrange(len(sframes)):
                    numarr = np.append(numarr, sframes[i].shape[2])
                    msarc = arcomb.comb_frames(sframes[i], det, spect=self._spect,
                                               frametype='arc', **self._argflag['arc']['comb'])
                    # Send the data away to be saved
                    subframes[:,:,i] = msarc.copy()
                del sframes
                # Combine all sub-frames
                msarc = arcomb.comb_frames(subframes, det, spect=self._spect,
                                           frametype='arc', weights=numarr, **self._argflag['arc']['comb'])
                del subframes
            else:
                msarc = arcomb.comb_frames(frames, det, spect=self._spect,
                                           frametype='arc', **self._argflag['arc']['comb'])
            del frames
            # # Derive a suitable name for the master arc frame
            # msarc_name = "{0:s}/{1:s}/msarc{2:s}_{3:03d}.fits".format(os.getcwd(),self._argflag['run']['masterdir'],self._spect["det"][det-1]["suffix"],len(self._done_arcs))
            # self._tltprefix = os.path.splitext(os.path.basename(msarc_name))[0]
            # # Send the data away to be saved
            # arsave.save_master(self, msarc, filename=msarc_name, frametype='arc', ind=ind)
            # # Store the files used and the master bias name in case it can be used during the later reduction processes
            # self._done_arcs.append(ind)
            # self._name_arcs.append(msarc_name)
        else:
            msarc_name = self._argflag['run']['masterdir']+'/'+self._argflag['reduce']['usearc']
            msarc = arload.load_master(msarc_name, frametype=None)
        # Set and then delete the Master Arc frame
        self.SetMasterFrame(msarc, "arc", det)
        del msarc
        return True

    def MasterBias(self, fitsdict, det):
        """
        Generate Master Bias frame for a given detector

        Parameters
        ----------
        fitsdict : dict
          Contains relevant information from fits header files
        det : int
          Index of the detector

        Returns
        -------
        boolean : bool
          Should other ScienceExposure classes be updated?
        """

        # If the master bias is already made, use it
        if self._msbias[det-1] is not None:
            msgs.info("An identical master {0:s} frame already exists".format(self._argflag['reduce']['usebias']))
            return False
        if self._argflag['reduce']['usebias'] in ['bias', 'dark']:
            msgs.info("Preparing a master {0:s} frame".format(self._argflag['reduce']['usebias']))
            # Get all of the bias frames for this science frame
            ind = self._idx_bias
            # Load the Bias/Dark frames
            frames = arload.load_frames(self, fitsdict, ind, det, frametype=self._argflag['reduce']['usebias'], transpose=self._transpose)
            msbias = arcomb.comb_frames(frames, det, spect=self._spect, frametype=self._argflag['reduce']['usebias'], **self._argflag['bias']['comb'])
            del frames
        elif self._argflag['reduce']['usebias'] == 'overscan':
            self.SetMasterFrame('overscan', "bias", det, copy=False)
            return False
        elif self._argflag['reduce']['usebias'] == 'none':
            msgs.info("Not performing a bias/dark subtraction")
            self.SetMasterFrame(None, "bias", det, copy=False)
            return False
        else: # It must be the name of a file the user wishes to load
            msbias_name = self._argflag['run']['masterdir']+'/'+self._argflag['reduce']['usebias']
            msbias = arload.load_master(msbias_name, frametype="bias")
        # Set and then delete the Master Bias frame
        self.SetMasterFrame(msbias, "bias", det)
        del msbias
        return True

    def MasterFlatField(self, fitsdict, det):
        """
        Generate Master Flat-field frame for a given detector

        Parameters
        ----------
        fitsdict : dict
          Contains relevant information from fits header files
        det : int
          Index of the detector

        Returns
        -------
        boolean : bool
          Should other ScienceExposure classes be updated?
        """

        if self._argflag['reduce']['flatfield']:  # Only do it if the user wants to flat field
        # If the master pixflat is already made, use it
            if self._mspixflat[det-1] is not None:
                msgs.info("An identical master pixflat frame already exists")
                if self._mspixflatnrm[det-1] is None:
                    # Normalize the flat field
                    msgs.info("Normalizing the pixel flat")
                    mspixflatnrm, msblaze = arproc.flatnorm(self, det, self.GetMasterFrame("pixflat", det),
                                                            overpix=0, plotdesc="Blaze function")
                    self.SetFrame(self._msblaze, msblaze, det)
                    self.SetMasterFrame(mspixflatnrm, "normpixflat", det)
                return False
            ###############
            # Generate a master pixel flat frame
            if self._argflag['reduce']['useflat'] in ['pixflat', 'blzflat']:
                msgs.info("Preparing a master pixel flat frame with {0:s}".format(self._argflag['reduce']['useflat']))
                # Get all of the pixel flat frames for this science frame
                ind = self._idx_flat
                # Load the frames for tracing
                frames = arload.load_frames(self, fitsdict, ind, det, frametype='pixel flat',
                                            msbias=self._msbias[det-1], transpose=self._transpose)
                if self._argflag['reduce']['flatmatch'] > 0.0:
                    sframes = arsort.match_frames(frames, self._argflag['reduce']['flatmatch'],
                                                  frametype='pixel flat', satlevel=self._nonlinear)
                    subframes = np.zeros((frames.shape[0], frames.shape[1], len(sframes)))
                    numarr = np.array([])
                    for i in xrange(len(sframes)):
                        numarr = np.append(numarr, sframes[i].shape[2])
                        mspixflat = arcomb.comb_frames(sframes[i], det, spect=self._spect, frametype='pixel flat',
                                                       **self._argflag['pixflat']['comb'])
                        subframes[:,:,i] = mspixflat.copy()
                    del sframes
                    # Combine all sub-frames
                    mspixflat = arcomb.comb_frames(subframes, det, spect=self._spect, frametype='pixel flat',
                                                   weights=numarr, **self._argflag['pixflat']['comb'])
                    del subframes
                else:
                    mspixflat = arcomb.comb_frames(frames, det, spect=self._spect, frametype='pixel flat',
                                                   **self._argflag['pixflat']['comb'])
                del frames
            else:  # It must be the name of a file the user wishes to load
                mspixflat_name = self._argflag['run']['masterdir']+'/'+self._argflag['reduce']['usepixflat']
                mspixflat = arload.load_master(mspixflat_name, msgs, frametype=None)
            # Now that the combined, master flat field frame is loaded...
            # Normalize the flat field
            mspixflatnrm, msblaze = arproc.flatnorm(self, det, mspixflat, overpix=0, plotdesc="Blaze function")
            self.SetFrame(self._msblaze, msblaze, det)
        else:
            msgs.work("Pixel Flat arrays need to be generated when not flat fielding")
            msgs.bug("Blaze is currently undefined")
            mspixflat = np.ones_like(self._msarc)
            mspixflatnrm = np.ones_like(self._msarc)
        self.SetMasterFrame(mspixflat, "pixflat", det)
        self.SetMasterFrame(mspixflatnrm, "normpixflat", det)
        return True

    def MasterTrace(self, fitsdict, det):
        """
        Generate Master Trace frame for a given detector

        Parameters
        ----------
        fitsdict : dict
          Contains relevant information from fits header files
        det : int
          Index of the detector

        Returns
        -------
        boolean : bool
          Should other ScienceExposure classes be updated?
        """

        # If the master trace is already made, use it
        if self._mstrace[det-1] is not None:
            msgs.info("An identical master trace frame already exists")
            return False
        if self._argflag['reduce']['usetrace'] in ['trace', 'blzflat']:
            msgs.info("Preparing a master trace frame with {0:s}".format(self._argflag['reduce']['usetrace']))
            ind = self._idx_trace
            # Load the frames for tracing
            frames = arload.load_frames(self, fitsdict, ind, det, frametype='trace', msbias=self._msbias[det-1],
                                        trim=self._argflag['reduce']['trim'], transpose=self._transpose)
            if self._argflag['reduce']['flatmatch'] > 0.0:
                sframes = arsort.match_frames(frames, self._argflag['reduce']['flatmatch'], msgs, frametype='trace', satlevel=self._spect['det'][det-1]['saturation']*self._spect['det'][det-1]['nonlinear'])
                subframes = np.zeros((frames.shape[0], frames.shape[1], len(sframes)))
                numarr = np.array([])
                for i in xrange(len(sframes)):
                    numarr = np.append(numarr, sframes[i].shape[2])
                    mstrace = arcomb.comb_frames(sframes[i], det, spect=self._spect, frametype='trace', **self._argflag['trace']['comb'])
                    subframes[:,:,i] = mstrace.copy()
                del sframes
                # Combine all sub-frames
                mstrace = arcomb.comb_frames(subframes, det, spect=self._spect, frametype='trace', weights=numarr, **self._argflag['trace']['comb'])
                del subframes
            else:
                mstrace = arcomb.comb_frames(frames, det, spect=self._spect, frametype='trace', **self._argflag['trace']['comb'])
            del frames
        elif self._argflag['reduce']['usetrace'] == 'science':
            msgs.error("Tracing with a science frame is not yet implemented")
        else: # It must be the name of a file the user wishes to load
            mstrace_name = self._argflag['run']['masterdir']+'/'+self._argflag['reduce']['usetrace']
            mstrace = arload.load_master(mstrace_name, frametype=None)
        # Set and then delete the Master Trace frame
        self.SetMasterFrame(mstrace, "trace", det)
        del mstrace
        return True

    def Setup(self):

        # Sort the data
        msgs.bug("Files and folders should not be deleted -- there should be an option to overwrite files automatically if they already exist, or choose to rename them if necessary")
        self._filesort = arsort.sort_data(self)
        # Write out the details of the sorted files
        if self._argflag['out']['sorted'] is not None: arsort.sort_write(self)
        # Match Science frames to calibration frames
        arsort.match_science(self)
        # If the user is only debugging, then exit now
        if self._argflag['run']['calcheck']:
            msgs.info("Calibration check complete. Change the 'calcheck' flag to continue with data reduction")
            sys.exit()
        # Make directory structure for different objects
        self._sci_targs = arsort.make_dirs(self)
        return

    # Setters
    @staticmethod
    def SetFrame(toarray, value, det, copy=True):
        if copy: toarray[det-1] = value.copy()
        else: toarray[det-1] = value
        return

    def SetMasterFrame(self, frame, ftype, det, copy=True):
        det -= 1
        if copy: cpf = frame.copy()
        else: cpf = frame
        # Set the frame
        if ftype == "arc": self._msarc[det] = cpf
        elif ftype == "bias": self._msbias[det] = cpf
        elif ftype == "normpixflat": self._mspixflatnrm[det] = cpf
        elif ftype == "pixflat": self._mspixflat[det] = cpf
        elif ftype == "trace": self._mstrace[det] = cpf
        else:
            msgs.bug("I could not set master frame of type: {0:s}".format(ftype))
            msgs.error("Please contact the authors")
        return

    # Getters
    @staticmethod
    def GetFrame(getarray, det, copy=True):
        if copy:
            return getarray[det-1].copy()
        else:
            return getarray[det-1]

    def GetMasterFrame(self, ftype, det, copy=True):

        det -= 1
        # Get the frame
        if copy:
            if ftype == "arc": return self._msarc[det].copy()
            elif ftype == "bias": return self._msbias[det].copy()
            elif ftype == "normpixflat": return self._mspixflatnrm[det].copy()
            elif ftype == "pixflat": return self._mspixflat[det].copy()
            elif ftype == "trace": return self._mstrace[det].copy()
            else:
                msgs.bug("I could not get master frame of type: {0:s}".format(ftype))
                msgs.error("Please contact the authors")
        else:
            if ftype == "arc": return self._msarc[det]
            elif ftype == "bias": return self._msbias[det]
            elif ftype == "normpixflat": return self._mspixflatnrm[det]
            elif ftype == "pixflat": return self._mspixflat[det]
            elif ftype == "trace": return self._mstrace[det]
            else:
                msgs.bug("I could not get master frame of type: {0:s}".format(ftype))
                msgs.error("Please contact the authors")
        return None
