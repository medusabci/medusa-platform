import medusa
from abc import ABC, abstractmethod


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
    keeping it simple: band-pass filter and notch filter"""

    def __init__(self, preprocessing_settings):
        # Settings
        self.freq_filt_settings = preprocessing_settings['frequency-filter']
        self.notch_filt_settings = preprocessing_settings['notch-filter']
        self.apply_freq_filt = self.freq_filt_settings['apply']
        self.apply_notch = self.notch_filt_settings['apply']
        # Variables to fit
        self.fs = None
        self.n_cha = None
        self.subsample_filt = None
        self.freq_filt = None
        self.notch_filt = None

    def fit(self, fs, n_cha):
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

    def transform(self, chunk_data):
        if self.apply_freq_filt:
            chunk_data = self.freq_filt.transform(chunk_data)
        if self.apply_notch:
            chunk_data = self.notch_filt.transform(chunk_data)
        return chunk_data
