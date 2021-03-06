# BUILT-IN MODULES
import time
from abc import ABC, abstractmethod
import weakref
import traceback
# EXTERNAL MODULES
import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import QFont
from scipy import signal as scp_signal
# MEDUSA-CORE MODULES
from acquisition import lsl_utils, real_time_preprocessing
import constants
# MEDUSA-PLATFORM MODULES
import medusa


class RealTimePlot(ABC):

    def __init__(self, uid, plot_state, medusa_interface, theme):
        super().__init__()
        # Components and settings
        self.uid = uid
        self.plot_state = plot_state
        self.medusa_interface = medusa_interface
        self.ready = False
        self.preprocessing_settings = None
        self.visualization_settings = None
        self.lsl_stream_info = None
        self.lsl_stream = None
        self.receiver = None
        self.preprocessor = None
        self.worker = None
        self.init_time = None
        # Create widget
        self.widget = pg.PlotWidget()
        self.widget.setSizePolicy(QSizePolicy.Ignored,
                                  QSizePolicy.Ignored)
        self.plot_item = self.widget.getPlotItem()
        self.plot_item_view_box = self.plot_item.getViewBox()
        # Get axis
        self.y_axis = self.plot_item.getAxis('left')
        self.x_axis = self.plot_item.getAxis('bottom')
        # Style and theme
        self.theme = theme
        self.background_color = theme['THEME_BG_DARK']
        self.curve_color = theme['THEME_SIGNAL_CURVE']
        self.offset_color = theme['THEME_SIGNAL_OFFSET']
        self.widget.setBackground(self.background_color)
        self.curve_width = 1
        self.offset_width = 1

    @staticmethod
    @abstractmethod
    def get_default_settings():
        """Create de default settings dict"""
        raise NotImplemented

    @staticmethod
    @abstractmethod
    def check_settings(signal_settings, plot_settings):
        """Check settings dicts to see if it's correctly formatted"""
        raise NotImplemented

    @staticmethod
    @abstractmethod
    def check_signal(signal_type):
        raise NotImplemented

    @abstractmethod
    def init_plot(self):
        """Init the plot. It's called before starting the worker"""
        raise NotImplemented

    @abstractmethod
    def update_plot(self, chunk_times, chunk_signal):
        """Update the plot with the last chunk of signal received in the
        worker. Since this function is called recursively when a new chunk
        of signal is received, it must handle errors with the following block:
            try:
                pass
            except Exception as e:
                self.exception_handler(e)
        """
        raise NotImplemented

    @abstractmethod
    def clear_plot(self):
        """Clear custom variables and widgets if necessary. Called from
        destroy_plot.
        """
        raise NotImplemented

    def set_ready(self):
        self.ready = True

    def set_titles(self, plot_title, x_axis_title, y_axis_title):
        self.widget.setTitle(plot_title)
        self.widget.setLabel('bottom', text=x_axis_title[0],
                             units=x_axis_title[1])
        self.widget.setLabel('left', text=y_axis_title[0],
                             units=y_axis_title[1])
        fn = QFont()
        fn.setBold(True)
        self.widget.getAxis("bottom").setTickFont(fn)
        self.widget.getAxis("left").setTickFont(fn)

    def set_settings(self, signal_settings, plot_settings):
        """Set settings dicts"""
        self.check_settings(signal_settings, plot_settings)
        self.preprocessing_settings = signal_settings
        self.visualization_settings = plot_settings

    def set_receiver(self, lsl_stream_info):
        """Set settings dicts

        Parameters
        ----------
        lsl_stream_info: lsl_utils.LSLStreamWrapper
            LSL stream (medusa wrapper)
        """
        if self.check_signal(lsl_stream_info.medusa_type):
            self.lsl_stream_info = lsl_stream_info
            self.receiver = lsl_utils.LSLStreamReceiver(self.lsl_stream_info)

    def get_settings(self):
        """Create de default settings dict"""
        settings = {
            'preprocessing_settings': self.preprocessing_settings,
            'visualization_settings': self.visualization_settings
        }
        return settings

    def get_widget(self):
        return self.widget

    def start(self):
        self.preprocessor = real_time_preprocessing.PlotsRealTimePreprocessor(
            self.preprocessing_settings)
        self.init_plot()
        self.worker = RealTimePlotWorker(self.plot_state,
                                         self.receiver,
                                         self.preprocessor)
        self.worker.update.connect(self.update_plot)
        self.worker.error.connect(self.handle_exception)
        self.worker.start()

    def destroy_plot(self):
        self.init_time = None
        self.widget.clear()
        self.clear_plot()

    def handle_exception(self, ex):
        self.medusa_interface.error(ex)


class TimePlotMultichannel(RealTimePlot):

    def __init__(self, uid, plot_state, queue_to_medusa, theme):
        super().__init__(uid, plot_state, queue_to_medusa, theme)
        # Graph variables
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.curves = None
        self.offsets = None
        self.cha_separation = None
        self.win_t = None
        self.subsample_factor = None
        # Custom menu
        self.plot_item_view_box = None

    class TimePlotMultichannelViewBoxMenu(QMenu):
        """ This class inherits from GMenu and implements the menu that appears
        when right click is performed on the graph
        """

        def __init__(self, view):
            """ Class constructor

            Parameters
            ----------
            view: PlotWidget
                PyQtGraph PlotWidget class where the actions are performed
            """
            QMenu.__init__(self)
            # Keep weakref to view to avoid circular reference (don't know why,
            # but this prevents the ViewBox from crash)
            self.view = weakref.ref(view)
            # Some options
            self.setTitle("ViewBox options")
            self.auto_range_action = QAction("Autorange", self)
            self.auto_range_action.triggered.connect(self.auto_range)
            self.addAction(self.auto_range_action)

        def auto_range(self):
            self.view().plot_item.autoRange()

    def set_custom_menu(self):
        # Delete the context menu
        self.widget.sceneObj.contextMenu = None
        # Delete the ctrlMenu (transformations options)
        self.widget.getPlotItem().ctrlMenu = None
        # Get view box
        self.plot_item_view_box = self.widget.getPlotItem().getViewBox()
        # Set the customized menu in the graph
        self.plot_item_view_box.menu = self.TimePlotMultichannelViewBoxMenu(self)

    @staticmethod
    def get_default_settings():
        preprocessing_settings = {
            'frequency-filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff-freq': [1],
                'order': 5
            },
            'notch-filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            }
        }
        visualization_settings = {
            'seconds_displayed': 5,
            'subsample_factor': 2,
            'scaling': {
                'apply_autoscale': True,
                'n_std_tolerance_autoscale': 1.25,
                'std_factor_separation_autoscale': 5,
                'initial_channel_separation': 150,
            },
            'title': '<b>TimePlotMultichannel</b>',
            'x_axis_label': ['<b>Time</b>', 's'],
            'y_axis_label': ['<b>Signal</b>', 'V'],
        }
        return preprocessing_settings, visualization_settings

    @staticmethod
    def check_settings(preprocessing_settings, visualization_settings):
        # Check subsample factor
        if visualization_settings['subsample_factor'] < 1:
            raise ValueError('The subsample factor must be '
                             'equal or greater than 1\n')

    @staticmethod
    def check_signal(signal_type):
        return True

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frecuency.
        """
        # Set custom menu
        self.set_custom_menu()
        self.set_titles(self.visualization_settings['title'],
                        self.visualization_settings['x_axis_label'],
                        self.visualization_settings['y_axis_label'])
        # Update variables
        self.cha_separation = \
            self.visualization_settings['scaling']['initial_channel_separation']
        self.win_t = self.visualization_settings['seconds_displayed']
        self.subsample_factor = self.visualization_settings['subsample_factor']
        self.win_s = int(self.win_t * self.receiver.fs)
        # Place curves in plot
        self.curves = []
        self.offsets = []
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        offset_pen = pg.mkPen(color=self.offset_color,
                              width=self.offset_width,
                              style=Qt.SolidLine)
        for i in range(self.receiver.n_cha):
            self.offsets.append(self.widget.plot(pen=offset_pen))
            self.curves.append(self.widget.plot(pen=curve_pen))
        # Draw y axis
        self.draw_y_axis_ticks()
        # Signal plotted
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.receiver.n_cha])

    def draw_y_axis_ticks(self):
        # Draw y axis ticks (channel labels)
        ticks = list()
        if self.receiver.l_cha is not None:
            for i in range(self.receiver.n_cha):
                offset = self.cha_separation * i
                label = self.receiver.l_cha[-i - 1]
                ticks.append((offset, label))
        ticks = [ticks]   # Two levels for ticks
        self.y_axis.setTicks(ticks)
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.receiver.n_cha * self.cha_separation
        if self.receiver.n_cha > 1:
            self.plot_item.setYRange(y_min, y_max, padding=0)

    def draw_x_axis_ticks(self, x_in_graph):
        # Draw x axis ticks (time)
        n_ticks = 4
        x = np.arange(x_in_graph.shape[0])
        step = x_in_graph.shape[0] // n_ticks
        margin_last_tick = (3 * x_in_graph.shape[0] // 100) + 1
        x_ticks_pos = [x[i * step] for i in range(n_ticks)]
        x_ticks_pos.append(x[n_ticks * step - margin_last_tick])
        x_ticks_val = ['%.1f' % x_in_graph[i * step] for i in range(n_ticks)]
        x_ticks_val.append(
            '%.1f' % x_in_graph[n_ticks * step - margin_last_tick])
        self.x_axis.setTicks([[(x_ticks_pos[i], str(x_ticks_val[i])) for
                               i in range(n_ticks + 1)]])
        self.plot_item.setXRange(x[0], x[-1], padding=0)

    def append_data(self, chunk_times, chunk_signal):
        self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
        if len(self.time_in_graph) >= self.win_s:
            self.time_in_graph = self.time_in_graph[-self.win_s:]
        self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
        if len(self.sig_in_graph) >= self.win_s:
            self.sig_in_graph = self.sig_in_graph[-self.win_s:]

        # return self.time_in_graph.copy(), self.sig_in_graph.copy()
        return self.time_in_graph, self.sig_in_graph

    def subsample(self, x_in_graph, sig_in_graph):
        if self.subsample_factor > 1:
            if sig_in_graph.shape[0] > 27:
                # Decimate applies IIR filtering to avoid aliasing
                sig_in_graph = scp_signal.decimate(sig_in_graph,
                                                   self.subsample_factor,
                                                   axis=0)
                x_in_graph = np.linspace(x_in_graph[0],
                                         x_in_graph[-1],
                                         sig_in_graph.shape[0])
            else:
                target_samp = len(sig_in_graph) // self.subsample_factor
                sig_in_graph = scp_signal.resample(sig_in_graph,
                                                   target_samp,
                                                   axis=0)
                x_in_graph = np.linspace(x_in_graph[0],
                                         x_in_graph[-1],
                                         sig_in_graph.shape[0])
        return x_in_graph, sig_in_graph

    def set_data(self, x_in_graph, sig_in_graph):
        x = np.arange(x_in_graph.shape[0])
        off_y = np.ones(x_in_graph.shape)
        for i in range(self.receiver.n_cha):
            temp = sig_in_graph[:, self.receiver.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].setData(x=x, y=temp)
            self.offsets[i].setData(x=x, y=self.cha_separation * i * off_y)

    def autoscale(self, y_in_graph):
        scaling_sett = self.visualization_settings['scaling']
        if scaling_sett['apply_autoscale']:
            y_std = np.std(y_in_graph)
            std_tol = scaling_sett['n_std_tolerance_autoscale']
            std_factor = scaling_sett['std_factor_separation_autoscale']
            if y_std > self.cha_separation * std_tol or \
                    y_std < self.cha_separation / std_tol:
                self.cha_separation = std_factor * y_std
                self.draw_y_axis_ticks()

    def update_plot(self, chunk_times, chunk_signal):
        """
        This function updates the data in the graph. Notice that channel 0 is
        drew up in the chart, whereas the last channel is in the bottom.
        """
        try:
            # Init time
            if self.init_time is None:
                self.init_time = chunk_times[0]
            # Temporal series are always plotted from zero.
            chunk_times = np.array(chunk_times) - self.init_time
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            # Subsampling (do not modify all the signal)
            x_in_graph, sig_in_graph = self.subsample(x_in_graph, sig_in_graph)
            # Set data
            self.set_data(x_in_graph, sig_in_graph)
            # Update y range (only if autoscale is activated)
            self.autoscale(sig_in_graph)
            # Update x range
            self.draw_x_axis_ticks(x_in_graph)
        except Exception as e:
            traceback.print_exc()
            self.handle_exception(e)

    def clear_plot(self):
        pass


class PSDPlotMultichannel(RealTimePlot):

    def __init__(self, uid, plot_state, queue_to_medusa, theme):
        super().__init__(uid, plot_state, queue_to_medusa, theme)
        # Graph variables
        self.win_t = None
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.curves = None
        self.offsets = None
        self.cha_separation = None
        self.n_samples_psd = None
        # Custom menu
        self.plot_item_view_box = None

    class PSDPlotMultichannelViewBoxMenu(QMenu):
        """ This class inherits from GMenu and implements the menu that appears
        when right click is performed on the graph
        """

        def __init__(self, view):
            """ Class constructor

            Parameters
            ----------
            view: PlotWidget
                PyQtGraph PlotWidget class where the actions are performed
            """
            QMenu.__init__(self)
            # Keep weakref to view to avoid circular reference (don't know why,
            # but this prevents the ViewBox from crash)
            self.view = weakref.ref(view)
            # Some options
            self.setTitle("ViewBox options")
            self.viewAll = QAction("Autorange", self)
            self.viewAll.triggered.connect(self.auto_range)
            self.addAction(self.viewAll)

        def auto_range(self):
            self.view().plot_item.autoRange()

    def set_custom_menu(self):
        # Delete the context menu
        self.widget.sceneObj.contextMenu = None
        # Delete the ctrlMenu (transformations options)
        self.widget.getPlotItem().ctrlMenu = None
        # Get view box
        self.plot_item_view_box = self.widget.getPlotItem().getViewBox()
        # Set the customized menu in the graph
        self.plot_item_view_box.menu = self.PSDPlotMultichannelViewBoxMenu(self)

    @staticmethod
    def get_default_settings():
        preprocessing_settings = {
            'frequency-filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff-freq': [1],
                'order': 5
            },
            'notch-filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            }
        }
        visualization_settings = {
            'psd_window_seconds': 5,
            'scaling': {
                'apply_autoscale': True,
                'n_std_tolerance_autoscale': 1.25,
                'std_factor_separation_autoscale': 5,
                'initial_channel_separation': 10e-3,
            },
            'welch_overlap_pct': 25,
            'welch_seg_len_pct': 50,
            'x_range': [0.1, 30],
            'y_range': 'auto',
            'init_channel_label': None,
            'title': '<b>PSDPlotMultichannel</b>',
            'x_axis_label': ['<b>Frequency</b>', 'Hz'],
            'y_axis_label': ['<b>Power</b>', '<math>V<sup>2</sup>/Hz</math>'],
        }
        return preprocessing_settings, visualization_settings

    @staticmethod
    def check_settings(preprocessing_settings, visualization_settings):
        pass

    @staticmethod
    def check_signal(signal_type):
        return True

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frecuency.
        """
        # Set custom menu
        self.set_custom_menu()
        self.set_titles(self.visualization_settings['title'],
                        self.visualization_settings['x_axis_label'],
                        self.visualization_settings['y_axis_label'])
        # Update variables
        self.cha_separation = \
            self.visualization_settings['scaling']['initial_channel_separation']
        self.win_t = self.visualization_settings['psd_window_seconds']
        self.win_s = int(self.win_t * self.receiver.fs)
        self.n_samples_psd = self.win_s
        # Place curves in plot
        self.curves = []
        self.offsets = []
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        offset_pen = pg.mkPen(color=self.offset_color,
                              width=self.offset_width,
                              style=Qt.SolidLine)
        for i in range(self.receiver.n_cha):
            self.offsets.append(self.widget.plot(pen=offset_pen))
            self.curves.append(self.widget.plot(pen=curve_pen))
        # Draw y axis
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()
        # Signal plotted
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.receiver.n_cha])

    def draw_y_axis_ticks(self):
        ticks = list()
        if self.receiver.l_cha is not None:
            for i in range(self.receiver.n_cha):
                offset = self.cha_separation * i
                label = self.receiver.l_cha[-i - 1]
                ticks.append((offset, label))
        ticks = [ticks]  # Two levels for ticks
        self.y_axis.setTicks(ticks)
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.receiver.n_cha * self.cha_separation
        if self.receiver.n_cha > 1:
            self.plot_item.setYRange(y_min, y_max, padding=0)

    def draw_x_axis_ticks(self):
        self.plot_item.setXRange(
            self.visualization_settings['x_range'][0],
            self.visualization_settings['x_range'][1],
            padding=0)

    def append_data(self, chunk_times, chunk_signal):
        self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
        if len(self.time_in_graph) >= self.win_s:
            self.time_in_graph = self.time_in_graph[-self.win_s:]
        self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
        if len(self.sig_in_graph) >= self.win_s:
            self.sig_in_graph = self.sig_in_graph[-self.win_s:]

        return self.time_in_graph.copy(), self.sig_in_graph.copy()

    def set_data(self, x_in_graph, sig_in_graph):
        x = np.arange(x_in_graph.shape[0])
        off_y = np.ones(x_in_graph.shape)
        for i in range(self.receiver.n_cha):
            temp = sig_in_graph[:, self.receiver.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].setData(x=x, y=temp)
            self.offsets[i].setData(x=x, y=self.cha_separation * i * off_y)

    def autoscale(self, y_in_graph):
        scaling_sett = self.visualization_settings['scaling']
        if scaling_sett['apply_autoscale']:
            y_std = np.std(y_in_graph)
            std_tol = scaling_sett['n_std_tolerance_autoscale']
            std_factor = scaling_sett['std_factor_separation_autoscale']
            if y_std > self.cha_separation * std_tol or \
                    y_std < self.cha_separation / std_tol:
                self.cha_separation = std_factor * y_std
                self.draw_y_axis_ticks()

    def update_plot(self, chunk_times, chunk_signal):
        """
        This function updates the data in the graph. Notice that channel 0 is
        drew up in the chart, whereas the last channel is in the bottom.
        """
        try:
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            # Compute PSD
            welch_seg_len = np.round(
                self.visualization_settings['welch_seg_len_pct'] / 100.0 *
                sig_in_graph.shape[0]).astype(int)
            welch_overlap = np.round(
                self.visualization_settings['welch_overlap_pct'] / 100.0 *
                welch_seg_len).astype(int)
            welch_ndft = welch_seg_len
            x_in_graph, sig_in_graph = scp_signal.welch(
                sig_in_graph, fs=self.receiver.fs,
                nperseg=welch_seg_len, noverlap=welch_overlap,
                nfft=welch_ndft, axis=0)
            # Set data
            self.set_data(x_in_graph, sig_in_graph)
            # Update y range (only if autoscale is activated)
            self.autoscale(sig_in_graph)
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        pass


class TimePlot(RealTimePlot):

    def __init__(self, uid, plot_state, queue_to_medusa, theme):
        super().__init__(uid, plot_state, queue_to_medusa, theme)
        # Graph variables
        self.win_t = None
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.curve = None
        self.y_range = None
        self.subsample_factor = None
        # Custom menu
        self.plot_item_view_box = None

    class TimePlotViewBoxMenu(QMenu):
        """This class inherits from GMenu and implements the menu that appears
        when right click is performed on a graph
        """

        def __init__(self, plot_handler):
            """Class constructor

            Parameters
            -----------
            plot_handler: PlotWidget
                PyQtGraph PlotWidget class where the actions are performed
            """
            QMenu.__init__(self)
            # Pointer to the psd_plot_handler
            self.plot_handler = plot_handler

        def select_channel(self):
            cha_label = self.sender().text()
            for i in range(self.plot_handler.receiver.n_cha):
                if self.plot_handler.receiver.l_cha[i] == cha_label:
                    self.plot_handler.select_channel(i)

        def set_channel_list(self):
            for i in range(self.plot_handler.receiver.n_cha):
                channel_action = QAction(
                    self.plot_handler.receiver.l_cha[i], self)
                channel_action.triggered.connect(self.select_channel)
                self.addAction(channel_action)

    def set_custom_menu(self):
        # Delete the context menu
        self.widget.sceneObj.contextMenu = None
        # Delete the ctrlMenu (transformations options)
        self.plot_item.ctrlMenu = None
        # Get view box
        self.plot_item_view_box = self.plot_item.getViewBox()
        # Set the customized menu in the graph
        self.plot_item_view_box.menu = self.TimePlotViewBoxMenu(self)

    @staticmethod
    def get_default_settings():
        preprocessing_settings = {
            'frequency-filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff-freq': [1],
                'order': 5
            },
            'notch-filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            }
        }
        visualization_settings = {
            'init_channel_label': None,
            'seconds_displayed': 5,
            'subsample_factor': 2,
            'scaling': {
                'apply_autoscale': True,
                'n_std_tolerance_autoscale': 1.25,
                'std_factor_separation_autoscale': 5,
                'initial_y_range': [-1, 1],
            },
            'title': '<b>TimePlot</b>',
            'x_axis_label': ['<b>Time</b>', 's'],
            'y_axis_label': ['<b>Signal</b>', 'V'],
        }
        return preprocessing_settings, visualization_settings

    @staticmethod
    def check_settings(preprocessing_settings, visualization_settings):
        # Check subsample factor
        if visualization_settings['subsample_factor'] < 1:
            raise ValueError('The subsample factor must be '
                             'equal or greater than 1\n')

    @staticmethod
    def check_signal(signal_type):
        return True

    def select_channel(self, cha):
        """ This function changes the channel used to compute the PSD displayed in the graph.

        :param cha: sample frecuency in Hz
        """
        self.curr_cha = cha
        self.widget.setTitle(str(self.receiver.l_cha[cha]))

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frecuency.
        """
        # Set custom menu
        self.set_custom_menu()
        self.set_titles(self.visualization_settings['title'],
                        self.visualization_settings['x_axis_label'],
                        self.visualization_settings['y_axis_label'])
        # Update variables
        self.win_t = self.visualization_settings['seconds_displayed']
        self.subsample_factor = self.visualization_settings['subsample_factor']
        self.win_s = int(self.win_t * self.receiver.fs)
        self.y_range = self.visualization_settings['scaling']['initial_y_range']
        # Update view box menu
        self.plot_item_view_box.menu.set_channel_list()
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.receiver.get_channel_indexes_from_labels(init_cha_label) if \
            init_cha_label is not None else 0
        self.select_channel(init_cha)
        # Place curves in plot
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        self.curve = self.widget.plot(pen=curve_pen)
        # Draw y axis
        self.draw_y_axis_ticks()
        # Signal plotted
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.receiver.n_cha])

    def draw_y_axis_ticks(self):
        if self.receiver.n_cha > 1:
            self.plot_item.setYRange(self.y_range[0],
                                     self.y_range[1],
                                     padding=0)

    def draw_x_axis_ticks(self, x_in_graph):
        # Draw x axis ticks (time)
        n_ticks = 4
        x = np.arange(x_in_graph.shape[0])
        step = x_in_graph.shape[0] // n_ticks
        margin_last_tick = (3 * x_in_graph.shape[0] // 100) + 1
        x_ticks_pos = [x[i * step] for i in range(n_ticks)]
        x_ticks_pos.append(x[n_ticks * step - margin_last_tick])
        x_ticks_val = ['%.1f' % x_in_graph[i * step] for i in range(n_ticks)]
        x_ticks_val.append(
            '%.1f' % x_in_graph[n_ticks * step - margin_last_tick])
        self.x_axis.setTicks([[(x_ticks_pos[i], str(x_ticks_val[i])) for
                               i in range(n_ticks + 1)]])
        self.plot_item.setXRange(x[0], x[-1], padding=0)

    def append_data(self, chunk_times, chunk_signal):
        self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
        if len(self.time_in_graph) >= self.win_s:
            self.time_in_graph = self.time_in_graph[-self.win_s:]
        self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
        if len(self.sig_in_graph) >= self.win_s:
            self.sig_in_graph = self.sig_in_graph[-self.win_s:]
        return self.time_in_graph.copy(), self.sig_in_graph.copy()

    def set_data(self, x_in_graph, sig_in_graph):
        x = np.arange(x_in_graph.shape[0])
        self.curve.setData(x=x, y=sig_in_graph)

    def subsample(self, x_in_graph, sig_in_graph):
        if self.subsample_factor > 1:
            if sig_in_graph.shape[0] > 27:
                # Decimate applies IIR filtering to avoid aliasing
                sig_in_graph = scp_signal.decimate(sig_in_graph,
                                                   self.subsample_factor,
                                                   axis=0)
                x_in_graph = np.linspace(x_in_graph[0],
                                         x_in_graph[-1],
                                         sig_in_graph.shape[0])
            else:
                target_samp = len(sig_in_graph) // self.subsample_factor
                sig_in_graph = scp_signal.resample(sig_in_graph,
                                                   target_samp,
                                                   axis=0)
                x_in_graph = np.linspace(x_in_graph[0],
                                         x_in_graph[-1],
                                         sig_in_graph.shape[0])
        return x_in_graph, sig_in_graph

    def autoscale(self, y_in_graph):
        scaling_sett = self.visualization_settings['scaling']
        if scaling_sett['apply_autoscale']:
            y_std = np.std(y_in_graph)
            std_tol = scaling_sett['n_std_tolerance_autoscale']
            std_factor = scaling_sett['std_factor_separation_autoscale']
            if y_std > self.y_range[1] * std_tol or \
                    y_std < self.y_range[1] / std_tol:
                self.y_range[0] = - std_factor * y_std
                self.y_range[1] = std_factor * y_std
                self.draw_y_axis_ticks()

    def update_plot(self, chunk_times, chunk_signal):
        """
        This function updates the data in the graph. Notice that channel 0 is
        drew up in the chart, whereas the last channel is in the bottom.
        """
        try:
            # Init time
            if self.init_time is None:
                self.init_time = chunk_times[0]
            # Temporal series are always plotted from zero.
            chunk_times = np.array(chunk_times) - self.init_time
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            sig_in_graph = sig_in_graph[:, self.curr_cha]
            # Subsampling (do not modify all the signal)
            x_in_graph, sig_in_graph = self.subsample(x_in_graph, sig_in_graph)
            # Set data
            self.set_data(x_in_graph, sig_in_graph)
            # Update y range (only if autoscale is activated)
            self.autoscale(sig_in_graph)
            # Update x range
            self.draw_x_axis_ticks(x_in_graph)
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        pass


class PSDPlot(RealTimePlot):

    def __init__(self, uid, plot_state, queue_to_medusa, theme):
        super().__init__(uid, plot_state, queue_to_medusa, theme)
        # Graph variables
        self.win_t = None
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.curve = None
        self.n_samples_psd = None
        self.y_range = None
        # Custom menu
        self.plot_item_view_box = None

    class PSDPlotViewBoxMenu(QMenu):
        """This class inherits from GMenu and implements the menu that appears
        when right click is performed on a graph
        """

        def __init__(self, psd_plot_handler):
            """Class constructor

            Parameters
            -----------
            psd_plot_handler: PlotWidget
                PyQtGraph PlotWidget class where the actions are performed
            """
            QMenu.__init__(self)
            # Pointer to the psd_plot_handler
            self.psd_plot_handler = psd_plot_handler

        def select_channel(self):
            cha_label = self.sender().text()
            for i in range(self.psd_plot_handler.receiver.n_cha):
                if self.psd_plot_handler.receiver.l_cha[i] == cha_label:
                    self.psd_plot_handler.select_channel(i)

        def set_channel_list(self):
            for i in range(self.psd_plot_handler.receiver.n_cha):
                channel_action = QAction(
                    self.psd_plot_handler.receiver.l_cha[i], self)
                channel_action.triggered.connect(self.select_channel)
                self.addAction(channel_action)

    def set_custom_menu(self):
        # Delete the context menu
        self.widget.sceneObj.contextMenu = None
        # Delete the ctrlMenu (transformations options)
        self.plot_item.ctrlMenu = None
        # Get view box
        self.plot_item_view_box = self.plot_item.getViewBox()
        # Set the customized menu in the graph
        self.plot_item_view_box.menu = self.PSDPlotViewBoxMenu(self)

    @staticmethod
    def get_default_settings():
        preprocessing_settings = {
            'frequency-filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff-freq': [1],
                'order': 5
            },
            'notch-filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            }
        }
        visualization_settings = {
            'init_channel_label': None,
            'psd_window_seconds': 5,
            'scaling': {
                'apply_autoscale': True,
                'n_std_tolerance_autoscale': 1.25,
                'std_factor_separation_autoscale': 5,
                'initial_y_range': [0, 10e-3],
            },
            'welch_overlap_pct': 25,
            'welch_seg_len_pct': 50,
            'x_range': [0.1, 30],
            'title': '<b>PSDPlotMultichannel</b>',
            'x_axis_label': ['<b>Frequency</b>', 'Hz'],
            'y_axis_label': ['<b>Power</b>', 'V^2/Hz'],
        }
        return preprocessing_settings, visualization_settings

    @staticmethod
    def check_settings(preprocessing_settings, visualization_settings):
        pass

    @staticmethod
    def check_signal(signal_type):
        return True

    def select_channel(self, cha):
        """ This function changes the channel used to compute the PSD displayed in the graph.

        :param cha: sample frecuency in Hz
        """
        self.curr_cha = cha
        self.widget.setTitle(str(self.receiver.l_cha[cha]))

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frecuency.
        """
        # Set custom menu
        self.set_custom_menu()
        self.set_titles(self.visualization_settings['title'],
                        self.visualization_settings['x_axis_label'],
                        self.visualization_settings['y_axis_label'])
        # Update variables
        self.win_t = self.visualization_settings['psd_window_seconds']
        self.win_s = int(self.win_t * self.receiver.fs)
        self.n_samples_psd = self.win_s
        self.y_range = self.visualization_settings['scaling']['initial_y_range']
        # Update view box menu
        self.plot_item_view_box.menu.set_channel_list()
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.receiver.get_channel_indexes_from_labels(init_cha_label) if \
            init_cha_label is not None else 0
        self.select_channel(init_cha)
        # Place curves in plot
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        self.curve = self.widget.plot(pen=curve_pen)
        # Draw y axis
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()
        # Signal plotted
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.receiver.n_cha])

    def draw_y_axis_ticks(self):
        if self.receiver.n_cha > 1:
            self.plot_item.setYRange(self.y_range[0],
                                     self.y_range[1],
                                     padding=0)

    def draw_x_axis_ticks(self):
        self.plot_item.setXRange(
            self.visualization_settings['x_range'][0],
            self.visualization_settings['x_range'][1],
            padding=0)

    def append_data(self, chunk_times, chunk_signal):
        self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
        if len(self.time_in_graph) >= self.win_s:
            self.time_in_graph = self.time_in_graph[-self.win_s:]
        self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
        if len(self.sig_in_graph) >= self.win_s:
            self.sig_in_graph = self.sig_in_graph[-self.win_s:]
        return self.time_in_graph.copy(), self.sig_in_graph.copy()

    def set_data(self, x_in_graph, sig_in_graph):
        self.curve.setData(x=x_in_graph, y=sig_in_graph)

    def autoscale(self, y_in_graph):
        scaling_sett = self.visualization_settings['scaling']
        if scaling_sett['apply_autoscale']:
            y_std = np.std(y_in_graph)
            std_tol = scaling_sett['n_std_tolerance_autoscale']
            std_factor = scaling_sett['std_factor_separation_autoscale']
            if y_std > self.y_range[1] * std_tol or \
                    y_std < self.y_range[1] / std_tol:
                self.y_range[1] = std_factor * y_std
                self.draw_y_axis_ticks()

    def update_plot(self, chunk_times, chunk_signal):
        """
        This function updates the data in the graph. Notice that channel 0 is
        drew up in the chart, whereas the last channel is in the bottom.
        """
        try:
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            # Compute PSD
            welch_seg_len = np.round(
                self.visualization_settings['welch_seg_len_pct'] / 100.0 *
                sig_in_graph.shape[0]).astype(int)
            welch_overlap = np.round(
                self.visualization_settings['welch_overlap_pct'] / 100.0 *
                welch_seg_len).astype(int)
            welch_ndft = welch_seg_len
            x_in_graph, sig_in_graph = scp_signal.welch(
                sig_in_graph[:, self.curr_cha], fs=self.receiver.fs,
                nperseg=welch_seg_len, noverlap=welch_overlap,
                nfft=welch_ndft, axis=0)
            # Set data
            self.set_data(x_in_graph, sig_in_graph)
            # Update y range (only if autoscale is activated)
            self.autoscale(sig_in_graph)
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        pass


class RealTimePlotWorker(QThread):

    """Thread that receives samples in real time and sends them to the gui
    for plotting
    """
    update = pyqtSignal(np.ndarray, np.ndarray)
    error = pyqtSignal(Exception)

    def __init__(self, plot_state, receiver, preprocessor):
        super().__init__()
        self.plot_state = plot_state
        self.receiver = receiver
        self.preprocessor = preprocessor
        self.preprocessor.fit(self.receiver.fs, self.receiver.n_cha)

    def run(self):
        try:
            while self.plot_state.value == constants.PLOT_STATE_ON:
                chunk_data, chunk_times = self.receiver.get_chunk()
                chunk_data = self.preprocessor.transform(chunk_data)
                self.update.emit(chunk_times, chunk_data)
        except Exception as e:
            self.error.emit(e)


def get_plot_info(plot_uid):
    for plot in __plots_info__:
        if plot['uid'] == plot_uid:
            return plot


__plots_info__ = [
    {
        'uid': 'TimePlotMultichannel',
        'description': 'Plot to represent signals in time. If the '
                       'signal has several channels, the plot will '
                       'display each of them with different offset.',
        'class': TimePlotMultichannel
    },
    {
        'uid': 'PSDPlotMultichannel',
        'description': 'Plot to represent the power spectral density of a '
                       'signal. If the signal has several channels, the plot '
                       'will display each of them with different offset.',
        'class': PSDPlotMultichannel
    },
    {
        'uid': 'TimePlot',
        'description': 'Plot to represent a signal.',
        'class': TimePlot
    },
    {
        'uid': 'PSDPlot',
        'description': 'Plot to represent the power spectral density.',
        'class': PSDPlot
    }
]
