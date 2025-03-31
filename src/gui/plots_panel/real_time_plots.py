# BUILT-IN MODULES
import warnings
from abc import ABC, abstractmethod
import weakref
import traceback
import time
import math

# EXTERNAL MODULES
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import QFont, QAction
from scipy import signal as scp_signal
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

# MEDUSA-PLATFORM MODULES
from acquisition import lsl_utils
import constants, exceptions

# MEDUSA-CORE MODULES
import medusa
from medusa import meeg
from medusa.local_activation import spectral_parameteres
from medusa.connectivity import amplitude_connectivity, phase_connectivity
from medusa.plots import head_plots


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
        self.active = False

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
                self.signal_settings,
                self.medusa_interface)
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
        self.init_plot()

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
        self.channel_set = None
        self.sel_channels = None
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
            'update_rate': 0.2,
            'frequency_filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff_freq': [1],
                'order': 5
            },
            'notch_filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            },
            're_referencing': {
                'apply': False,
                'type': 'car',
                'channel': ''
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            },
            'psd': {
                'time_window': 5,
                'welch_overlap_pct': 25,
                'welch_seg_len_pct': 50,
                'power_range': [8, 13]
            }
        }
        visualization_settings = {
            'title': '<b>TopoPlot</b>',
            'channel_standard': '10-05',
            'head_radius': 1.0,
            'head_line_width': 4.0,
            'head_skin_color': "#E8BEAC",
            'plot_channel_labels': False,
            'plot_channel_points': True,
            'channel_radius_size': None,
            'interpolate': True,
            'extra_radius': 0, 'interp_neighbors': 3,
            'interp_points': 100,
            'interp_contour_width': 0.8,
            'cmap': "YlGnBu_r",
            'clim': None,
            'label_color': 'w'
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
        # Create channel set
        self.channel_set, self.sel_channels = (
            lsl_utils.lsl_channel_info_to_eeg_channel_set(
            self.lsl_stream_info.cha_info,
            discard_unlocated_channels=True))
        # Initialize
        self.topo_plot = head_plots.TopographicPlot(
            axes=self.widget.figure.axes[0],
            channel_set=self.channel_set,
            head_radius=self.visualization_settings['head_radius'],
            head_line_width=self.visualization_settings['head_line_width'],
            head_skin_color=self.visualization_settings['head_skin_color'],
            plot_channel_labels=self.visualization_settings['plot_channel_labels'],
            plot_channel_points=self.visualization_settings['plot_channel_points'],
            channel_radius_size=self.visualization_settings['channel_radius_size'],
            interpolate=self.visualization_settings['interpolate'],
            extra_radius=self.visualization_settings['extra_radius'],
            interp_neighbors=self.visualization_settings['interp_neighbors'],
            interp_points=self.visualization_settings['interp_points'],
            interp_contour_width=self.visualization_settings['interp_contour_width'],
            cmap=self.visualization_settings['cmap'],
            clim=self.visualization_settings['clim'],
            label_color=self.visualization_settings['label_color'])
        # Signal processing
        self.win_s = int(self.signal_settings['psd']['time_window'] * self.fs)
        # Update view box menu
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, len(self.sel_channels)])

    def update_plot(self, chunk_times, chunk_signal):
        try:
            # print('Chunk received at: %.6f' % time.time())
            # Append new data and get safe copy
            chunk_signal = chunk_signal[:, self.sel_channels]
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            # Compute PSD
            welch_seg_len = np.round(
                self.signal_settings['psd']['welch_seg_len_pct'] / 100.0
                * sig_in_graph.shape[0]).astype(int)
            welch_overlap = np.round(
                self.signal_settings['psd']['welch_overlap_pct'] / 100.0
                * welch_seg_len).astype(int)
            welch_ndft = welch_seg_len
            _, psd = scp_signal.welch(
                sig_in_graph, fs=self.fs,
                nperseg=welch_seg_len, noverlap=welch_overlap,
                nfft=welch_ndft, axis=0)
            # Compute power
            power_values = spectral_parameteres.band_power(
                psd=psd[np.newaxis, :, :], fs=self.fs,
                target_band=self.signal_settings['psd']['power_range'])
            # Update plot checking for dims to avoid errors when plot is not
            # being displayed
            self.topo_plot.update(values=power_values)
            width, height = self.widget.get_width_height()
            if width > 0 and height > 0:
                self.widget.draw()
            # print('Chunk plotted at: %.6f' % time.time())
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.topo_plot.clear()
        # Check dims to avoid errors when plot is not being displayed
        width, height = self.widget.get_width_height()
        if width > 0 and height > 0:
            # Update plot
            self.widget.draw()


class ConnectivityPlot(RealTimePlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Graph variables
        self.channel_set = None
        self.sel_channels = None
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
            'update_rate': 0.2,
            'frequency_filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff_freq': [1],
                'order': 5
            },
            'notch_filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            },
            're_referencing': {
                'apply': False,
                'type': 'car',
                'channel': ''
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            },
            'connectivity': {
                'time_window': 2,
                'conn_metric': 'aec',
                'threshold': 50,
                'band_range': [8, 13]
            }
        }
        visualization_settings = {
            'title': '<b>ConnectivityPlot</b>',
            'channel_standard': '10-05',
            'head_radius': 1.0,
            'head_line_width': 4.0,
            'head_skin_color': "#E8BEAC",
            'plot_channel_labels': False,
            'plot_channel_points': True,
            'channel_radius_size': 0,
            'percentile_th': 85,
            'cmap': "RdBu",
            'clim': None,
            'label_color': 'w'
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
        # Create channel set
        self.channel_set, self.sel_channels = (
            lsl_utils.lsl_channel_info_to_eeg_channel_set(
                self.lsl_stream_info.cha_info,
                discard_unlocated_channels=True))
        # Initialize
        self.conn_plot = head_plots.ConnectivityPlot(
            axes=self.widget.figure.axes[0],
            channel_set=self.channel_set,
            head_radius=self.visualization_settings['head_radius'],
            head_line_width=self.visualization_settings['head_line_width'],
            head_skin_color=self.visualization_settings['head_skin_color'],
            plot_channel_labels=self.visualization_settings['plot_channel_labels'],
            plot_channel_points=self.visualization_settings['plot_channel_points'],
            channel_radius_size=self.visualization_settings['channel_radius_size'],
            percentile_th=self.visualization_settings['percentile_th'],
            cmap=self.visualization_settings['cmap'],
            clim=self.visualization_settings['clim'],
            label_color=self.visualization_settings['label_color'],
        )
        # Signal processing
        self.win_s = int(
            self.signal_settings['connectivity']['time_window'] * self.fs)
        # Update view box menu
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, len(self.sel_channels)])
        if self.signal_settings['connectivity']['conn_metric'] == 'aec':
            self.clim = [-1, 1]
        else:
            self.clim = [0, 1]

    def update_plot(self, chunk_times, chunk_signal):
        try:
            # Append new data and get safe copy
            chunk_signal = chunk_signal[:, self.sel_channels]
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
            # Update plot checking for dims to avoid errors when plot is not
            # being displayed
            self.conn_plot.update(adj_mat=adj_mat)
            width, height = self.widget.get_width_height()
            if width > 0 and height > 0:
                self.widget.draw()
            # print('Chunk plotted at: %.6f' % time.time())
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.conn_plot.clear()
        # Check dims to avoid errors when plot is not being displayed
        width, height = self.widget.get_width_height()
        if width > 0 and height > 0:
            # Update plot
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
        self.grid_color = theme_colors['THEME_SIGNAL_GRID']
        self.marker_color = theme_colors['THEME_SIGNAL_MARKER']
        self.widget.setBackground(self.background_color)
        self.curve_width = 1
        self.grid_width = 1
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

    @staticmethod
    def parse_cha_idx(s):
        # Remove brackets and spaces
        s = s.strip('[] ')
        # Split by commas
        parts = s.split(',')
        result = []
        for part in parts:
            part = part.strip()
            # Check for ranges (e.g., "1:3")
            if ':' in part:
                start, end = map(int, part.split(':'))
                result.extend(range(start, end + 1))
            else:
                # Otherwise, it's a single number
                result.append(int(part))
        return result


class TimePlotMultichannel(RealTimePlotPyQtGraph):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Channels idx
        self.cha_idx = None
        self.n_cha = None
        self.l_cha = None
        # Graph variables
        self.win_t = None
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.curves = None
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
            'update_rate': 0.1,
            'frequency_filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff_freq': [1],
                'order': 5
            },
            'notch_filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            },
            're_referencing': {
                'apply': False,
                'type': 'car',
                'channel': ''
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            },
        }
        visualization_settings = {
            'mode': 'clinical',
            'cha_idx': 'all',
            'x_axis': {
                'seconds_displayed': 10,
                'display_grid': True,
                'line_separation': 1,
                'label': '<b>Time</b> (s)'
            },
            'y_axis': {
                'cha_separation': 1,
                'display_grid': True,
                'autoscale': {
                    'apply': False,
                    'n_std_tolerance': 1.25,
                    'n_std_separation': 5,
                },
                'label': {
                    'text': '<b>Signal</b>',
                    'units': 'auto'
                }
            },
            'title': 'auto',
        }
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        # Visualization modes
        possible_modes = ['geek', 'clinical']
        if visualization_settings['mode'] not in possible_modes:
            raise ValueError('Unknown plot mode %s. Possible options: %s' %
                             (visualization_settings['mode'], possible_modes))
        # Channels idx
        if not isinstance(visualization_settings['cha_idx'], str):
            raise ValueError('Parameter cha_idx must be a string')
        if visualization_settings['cha_idx'] != 'all':
            try:
                RealTimePlotPyQtGraph.parse_cha_idx(
                    visualization_settings['cha_idx'])
            except Exception as e:
                raise ValueError(
                    'Parameter cha_idx must be either "all" or a list '
                    'of the channels index that should be displayed '
                    'using this format: "[1:3, 19, 21, 22:24]"')

    @staticmethod
    def check_signal(signal_type):
        return True

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frequency.
        """
        # Set custom menu
        self.set_custom_menu()
        # Get channels
        if self.visualization_settings['cha_idx'] == 'all':
            self.cha_idx = np.arange(self.lsl_stream_info.n_cha).astype(int)
            self.n_cha = len(self.cha_idx)
            self.l_cha = [self.lsl_stream_info.l_cha[i] for i in self.cha_idx]
        else:
            self.cha_idx = self.parse_cha_idx(
                self.visualization_settings['cha_idx'])
            self.n_cha = len(self.cha_idx)
            self.l_cha = [self.lsl_stream_info.l_cha[i] for i in self.cha_idx]
        # Update variables
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, len(self.cha_idx)])
        self.cha_separation = \
            self.visualization_settings['y_axis']['cha_separation']
        self.win_t = self.visualization_settings['x_axis']['seconds_displayed']
        self.win_s = int(self.win_t * self.fs)
        # Set titles
        self.set_titles(self.visualization_settings['title'],
                        self.visualization_settings['x_axis']['label'],
                        self.visualization_settings['y_axis']['label'])
        # Pens
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        grid_pen = pg.mkPen(color=self.grid_color,
                            width=self.grid_width,
                            style=Qt.SolidLine)
        # Place curves in plot
        self.curves = []
        for i in range(self.n_cha):
            self.curves.append(self.widget.plot(pen=curve_pen))
        # Place marker for clinical mode
        if self.visualization_settings['mode'] == 'clinical':
            marker_pen = pg.mkPen(color=self.marker_color,
                                  width=self.marker_width,
                                  style=Qt.SolidLine)
            self.marker = pg.InfiniteLine(pos=0, angle=90, pen=marker_pen)
            self.pointer = -1
        # X-axis
        if self.visualization_settings['x_axis']['display_grid']:
            alpha = self.visualization_settings['x_axis']['display_grid']
            alpha = 255 if isinstance(alpha, bool) else alpha
            self.x_axis.setPen(grid_pen)
            self.x_axis.setGrid(alpha)
        # Y-axis
        if self.visualization_settings['y_axis']['display_grid']:
            alpha = self.visualization_settings['y_axis']['display_grid']
            alpha = 255 if isinstance(alpha, bool) else alpha
            self.y_axis.setPen(grid_pen)
            self.y_axis.setGrid(alpha)
        # Draw
        self.set_data()
        self.draw_x_axis_ticks()
        self.draw_y_axis_ticks()

    def draw_y_axis_ticks(self):
        # Draw y axis ticks (channel labels)
        ticks = list()
        if self.l_cha is not None:
            for i in range(self.n_cha):
                offset = self.cha_separation * i
                label = self.l_cha[-i - 1]
                ticks.append((offset, label))
        ticks = [ticks]   # Two levels for ticks
        self.y_axis.setTicks(ticks)
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.n_cha * self.cha_separation
        if self.n_cha > 1:
            self.plot_item.setYRange(y_min, y_max, padding=0)

    def draw_x_axis_ticks(self):
        if len(self.time_in_graph) > 0:
            if self.visualization_settings['mode'] == 'geek':
                # Set timestamps
                x = self.time_in_graph
                # Range
                x_range = (x[0], x[-1])
                # Time ticks
                x_ticks_pos = []
                x_ticks_val = []
                if self.visualization_settings['x_axis']['display_grid']:
                    step = self.visualization_settings[
                        'x_axis']['line_separation']
                    x_ticks_pos = np.arange(x[0], x[-1], step=step).tolist()
                    x_ticks_val = ['%.1f' % v for v in x_ticks_pos]
                # Set ticks
                self.x_axis.setTicks([list(zip(x_ticks_pos, x_ticks_val))])
            elif self.visualization_settings['mode'] == 'clinical':
                # Set timestamps
                x = np.mod(self.time_in_graph, self.win_t)
                # Range
                n_win = self.time_in_graph.max() // self.win_t
                x_range = (0, self.win_t) if n_win==0 else (x[0], x[-1])
                # Time ticks
                x_ticks_pos = []
                x_ticks_val = []
                if self.visualization_settings['x_axis']['display_grid']:
                    step = self.visualization_settings[
                        'x_axis']['line_separation']
                    x_ticks_pos = np.arange(x[0], x[-1], step=step).tolist()
                    x_ticks_val = ['' for v in x_ticks_pos]
                # Pointer
                x_ticks_pos.append(x[self.pointer])
                x_ticks_val.append('%.1f' % self.time_in_graph[self.pointer])
                self.x_axis.setTicks([list(zip(x_ticks_pos, x_ticks_val))])
            else:
                raise ValueError
            # Set range
            self.plot_item.setXRange(x_range[0], x_range[1], padding=0)
        else:
            self.x_axis.setTicks([])
            self.plot_item.setXRange(0, 0, padding=0)

    def append_data(self, chunk_times, chunk_signal):
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
            # Useful params
            max_t = self.time_in_graph.max(initial=0)
            n_win = max_t // self.win_t
            max_win_t = (n_win+1) * self.win_t
            # Check overflow
            if chunk_times[-1] > max_win_t:
                idx_overflow = chunk_times > max_win_t
                # Append part of the chunk at the end
                time_in_graph = np.insert(
                    self.time_in_graph,
                    self.pointer+1,
                    chunk_times[np.logical_not(idx_overflow)], axis=0)
                sig_in_graph = np.insert(
                    self.sig_in_graph,
                    self.pointer+1,
                    chunk_signal[np.logical_not(idx_overflow)], axis=0)
                # Append part of the chunk at the beginning
                time_in_graph = np.insert(
                    time_in_graph, 0,
                    chunk_times[idx_overflow], axis=0)
                sig_in_graph = np.insert(
                    sig_in_graph, 0,
                    chunk_signal[idx_overflow], axis=0)
                self.pointer = len(chunk_times[idx_overflow]) - 1
            else:
                # Append chunk at pointer
                time_in_graph = np.insert(self.time_in_graph,
                                          self.pointer+1,
                                          chunk_times, axis=0)
                sig_in_graph = np.insert(self.sig_in_graph,
                                         self.pointer+1,
                                         chunk_signal, axis=0)
                self.pointer += len(chunk_times)
            # Check old samples
            max_t = time_in_graph[self.pointer]
            idx_old = time_in_graph < (max_t - self.win_t)
            if np.any(idx_old):
                time_in_graph = np.delete(time_in_graph, idx_old, axis=0)
                sig_in_graph = np.delete(sig_in_graph, idx_old, axis=0)
            # Update
            self.time_in_graph = time_in_graph
            self.sig_in_graph = sig_in_graph
            # ============================DEBUG=============================== #
            # if np.sum(np.diff(time_in_graph) < 0) > 1:
            #     warnings.warn(
            #         'Unordered data!!'
            #         f'\nPointer position: {self.pointer}'
            #         f'\nTime at pointer: {max_t}'
            #         f'\nMax time: {np.max(time_in_graph)}'
            #         f'\nOld positions (time < '
            #         f'{(max_t - self.win_t)}): '
            #         f'{np.where(time_in_graph < (max_t - self.win_t))}')
            # print(f'Pointer no correction: {pointer_no_corr}')
            # print(f'Pointer with correction: {self.pointer}')
            # print(idx_old)
            # print(time_in_graph)
            # ================================================================ #
        return self.time_in_graph, self.sig_in_graph

    def set_data(self):
        # Calculate x axis
        if self.visualization_settings['mode'] == 'geek':
            x = self.time_in_graph
        elif self.visualization_settings['mode'] == 'clinical':
            max_t = self.time_in_graph.max(initial=0)
            x = np.mod(self.time_in_graph, self.win_t)
            # Marker
            if max_t >= self.win_t:
                self.marker.setPos(x[self.pointer])
        else:
            raise ValueError
        # Set data
        for i in range(self.n_cha):
            temp = self.sig_in_graph[:, self.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].setData(x=x, y=temp)

    def autoscale(self):
        scaling_sett = self.visualization_settings['y_axis']['autoscale']
        if scaling_sett['apply']:
            y_std = np.std(self.sig_in_graph)
            std_tol = scaling_sett['n_std_tolerance']
            std_factor = scaling_sett['n_std_separation']
            if y_std > self.cha_separation * std_tol or \
                    y_std < self.cha_separation / std_tol:
                self.cha_separation = std_factor * y_std
                self.draw_y_axis_ticks()

    def update_plot(self, chunk_times, chunk_signal):
        """This function updates the data in the graph. Notice that channel 0 is
        drawn up in the chart, whereas the last channel is in the bottom.
        """
        try:
            # t0 = time.time()
            # Init time
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if self.visualization_settings['mode'] == 'clinical':
                    self.widget.addItem(self.marker)
            # Temporal series are always plotted from zero.
            chunk_times = chunk_times - self.init_time
            # Append new data and get safe copy
            self.append_data(chunk_times, chunk_signal[:, self.cha_idx])
            # Set data
            self.set_data()
            # Update y range (only if autoscale is activated)
            self.autoscale()
            # Update x range
            self.draw_x_axis_ticks()
            # Print info
            # if time.time() - t0 > self.signal_settings['update_rate']:
            #     self.medusa_interface.log(
            #         '[Plot %i] The plot time per chunk is higher than the '
            #         'update rate. This may end up freezing MEDUSA.' %
            #         self.uid,
            #         style='warning', mode='replace')
            # print('Chunk plotted at: %.6f' % time.time())
        except Exception as e:
            traceback.print_exc()
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
            'update_rate': 0.1,
            'frequency_filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff_freq': [1],
                'order': 5
            },
            'notch_filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            },
            're_referencing': {
                'apply': False,
                'type': 'car',
                'channel': ''
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            }
        }
        visualization_settings = {
            'mode': 'clinical',
            'init_channel_label': None,
            'x_axis': {
                'seconds_displayed': 10,
                'display_grid': True,
                'line_separation': 1,
                'label': '<b>Time</b> (s)'
            },
            'y_axis': {
                'range': [-1, 1],
                'autoscale': {
                    'apply': False,
                    'n_std_tolerance': 1.25,
                    'n_std_separation': 5,
                },
                'label': {
                    'text': '<b>Signal</b>',
                    'units': 'auto'
                }
            },
            'title': 'auto',
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
        self.plot_item_view_box.menu.set_channel_list()
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label) if init_cha_label is not None else 0
        self.select_channel(init_cha)
        # Update variables
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, self.lsl_stream_info.n_cha])
        self.win_t = self.visualization_settings['x_axis']['seconds_displayed']
        self.win_s = int(self.win_t * self.fs)
        self.y_range = self.visualization_settings['y_axis']['range']
        if not isinstance(self.y_range, list):
            self.y_range = [-self.y_range, self.y_range]
        # Set titles
        self.set_titles(self.visualization_settings['title'],
                        self.visualization_settings['x_axis']['label'],
                        self.visualization_settings['y_axis']['label'])
        # Place curves in plot
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        grid_pen = pg.mkPen(color=self.grid_color,
                            width=self.grid_width,
                            style=Qt.SolidLine)
        # Curve
        self.curve = self.widget.plot(pen=curve_pen)
        if self.visualization_settings['mode'] == 'clinical':
            marker_pen = pg.mkPen(color=self.marker_color,
                                  width=self.marker_width,
                                  style=Qt.SolidLine)
            self.marker = pg.InfiniteLine(pos=0, angle=90, pen=marker_pen)
            self.pointer = -1
        # X-axis
        if self.visualization_settings['x_axis']['display_grid']:
            alpha = self.visualization_settings['x_axis']['display_grid']
            alpha = 255 if isinstance(alpha, bool) else alpha
            self.x_axis.setPen(grid_pen)
            self.x_axis.setGrid(alpha)
        # Draw
        self.set_data()
        self.draw_x_axis_ticks()
        self.draw_y_axis_ticks()

    def draw_y_axis_ticks(self):
        self.plot_item.setYRange(self.y_range[0],
                                 self.y_range[1],
                                 padding=0)

    def draw_x_axis_ticks(self):
        if len(self.time_in_graph) > 0:
            if self.visualization_settings['mode'] == 'geek':
                # Set timestamps
                x = self.time_in_graph
                # Range
                x_range = (x[0], x[-1])
                # Time ticks
                x_ticks_pos = []
                x_ticks_val = []
                if self.visualization_settings['x_axis']['display_grid']:
                    step = self.visualization_settings[
                        'x_axis']['line_separation']
                    x_ticks_pos = np.arange(x[0], x[-1], step=step).tolist()
                    x_ticks_val = ['%.1f' % v for v in x_ticks_pos]
                # Set ticks
                self.x_axis.setTicks([list(zip(x_ticks_pos, x_ticks_val))])
            elif self.visualization_settings['mode'] == 'clinical':
                # Set timestamps
                x = np.mod(self.time_in_graph, self.win_t)
                # Range
                n_win = self.time_in_graph.max() // self.win_t
                x_range = (0, self.win_t) if n_win == 0 else (x[0], x[-1])
                # Time ticks
                x_ticks_pos = []
                x_ticks_val = []
                if self.visualization_settings['x_axis']['display_grid']:
                    step = self.visualization_settings[
                        'x_axis']['line_separation']
                    x_ticks_pos = np.arange(x[0], x[-1], step=step).tolist()
                    x_ticks_val = ['' for v in x_ticks_pos]
                # Pointer
                x_ticks_pos.append(x[self.pointer])
                x_ticks_val.append('%.1f' % self.time_in_graph[self.pointer])
                self.x_axis.setTicks([list(zip(x_ticks_pos, x_ticks_val))])
            else:
                raise ValueError
                # Set range
                self.plot_item.setXRange(x_range[0], x_range[1], padding=0)
        else:
            self.x_axis.setTicks([])
            self.plot_item.setXRange(0, 0, padding=0)

    def append_data(self, chunk_times, chunk_signal):
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
            # Useful params
            max_t = self.time_in_graph.max(initial=0)
            n_win = max_t // self.win_t
            max_win_t = (n_win+1) * self.win_t
            # Check overflow
            if chunk_times[-1] > max_win_t:
                idx_overflow = chunk_times >= max_win_t
                # Append part of the chunk at the end
                time_in_graph = np.insert(
                    self.time_in_graph,
                    self.pointer+1,
                    chunk_times[np.logical_not(idx_overflow)], axis=0)
                sig_in_graph = np.insert(
                    self.sig_in_graph,
                    self.pointer+1,
                    chunk_signal[np.logical_not(idx_overflow)], axis=0)
                # Append part of the chunk at the beginning
                time_in_graph = np.insert(
                    time_in_graph, 0,
                    chunk_times[idx_overflow], axis=0)
                sig_in_graph = np.insert(
                    sig_in_graph, 0,
                    chunk_signal[idx_overflow], axis=0)
                self.pointer = len(chunk_times[idx_overflow]) - 1
            else:
                # Append chunk at pointer
                time_in_graph = np.insert(self.time_in_graph,
                                          self.pointer+1,
                                          chunk_times, axis=0)
                sig_in_graph = np.insert(self.sig_in_graph,
                                         self.pointer+1,
                                         chunk_signal, axis=0)
                self.pointer += len(chunk_times)
            # Check old samples
            max_t = time_in_graph[self.pointer]
            idx_old = time_in_graph < (max_t - self.win_t)
            if np.any(idx_old):
                time_in_graph = np.delete(time_in_graph, idx_old, axis=0)
                sig_in_graph = np.delete(sig_in_graph, idx_old, axis=0)
            # Update
            self.time_in_graph = time_in_graph
            self.sig_in_graph = sig_in_graph
        return self.time_in_graph, self.sig_in_graph

    def set_data(self):
        # Calculate x axis
        if self.visualization_settings['mode'] == 'geek':
            x = self.time_in_graph
        elif self.visualization_settings['mode'] == 'clinical':
            max_t = self.time_in_graph.max(initial=0)
            n_win = max_t // self.win_t
            x = self.time_in_graph if n_win <= 0 else \
                np.mod(self.time_in_graph, self.win_t)
            # Marker
            if max_t >= self.win_t:
                self.marker.setPos(x[self.pointer])
        else:
            raise ValueError
        # Set data
        self.curve.setData(x=x, y=self.sig_in_graph[:, self.curr_cha])

    def autoscale(self):
        scaling_sett = self.visualization_settings['y_axis']['autoscale']
        if scaling_sett['apply']:
            y_std = np.std(self.sig_in_graph)
            std_tol = scaling_sett['n_std_tolerance']
            std_factor = scaling_sett['n_std_separation']
            if y_std > self.y_range[1] * std_tol or \
                    y_std < self.y_range[1] / std_tol:
                self.y_range[0] = - std_factor * y_std
                self.y_range[1] = std_factor * y_std
                self.draw_y_axis_ticks()

    def update_plot(self, chunk_times, chunk_signal):
        try:
            # t0 = time.time()
            # Reference time
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if self.visualization_settings['mode'] == 'clinical':
                    self.widget.addItem(self.marker)
            # Temporal series are always plotted from zero.
            chunk_times = np.array(chunk_times) - self.init_time
            # Append new data and get safe copy
            self.append_data(chunk_times, chunk_signal)
            # Set data
            self.set_data()
            # Update y range (only if autoscale is activated)
            self.autoscale()
            # Update x range
            self.draw_x_axis_ticks()
            # if time.time() - t0 > self.signal_settings['update_rate']:
            #     self.medusa_interface.log(
            #         '[Plot %i] The plot time per chunk is higher than the '
            #         'update rate. This may end up freezing MEDUSA.' %
            #         self.uid,
            #         style='warning', mode='replace')
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.widget.clear()


class PSDPlotMultichannel(RealTimePlotPyQtGraph):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Channels idx
        self.cha_idx = None
        self.n_cha = None
        self.l_cha = None
        # Graph variables
        self.win_t = None
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.curves = None
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
            'update_rate': 0.1,
            'frequency_filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff_freq': [1],
                'order': 5
            },
            'notch_filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            },
            're_referencing': {
                'apply': False,
                'type': 'car',
                'channel': ''
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            },
        }
        visualization_settings = {
            'cha_idx': 'all',
            'x_axis': {
                'range': [0.1, 30],
                'display_grid': False,
                'line_separation': 1,
                'label': '<b>Frequency</b> (Hz)'
            },
            'y_axis': {
                'cha_separation': 1,
                'display_grid': True,
                'autoscale': {
                    'apply': True,
                    'n_std_tolerance': 1.25,
                    'n_std_separation': 5,
                },
                'label': {
                    'text': '<b>Power</b>',
                    'units': 'auto'
                }
            },
            'psd': {
                'time_window_seconds': 5,
                'welch_overlap_pct': 25,
                'welch_seg_len_pct': 50,
            },
            'title': 'auto',
        }
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        # Channel separation
        if isinstance(visualization_settings['y_axis']['cha_separation'], list):
            raise ValueError('Incorrect configuration. The channel separation'
                             'must be a number.')
        # Channels idx
        if not isinstance(visualization_settings['cha_idx'], str):
            raise ValueError('Parameter cha_idx must be a string')
        if visualization_settings['cha_idx'] != 'all':
            try:
                RealTimePlotPyQtGraph.parse_cha_idx(
                    visualization_settings['cha_idx'])
            except Exception as e:
                raise ValueError(
                    'Parameter cha_idx must be either "all" or a list '
                    'of the channels index that should be displayed '
                    'using this format: "[1:3, 19, 21, 22:24]"')

    @staticmethod
    def check_signal(signal_type):
        return True

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frecuency.
        """
        # Set custom menu
        self.set_custom_menu()
        # Get channels
        if self.visualization_settings['cha_idx'] == 'all':
            self.cha_idx = np.arange(self.lsl_stream_info.n_cha).astype(int)
            self.n_cha = len(self.cha_idx)
            self.l_cha = [self.lsl_stream_info.l_cha[i] for i in self.cha_idx]
        else:
            self.cha_idx = self.parse_cha_idx(
                self.visualization_settings['cha_idx'])
            self.n_cha = len(self.cha_idx)
            self.l_cha = [self.lsl_stream_info.l_cha[i] for i in self.cha_idx]
        # Update variables
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, self.n_cha])
        self.cha_separation = \
            self.visualization_settings['y_axis']['cha_separation']
        self.win_t = self.visualization_settings['psd']['time_window_seconds']
        self.win_s = int(self.win_t * self.fs)
        self.n_samples_psd = self.win_s
        # Set titles
        self.set_titles(self.visualization_settings['title'],
                        self.visualization_settings['x_axis']['label'],
                        self.visualization_settings['y_axis']['label'])
        # Place curves in plot
        self.curves = []
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        grid_pen = pg.mkPen(color=self.grid_color,
                            width=self.grid_width,
                            style=Qt.SolidLine)
        # Curve
        for i in range(self.n_cha):
            self.curves.append(self.widget.plot(pen=curve_pen))
        # X-axis
        if self.visualization_settings['x_axis']['display_grid']:
            alpha = self.visualization_settings['x_axis']['display_grid']
            alpha = 255 if isinstance(alpha, bool) else alpha
            self.x_axis.setPen(grid_pen)
            self.x_axis.setGrid(alpha)
        # Y-axis
        if self.visualization_settings['y_axis']['display_grid']:
            alpha = self.visualization_settings['y_axis']['display_grid']
            alpha = 255 if isinstance(alpha, bool) else alpha
            self.y_axis.setPen(grid_pen)
            self.y_axis.setGrid(alpha)
        # Draw y axis
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()

    def draw_y_axis_ticks(self):
        ticks = list()
        if self.lsl_stream_info.l_cha is not None:
            for i in range(self.n_cha):
                offset = self.cha_separation * i
                label = self.l_cha[-i - 1]
                ticks.append((offset, label))
        ticks = [ticks]  # Two levels for ticks
        self.y_axis.setTicks(ticks)
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.n_cha * self.cha_separation
        if self.n_cha > 1:
            self.plot_item.setYRange(y_min, y_max, padding=0)

    def draw_x_axis_ticks(self):
        self.plot_item.setXRange(
            self.visualization_settings['x_axis']['range'][0],
            self.visualization_settings['x_axis']['range'][1],
            padding=0)

    def append_data(self, chunk_times, chunk_signal):
        self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
        if len(self.time_in_graph) >= self.win_s:
            self.time_in_graph = self.time_in_graph[-self.win_s:]
        self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
        if len(self.sig_in_graph) >= self.win_s:
            self.sig_in_graph = self.sig_in_graph[-self.win_s:]

        return self.time_in_graph.copy(), self.sig_in_graph.copy()

    def set_data(self, x_in_graph, y_in_graph):
        x = np.arange(x_in_graph.shape[0])
        for i in range(self.n_cha):
            temp = y_in_graph[:, self.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].setData(x=x, y=temp)

    def autoscale(self, y_in_graph):
        scaling_sett = self.visualization_settings['y_axis']['autoscale']
        if scaling_sett['apply']:
            y_std = np.std(y_in_graph)
            std_tol = scaling_sett['n_std_tolerance']
            std_factor = scaling_sett['n_std_separation']
            if y_std > self.cha_separation * std_tol or \
                    y_std < self.cha_separation / std_tol:
                self.cha_separation = std_factor * y_std
                self.draw_y_axis_ticks()

    def update_plot(self, chunk_times, chunk_signal):
        """
        This function updates the data in the graph. Notice that channel 0 is
        drawn up in the chart, whereas the last channel is in the bottom.
        """
        try:
            # Append new data and get safe copy
            self.append_data(chunk_times, chunk_signal[:, self.cha_idx])
            # Compute PSD
            welch_seg_len = np.round(
                self.visualization_settings['psd']['welch_seg_len_pct'] /
                100.0 * self.sig_in_graph.shape[0]).astype(int)
            welch_overlap = np.round(
                self.visualization_settings['psd']['welch_overlap_pct'] /
                100.0 * welch_seg_len).astype(int)
            welch_ndft = welch_seg_len
            x_in_graph, y_in_graph = scp_signal.welch(
                self.sig_in_graph, fs=self.fs,
                nperseg=welch_seg_len, noverlap=welch_overlap,
                nfft=welch_ndft, axis=0)
            # Set data
            self.set_data(x_in_graph, y_in_graph)
            # Update y range (only if autoscale is activated)
            self.autoscale(y_in_graph)
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
            'update_rate': 0.1,
            'frequency_filter': {
                'apply': True,
                'type': 'highpass',
                'cutoff_freq': [1],
                'order': 5
            },
            'notch_filter': {
                'apply': True,
                'freq': 50,
                'bandwidth': [-0.5, 0.5],
                'order': 5
            },
            're_referencing': {
                'apply': False,
                'type': 'car',
                'channel': ''
            },
            'downsampling': {
                'apply': False,
                'factor': 2
            }
        }
        visualization_settings = {
            'init_channel_label': None,
            'x_axis': {
                'range': [0.1, 30],
                'display_grid': False,
                'line_separation': 1,
                'label': '<b>Frequency</b> (Hz)'
            },
            'y_axis': {
                'range': [0, 1],
                'autoscale': {
                    'apply': True,
                    'n_std_tolerance': 1.25,
                    'n_std_separation': 5,
                },
                'label': {
                    'text': '<b>Power</b>',
                    'units': 'auto'
                }
            },
            'psd': {
                'time_window_seconds': 5,
                'welch_overlap_pct': 25,
                'welch_seg_len_pct': 50,
            },
            'title': 'auto',
        }
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        pass

    @staticmethod
    def check_signal(signal_type):
        return True

    def select_channel(self, cha):
        """ This function changes the channel used to compute the PSD displayed
        in the graph.

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
        # Update view box menu
        self.plot_item_view_box.menu.set_channel_list()
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.receiver.get_channel_indexes_from_labels(
            init_cha_label) if \
            init_cha_label is not None else 0
        self.select_channel(init_cha)
        # Update variables
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, self.lsl_stream_info.n_cha])
        self.win_t = self.visualization_settings['psd']['time_window_seconds']
        self.win_s = int(self.win_t * self.fs)
        self.n_samples_psd = self.win_s
        self.y_range = self.visualization_settings['y_axis']['range']
        if not isinstance(self.y_range, list):
            self.y_range = [0, self.y_range]
        # Set titles
        self.set_titles(self.visualization_settings['title'],
                        self.visualization_settings['x_axis']['label'],
                        self.visualization_settings['y_axis']['label'])
        # Place curves in plot
        curve_pen = pg.mkPen(color=self.curve_color,
                             width=self.curve_width,
                             style=Qt.SolidLine)
        grid_pen = pg.mkPen(color=self.grid_color,
                            width=self.grid_width,
                            style=Qt.SolidLine)
        # Curve
        self.curve = self.widget.plot(pen=curve_pen)
        # X-axis
        if self.visualization_settings['x_axis']['display_grid']:
            alpha = self.visualization_settings['x_axis']['display_grid']
            alpha = 255 if isinstance(alpha, bool) else alpha
            self.x_axis.setPen(grid_pen)
            self.x_axis.setGrid(alpha)
        # Draw y axis
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()

    def draw_y_axis_ticks(self):
        self.plot_item.setYRange(self.y_range[0],
                                 self.y_range[1],
                                 padding=0)

    def draw_x_axis_ticks(self):
        self.plot_item.setXRange(
            self.visualization_settings['x_axis']['range'][0],
            self.visualization_settings['x_axis']['range'][1],
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
        scaling_sett = self.visualization_settings['y_axis']['autoscale']
        if scaling_sett['apply']:
            y_std = np.std(y_in_graph)
            std_tol = scaling_sett['n_std_tolerance']
            std_factor = scaling_sett['n_std_separation']
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
                self.visualization_settings['psd']['welch_seg_len_pct'] /
                100.0 * self.sig_in_graph.shape[0]).astype(int)
            welch_overlap = np.round(
                self.visualization_settings['psd']['welch_overlap_pct'] /
                100.0 * welch_seg_len).astype(int)
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
    update = Signal(np.ndarray, np.ndarray)
    error = Signal(Exception)

    def __init__(self, plot_state, lsl_stream_info, signal_settings,
                 medusa_interface):
        super().__init__()
        self.plot_state = plot_state
        self.lsl_stream_info = lsl_stream_info
        self.signal_settings = signal_settings
        self.medusa_interface = medusa_interface
        self.fs = self.lsl_stream_info.fs
        self.sleep_time = self.signal_settings['update_rate'] * 0.9
        # Get minimum chunk size to comply with the update rate
        min_chunk_size = int(self.signal_settings['update_rate'] * self.fs)
        min_chunk_size = max(min_chunk_size, 1)
        # Set receiver
        self.receiver = lsl_utils.LSLStreamReceiver(
            self.lsl_stream_info,
            min_chunk_size=min_chunk_size)
        # Set real time preprocessor
        self.preprocessor = PlotsRealTimePreprocessor(self.signal_settings)
        self.preprocessor.fit(self.receiver.fs,
                              self.receiver.n_cha,
                              self.receiver.l_cha,
                              self.receiver.min_chunk_size)
        self.wait = False

    def handle_exception(self, ex):
        self.medusa_interface.error(ex)

    def get_effective_fs(self):
        if self.signal_settings['downsampling']['apply']:
            fs = self.fs // self.signal_settings['downsampling']['factor']
        else:
            fs = self.fs
        return fs

    @exceptions.error_handler(def_importance='important', scope='plots')
    def run(self):
        error_counter = 0
        self.receiver.flush_stream()
        while self.plot_state.value == constants.PLOT_STATE_ON:
            # Get chunks
            try:
                chunk_data, chunk_times, _ = self.receiver.get_chunk()
            except exceptions.LSLStreamTimeout as e:
                error_counter += 1
                if error_counter > 5:
                    raise exceptions.MedusaException(
                        e, importance='important',
                        msg='LSLStreamAppWorker is not receiving signal from '
                            '%s. Is the device connected?' % self.receiver.name,
                        scope='app', origin='LSLStreamAppWorker.run')
                else:
                    self.medusa_interface.log(
                        msg='LSLStreamAppWorker is not receiving signal from '
                            '%s. Trying to reconnect.' % self.receiver.name,
                        style='warning')
                    continue
            chunk_times, chunk_data = self.preprocessor.transform(
                chunk_times, chunk_data)
            # print('Chunk received at: %.6f' % time.time())
            # Check if the plot is ready to receive data (sometimes get
            # chunk takes a while and the user presses the button in
            # between)
            if self.plot_state.value == constants.PLOT_STATE_ON:
                self.update.emit(chunk_times, chunk_data)
            time.sleep(self.sleep_time)

        # ==================================================================== #
        # Debugging synchronization
        # ==================================================================== #
        # path = r'..\data'
        # curr_date = time.strftime("%d-%m-%Y_%H%M%S", time.localtime())
        # fname = 'sync_debug_%s' % curr_date
        # data = {'unix_clock_offsets': self.receiver.hist_unix_clock_offsets,
        #         'lsl_clock_offsets': self.receiver.hist_lsl_clock_offsets,
        #         'init_unix_clock_offset': self.receiver.unix_clock_offset,
        #         'init_lsl_clock_offset': self.receiver.lsl_clock_offset,
        #         'local_timestamps': self.receiver.hist_local_timestamps,
        #         'lsl_timestamps': self.receiver.hist_lsl_timestamps,
        #         'init_time': self.receiver.init_time,
        #         'last_time': self.receiver.last_time,
        #         'n_chunk': self.receiver.chunk_counter,
        #         'n_samples': self.receiver.sample_counter}
        # import json
        # with open(r'%s\%s.json' % (path, fname), 'w') as f:
        #     json.dump(data, f, indent=4)
        # print('Synchronization data correctly saved!')
        # ==================================================================== #


class PlotsRealTimePreprocessor:

    """Class that implements real time preprocessing functions for plotting,
    keeping it simple: band-pass filter and notch filter. For more advanced
    pre-processing, implement another class"""

    def __init__(self, preprocessing_settings, **kwargs):
        # Settings
        super().__init__(**kwargs)
        self.freq_filt_settings = preprocessing_settings['frequency_filter']
        self.notch_filt_settings = preprocessing_settings['notch_filter']
        self.re_referencing_settings = preprocessing_settings['re_referencing']
        self.downsampling_settings = preprocessing_settings['downsampling']
        self.apply_freq_filt = self.freq_filt_settings['apply']
        self.apply_notch = self.notch_filt_settings['apply']
        self.apply_re_referencing = self.re_referencing_settings['apply']
        self.apply_downsampling = self.downsampling_settings['apply']
        # Variables to fit
        self.fs = None
        self.n_cha = None
        self.l_cha = None
        self.freq_filt = None
        self.notch_filt = None

    def fit(self, fs, n_cha, l_cha, min_chunk_size):
        self.fs = fs
        self.n_cha = n_cha
        self.l_cha = l_cha
        # Frequency filter
        if self.apply_freq_filt:
            self.freq_filt = medusa.IIRFilter(
                order=self.freq_filt_settings['order'],
                cutoff=self.freq_filt_settings['cutoff_freq'],
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
        # Re-referencing
        if self.apply_re_referencing:
            if self.re_referencing_settings['type'] not in ['car', 'channel']:
                raise ValueError('Incorrect re-referencing type. Allowed '
                                 'values: {car, channel}')
        # Downsampling
        if self.apply_downsampling:
            if self.freq_filt_settings['type'] not in ['bandpass', 'lowpass']:
                raise ValueError('Incorrect frequency filter btype. Only '
                                 'bandpass and lowpass are available if '
                                 'downsampling is applied.')
            nyquist_cutoff = self.fs / 2 / self.downsampling_settings['factor']
            if self.freq_filt_settings['type'] == 'lowpass':
                if self.freq_filt_settings['cutoff_freq'] > nyquist_cutoff:
                    raise ValueError(
                        'Incorrect frequency filter for downsampling factor '
                        '%i. The upper cutoff must be less than %.2f to '
                        'comply with Nyquist criterion' %
                        (self.downsampling_settings['factor'], nyquist_cutoff))
            elif self.freq_filt_settings['type'] == 'bandpass':
                if self.freq_filt_settings['cutoff_freq'][1] > nyquist_cutoff:
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
        if self.apply_re_referencing:
            if self.re_referencing_settings['type'] == 'car':
                chunk_data = medusa.car(chunk_data)
            elif self.re_referencing_settings['type'] == 'channel':
                cha_idx = self.l_cha.index(
                    self.re_referencing_settings['channel'])
                chunk_data = chunk_data - chunk_data[:, [cha_idx]]
        if self.apply_downsampling:
            chunk_times = chunk_times[0::self.downsampling_settings['factor']]
            chunk_data = chunk_data[0::self.downsampling_settings['factor'], :]
        return chunk_times, chunk_data


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
