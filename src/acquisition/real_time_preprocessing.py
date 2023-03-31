import medusa
from abc import ABC, abstractmethod
import numpy as np


class RealTimePreprocessor(ABC):

    """Abstract class to implement different real time preprocessing
    algorithms
    """

    @abstractmethod
    def fit(self, *args):
        raise NotImplemented

    @abstractmethod
    def transform(self, *args):
        raise NotImplemented


class PlotsRealTimePreprocessor(RealTimePreprocessor):

    """Class that implements real time preprocessing functions for plotting,
    keeping it simple: band-pass filter and notch filter. For more advanced
    pre-processing, implement another class"""

    def __init__(self, preprocessing_settings):
        # Settings
        self.freq_filt_settings = preprocessing_settings['frequency-filter']
        self.notch_filt_settings = preprocessing_settings['notch-filter']
        self.downsampling_settings = preprocessing_settings['downsampling']
        self.apply_freq_filt = self.freq_filt_settings['apply']
        self.apply_notch = self.notch_filt_settings['apply']
        self.apply_downsampling = self.downsampling_settings['apply']
        # Variables to fit
        self.fs = None
        self.n_cha = None
        self.freq_filt = None
        self.notch_filt = None

    def fit(self, fs, n_cha, min_chunk_size):
        self.fs = fs
        self.n_cha = n_cha
        # Frequency filter
        if self.apply_freq_filt:
            self.freq_filt = medusa.IIRFilter(
                order=self.freq_filt_settings['order'],
                cutoff=self.freq_filt_settings['cutoff-freq'],
                btype=self.freq_filt_settings['type'],
                filt_method='sosfilt',
                axis=0)
            self.freq_filt.fit(self.fs, self.n_cha)
        # Notch filter
        if self.apply_notch:
            cutoff = [
                self.notch_filt_settings['freq'] +
                self.notch_filt_settings['bandwidth'][0],
                self.notch_filt_settings['freq'] +
                self.notch_filt_settings['bandwidth'][1]
            ]
            self.notch_filt = medusa.IIRFilter(
                order=self.notch_filt_settings['order'],
                cutoff=cutoff,
                btype='bandstop',
                filt_method='sosfilt',
                axis=0)
            self.notch_filt.fit(self.fs, self.n_cha)
        # Downsampling
        if self.apply_downsampling:
            if self.freq_filt_settings['type'] not in ['bandpass', 'lowpass']:
                raise ValueError('Incorrect frequency filter btype. Only '
                                 'bandpass and lowpass are available if '
                                 'downsampling is applied.')
            nyquist_cutoff = self.fs / 2 / self.downsampling_settings['factor']
            if self.freq_filt_settings['type'] == 'lowpass':
                if self.freq_filt_settings['cutoff-freq'] > nyquist_cutoff:
                    raise ValueError(
                        'Incorrect frequency filter for downsampling factor '
                        '%i. The upper cutoff must be less than %.2f to '
                        'comply with Nyquist criterion' %
                        (self.downsampling_settings['factor'], nyquist_cutoff))
            elif self.freq_filt_settings['type'] == 'bandpass':
                if self.freq_filt_settings['cutoff-freq'][1] > nyquist_cutoff:
                    raise ValueError(
                        'Incorrect frequency filter for downsampling factor '
                        '%i. The upper cutoff must be less than %.2f to '
                        'comply with Nyquist criterion' %
                        (self.downsampling_settings['factor'], nyquist_cutoff))

            # Check downsampling factor
            if min_chunk_size <= 1:
                raise ValueError(
                    'Downsampling is not allowed with the current values of '
                    'update and sample rates. Increase the update rate to '
                    'apply downsampling.')
            elif min_chunk_size // self.downsampling_settings['factor'] < 1:
                raise ValueError(
                    'The downsampling factor is to high for the current '
                    'values of update and sample rates. The maximum value '
                    'is: %i' % min_chunk_size)

    def transform(self, chunk_times, chunk_data):
        if self.apply_freq_filt:
            chunk_data = self.freq_filt.transform(chunk_data)
        if self.apply_notch:
            chunk_data = self.notch_filt.transform(chunk_data)
        if self.apply_downsampling:
            chunk_times = chunk_times[0::self.downsampling_settings['factor']]
            chunk_data = chunk_data[0::self.downsampling_settings['factor'], :]
        return chunk_times, chunk_data
