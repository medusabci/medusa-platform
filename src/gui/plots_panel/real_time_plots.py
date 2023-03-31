# BUILT-IN MODULES
import warnings
from abc import ABC, abstractmethod
import weakref
import traceback
import time

# EXTERNAL MODULES
import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import QFont
from scipy import signal as scp_signal
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg

# MEDUSA-PLATFORM MODULES
from acquisition import lsl_utils, real_time_preprocessing
import constants
# ToDo: remove this dependency and change it to medusa.plots.head_plots for
#  MEDUSA v2024
from gui.plots_panel import head_plots

# MEDUSA-CORE MODULES
from medusa import meeg
from medusa.local_activation import spectral_parameteres
from medusa.connectivity import amplitude_connectivity, phase_connectivity


class RealTimePlot(ABC):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__()
        # Parameters
        self.uid = uid
        self.plot_state = plot_state
        self.medusa_interface = medusa_interface
        self.theme_colors = theme_colors
        # Init variables
        self.ready = False
        self.signal_settings = None
        self.visualization_settings = None
        self.lsl_stream_info = None
        self.worker = None
        self.init_time = None
        self.widget = None
        self.fs = None

    def handle_exception(self, ex):
        self.medusa_interface.error(ex)

    def set_ready(self):
        self.ready = True

    def set_settings(self, signal_settings, plot_settings):
        """Set settings dicts"""
        self.check_settings(signal_settings, plot_settings)
        self.signal_settings = signal_settings
        self.visualization_settings = plot_settings

    def get_settings(self):
        """Create de default settings dict"""
        settings = {
            'signal_settings': self.signal_settings,
            'visualization_settings': self.visualization_settings
        }
        return settings

    def set_lsl_worker(self, lsl_stream_info):
        """Create a new lsl worker for each plot

        Parameters
        ----------
        lsl_stream_info: lsl_utils.LSLStreamWrapper
            LSL stream (medusa wrapper)
        """
        if self.check_signal(lsl_stream_info.medusa_type):
            # Save lsl info
            self.lsl_stream_info = lsl_stream_info
            # Set worker
            self.worker = RealTimePlotWorker(
                self.plot_state,
                self.lsl_stream_info,
                self.signal_settings)
            self.worker.update.connect(self.update_plot)
            self.worker.error.connect(self.handle_exception)
            self.fs = self.worker.get_effective_fs()

    def get_widget(self):
        return self.widget

    def start(self):
        self.worker.start()

    def destroy_plot(self):
        self.init_time = None
        self.clear_plot()

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


class TopographyPlot(RealTimePlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Graph variables
        self.fig = None
        self.axes = None
        self.channel_set = None
        self.win_s = None
        self.interp_p = None
        self.cmap = None
        self.show_channels = None
        self.show_clabel = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.head_handles = None
        self.plot_handles = None

        # Create widget
        fig = Figure()
        fig.add_subplot(111)
        fig.tight_layout()
        fig.patch.set_color(self.theme_colors['THEME_BG_DARK'])
        # fig.patch.set_alpha(0.0)
        self.widget = FigureCanvasQTAgg(fig)
        # Important to avoid minimum size of the figure!!
        self.widget.figure.set_size_inches(0, 0)
        self.topo_plot = None

    @staticmethod
    def check_signal(signal_type):
        if signal_type != 'EEG':
            raise ValueError('Only EEG signals are supported for the moment')
        else:
            return True

    @staticmethod
    def get_default_settings():
        signal_settings = {
            'update-rate': 0.2,
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
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            },
            'PSD': {
                'time-window': 2,
                'welch_overlap_pct': 25,
                'welch_seg_len_pct': 50,
                'power-range': [8, 13]
            }
        }
        visualization_settings = {
            'title': '<b>TopoPlot</b>',
            'channel-standard': '10-05',
            'extra_radius': 0.29,
            'interp_points': 100,
            'cmap': 'PiYG',
            'head_skin_color': '#E8BEAC',
            'plot_channel_labels': True,
            'plot_channel_points': True
        }
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, plot_settings):
        return True

    def append_data(self, chunk_times, chunk_signal):
        self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
        if len(self.time_in_graph) >= self.win_s:
            self.time_in_graph = self.time_in_graph[-self.win_s:]
        self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
        if len(self.sig_in_graph) >= self.win_s:
            self.sig_in_graph = self.sig_in_graph[-self.win_s:]
        return self.time_in_graph.copy(), self.sig_in_graph.copy()

    def init_plot(self):
        # Create widget
        self.channel_set = meeg.EEGChannelSet()
        self.channel_set.set_standard_montage(
            l_cha=self.lsl_stream_info.l_cha,
            standard=self.visualization_settings['channel-standard'])
        # Initialize
        self.topo_plot = head_plots.TopographicPlot(
            axes=self.widget.figure.axes[0],
            channel_set=self.channel_set,
            **self.visualization_settings
        )
        # Signal processing
        self.win_s = int(self.signal_settings['PSD']['time-window'] * self.fs)
        # Update view box menu
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.lsl_stream_info.n_cha])

    def update_plot(self, chunk_times, chunk_signal):
        try:
            # print('Chunk received at: %.6f' % time.time())
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            # Compute PSD
            welch_seg_len = np.round(
                self.signal_settings['PSD']['welch_seg_len_pct'] / 100.0
                * sig_in_graph.shape[0]).astype(int)
            welch_overlap = np.round(
                self.signal_settings['PSD']['welch_overlap_pct'] / 100.0
                * welch_seg_len).astype(int)
            welch_ndft = welch_seg_len
            _, psd = scp_signal.welch(
                sig_in_graph, fs=self.fs,
                nperseg=welch_seg_len, noverlap=welch_overlap,
                nfft=welch_ndft, axis=0)
            # Compute power
            power_values = spectral_parameteres.absolute_band_power(
                psd=psd[np.newaxis, :, :], fs=self.fs,
                target_band=self.signal_settings['PSD']['power-range'])
            # Plot topography
            self.topo_plot.update(values=power_values)
            self.widget.draw()
            print('Chunk plotted at: %.6f' % time.time())
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.topo_plot.clear()
        self.widget.draw()


class ConnectivityPlot(RealTimePlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Graph variables
        self.fig = None
        self.axes = None
        self.channel_set = None
        self.win_s = None
        self.interp_p = None
        self.cmap = None
        self.show_channels = None
        self.show_clabel = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.head_handles = None
        self.plot_handles = None
        self.clim = None

        # Create widget
        fig = Figure()
        fig.add_subplot(111)
        fig.tight_layout()
        fig.patch.set_color(self.theme_colors['THEME_BG_DARK'])
        # fig.patch.set_alpha(0.0)
        self.widget = FigureCanvasQTAgg(fig)
        # Important to avoid minimum size of the figure!!
        self.widget.figure.set_size_inches(0, 0)
        self.conn_plot = None

    @staticmethod
    def check_signal(signal_type):
        if signal_type != 'EEG':
            raise ValueError('Only EEG signals are supported for the moment')
        else:
            return True

    @staticmethod
    def get_default_settings():
        signal_settings = {
            'update-rate': 0.2,
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
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            },
            'connectivity': {
                'time-window': 2,
                'conn_metric': 'aec',
                'threshold': 50,
                'band-range': [8, 13]
            }
        }
        visualization_settings = {
            'title': '<b>ConnectivityPlot</b>',
            'channel-standard': '10-05',
            'cmap': 'RdBu',
            'head_skin_color': '#E8BEAC',
            'plot_channel_labels': True,
            'plot_channel_points': True
        }
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, plot_settings):
        allowed_conn_metrics = ['aec','plv','pli','wpli']
        if signal_settings['connectivity']\
            ['conn_metric'] not in allowed_conn_metrics:
            raise ValueError("Connectivity metric selected not implemented."
                             "Please, select between the following:"
                             "aec, plv, pli or plv")
        else:
            return True

    def append_data(self, chunk_times, chunk_signal):
        self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
        if len(self.time_in_graph) >= self.win_s:
            self.time_in_graph = self.time_in_graph[-self.win_s:]
        self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
        if len(self.sig_in_graph) >= self.win_s:
            self.sig_in_graph = self.sig_in_graph[-self.win_s:]
        return self.time_in_graph.copy(), self.sig_in_graph.copy()

    def init_plot(self):
        # Create widget
        self.channel_set = meeg.EEGChannelSet()
        self.channel_set.set_standard_montage(
            l_cha=self.lsl_stream_info.l_cha,
            standard=self.visualization_settings['channel-standard'])
        # Initialize
        self.conn_plot = head_plots.ConnectivityPlot(
            axes=self.widget.figure.axes[0],
            channel_set=self.channel_set,
            **self.visualization_settings
        )
        # Signal processing
        self.win_s = int(
            self.signal_settings['connectivity']['time-window'] * self.fs)
        # Update view box menu
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.lsl_stream_info.n_cha])
        if self.signal_settings['connectivity']['conn_metric'] == 'aec':
            self.clim = [-1, 1]
        else:
            self.clim = [0, 1]

    def update_plot(self, chunk_times, chunk_signal):
        try:
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            # Compute connectivity
            if self.signal_settings['connectivity']['conn_metric'] == 'aec':
                adj_mat = amplitude_connectivity.aec(sig_in_graph).squeeze()
            else:
                adj_mat = phase_connectivity.phase_connectivity(
                    sig_in_graph,
                    self.signal_settings['connectivity']['conn_metric']
                ).squeeze()

            # Apply threshold
            if self.signal_settings['connectivity']['threshold'] is not None:
                th_idx = np.abs(adj_mat) > np.percentile(
                    np.abs(adj_mat),
                    self.signal_settings['connectivity']['threshold'])
                adj_mat = adj_mat * th_idx

                # Plot connectivity
                self.conn_plot.update(adj_mat=adj_mat)
                self.widget.draw()
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.conn_plot.clear()
        self.widget.draw()


class RealTimePlotPyQtGraph(RealTimePlot, ABC):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
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
        self.theme = theme_colors
        self.background_color = theme_colors['THEME_BG_DARK']
        self.curve_color = theme_colors['THEME_SIGNAL_CURVE']
        self.offset_color = theme_colors['THEME_SIGNAL_OFFSET']
        self.marker_color = theme_colors['THEME_SIGNAL_MARKER']
        self.widget.setBackground(self.background_color)
        self.curve_width = 1
        self.offset_width = 1
        self.marker_width = 2

    def set_titles(self, title, x_axis_label, y_axis_label):
        title = self.lsl_stream_info.medusa_uid if title == 'auto' \
            else title
        if y_axis_label['units'] == 'auto':
            try:
                cha_units = [self.lsl_stream_info.cha_info[0]['units']
                             for x in self.lsl_stream_info.cha_info]
                if all(cha_units[0] == units for units in cha_units):
                    units = '(%s)' % cha_units[0]
                else:
                    units = ''
            except Exception as e:
                units = ''
            y_axis_label = '%s %s' % (y_axis_label['text'], units)
        else:
            y_axis_label = '%s (%s)' % (y_axis_label['text'],
                                        y_axis_label['units'])
        self.widget.setTitle(title)
        self.widget.setLabel('bottom', text=x_axis_label)
        self.widget.setLabel('left', text=y_axis_label)
        fn = QFont()
        fn.setBold(True)
        self.widget.getAxis("bottom").setTickFont(fn)
        self.widget.getAxis("left").setTickFont(fn)


class TimePlotMultichannel(RealTimePlotPyQtGraph):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Graph variables
        self.win_t = None
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.curves = None
        self.offsets = None
        self.marker = None
        self.pointer = None
        self.cha_separation = None
        # Custom menu
        self.plot_item_view_box = None
        self.widget.wheelEvent = self.mouse_wheel_event

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

    def mouse_wheel_event(self, event):
        if event.angleDelta().y() > 0:
            self.cha_separation /= 1.5
        else:
            self.cha_separation *= 1.5
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings():
        signal_settings = {
            'update-rate': 0.1,
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
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            },
        }
        visualization_settings = {
            'mode': 'clinical',
            'seconds_displayed': 10,
            'scaling': {
                'scale': 1,
                'apply_autoscale': True,
                'n_std_tolerance_autoscale': 1.25,
                'std_factor_separation_autoscale': 5,
            },
            'title': 'auto',
            'x_axis_label': '<b>Time</b> (s)',
            'y_axis_label': {
                'text': '<b>Signal</b>',
                'units': 'auto'
            }
        }
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        possible_modes = ['geek', 'clinical']
        if visualization_settings['mode'] not in possible_modes:
            raise ValueError('Unknown plot mode %s. Possible options: %s' %
                             (visualization_settings['mode'], possible_modes))

    @staticmethod
    def check_signal(signal_type):
        return True

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frequency.
        """
        # Set custom menu
        self.set_custom_menu()
        self.set_titles(self.visualization_settings['title'],
                        self.visualization_settings['x_axis_label'],
                        self.visualization_settings['y_axis_label'])
        # Update variables
        self.cha_separation = \
            self.visualization_settings['scaling']['scale']
        self.win_t = self.visualization_settings['seconds_displayed']
        self.win_s = int(self.win_t * self.fs)
        # Place curves in plot
        self.curves = []
        self.offsets = []
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        offset_pen = pg.mkPen(color=self.offset_color,
                              width=self.offset_width,
                              style=Qt.SolidLine)
        for i in range(self.lsl_stream_info.n_cha):
            self.offsets.append(self.widget.plot(pen=offset_pen))
            self.curves.append(self.widget.plot(pen=curve_pen))
        if self.visualization_settings['mode'] == 'clinical':
            marker_pen = pg.mkPen(color=self.marker_color,
                                  width=self.marker_width,
                                  style=Qt.SolidLine)
            self.marker = pg.InfiniteLine(pos=0, angle=90, pen=marker_pen)
            self.pointer = 0
        # Draw y axis
        self.draw_y_axis_ticks()
        # Signal plotted
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, self.lsl_stream_info.n_cha])

    def draw_y_axis_ticks(self):
        # Draw y axis ticks (channel labels)
        ticks = list()
        if self.lsl_stream_info.l_cha is not None:
            for i in range(self.lsl_stream_info.n_cha):
                offset = self.cha_separation * i
                label = self.lsl_stream_info.l_cha[-i - 1]
                ticks.append((offset, label))
        ticks = [ticks]   # Two levels for ticks
        self.y_axis.setTicks(ticks)
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.lsl_stream_info.n_cha * self.cha_separation
        if self.lsl_stream_info.n_cha > 1:
            self.plot_item.setYRange(y_min, y_max, padding=0)

    def draw_x_axis_ticks(self, x_in_graph):
        # Draw x axis ticks (time)
        n_ticks = 4
        x = np.arange(x_in_graph.shape[0])
        if self.visualization_settings['mode'] == 'geek':
            step = x_in_graph.shape[0] // n_ticks
            margin_last_tick = (3 * x_in_graph.shape[0] // 100) + 1
            x_ticks_pos = [x[i * step] for i in range(n_ticks)]
            x_ticks_pos.append(x[n_ticks * step - margin_last_tick])
            x_ticks_val = ['%.1f' % x_in_graph[i * step] for i in range(n_ticks)]
            x_ticks_val.append(
                '%.1f' % x_in_graph[n_ticks * step - margin_last_tick])
            self.x_axis.setTicks([[(x_ticks_pos[i], str(x_ticks_val[i])) for
                                   i in range(n_ticks + 1)]])
        elif self.visualization_settings['mode'] == 'clinical':
            x_tick_pos = self.pointer
            x_tick_val = '%.1f' % self.time_in_graph[self.pointer - 1]
            self.x_axis.setTicks([[(x_tick_pos, x_tick_val)]])
        self.plot_item.setXRange(x[0], x[-1], padding=0)

    def append_data(self, chunk_times, chunk_signal):
        n_samp = len(chunk_times)
        if self.visualization_settings['mode'] == 'geek':
            self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
            self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
            abs_time_in_graph = self.time_in_graph - self.time_in_graph[0]
            if abs_time_in_graph[-1] >= self.win_t:
                cut_idx = np.argmin(
                    np.abs(abs_time_in_graph -
                           (abs_time_in_graph[-1] - self.win_t)))
                self.time_in_graph = self.time_in_graph[cut_idx:]
                self.sig_in_graph = self.sig_in_graph[cut_idx:]
        elif self.visualization_settings['mode'] == 'clinical':
            if len(self.time_in_graph) < self.win_s:
                # Time window is not complete
                if len(self.time_in_graph) + n_samp < self.win_s:
                    self.time_in_graph = np.hstack(
                        (self.time_in_graph, chunk_times))
                    self.sig_in_graph = np.vstack(
                        (self.sig_in_graph, chunk_signal))
                    self.pointer += n_samp
                else:
                    n_samp_to_complete = self.win_s - self.pointer
                    self.time_in_graph = np.hstack(
                        (self.time_in_graph,
                         chunk_times[:n_samp_to_complete]))
                    self.sig_in_graph = np.vstack(
                        (self.sig_in_graph,
                         chunk_signal[:n_samp_to_complete]))
                    self.pointer = 0
                    self.append_data(chunk_times[n_samp_to_complete:],
                                     chunk_signal[n_samp_to_complete:])
            else:
                # Time window is complete
                if self.pointer + n_samp < self.win_s:
                    self.time_in_graph[self.pointer:self.pointer + n_samp] = \
                        chunk_times
                    self.sig_in_graph[self.pointer:self.pointer + n_samp] = \
                        chunk_signal
                    self.pointer += n_samp
                else:
                    n_samp_to_complete = self.win_s - self.pointer
                    self.time_in_graph[-n_samp_to_complete:] = \
                        chunk_times[:n_samp_to_complete]
                    self.sig_in_graph[-n_samp_to_complete:] = \
                        chunk_signal[:n_samp_to_complete]
                    self.pointer = 0
                    self.append_data(chunk_times[n_samp_to_complete:],
                                     chunk_signal[n_samp_to_complete:])
        return self.time_in_graph, self.sig_in_graph

    def set_data(self, x_in_graph, sig_in_graph):
        x = np.arange(x_in_graph.shape[0])
        off_y = np.ones(x_in_graph.shape)
        for i in range(self.lsl_stream_info.n_cha):
            temp = sig_in_graph[:, self.lsl_stream_info.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].setData(x=x, y=temp)
            self.offsets[i].setData(x=x, y=self.cha_separation * i * off_y)
        if self.visualization_settings['mode'] == 'clinical':
            self.marker.setPos(self.pointer)

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
        """This function updates the data in the graph. Notice that channel 0 is
        drawn up in the chart, whereas the last channel is in the bottom.
        """
        try:
            t0 = time.time()
            # Init time
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if self.visualization_settings['mode'] == 'clinical':
                    self.widget.addItem(self.marker)
            # Temporal series are always plotted from zero.
            chunk_times = chunk_times - self.init_time
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            # Set data
            self.set_data(x_in_graph, sig_in_graph)
            # Update y range (only if autoscale is activated)
            self.autoscale(sig_in_graph)
            # Update x range
            self.draw_x_axis_ticks(x_in_graph)
            # Print info
            if time.time() - t0 > self.signal_settings['update-rate']:
                warnings.warn('The plot time per chunk is higher than the '
                              'update rate. This may end freezing MEDUSA.')
                # print('[MultiChannelTimeplot] Received %i samples, pointer at %i, '
                #       'draw time %.6f' %
                #       (len(chunk_times), self.pointer,
                #        sum(self.draw_times) / len(self.draw_times)))
        except Exception as e:
            traceback.print_exc()
            self.handle_exception(e)

    def clear_plot(self):
        self.widget.clear()


class PSDPlotMultichannel(RealTimePlotPyQtGraph):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
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
        self.widget.wheelEvent = self.mouse_wheel_event

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

    def mouse_wheel_event(self, event):
        if event.angleDelta().y() > 0:
            self.cha_separation /= 1.5
        else:
            self.cha_separation *= 1.5
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings():
        signal_settings = {
            'update-rate': 0.1,
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
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            },
        }
        visualization_settings = {
            'x_range': [0.1, 30],
            'scaling': {
                'scale': 1,
                'apply_autoscale': True,
                'n_std_tolerance_autoscale': 1.25,
                'std_factor_separation_autoscale': 5
            },
            'psd_window_seconds': 5,
            'welch_overlap_pct': 25,
            'welch_seg_len_pct': 50,
            'init_channel_label': None,
            'title': 'auto',
            'x_axis_label': '<b>Frequency</b> (Hz)',
            'y_axis_label': {
                'text': '<b>Power</b>',
                'units': 'auto',
            }
        }
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        if isinstance(visualization_settings['scaling']['scale'], list):
            raise ValueError('Incorrect configuration. Parameter scaling/scale'
                             'must be a number.')

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
            self.visualization_settings['scaling']['scale']
        self.win_t = self.visualization_settings['psd_window_seconds']
        self.win_s = int(self.win_t * self.fs)
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
        for i in range(self.lsl_stream_info.n_cha):
            self.offsets.append(self.widget.plot(pen=offset_pen))
            self.curves.append(self.widget.plot(pen=curve_pen))
        # Draw y axis
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()
        # Signal plotted
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.lsl_stream_info.n_cha])

    def draw_y_axis_ticks(self):
        ticks = list()
        if self.lsl_stream_info.l_cha is not None:
            for i in range(self.lsl_stream_info.n_cha):
                offset = self.cha_separation * i
                label = self.lsl_stream_info.l_cha[-i - 1]
                ticks.append((offset, label))
        ticks = [ticks]  # Two levels for ticks
        self.y_axis.setTicks(ticks)
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.lsl_stream_info.n_cha * self.cha_separation
        if self.lsl_stream_info.n_cha > 1:
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
        for i in range(self.lsl_stream_info.n_cha):
            temp = sig_in_graph[:, self.lsl_stream_info.n_cha - i - 1]
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
                sig_in_graph, fs=self.fs,
                nperseg=welch_seg_len, noverlap=welch_overlap,
                nfft=welch_ndft, axis=0)
            # Set data
            self.set_data(x_in_graph, sig_in_graph)
            # Update y range (only if autoscale is activated)
            self.autoscale(sig_in_graph)
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.widget.clear()


class TimePlot(RealTimePlotPyQtGraph):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Graph variables
        self.win_t = None
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.pointer = None
        self.curve = None
        self.marker = None
        self.y_range = None
        # Custom menu
        self.plot_item_view_box = None
        self.widget.wheelEvent = self.mouse_wheel_event

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
            for i in range(self.plot_handler.lsl_stream_info.n_cha):
                if self.plot_handler.lsl_stream_info.l_cha[i] == cha_label:
                    self.plot_handler.select_channel(i)

        def set_channel_list(self):
            for i in range(self.plot_handler.lsl_stream_info.n_cha):
                channel_action = QAction(
                    self.plot_handler.lsl_stream_info.l_cha[i], self)
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

    def mouse_wheel_event(self, event):
        if event.angleDelta().y() > 0:
            self.y_range = [r / 1.5 for r in self.y_range]

        else:
            self.y_range = [r * 1.5 for r in self.y_range]
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings():
        signal_settings = {
            'update-rate': 0.1,
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
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            }
        }
        visualization_settings = {
            'mode': 'clinical',
            'seconds_displayed': 10,
            'scaling': {
                'scale': [-1, 1],
                'apply_autoscale': True,
                'n_std_tolerance_autoscale': 1.25,
                'std_factor_separation_autoscale': 5
            },
            'init_channel_label': None,
            'title': 'auto',
            'x_axis_label': '<b>Time</b> (s)',
            'y_axis_label': {
                'text': '<b>Signal</b>',
                'units': 'auto'
            }
        }
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        # Check mode
        possible_modes = ['geek', 'clinical']
        if visualization_settings['mode'] not in possible_modes:
            raise ValueError('Unknown plot mode %s. Possible options: %s' %
                             (visualization_settings['mode'], possible_modes))

    @staticmethod
    def check_signal(signal_type):
        return True

    def select_channel(self, cha):
        """ This function changes the channel used to compute the PSD displayed in the graph.

        :param cha: sample frecuency in Hz
        """
        self.curr_cha = cha
        self.widget.setTitle(str(self.lsl_stream_info.l_cha[cha]))

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
        self.win_s = int(self.win_t * self.fs)
        self.y_range = self.visualization_settings['scaling']['scale']
        if not isinstance(self.y_range, list):
            self.y_range = [-self.y_range, self.y_range]
        # Update view box menu
        self.plot_item_view_box.menu.set_channel_list()
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label) if init_cha_label is not None else 0
        self.select_channel(init_cha)
        # Place curves in plot
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        self.curve = self.widget.plot(pen=curve_pen)
        if self.visualization_settings['mode'] == 'clinical':
            marker_pen = pg.mkPen(color=self.marker_color,
                                  width=self.marker_width,
                                  style=Qt.SolidLine)
            self.marker = pg.InfiniteLine(pos=0, angle=90, pen=marker_pen)
            self.pointer = 0
        # Draw y axis
        self.draw_y_axis_ticks()
        # Signal plotted
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, self.lsl_stream_info.n_cha])

    def draw_y_axis_ticks(self):
        self.plot_item.setYRange(self.y_range[0],
                                 self.y_range[1],
                                 padding=0)

    def draw_x_axis_ticks(self, x_in_graph):
        """Controls the X axis visualization (e.g., ticks, range, etc)"""
        n_ticks = 4
        x = np.arange(x_in_graph.shape[0])
        if self.visualization_settings['mode'] == 'geek':
            step = x_in_graph.shape[0] // n_ticks
            margin_last_tick = (3 * x_in_graph.shape[0] // 100) + 1
            x_ticks_pos = [x[i * step] for i in range(n_ticks)]
            x_ticks_pos.append(x[n_ticks * step - margin_last_tick])
            x_ticks_val = ['%.1f' % x_in_graph[i * step] for i in
                           range(n_ticks)]
            x_ticks_val.append(
                '%.1f' % x_in_graph[n_ticks * step - margin_last_tick])
            self.x_axis.setTicks([[(x_ticks_pos[i], str(x_ticks_val[i])) for
                                   i in range(n_ticks + 1)]])
        elif self.visualization_settings['mode'] == 'clinical':
            x_tick_pos = self.pointer
            x_tick_val = '%.1f' % self.time_in_graph[self.pointer-1]
            self.x_axis.setTicks([[(x_tick_pos, x_tick_val)]])
        self.plot_item.setXRange(x[0], x[-1], padding=0)

    def append_data(self, chunk_times, chunk_signal):
        n_samp = len(chunk_times)
        if self.visualization_settings['mode'] == 'geek':
            self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
            self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
            abs_time_in_graph = self.time_in_graph - self.time_in_graph[0]
            if abs_time_in_graph[-1] >= self.win_t:
                cut_idx = np.argmin(
                    np.abs(abs_time_in_graph -
                           (abs_time_in_graph[-1] - self.win_t)))
                self.time_in_graph = self.time_in_graph[cut_idx:]
                self.sig_in_graph = self.sig_in_graph[cut_idx:]
        elif self.visualization_settings['mode'] == 'clinical':
            if len(self.time_in_graph) < self.win_s:
                # Beginning
                if len(self.time_in_graph) + n_samp < self.win_s:
                    self.time_in_graph = np.hstack(
                        (self.time_in_graph, chunk_times))
                    self.sig_in_graph = np.vstack(
                        (self.sig_in_graph, chunk_signal))
                    self.pointer += n_samp
                else:
                    n_samp_to_complete = self.win_s - self.pointer
                    self.time_in_graph = np.hstack(
                        (self.time_in_graph,
                         chunk_times[:n_samp_to_complete]))
                    self.sig_in_graph = np.vstack(
                        (self.sig_in_graph,
                         chunk_signal[:n_samp_to_complete]))
                    self.pointer = 0
                    self.append_data(chunk_times[n_samp_to_complete:],
                                     chunk_signal[n_samp_to_complete:])
            else:
                # After one window is complete
                if self.pointer + n_samp < self.win_s:
                    self.time_in_graph[self.pointer:self.pointer + n_samp] = \
                        chunk_times
                    self.sig_in_graph[self.pointer:self.pointer + n_samp] = \
                        chunk_signal
                    self.pointer += n_samp
                else:
                    n_samp_to_complete = self.win_s - self.pointer
                    self.time_in_graph[-n_samp_to_complete:] = \
                        chunk_times[:n_samp_to_complete]
                    self.sig_in_graph[-n_samp_to_complete:] = \
                        chunk_signal[:n_samp_to_complete]
                    self.pointer = 0
                    self.append_data(chunk_times[n_samp_to_complete:],
                                     chunk_signal[n_samp_to_complete:])
        return self.time_in_graph, self.sig_in_graph

    def set_data(self, x_in_graph, sig_in_graph):
        x = np.arange(x_in_graph.shape[0])
        self.curve.setData(x=x, y=sig_in_graph)
        if self.visualization_settings['mode'] == 'clinical':
            self.marker.setPos(self.pointer)

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
        try:
            t0 = time.time()
            # Reference time
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if self.visualization_settings['mode'] == 'clinical':
                    self.widget.addItem(self.marker)
            # Temporal series are always plotted from zero.
            chunk_times = np.array(chunk_times) - self.init_time
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            sig_in_graph = sig_in_graph[:, self.curr_cha]
            # Set data
            self.set_data(x_in_graph, sig_in_graph)
            # Update y range (only if autoscale is activated)
            self.autoscale(sig_in_graph)
            # Update x range
            self.draw_x_axis_ticks(x_in_graph)
            if time.time() - t0 > self.signal_settings['update-rate']:
                warnings.warn('The plot time per chunk is higher than the '
                              'update rate. This may end freezing MEDUSA.')
            # print('[Timeplot] Received %i samples, pointer at %i, draw time '
            #       '%.6f' % (len(chunk_times), self.pointer, time.time() - t0))
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.widget.clear()


class PSDPlot(RealTimePlotPyQtGraph):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
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
        self.widget.wheelEvent = self.mouse_wheel_event

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
            for i in range(self.psd_plot_handler.lsl_stream_info.n_cha):
                if self.psd_plot_handler.lsl_stream_info.l_cha[i] == cha_label:
                    self.psd_plot_handler.select_channel(i)

        def set_channel_list(self):
            for i in range(self.psd_plot_handler.lsl_stream_info.n_cha):
                channel_action = QAction(
                    self.psd_plot_handler.lsl_stream_info.l_cha[i], self)
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

    def mouse_wheel_event(self, event):
        if event.angleDelta().y() > 0:
            self.y_range = [r / 1.5 for r in self.y_range]

        else:
            self.y_range = [r * 1.5 for r in self.y_range]
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings():
        signal_settings = {
            'update-rate': 0.1,
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
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            }
        }
        visualization_settings = {
            'x_range': [0.1, 30],
            'scaling': {
                'scale': [0, 1],
                'apply_autoscale': True,
                'n_std_tolerance_autoscale': 1.25,
                'std_factor_separation_autoscale': 5,
            },
            'psd_window_seconds': 5,
            'welch_overlap_pct': 25,
            'welch_seg_len_pct': 50,
            'init_channel_label': None,
            'title': 'auto',
            'x_axis_label': '<b>Frequency</b> (Hz)',
            'y_axis_label': {
                'text': '<b>Power</b>',
                'units': 'auto'
            }
        }
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        pass

    @staticmethod
    def check_signal(signal_type):
        return True

    def select_channel(self, cha):
        """ This function changes the channel used to compute the PSD displayed in the graph.

        :param cha: sample frecuency in Hz
        """
        self.curr_cha = cha
        self.widget.setTitle(str(self.lsl_stream_info.l_cha[cha]))

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
        self.win_s = int(self.win_t * self.fs)
        self.n_samples_psd = self.win_s
        self.y_range = self.visualization_settings['scaling']['scale']
        if not isinstance(self.y_range, list):
            self.y_range = [-self.y_range, self.y_range]
        # Update view box menu
        self.plot_item_view_box.menu.set_channel_list()
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label) if init_cha_label is not None else 0
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
        self.sig_in_graph = np.zeros([1, self.lsl_stream_info.n_cha])

    def draw_y_axis_ticks(self):
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
                sig_in_graph[:, self.curr_cha], fs=self.fs,
                nperseg=welch_seg_len, noverlap=welch_overlap,
                nfft=welch_ndft, axis=0)
            # Set data
            self.set_data(x_in_graph, sig_in_graph)
            # Update y range (only if autoscale is activated)
            self.autoscale(sig_in_graph)
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.widget.clear()


class RealTimePlotWorker(QThread):

    """Thread that receives samples in real time and sends them to the gui
    for plotting
    """
    update = pyqtSignal(np.ndarray, np.ndarray)
    error = pyqtSignal(Exception)

    def __init__(self, plot_state, lsl_stream_info, signal_settings):
        super().__init__()
        self.plot_state = plot_state
        self.lsl_stream_info = lsl_stream_info
        self.signal_settings = signal_settings
        self.fs = self.lsl_stream_info.fs
        # Get minimum and maximum chunk sizes
        min_chunk_size = self.signal_settings['update-rate'] * self.fs
        min_chunk_size = max(int(min_chunk_size), 1)
        max_chunk_size = 10 * min_chunk_size
        timeout = max(int(max_chunk_size / lsl_stream_info.fs), 1)
        # Set receiver
        self.receiver = lsl_utils.LSLStreamReceiver(
            self.lsl_stream_info,
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size,
            timeout=timeout
        )
        # Set real time preprocessor
        self.preprocessor = real_time_preprocessing.PlotsRealTimePreprocessor(
            self.signal_settings)
        self.preprocessor.fit(self.receiver.fs, self.receiver.n_cha,
                              self.receiver.min_chunk_size)
        self.wait = False

    def get_effective_fs(self):
        if self.signal_settings['downsampling']['apply']:
            fs = self.fs // self.signal_settings['downsampling']['factor']
        else:
            fs = self.fs
        return fs

    def run(self):
        try:
            self.receiver.flush_stream()
            while self.plot_state.value == constants.PLOT_STATE_ON:
                # Get chunks
                chunk_data, chunk_times = self.receiver.get_chunk()
                chunk_times, chunk_data = self.preprocessor.transform(
                    chunk_times, chunk_data)
                # Check if the plot is ready to receive data (sometimes get
                # chunk takes a while and the user presses the button in
                # between)
                if self.plot_state.value == constants.PLOT_STATE_ON:
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
    },
    {
        'uid': 'TopographyPlot',
        'description': 'Real time topography plot for M/EEG signals.',
        'class': TopographyPlot
    },
    {
        'uid': 'ConnectivityPlot',
        'description': 'Real time connectivity plot for M/EEG signals.',
        'class': ConnectivityPlot
    },
]
