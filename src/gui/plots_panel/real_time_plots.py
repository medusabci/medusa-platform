# BUILT-IN MODULES
from abc import ABC, abstractmethod
import traceback
import time

# EXTERNAL MODULES
import numpy as np
from PySide6.QtCore import *
from PySide6.QtGui import QFont, QAction
from scipy import signal as scp_signal, interpolate
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.cm import get_cmap

# MEDUSA-PLATFORM MODULES
from acquisition import lsl_utils
from gui import gui_utils
import constants, exceptions

# MEDUSA-CORE MODULES
import medusa
from medusa import meeg
from medusa.transforms import power_spectral_density, fourier_spectrogram
from medusa.local_activation import spectral_parameteres
from medusa.connectivity import amplitude_connectivity, phase_connectivity
from medusa.plots import head_plots
from medusa.settings_schema import *


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
        signal_settings = self.to_key_value_dict(signal_settings)
        plot_settings = self.to_key_value_dict(plot_settings)
        self.check_settings(signal_settings, plot_settings)
        self.signal_settings = signal_settings
        self.visualization_settings = plot_settings

    def to_key_value_dict(self, settings_dict):
        """Simply the SettingsTree dictionary into a dictionary managing just keys
        and default values"""
        key_value_dict = {}
        for item in settings_dict:
            key = item["key"]

            if "items" in item:
                key_value_items = {}
                for item in item["items"]:
                    key_value_items[item["key"]] = (
                        self.to_key_value_dict(item["items"])) if (
                            "items" in item) else item["default_value"]
                key_value_dict[key] = key_value_items
            else:
                key_value_dict[key] = item["default_value"]
        return key_value_dict

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
        if self.check_signal(lsl_stream_info):
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
    def get_default_settings(stream_info=None):
        """Create de default settings dict"""
        raise NotImplemented

    @staticmethod
    @abstractmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
        """Update LSL stream related settings if the LSL stream changes"""
        raise NotImplemented

    @staticmethod
    @abstractmethod
    def check_settings(signal_settings, plot_settings):
        """Check settings dicts to see if it's correctly formatted"""
        raise NotImplemented

    @staticmethod
    @abstractmethod
    def check_signal(lsl_stream_info):
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


class TimePlotMultichannel(RealTimePlot):

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

        # Style and  theme
        self.curve_color = self.theme_colors['THEME_SIGNAL_CURVE']
        self.grid_color = self.theme_colors['THEME_SIGNAL_GRID']
        self.marker_color = self.theme_colors['THEME_SIGNAL_MARKER']
        self.curve_width = 1
        self.grid_width = 1
        self.marker_width = 2

        # Create figure & widget
        fig = Figure(figsize=(5, 5), dpi=100)
        fig.add_subplot(111)
        fig.tight_layout()
        fig.patch.set_facecolor(self.theme_colors['THEME_BG_DARK'])
        self.widget = FigureCanvasQTAgg(fig)
        self.widget.figure.set_size_inches(0, 0)
        self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ax = self.widget.figure.axes[0]
        self.ax.set_facecolor(self.theme_colors['THEME_BG_DARK'])
        self.ax.tick_params(axis='both', colors=self.theme_colors['THEME_TEXT_LIGHT'])
        for s in self.ax.spines.values():
            s.set_color(self.theme_colors['THEME_TEXT_LIGHT'])

        # Custom menu
        self.plot_menu = None
        self.widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.widget.customContextMenuRequested.connect(self.show_context_menu)
        self.widget.wheelEvent = self.mouse_wheel_event


    def show_context_menu(self, pos: QPoint):
        """
        Called automatically on right-click within the canvas.
        pos is in widget coordinates, so we map it to global coords.
        """
        menu = AutorangeMenu(self,'time')
        global_pos = self.widget.mapToGlobal(pos)
        menu.exec_(global_pos)


    def mouse_wheel_event(self, event):
        if event.angleDelta().y() > 0:
            self.cha_separation /= 1.5
        else:
            self.cha_separation *= 1.5
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings(stream_info=None):
        signal_settings = SettingsTree()
        signal_settings.add_item("update_rate", default_value=0.1, info="Update rate (s) of the plot", value_range=[0, None])
        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item("apply", default_value=True, info="Apply IIR filter in real-time")
        freq_filt.add_item("type", default_value="highpass", value_options=["highpass", "lowpass", "bandpass", "stopband"], info="Filter type")
        freq_filt.add_item("cutoff_freq", default_value=[1], info="List with one cutoff for highpass/lowpass, two for bandpass/stopband")
        freq_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item("apply", default_value=True, info="Apply notch filter to get rid of power line interference")
        notch_filt.add_item("freq", default_value=50.0, info="Center frequency to be filtered", value_range=[0, None])
        notch_filt.add_item("bandwidth", default_value=[-0.5, 0.5], info="List with relative limits of center frequency")
        notch_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item("apply", default_value=False, info="Change the reference of your signals")
        re_ref.add_item("type", default_value="car", value_options=["car", "channel"], info="Type of re-referencing: Common Average Reference or channel subtraction")
        if stream_info is not None:
            re_ref.add_item("channel", default_value=stream_info.l_cha[0],
                            info="Channel label for re-referencing if channel is selected",
                            value_options=stream_info.l_cha)
        else:
            re_ref.add_item("channel", default_value="", info="Channel label for re-referencing if channel is selected")
        down_samp= signal_settings.add_item("downsampling")
        down_samp.add_item("apply", default_value=False, info="Reduce the sample rate of the incoming LSL stream")
        down_samp.add_item("factor", default_value=2.0, info="Downsampling factor", value_range=[0, None])

        visualization_settings = SettingsTree()
        visualization_settings.add_item("mode", default_value="clinical", info="Determine how events are visualized. Clinical, update in sweeping manner. Geek, signal appears continuously.", value_options=["clinical", "geek"])
        if stream_info is not None:
            visualization_settings.add_item("l_cha", default_value=stream_info.l_cha,
                                            info="List with labels of channels to be displayed")
        else:
            visualization_settings.add_item("l_cha", default_value=[], info="List with labels of channels to be displayed")

        x_ax = visualization_settings.add_item("x_axis")
        x_ax.add_item("seconds_displayed", default_value=10.0, info="The time range (s) displayed", value_range=[0, None])
        x_ax.add_item("display_grid", default_value=True, info="Visibility of the grid")
        x_ax.add_item("line_separation", default_value=1.0, info="Display grid's dimensions", value_range=[0, None])
        x_ax.add_item("label", default_value="Time (s)", info="Label for x-axis")

        y_ax = visualization_settings.add_item("y_axis")
        y_ax.add_item("cha_separation", default_value=1.0, info="Initial limits of the y-axis", value_range=[0, None])
        y_ax.add_item("display_grid", default_value=True, info="Visibility of the grid")
        auto_scale = y_ax.add_item("autoscale")
        auto_scale.add_item("apply", default_value=False, info="Automatically scale the y-axis")
        auto_scale.add_item("n_std_tolerance", default_value=1.25, info="Autoscale limit: if the signal exceeds this value, the scale is re-adjusted", value_range=[0, None])
        auto_scale.add_item("n_std_separation", default_value=5.0, info="Separation between channels (in std)", value_range=[0, None])
        y_label = y_ax.add_item("label")
        y_label.add_item("text", default_value="Signal", info="Label for y-axis")
        y_label.add_item("units", default_value="auto", info="Units for y-axis")
        visualization_settings.add_item("title", default_value="auto", info="Title for the plot")
        visualization_settings.add_item("colors", default_value="auto",
                                        info="Title for the plot")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel"). \
            edit_item(default_value=stream_info.l_cha[0],
                      value_options=stream_info.l_cha)
        visualization_settings.get_item("l_cha").edit_item(
            default_value=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        # Visualization modes
        possible_modes = ['geek', 'clinical']
        if visualization_settings['mode'] not in possible_modes:
            raise ValueError('Unknown plot mode %s. Possible options: %s' %
                             (visualization_settings['mode'], possible_modes))

    @staticmethod
    def check_signal(lsl_stream_info):
        return True

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frequency.
        """
        # Get channels
        self.l_cha = self.visualization_settings['l_cha']
        self.n_cha= len(self.l_cha)
        self.cha_idx = [i for i, label in enumerate(self.lsl_stream_info.l_cha) if label in self.l_cha]
        # Update variables
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, self.n_cha])
        self.cha_separation = \
            self.visualization_settings['y_axis']['cha_separation']
        self.win_t = self.visualization_settings['x_axis']['seconds_displayed']
        self.win_s = int(self.win_t * self.fs)
        # Set custom menu
        self.plot_menu = AutorangeMenu(self,'time')
        self.plot_menu.auto_range_time()

        # Set titles
        self.ax.set_xlabel(
            self.visualization_settings['x_axis']['label'],
            color=self.theme_colors['THEME_TEXT_LIGHT'])
        self.ax.set_ylabel(
            self.visualization_settings['y_axis']['label']['text'],
            color=self.theme_colors['THEME_TEXT_LIGHT'])
        self.ax.set_title(self.lsl_stream_info.lsl_stream.name(),
                          color=self.theme_colors['THEME_TEXT_LIGHT'])

        # Set the style for the curves
        curve_style = {'color': self.curve_color,
                       'linewidth': self.curve_width}

        # Place curves in plot
        self.curves = []
        for i in range(self.n_cha):
            curve, = self.ax.plot([], [], **curve_style)
            self.curves.append(curve)

        # Marker for clinical mode
        if self.visualization_settings['mode'] == 'clinical':
            self.marker = self.ax.axvline(x=0, color=self.marker_color,
                                          linewidth=self.marker_width)
            self.pointer = -1

        # Set grid for the axes
        if self.visualization_settings['x_axis']['display_grid']:
            self.ax.grid(True, axis='x',
                         color=self.grid_color,
                         linewidth=self.grid_width)

        if self.visualization_settings['y_axis']['display_grid']:
            self.ax.grid(True, axis='y',
                         color=self.grid_color,
                         linewidth=self.grid_width)

        # Set axis limits
        self.ax.set_xlim(0, self.win_s)
        self.ax.set_ylim(-self.cha_separation * (self.n_cha / 2),
                         self.cha_separation * (self.n_cha / 2))

        # Draw ticks on the axes
        self.draw_x_axis_ticks()
        self.draw_y_axis_ticks()

        # Refresh the plot
        self.set_data()
        self.widget.draw()

    def draw_y_axis_ticks(self):
        # Draw y axis ticks (channel labels)
        if self.l_cha is not None:
            y_ticks_pos = np.arange(self.n_cha) * self.cha_separation
            y_ticks_labels = self.l_cha[::-1]
        self.ax.set_yticks(y_ticks_pos)
        self.ax.set_yticklabels(y_ticks_labels,
                                color=self.theme_colors['THEME_TEXT_LIGHT'])
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.n_cha * self.cha_separation
        if self.n_cha > 1:
            self.ax.set_ylim(y_min, y_max)

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
                self.ax.set_xticks(x_ticks_pos)
                self.ax.set_xticklabels(x_ticks_val,
                                        color=self.theme_colors['THEME_TEXT_LIGHT'])
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
                self.ax.set_xticks(x_ticks_pos)
                self.ax.set_xticklabels(x_ticks_val,
                                        color=self.theme_colors['THEME_TEXT_LIGHT'])
            else:
                raise ValueError
            # Set range
            self.ax.set_xlim(x_range[0], x_range[1])
        else:
            self.ax.set_xticks([])
            self.ax.set_xlim(0, 1)

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
                self.marker.set_xdata([x[self.pointer]])
        else:
            raise ValueError
        # Set data
        for i in range(self.n_cha):
            temp = self.sig_in_graph[:, self.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].set_data(x,temp)

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
            # Init time
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if self.visualization_settings['mode'] == 'clinical':
                    self.ax.add_line(self.marker)
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

            #Update the plot
            self.widget.draw()
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
        self.ax.clear()
        width, height = self.widget.get_width_height()
        if width > 0 and height > 0:
            self.widget.draw()


class TimePlotSingleChannel(RealTimePlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Channels idx
        self.n_cha = 1
        self.curr_cha = None
        # Graph variables
        self.win_t = None
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.pointer = None
        self.curves = None
        self.marker = None
        self.y_range = None

        # Style and  theme
        self.curve_color = self.theme_colors['THEME_SIGNAL_CURVE']
        self.grid_color = self.theme_colors['THEME_SIGNAL_GRID']
        self.marker_color = self.theme_colors['THEME_SIGNAL_MARKER']
        self.curve_width = 1
        self.grid_width = 1
        self.marker_width = 2

        # Create figure & widget
        fig = Figure()
        fig.add_subplot(111)
        fig.tight_layout()
        fig.patch.set_facecolor(self.theme_colors['THEME_BG_DARK'])
        self.widget = FigureCanvasQTAgg(fig)
        self.widget.figure.set_size_inches(0, 0)
        self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ax = self.widget.figure.axes[0]
        self.ax.set_facecolor(self.theme_colors['THEME_BG_DARK'])
        self.ax.tick_params(axis='both', colors=self.theme_colors['THEME_TEXT_LIGHT'])
        for s in self.ax.spines.values():
            s.set_color(self.theme_colors['THEME_TEXT_LIGHT'])

        # Custom menu
        self.plot_menu = None
        self.widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.widget.customContextMenuRequested.connect(self.show_context_menu)
        self.widget.wheelEvent = self.mouse_wheel_event

    def show_context_menu(self, pos: QPoint):
        """
        Called automatically on right-click within the canvas.
        pos is in widget coordinates, so we map it to global coords.
        """
        menu = SelectChannelMenu(self)
        menu.set_channel_list()
        global_pos = self.widget.mapToGlobal(pos)
        menu.exec_(global_pos)

    def mouse_wheel_event(self, event):
        if event.angleDelta().y() > 0:
            self.y_range = [r / 1.5 for r in self.y_range]
        else:
            self.y_range = [r * 1.5 for r in self.y_range]
        self.draw_y_axis_ticks

    @staticmethod
    def get_default_settings(stream_info=None):
        signal_settings = SettingsTree()
        signal_settings.add_item("update_rate", default_value=0.1,
                                 info="Update rate (s) of the plot",
                                 value_range=[0, None])
        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item("apply", default_value=True,
                           info="Apply IIR filter in real-time")
        freq_filt.add_item("type", default_value="highpass",
                           value_options=["highpass", "lowpass", "bandpass",
                                          "stopband"], info="Filter type")
        freq_filt.add_item("cutoff_freq", default_value=[1.0],
                           info="List with one cutoff for highpass/lowpass, two for bandpass/stopband")
        freq_filt.add_item("order", default_value=5,
                           info="Order of the filter (the higher, the greater computational cost)",
                           value_range=[1, None])
        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item("apply", default_value=True,
                            info="Apply notch filter to get rid of power line interference")
        notch_filt.add_item("freq", default_value=50.0,
                            info="Center frequency to be filtered",
                            value_range=[0, None])
        notch_filt.add_item("bandwidth", default_value=[-0.5, 0.5],
                            info="List with relative limits of center frequency")
        notch_filt.add_item("order", default_value=5,
                            info="Order of the filter (the higher, the greater computational cost)",
                            value_range=[1, None])
        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item("apply", default_value=False,
                        info="Change the reference of your signals")
        re_ref.add_item("type", default_value="car",
                        value_options=["car", "channel"],
                        info="Type of re-referencing: Common Average Reference or channel subtraction")
        if stream_info is not None:
            re_ref.add_item("channel", default_value=stream_info.l_cha[0],
                            info="Channel label for re-referencing if channel is selected",
                            value_options=stream_info.l_cha)
        else:
            re_ref.add_item("channel", default_value="",
                            info="Channel label for re-referencing if channel is selected")
        down_samp = signal_settings.add_item("downsampling")
        down_samp.add_item("apply", default_value=False,
                           info="Reduce the sample rate of the incoming LSL stream")
        down_samp.add_item("factor", default_value=2.0,
                           info="Downsampling factor", value_range=[0, None])

        visualization_settings = SettingsTree()
        visualization_settings.add_item("mode", default_value="clinical",
                                        info="Determine how events are visualized. Clinical, update in sweeping manner. Geek, signal appears continuously.",
                                        value_options=["clinical", "geek"])
        if stream_info is not None:
            visualization_settings.add_item("init_channel_label",
                                            default_value=stream_info.l_cha[0],
                                            info="Channel selected for visualization",
                                            value_options=stream_info.l_cha)
        else:
            visualization_settings.add_item("init_channel_label",
                                            default_value="",
                                            info="Channel selected for visualization")

        visualization_settings.add_item("title_label_size", default_value=10.0,
                                        info="Title label size",
                                        value_range=[0, None])
        x_ax = visualization_settings.add_item("x_axis")
        x_ax.add_item("seconds_displayed", default_value=10.0,
                      info="The time range (s) displayed",
                      value_range=[0, None])
        x_ax.add_item("display_grid", default_value=True,
                      info="Visibility of the grid")
        x_ax.add_item("line_separation", default_value=1.0,
                      info="Display grid's dimensions", value_range=[0, None])
        x_ax.add_item("label", default_value="Time (s)",
                      info="Label for x-axis")
        y_ax = visualization_settings.add_item("y_axis")
        y_ax.add_item("range", default_value=[-1, 1], info="Range of y-axis")
        y_ax.add_item("display_grid", default_value=True,
                      info="Visibility of the grid")
        auto_scale = y_ax.add_item("autoscale")
        auto_scale.add_item("apply", default_value=False,
                            info="Automatically scale the y-axis")
        auto_scale.add_item("n_std_tolerance", default_value=1.25,
                            info="Autoscale limit: if the signal exceeds this value, the scale is re-adjusted",
                            value_range=[0, None])
        auto_scale.add_item("n_std_separation", default_value=5.0,
                            info="Separation between channels (in std)",
                            value_range=[0, None])
        y_label = y_ax.add_item("label")
        y_label.add_item("text", default_value="Signal",
                         info="Label for y-axis")
        y_label.add_item("units", default_value="auto", info="Units for y-axis")
        visualization_settings.add_item("title", default_value="auto",
                                        info="Title for the plot")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel"). \
            edit_item(default_value=stream_info.l_cha[0],
                      value_options=stream_info.l_cha)
        visualization_settings.get_item("init_channel_label"). \
            edit_item(default_value=stream_info.l_cha[0],
                      value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        # Check mode
        possible_modes = ['geek', 'clinical']
        if visualization_settings['mode'] not in possible_modes:
            raise ValueError('Unknown plot mode %s. Possible options: %s' %
                             (visualization_settings['mode'], possible_modes))

    @staticmethod
    def check_signal(lsl_stream_info):
        return True

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frecuency.
        """
        # Update view box menu
        self.plot_menu = SelectChannelMenu(self)
        self.plot_menu.set_channel_list()

        # Set initial channel
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label)
        self.plot_menu.select_channel(init_cha)

        # Update variables
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, self.lsl_stream_info.n_cha])
        self.win_t = self.visualization_settings['x_axis']['seconds_displayed']
        self.win_s = int(self.win_t * self.fs)

        self.y_range = self.visualization_settings['y_axis']['range']
        if not isinstance(self.y_range, list):
            self.y_range = [-self.y_range, self.y_range]

        # Set titles
        self.ax.set_xlabel(
            self.visualization_settings['x_axis']['label'],
            color=self.theme_colors['THEME_TEXT_LIGHT'])
        self.ax.set_ylabel(
            self.visualization_settings['y_axis']['label']['text'],
            color=self.theme_colors['THEME_TEXT_LIGHT'])
        self.ax.set_title(self.lsl_stream_info.l_cha[init_cha],
                          color=self.theme_colors['THEME_TEXT_LIGHT'],
                          fontsize=self.visualization_settings['title_label_size'])

        # Set the style for the curves
        curve_style = {'color': self.curve_color,
                       'linewidth': self.curve_width}
        curve, = self.ax.plot([], [], **curve_style)
        self.curves = [curve]

        # Marker for clinical mode
        if self.visualization_settings['mode'] == 'clinical':
            self.marker = self.ax.axvline(x=0, color=self.marker_color,
                                          linewidth=self.marker_width)
            self.pointer = -1

        # Set grid for the axes
        if self.visualization_settings['x_axis']['display_grid']:
            self.ax.grid(True, axis='x',
                         color=self.grid_color,
                         linewidth=self.grid_width)

        if self.visualization_settings['y_axis']['display_grid']:
            self.ax.grid(True, axis='y',
                         color=self.grid_color,
                         linewidth=self.grid_width)

        # Set axis limits
        self.ax.set_xlim(0, self.win_s)
        self.ax.set_ylim(self.y_range )

        # Draw ticks on the axes
        self.draw_x_axis_ticks()
        self.draw_y_axis_ticks

        # Refresh the plot
        self.set_data()
        self.widget.draw()


    @property
    def draw_y_axis_ticks(self):
        self.ax.set_ylim(self.y_range[0],
                                 self.y_range[1])
        self.ax.tick_params(axis='y', labelcolor=self.theme_colors['THEME_TEXT_LIGHT'])

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
                self.ax.set_xticks(x_ticks_pos)
                self.ax.set_xticklabels(x_ticks_val,
                                        color=self.theme_colors[
                                            'THEME_TEXT_LIGHT'])
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
                self.ax.set_xticks(x_ticks_pos)
                self.ax.set_xticklabels(x_ticks_val,
                                        color=self.theme_colors[
                                            'THEME_TEXT_LIGHT'])
            else:
                raise ValueError
            # Set range
            self.ax.set_xlim(x_range[0], x_range[1])
        else:
            self.ax.set_xticks([])
            self.ax.set_xlim(0, 1)

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
            max_win_t = (n_win + 1) * self.win_t
            # Check overflow
            if chunk_times[-1] > max_win_t:
                idx_overflow = chunk_times > max_win_t
                # Append part of the chunk at the end
                time_in_graph = np.insert(
                    self.time_in_graph,
                    self.pointer + 1,
                    chunk_times[np.logical_not(idx_overflow)], axis=0)
                sig_in_graph = np.insert(
                    self.sig_in_graph,
                    self.pointer + 1,
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
                                          self.pointer + 1,
                                          chunk_times, axis=0)
                sig_in_graph = np.insert(self.sig_in_graph,
                                         self.pointer + 1,
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
                self.marker.set_xdata([x[self.pointer]])
        else:
            raise ValueError
        tmp = self.sig_in_graph[:, self.curr_cha - 1]
        self.curves[0].set_data(x, tmp)

    def autoscale(self):
        scaling_sett = self.visualization_settings['y_axis']['autoscale']
        if scaling_sett['apply']:
            y_std = np.std(self.sig_in_graph)
            std_tol = scaling_sett['n_std_tolerance']
            std_factor = scaling_sett['n_std_separation']
            if y_std > self.cha_separation * std_tol or \
                    y_std < self.cha_separation / std_tol:
                self.cha_separation = std_factor

    def update_plot(self, chunk_times, chunk_signal):
        try:
            # Reference time
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if self.visualization_settings['mode'] == 'clinical':
                    self.ax.add_line(self.marker)
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

            # Update the plot
            self.widget.draw()
            # if time.time() - t0 > self.signal_settings['update_rate']:
            #     self.medusa_interface.log(
            #         '[Plot %i] The plot time per chunk is higher than the '
            #         'update rate. This may end up freezing MEDUSA.' %
            #         self.uid,
            #         style='warning', mode='replace')
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.ax.clear()
        width, height = self.widget.get_width_height()
        if width > 0 and height > 0:
            self.widget.draw()


class PSDPlotMultichannel(RealTimePlot):

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
        # Style and  theme
        self.curve_color = self.theme_colors['THEME_SIGNAL_CURVE']
        self.grid_color = self.theme_colors['THEME_SIGNAL_GRID']
        self.curve_width = 1
        self.grid_width = 1
        # Create figure & widget
        fig = Figure()
        fig.add_subplot(111)
        fig.tight_layout()
        fig.patch.set_facecolor(self.theme_colors['THEME_BG_DARK'])
        self.widget = FigureCanvasQTAgg(fig)
        self.widget.figure.set_size_inches(0, 0)
        self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ax = self.widget.figure.axes[0]
        self.ax.set_facecolor(self.theme_colors['THEME_BG_DARK'])
        self.ax.tick_params(axis='both',
                            colors=self.theme_colors['THEME_TEXT_LIGHT'])
        for s in self.ax.spines.values():
            s.set_color(self.theme_colors['THEME_TEXT_LIGHT'])
        # Custom menu
        self.plot_menu = None
        self.widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.widget.customContextMenuRequested.connect(self.show_context_menu)
        self.widget.wheelEvent = self.mouse_wheel_event

    def show_context_menu(self, pos: QPoint):
        """
        Called automatically on right-click within the canvas.
        pos is in widget coordinates, so we map it to global coords.
        """
        menu = AutorangeMenu(self,'PSD')
        global_pos = self.widget.mapToGlobal(pos)
        menu.exec_(global_pos)

    def mouse_wheel_event(self, event):
        if event.angleDelta().y() > 0:
            self.cha_separation /= 1.5
        else:
            self.cha_separation *= 1.5
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings(stream_info=None):
        signal_settings = SettingsTree()
        signal_settings.add_item("update_rate", default_value=0.1,
                                 info="Update rate (s) of the plot",
                                 value_range=[0, None])
        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item("apply", default_value=True,
                           info="Apply IIR filter in real-time")
        freq_filt.add_item("type", default_value="highpass",
                           value_options=["highpass", "lowpass", "bandpass",
                                          "stopband"], info="Filter type")
        freq_filt.add_item("cutoff_freq", default_value=[1.0],
                           info="List with one cutoff for highpass/lowpass, two for bandpass/stopband")
        freq_filt.add_item("order", default_value=5,
                           info="Order of the filter (the higher, the greater computational cost)",
                           value_range=[1, None])
        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item("apply", default_value=True,
                            info="Apply notch filter to get rid of power line interference")
        notch_filt.add_item("freq", default_value=50.0,
                            info="Center frequency to be filtered",
                            value_range=[0, None])
        notch_filt.add_item("bandwidth", default_value=[-0.5, 0.5],
                            info="List with relative limits of center frequency")
        notch_filt.add_item("order", default_value=5,
                            info="Order of the filter (the higher, the greater computational cost)",
                            value_range=[1, None])
        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item("apply", default_value=False,
                        info="Change the reference of your signals")
        re_ref.add_item("type", default_value="car",
                        value_options=["car", "channel"],
                        info="Type of re-referencing: Common Average Reference or channel subtraction")
        if stream_info is not None:
            re_ref.add_item("channel", default_value=stream_info.l_cha[0],
                            info="Channel label for re-referencing if channel is selected",
                            value_options=stream_info.l_cha)
        else:
            re_ref.add_item("channel", default_value="",
                            info="Channel label for re-referencing if channel is selected")
        down_samp = signal_settings.add_item("downsampling")
        down_samp.add_item("apply", default_value=False,
                           info="Reduce the sample rate of the incoming LSL stream")
        down_samp.add_item("factor", default_value=2.0,
                           info="Downsampling factor", value_range=[0, None])

        visualization_settings = SettingsTree()
        if stream_info is not None:
            visualization_settings.add_item("l_cha",
                                            default_value=stream_info.l_cha,
                                            info="List with labels of channels to be displayed")
        else:
            visualization_settings.add_item("l_cha", default_value=[],
                                            info="List with labels of channels to be displayed")
        x_ax = visualization_settings.add_item("x_axis")
        x_ax.add_item("range", default_value=[0.1, 30], info="X-axis range")
        x_ax.add_item("display_grid", default_value=False,
                      info="Visibility of the grid")
        x_ax.add_item("line_separation", default_value=1.0,
                      info="Display grid's dimensions", value_range=[0, None])
        x_ax.add_item("label", default_value="Frequency (Hz)",
                      info="Label for x-axis")
        y_ax = visualization_settings.add_item("y_axis")
        y_ax.add_item("cha_separation", default_value=1.0,
                      info="Initial limits of the y-axis",
                      value_range=[0, None])
        y_ax.add_item("display_grid", default_value=True,
                      info="Visibility of the grid")
        auto_scale = y_ax.add_item("autoscale")
        auto_scale.add_item("apply", default_value=True,
                            info="Automatically scale the y-axis")
        auto_scale.add_item("n_std_tolerance", default_value=1.25,
                            info="Autoscale limit: if the signal exceeds this value, the scale is re-adjusted",
                            value_range=[0, None])
        auto_scale.add_item("n_std_separation", default_value=5.0,
                            info="Separation between channels (in std)",
                            value_range=[0, None])
        y_label = y_ax.add_item("label")
        y_label.add_item("text", default_value="Power",
                         info="Label for y-axis")
        y_label.add_item("units", default_value="auto", info="Units for y-axis")
        psd = visualization_settings.add_item("psd")
        psd.add_item("time_window_seconds", default_value=5.0,
                     info="Time (s) in which the PSD will be estimated",
                     value_range=[0, None])
        psd.add_item("welch_overlap_pct", default_value=25.0,
                     info="Percentage of segment overlapping",
                     value_range=[0, 100])
        psd.add_item("welch_seg_len_pct", default_value=50.0,
                     info="Percentage of the window that will be used",
                     value_range=[0, 100])
        visualization_settings.add_item("title", default_value="auto",
                                        info="Title for the plot")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel"). \
            edit_item(default_value=stream_info.l_cha[0],
                      value_options=stream_info.l_cha)
        visualization_settings.get_item("l_cha").edit_item(
            default_value=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        # Channel separation
        if isinstance(visualization_settings['y_axis']['cha_separation'], list):
            raise ValueError('Incorrect configuration. The channel separation'
                             'must be a number.')

    @staticmethod
    def check_signal(lsl_stream_info):
        return True

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frecuency.
        """
        # Get channels
        self.l_cha = self.visualization_settings['l_cha']
        self.n_cha = len(self.l_cha)
        self.cha_idx = [i for i, label in enumerate(self.lsl_stream_info.l_cha)
                        if label in self.l_cha]
        # Update variables
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, self.n_cha])
        self.cha_separation = \
            self.visualization_settings['y_axis']['cha_separation']
        self.win_t = self.visualization_settings['psd']['time_window_seconds']
        self.win_s = int(self.win_t * self.fs)
        self.n_samples_psd = self.win_s
        # Set custom menu
        self.plot_menu = AutorangeMenu(self,'PSD')
        self.plot_menu.auto_range_spect()
        # Set titles
        self.ax.set_xlabel(
            self.visualization_settings['x_axis']['label'],
            color=self.theme_colors['THEME_TEXT_LIGHT'])
        self.ax.set_ylabel(
            self.visualization_settings['y_axis']['label']['text'],
            color=self.theme_colors['THEME_TEXT_LIGHT'])
        self.ax.set_title(self.lsl_stream_info.lsl_stream.name(),
                          color=self.theme_colors['THEME_TEXT_LIGHT'])
        # Set the style for the curves
        curve_style = {'color': self.curve_color,
                       'linewidth': self.curve_width}
        # Place curves in plot
        self.curves = []
        for i in range(self.n_cha):
            curve, = self.ax.plot([], [], **curve_style)
            self.curves.append(curve)
        # Set grid for the axes
        if self.visualization_settings['x_axis']['display_grid']:
            self.ax.grid(True, axis='x',
                         color=self.grid_color,
                         linewidth=self.grid_width)

        if self.visualization_settings['y_axis']['display_grid']:
            self.ax.grid(True, axis='y',
                         color=self.grid_color,
                         linewidth=self.grid_width)
        # Draw y axis
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()

        self.widget.draw()

    def draw_y_axis_ticks(self):
        # Draw y axis ticks (channel labels)
        if self.l_cha is not None:
            y_ticks_pos = np.arange(self.n_cha) * self.cha_separation
            y_ticks_labels = self.l_cha[::-1]
        self.ax.set_yticks(y_ticks_pos)
        self.ax.set_yticklabels(y_ticks_labels,
                                color=self.theme_colors['THEME_TEXT_LIGHT'])
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.n_cha * self.cha_separation
        if self.n_cha > 1:
            self.ax.set_ylim(y_min, y_max)

    def draw_x_axis_ticks(self):
        self.ax.set_xlim(self.visualization_settings['x_axis']['range'])

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
            self.curves[i].set_data(x, temp)

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
            # Update the plot
            self.widget.draw()
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.ax.clear()
        width, height = self.widget.get_width_height()
        if width > 0 and height > 0:
            self.widget.draw()


class PSDPlotSingleChannel(RealTimePlot):
    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Graph variables
        self.curr_cha = None
        self.win_t = None
        self.win_s = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.curves = None
        self.n_samples_psd = None
        self.y_range = None
        self.x_range = None

        # Style and  theme
        self.curve_color = self.theme_colors['THEME_SIGNAL_CURVE']
        self.grid_color = self.theme_colors['THEME_SIGNAL_GRID']
        self.curve_width = 1
        self.grid_width = 1

        # Create figure & widget
        fig = Figure()
        fig.add_subplot(111)
        fig.tight_layout()
        fig.patch.set_color(self.theme_colors['THEME_BG_DARK'])
        self.widget = FigureCanvasQTAgg(fig)
        self.widget.figure.set_size_inches(0, 0)
        self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ax = self.widget.figure.axes[0]
        self.ax.set_facecolor(self.theme_colors['THEME_BG_DARK'])
        self.ax.tick_params(axis='both', colors=self.theme_colors['THEME_TEXT_LIGHT'])
        for s in self.ax.spines.values():
            s.set_color(self.theme_colors['THEME_TEXT_LIGHT'])

        # Custom menu
        self.plot_menu = None
        self.widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.widget.customContextMenuRequested.connect(self.show_context_menu)
        self.widget.wheelEvent = self.mouse_wheel_event

    def show_context_menu(self, pos: QPoint):
        """
        Called automatically on right-click within the canvas.
        pos is in widget coordinates, so we map it to global coords.
        """
        menu = SelectChannelMenu(self)
        menu.set_channel_list()
        global_pos = self.widget.mapToGlobal(pos)
        menu.exec_(global_pos)

    def mouse_wheel_event(self, event):
        if event.angleDelta().y() > 0:
            self.y_range = [r / 1.5 for r in self.y_range]

        else:
            self.y_range = [r * 1.5 for r in self.y_range]
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings(stream_info=None):
        signal_settings = SettingsTree()
        signal_settings.add_item("update_rate", default_value=0.1, info="Update rate (s) of the plot", value_range=[0, None])
        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item("apply", default_value=True, info="Apply IIR filter in real-time")
        freq_filt.add_item("type", default_value="highpass", value_options=["highpass", "lowpass", "bandpass", "stopband"], info="Filter type")
        freq_filt.add_item("cutoff_freq", default_value=[1.0], info="List with one cutoff for highpass/lowpass, two for bandpass/stopband")
        freq_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item("apply", default_value=True, info="Apply notch filter to get rid of power line interference")
        notch_filt.add_item("freq", default_value=50.0, info="Center frequency to be filtered", value_range=[0, None])
        notch_filt.add_item("bandwidth", default_value=[-0.5, 0.5], info="List with relative limits of center frequency")
        notch_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item("apply", default_value=False, info="Change the reference of your signals")
        re_ref.add_item("type", default_value="car", value_options=["car", "channel"], info="Type of re-referencing: Common Average Reference or channel subtraction")
        if stream_info is not None:
            re_ref.add_item("channel", default_value=stream_info.l_cha[0],
                            info="Channel label for re-referencing if channel is selected",
                            value_options=stream_info.l_cha)
        else:
            re_ref.add_item("channel", default_value="", info="Channel label for re-referencing if channel is selected")
        down_samp= signal_settings.add_item("downsampling")
        down_samp.add_item("apply", default_value=False, info="Reduce the sample rate of the incoming LSL stream")
        down_samp.add_item("factor", default_value=2, info="Downsampling factor")

        visualization_settings = SettingsTree()
        if stream_info is not None:
            visualization_settings.add_item("init_channel_label", default_value=stream_info.l_cha[0],
                                            info="Channel selected for visualization",
                                            value_options=stream_info.l_cha)
        else:
            visualization_settings.add_item("init_channel_label", default_value="",
                                            info="Channel selected for visualization")
        visualization_settings.add_item("title_label_size", default_value=10.0,
                                        info="Title label size",
                                        value_range=[0, None])
        x_ax = visualization_settings.add_item("x_axis")
        x_ax.add_item("range", default_value=[0.1, 30], info="X-axis range")
        x_ax.add_item("display_grid", default_value=False, info="Visibility of the grid")
        x_ax.add_item("line_separation", default_value=1.0, info="Display grid's dimensions", value_range=[0, None])
        x_ax.add_item("label", default_value="Frequency (Hz)", info="Label for x-axis")
        y_ax = visualization_settings.add_item("y_axis")
        y_ax.add_item("range", default_value=[0, 1], info="Y-axis range")
        auto_scale = y_ax.add_item("autoscale")
        auto_scale.add_item("apply", default_value=True, info="Automatically scale the y-axis")
        auto_scale.add_item("n_std_tolerance", default_value=1.25, info="Autoscale limit: if the signal exceeds this value, the scale is re-adjusted", value_range=[0, None])
        auto_scale.add_item("n_std_separation", default_value=5.0, info="Separation between channels (in std)", value_range=[0, None])
        y_label = y_ax.add_item("label")
        y_label.add_item("text", default_value="Power", info="Label for y-axis")
        y_label.add_item("units", default_value="auto", info="Units for y-axis")
        psd = visualization_settings.add_item("psd")
        psd.add_item("time_window_seconds", default_value=5.0, info="Time (s) in which the PSD will be estimated", value_range=[0, None])
        psd.add_item("welch_overlap_pct", default_value=25.0, info="Percentage of segment overlapping", value_range=[0, 100])
        psd.add_item("welch_seg_len_pct", default_value=50.0, info="Percentage of the window that will be used", value_range=[0, 100])
        visualization_settings.add_item("title", default_value="auto", info="Title for the plot")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel").\
            edit_item(default_value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        visualization_settings.get_item("init_channel_label").\
            edit_item(default_value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        pass

    @staticmethod
    def check_signal(lsl_stream_info):
        return True

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frecuency.
        """
        # Update view box menu
        self.plot_menu = SelectChannelMenu(self)
        self.plot_menu.set_channel_list()

        # Set initial channel
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label)
        self.plot_menu.select_channel(init_cha)

        # Update variables
        self.time_in_graph = np.zeros([0])
        self.sig_in_graph = np.zeros([0, self.lsl_stream_info.n_cha])
        self.win_t = self.visualization_settings['psd']['time_window_seconds']
        self.win_s = int(self.win_t * self.fs)
        self.n_samples_psd = self.win_s
        self.y_range = self.visualization_settings['y_axis']['range']
        self.x_range = self.visualization_settings['x_axis']['range']
        if not isinstance(self.y_range, list):
            self.y_range = [0, self.y_range]

        # Set titles
        self.ax.set_xlabel(
            self.visualization_settings['x_axis']['label'],
            color=self.theme_colors['THEME_TEXT_LIGHT'])
        self.ax.set_ylabel(
            self.visualization_settings['y_axis']['label']['text'],
            color=self.theme_colors['THEME_TEXT_LIGHT'])
        self.ax.set_title(self.lsl_stream_info.l_cha[init_cha],
                          color=self.theme_colors['THEME_TEXT_LIGHT'],
                          fontsize=self.visualization_settings['title_label_size'])

        # Set the style for the curves
        curve_style = {'color': self.curve_color,
                       'linewidth': self.curve_width}

        curve, = self.ax.plot([], [], **curve_style)
        self.curves = [curve]

        # Set grid for the axes
        if self.visualization_settings['x_axis']['display_grid']:
            self.ax.grid(True, axis='x',
                         color=self.grid_color,
                         linewidth=self.grid_width)
        # Draw y axis
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()

    def draw_y_axis_ticks(self):
        self.ax.set_ylim(self.y_range[0],
                                 self.y_range[1])
        self.ax.tick_params(axis='y', labelcolor=self.theme_colors['THEME_TEXT_LIGHT'])

    def draw_x_axis_ticks(self):
        self.ax.set_xlim(self.x_range[0],
                         self.x_range[1])
        self.ax.tick_params(axis='x',
                            labelcolor=self.theme_colors['THEME_TEXT_LIGHT'])


    def append_data(self, chunk_times, chunk_signal):
        self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
        if len(self.time_in_graph) >= self.win_s:
            self.time_in_graph = self.time_in_graph[-self.win_s:]
        self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
        if len(self.sig_in_graph) >= self.win_s:
            self.sig_in_graph = self.sig_in_graph[-self.win_s:]
        return self.time_in_graph.copy(), self.sig_in_graph.copy()

    def set_data(self, x_in_graph, sig_in_graph):
        self.curves[0].set_data(x_in_graph, sig_in_graph)

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
            # Update the plot
            self.widget.draw()
        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        self.ax.clear()
        width, height = self.widget.get_width_height()
        if width > 0 and height > 0:
            self.widget.draw()


class SpectrogramPlot(RealTimePlot):
    """
    A real-time spectrogram widget for time-frequency visualization of incoming data.
    """

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)

        # Graph variables
        self.curr_cha = None
        self.win_t = None
        self.win_s = None
        self.win_t_spec = None
        self.win_s_spec = None
        self.time_in_graph = None
        self.sig_in_graph = None
        self.marker = None
        self.marker_color = self.theme_colors['THEME_SIGNAL_MARKER']
        self.marker_width = 2

        # Spectrogram-specific handles
        self.ax = None         # Matplotlib axes
        self.im = None         # The image (imshow) handle

        # Create figure & widget
        fig = Figure()
        fig.add_subplot(111)
        fig.tight_layout()
        fig.patch.set_color(self.theme_colors['THEME_BG_DARK'])
        self.widget = FigureCanvasQTAgg(fig)
        self.widget.figure.set_size_inches(0, 0)
        self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Custom menu
        self.plot_menu = None
        self.widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.widget.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, pos: QPoint):
        """
        Called automatically on right-click within the canvas.
        pos is in widget coordinates, so we map it to global coords.
        """
        menu = SelectChannelMenu(self)
        menu.set_channel_list()
        global_pos = self.widget.mapToGlobal(pos)
        menu.exec_(global_pos)

    @staticmethod
    def check_signal(lsl_stream_info):
        """Checks that the incoming signal is compatible."""
        return True

    @staticmethod
    def get_default_settings(stream_info=None):
        """
        Returns a tuple: (signal_settings, visualization_settings).
        Adjust or rename keys to your needs.
        """
        # Basic signal-processing settings
        signal_settings = SettingsTree()
        signal_settings.add_item("update_rate", default_value=0.2, info="Update rate (s) of the plot", value_range=[0, None])
        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item("apply", default_value=True, info="Apply IIR filter in real-time")
        freq_filt.add_item("type", default_value="highpass", value_options=["highpass", "lowpass", "bandpass", "stopband"], info="Filter type")
        freq_filt.add_item("cutoff_freq", default_value=[1.0], info="List with one cutoff for highpass/lowpass, two for bandpass/stopband")
        freq_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item("apply", default_value=False, info="Apply notch filter to get rid of power line interference")
        notch_filt.add_item("freq", default_value=50.0, info="Center frequency to be filtered", value_range=[0, None])
        notch_filt.add_item("bandwidth", default_value=[-0.5, 0.5], info="List with relative limits of center frequency")
        notch_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item("apply", default_value=False, info="Change the reference of your signals")
        re_ref.add_item("type", default_value="car", value_options=["car", "channel"], info="Type of re-referencing: Common Average Reference or channel subtraction")
        if stream_info is not None:
            re_ref.add_item("channel", default_value=stream_info.l_cha[0], info="Channel label for re-referencing if channel is selected",value_options=stream_info.l_cha)
        else:
            re_ref.add_item("channel", default_value="", info="Channel label for re-referencing if channel is selected")
        down_samp= signal_settings.add_item("downsampling")
        down_samp.add_item("apply", default_value=False, info="Reduce the sample rate of the incoming LSL stream")
        down_samp.add_item("factor", default_value=2.0, info="Downsampling factor", value_range=[0, None])
        spectrogram = signal_settings.add_item("spectrogram")
        spectrogram.add_item("time_window", default_value=5.0, info="Time (s) of data kept in the buffer", value_range=[0, None])
        spectrogram.add_item("overlap_pct", default_value=90.0, info="Overlap (%) of segment length", value_range=[0,100])
        spectrogram.add_item("scale_to", default_value="psd", info="Choose how the spectrogram is scaled, so it represents either magnitude or a PSD spectrum.", value_options=["psd", "magnitude"])
        spectrogram.add_item("smooth", default_value=True, info="Use gaussian filter to smooth the final result")
        spectrogram.add_item("smooth_sigma", default_value=2.0, info="Sigma value used for the gaussian filter", value_range=[0, None])
        spectrogram.add_item("apply_detrend", default_value=True, info="Apply linear de-trending to the signal before the STFT")
        spectrogram.add_item("apply_normalization", default_value=True, info="Apply normalization to have a standard deviation of 1 before applying the STFT")
        spectrogram.add_item("log_power", default_value=True, info="Apply normalization before STFT")

        visualization_settings = SettingsTree()
        visualization_settings.add_item("mode", default_value="geek", info="Determine how events are visualized. Clinical, update in sweeping manner. Geek, signal appears continuously.", value_options=["clinical", "geek"])
        if stream_info is not None:
            visualization_settings.add_item("init_channel_label", default_value=stream_info.l_cha[0],
                                            info="Initial channel selected for visualization",
                                            value_options=stream_info.l_cha)
        else:
            visualization_settings.add_item("init_channel_label", default_value="", info="Channel selected for visualization")
        visualization_settings.add_item("display_grid", default_value=False, info="Visibility of the grid")
        visualization_settings.add_item("title_label_size", default_value=10.0, info="Title label size", value_range=[0, None])
        x_ax = visualization_settings.add_item("x_axis")
        x_ax.add_item("seconds_displayed", default_value=30.0, info="The time range (s) displayed", value_range=[0, None])
        x_ax.add_item("tick_separation", default_value=1.0, info="Tick separation", value_range=[0, None])
        x_ax.add_item("tick_label_size", default_value=8.0, info="Tick label size", value_range=[0, None])
        x_ax.add_item("label", default_value="<b>Time</b> (s)", info="Label for x-axis")
        x_ax.add_item("label_size", default_value=8.0, info="Label size", value_range=[0, None])
        y_ax = visualization_settings.add_item("y_axis")
        y_ax.add_item("range", default_value=[0, 30], info="Range of y-axis")
        y_ax.add_item("tick_separation", default_value=5.0, info="Tick separation", value_range=[0, None])
        y_ax.add_item("tick_label_size", default_value=8.0, info="Tick label size", value_range=[0, None])
        y_ax.add_item("label", default_value="<b>Frequency</b> (Hz)", info="Label for y-axis")
        y_ax.add_item("label_size", default_value=8.0, info="Label size", value_range=[0, None])
        z_ax = visualization_settings.add_item("z_axis")
        z_ax.add_item("cmap", default_value="inferno", info="Matplotlib colormap")
        clim = z_ax.add_item("clim")
        clim.add_item("auto", default_value=True, info="Click for automatic color bar limits computation")
        clim.add_item("values", default_value=[0.0, 1.0], info="Max and min bar limits customized")
        plot_adj = visualization_settings.add_item("plot_adjustment", info="Adjust layout margins for fine-tuning spacing within the figure")
        plot_adj.add_item("left", default_value=0.03, info="", value_range=[0,None])
        plot_adj.add_item("right", default_value=0.995, info="", value_range=[0, None])
        plot_adj.add_item("top", default_value=0.94, info="", value_range=[0, None])
        plot_adj.add_item("bottom", default_value=0.1, info="", value_range=[0, None])
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel").\
            edit_item(default_value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        visualization_settings.get_item("init_channel_label").\
            edit_item(default_value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, plot_settings):
        """Validate incoming settings if needed."""
        return True

    # def select_channel(self, cha):
    #     """ This function changes the channel used to compute the PSD displayed
    #     in the graph.
    #
    #     :param cha: sample frequency in Hz
    #     """
    #     self.curr_cha = cha
    #     self.ax.set_title(
    #         f'{self.lsl_stream_info.l_cha[cha]}',
    #         color=self.theme_colors['THEME_TEXT_LIGHT'],
    #         fontsize=self.visualization_settings['title_label_size'])



    def init_plot(self):
        """
        Initialize the spectrogram plot, figure, axes, etc.
        This is called once, when the stream is first set up.
        """
        # Update view box menu
        self.plot_menu = SelectChannelMenu(self)
        self.plot_menu.set_channel_list()

        # Inherit the main time-window size from the settings
        self.win_t = self.visualization_settings['x_axis']['seconds_displayed']
        self.win_s = int(self.win_t * self.fs)

        # Spectrogram window
        self.win_t_spec = self.signal_settings['spectrogram']['time_window']
        self.win_s_spec = (
            int(self.signal_settings['spectrogram']['time_window'] * self.fs))

        # Initialize buffers
        self.time_in_graph = np.zeros(0)
        self.sig_in_graph = np.zeros((0, self.lsl_stream_info.n_cha))

        # Axis
        self.y_range = self.visualization_settings['y_axis']['range']
        if not isinstance(self.y_range, list):
            self.y_range = [0, self.y_range]

        # Prepare a single axes for the spectrogram
        self.ax = self.widget.figure.axes[0]
        self.ax.set_facecolor(self.theme_colors['THEME_BG_DARK'])
        self.ax.set_xlabel(
            'Time (s)', color=self.theme_colors['THEME_TEXT_LIGHT'],
            fontsize=self.visualization_settings['y_axis']['label_size'])
        self.ax.set_ylabel(
            'Frequency (Hz)', color=self.theme_colors['THEME_TEXT_LIGHT'],
            fontsize=self.visualization_settings['y_axis']['label_size'])
        self.ax.spines['left'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['bottom'].set_visible(False)
        self.widget.figure.subplots_adjust(
            left=self.visualization_settings['plot_adjustment']['left'],
            right=self.visualization_settings['plot_adjustment']['right'],
            top=self.visualization_settings['plot_adjustment']['top'],
            bottom=self.visualization_settings['plot_adjustment']['bottom'])

        if self.visualization_settings['mode'] == 'clinical':
            self.marker = self.ax.axvline(x=0, color=self.marker_color,
                                          linewidth=self.marker_width)
            self.pointer = -1

        # Set initial channel
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label)
        self.plot_menu.select_channel(init_cha)

        # Display initial array
        height, width = 1, 1
        rgb_tuple = gui_utils.hex_to_rgb(self.theme_colors['THEME_BG_MID'], scale=True)
        solid_color = np.ones((height, width, 3)) * rgb_tuple
        self.im = self.ax.imshow(
            solid_color,
            aspect='auto',
            origin='lower')
        self.im.set_extent((0, width, self.y_range[0], self.y_range[1]))
        self.draw_y_axis_ticks()
        self.ax.tick_params(
            axis='x', colors=self.theme_colors['THEME_TEXT_LIGHT'],
            labelsize=self.visualization_settings['x_axis']['tick_label_size'])
        self.ax.tick_params(
            axis='y', colors=self.theme_colors['THEME_TEXT_LIGHT'],
            labelsize=self.visualization_settings['y_axis']['tick_label_size'])
        self.widget.draw()

    def draw_y_axis_ticks(self):
        # Settings
        display_grid = self.visualization_settings.get('display_grid', True)
        tick_sep = self.visualization_settings[
            'y_axis'].get('tick_separation', 1.0)
        # Time ticks
        y_ticks_pos = np.arange(self.y_range[0], self.y_range[1]+1e-12,
                                step=tick_sep).tolist()
        y_ticks_val = [f'{val:.1f}' for val in y_ticks_pos]
        if display_grid:
            self.ax.grid(True, color=self.theme_colors['THEME_TEXT_LIGHT'],
                         linestyle='-', linewidth=0.5)
        # Set limits, ticks, and labels
        self.ax.set_ylim(self.y_range[0], self.y_range[1])
        self.ax.set_yticks(y_ticks_pos)
        self.ax.set_yticklabels(y_ticks_val)

    def draw_x_axis_ticks(self):
        if len(self.time_in_graph) > 0:
            # Settings
            mode = self.visualization_settings.get('mode', 'geek')
            display_grid = self.visualization_settings.get('display_grid', True)
            tick_sep = self.visualization_settings[
                'x_axis'].get('tick_separation', 1.0)

            if mode == 'geek':
                # Set timestamps
                x = self.time_in_graph
                # Range
                x_range = (x[0], x[-1])
                # Time ticks
                x_ticks_pos = np.arange(x[0], x[-1], step=tick_sep).tolist()
                x_ticks_val = [f'{val:.1f}' for val in x_ticks_pos]
                # Set limits, ticks, and labels
                self.ax.set_xlim(x_range[0], x_range[1])
                self.ax.set_xticks(x_ticks_pos)
                self.ax.set_xticklabels(x_ticks_val)

            elif mode == 'clinical':
                # Set timestamps
                x = np.mod(self.time_in_graph, self.win_t)
                # Range
                n_win = self.time_in_graph.max() // self.win_t
                x_range = (0, self.win_t) if n_win==0 else (x[0], x[-1])
                # Time ticks
                x_ticks_pos = []
                x_ticks_val = []
                if self.visualization_settings['display_grid']:
                    step = self.visualization_settings[
                        'x_axis']['tick_separation']
                    x_ticks_pos = np.arange(x[0], x[-1], step=step).tolist()
                    x_ticks_val = ['' for v in x_ticks_pos]
                # Add pointer tick
                x_ticks_pos.append(x[self.pointer])
                x_ticks_val.append(f'{self.time_in_graph[self.pointer]:.1f}')
                # Set limits, ticks, and labels
                self.ax.set_xlim(x_range[0], x_range[1])
                self.ax.set_xticks(x_ticks_pos)
                self.ax.set_xticklabels(x_ticks_val,
                                        color=self.theme_colors['THEME_TEXT_LIGHT'])
            else:
                raise ValueError

            if display_grid:
                self.ax.grid(True, color=self.theme_colors['THEME_TEXT_LIGHT'],
                             linestyle='-', linewidth=2)
        else:
            self.ax.set_xticks([])
            self.ax.set_xlim(0, 1)
            self.ax.grid(False)

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

    def update_plot(self, chunk_times, chunk_signal):
        """
        Append the new data, then recalc and update the spectrogram.
        """
        try:
            # Init time
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if self.visualization_settings['mode'] == 'clinical':
                    self.ax.add_line(self.marker)
            # Temporal series are always plotted from zero.
            chunk_times = chunk_times - self.init_time
            # Append new data into our ring buffers
            t_in_graph, sig_in_graph = self.append_data(chunk_times, chunk_signal)
            time_window = self.signal_settings['spectrogram']['time_window'] \
                if len(t_in_graph) >= self.win_s_spec else len(t_in_graph) / self.fs

            # Chronological reordering of the signal
            if self.visualization_settings['mode'] == 'clinical':
                signal = np.vstack((sig_in_graph[np.argmax(t_in_graph)+1:],
                                       sig_in_graph[:np.argmax(t_in_graph)+1]))
            else:
                signal = sig_in_graph.copy()

            # Compute spectrogram
            spec, t, f = fourier_spectrogram(
                signal[:, self.curr_cha], self.fs,
                time_window=time_window,
                overlap_pct=self.signal_settings['spectrogram'][
                    'overlap_pct'],
                smooth=self.signal_settings['spectrogram'][
                    'smooth'],
                smooth_sigma=self.signal_settings['spectrogram'][
                    'smooth_sigma'],
                apply_detrend=self.signal_settings['spectrogram'][
                    'apply_detrend'],
                apply_normalization=self.signal_settings['spectrogram'][
                    'apply_normalization'],
                scale_to=self.signal_settings['spectrogram']['scale_to'])

            # Optionally convert to log scale
            if self.signal_settings['spectrogram']['log_power']:
                spec = 10 * np.log10(spec + 1e-12)

            # Update the image
            if self.visualization_settings['mode'] == 'clinical':
                # Update the time marker
                x = np.mod(self.time_in_graph, self.win_t)
                self.marker.set_xdata([x[self.pointer]])

                if t_in_graph.max() < self.win_t:
                    self.im.set_extent(
                        [t_in_graph[0], t_in_graph[-1], f[0], f[-1]])
                else:
                    # Redefine the t_in_graph vector to match t dimensions
                    interp_func = interpolate.interp1d(
                        np.linspace(0, 1, len(t_in_graph)),
                        t_in_graph, kind='linear',
                        fill_value="extrapolate")
                    t_resampled = interp_func(
                        np.linspace(0, 1, len(t)))
                    # Reorder the spectrogram
                    idx = np.argmax(t_resampled)
                    if idx < spec.shape[1] - 1:
                        spec = np.hstack((spec[:,-idx - 1:].copy(),
                                          spec[:,: -idx -1].copy()))

            elif self.visualization_settings['mode'] == 'geek':
                self.im.set_extent(
                    [t_in_graph[0], t_in_graph[-1], f[0], f[-1]])

            self.im.set_data(spec)
            self.draw_x_axis_ticks()
            self.draw_y_axis_ticks()

            # Set color limits if desired
            if self.visualization_settings['z_axis']['clim']['auto']:
                self.im.autoscale()
            else:
                self.im.set_clim(
                    self.visualization_settings['z_axis']['clim']['values'][0],
                    self.visualization_settings['z_axis']['clim']['values'][1])

            # Redraw only if widget has nonzero size
            width, height = self.widget.get_width_height()
            if width > 0 and height > 0:
                self.widget.draw()

        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        """
        Clear the internal figure or re-init image.
        """
        self.ax.clear()
        width, height = self.widget.get_width_height()
        if width > 0 and height > 0:
            self.widget.draw()


class PowerDistributionPlot(SpectrogramPlot):
    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)

        # Inicializar parámetros propios
        self.frequency_bands = None
        self.cmap = None
        self.patches = None

    @staticmethod
    def get_default_settings(stream_info=None):
        """
        Returns a tuple: (signal_settings, visualization_settings).
        Adjust or rename keys to your needs.
        """
        # Basic signal-processing settings
        signal_settings = SettingsTree()
        signal_settings.add_item("update_rate", default_value=0.2, info="Update rate (s) of the plot", value_range=[0, None])
        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item("apply", default_value=True, info="Apply IIR filter in real-time")
        freq_filt.add_item("type", default_value="highpass", value_options=["highpass", "lowpass", "bandpass", "stopband"], info="Filter type")
        freq_filt.add_item("cutoff_freq", default_value=[1], info="List with one cutoff for highpass/lowpass, two for bandpass/stopband")
        freq_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item("apply", default_value=False, info="Apply notch filter to get rid of power line interference")
        notch_filt.add_item("freq", default_value=50.0, info="Center frequency to be filtered", value_range=[0, None])
        notch_filt.add_item("bandwidth", default_value=[-0.5, 0.5], info="List with relative limits of center frequency")
        notch_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item("apply", default_value=False, info="Change the reference of your signals")
        re_ref.add_item("type", default_value="car", value_options=["car", "channel"], info="Type of re-referencing: Common Average Reference or channel subtraction")
        if stream_info is not None:
            re_ref.add_item("channel", default_value=stream_info.l_cha[0], info="Channel label for re-referencing if channel is selected",value_options=stream_info.l_cha)
        else:
            re_ref.add_item("channel", default_value="", info="Channel label for re-referencing if channel is selected")
        down_samp= signal_settings.add_item("downsampling")
        down_samp.add_item("apply", default_value=False, info="Reduce the sample rate of the incoming LSL stream")
        down_samp.add_item("factor", default_value=2.0, info="Downsampling factor", value_range=[0, None])
        spectrogram = signal_settings.add_item("spectrogram")
        spectrogram.add_item("time_window", default_value=5.0, info="Time (s) of data kept in the buffer", value_range=[0, None])
        spectrogram.add_item("overlap_pct", default_value=90.0, info="Overlap (%) of segment length", value_range=[0,100])
        spectrogram.add_item("scale_to", default_value="psd", info="Choose how the spectrogram is scaled, so it represents either magnitude or a PSD spectrum.", value_options=["psd", "magnitude"])
        spectrogram.add_item("smooth", default_value=True, info="Use gaussian filter to smooth the final result")
        spectrogram.add_item("smooth_sigma", default_value=2.0, info="Sigma value used for the gaussian filter", value_range=[0, None])
        spectrogram.add_item("apply_detrend", default_value=True, info="Apply linear de-trending to the signal before the STFT")
        spectrogram.add_item("apply_normalization", default_value=True, info="Apply normalization to have a standard deviation of 1 before applying the STFT")
        spectrogram.add_item("log_power", default_value=True, info="Apply normalization before STFT")

        power_distribution = signal_settings.add_item(
            "power_distribution")
        power_distribution.add_item('label', default_value=['Delta', 'Theta', 'Alpha', 'Beta 1', 'Beta 2'], info='List with a names of the frequency bands')
        power_distribution.add_item("lower_limit", default_value=[1,4,8,13,20], info="List with lower limits (in Hz) of each of the frequency bands")
        power_distribution.add_item("upper_limit", default_value=[4, 8, 13, 20, 30],
                       info="List with upper limits (in Hz) of each of the frequency bands")
        visualization_settings = SettingsTree()
        visualization_settings.add_item("mode", default_value="geek", info="Determine how events are visualized. Clinical, update in sweeping manner. Geek, signal appears continuously.", value_options=["clinical", "geek"])
        if stream_info is not None:
            visualization_settings.add_item("init_channel_label", default_value=stream_info.l_cha[0],
                                            info="Initial channel selected for visualization",
                                            value_options=stream_info.l_cha)
        else:
            visualization_settings.add_item("init_channel_label", default_value="", info="Channel selected for visualization")
        visualization_settings.add_item("display_grid", default_value=False, info="Visibility of the grid")
        visualization_settings.add_item("title_label_size", default_value=10.0, info="Title label size", value_range=[0, None])
        x_ax = visualization_settings.add_item("x_axis")
        x_ax.add_item("seconds_displayed", default_value=30.0, info="The time range (s) displayed", value_range=[0, None])
        x_ax.add_item("tick_separation", default_value=1.0, info="Tick separation", value_range=[0, None])
        x_ax.add_item("tick_label_size", default_value=8.0, info="Tick label size", value_range=[0, None])
        x_ax.add_item("label", default_value="<b>Time</b> (s)", info="Label for x-axis")
        x_ax.add_item("label_size", default_value=8.0, info="Label size", value_range=[0, None])
        y_ax = visualization_settings.add_item("y_axis")
        y_ax.add_item("range", default_value=[0, 100], info="Range of y-axis")
        y_ax.add_item("tick_separation", default_value=5.0, info="Tick separation", value_range=[0, None])
        y_ax.add_item("tick_label_size", default_value=8.0, info="Tick label size", value_range=[0, None])
        y_ax.add_item("label", default_value="<b>Frequency</b> (Hz)", info="Label for y-axis")
        y_ax.add_item("label_size", default_value=8.0, info="Label size", value_range=[0, None])
        color = visualization_settings.add_item("color")
        color.add_item("cmap", default_value="Accent", info="Matplotlib colormap")
        clim = color.add_item("clim")
        clim.add_item("auto", default_value=True, info="Click for automatic color bar limits computation")
        clim.add_item("values", default_value=[0.0, 1.0], info="Max and min bar limits customized")
        plot_adj = visualization_settings.add_item("plot_adjustment", info="Adjust layout margins for fine-tuning spacing within the figure")
        plot_adj.add_item("left", default_value=0.03, info="", value_range=[0,None])
        plot_adj.add_item("right", default_value=0.995, info="", value_range=[0, None])
        plot_adj.add_item("top", default_value=0.94, info="", value_range=[0, None])
        plot_adj.add_item("bottom", default_value=0.1, info="", value_range=[0, None])
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel").\
            edit_item(default_value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        visualization_settings.get_item("init_channel_label").\
            edit_item(default_value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    def init_plot(self):
        """
        Initialize the spectrogram plot, figure, axes, etc.
        This is called once, when the stream is first set up.
        """
        # Update view box menu
        self.plot_menu = SelectChannelMenu(self)
        self.plot_menu.set_channel_list()

        # Update frequency bands dict
        self.frequency_bands = self.signal_settings['power_distribution']

        # Inherit the main time-window size from the settings
        self.win_t = self.visualization_settings['x_axis']['seconds_displayed']
        self.win_s = int(self.win_t * self.fs)

        # Spectrogram window
        self.win_t_spec = self.signal_settings['spectrogram']['time_window']
        self.win_s_spec = (
            int(self.signal_settings['spectrogram']['time_window'] * self.fs))

        # Initialize buffers
        self.time_in_graph = np.zeros(0)
        self.sig_in_graph = np.zeros((0, self.lsl_stream_info.n_cha))


        # Axis
        self.y_range = self.visualization_settings['y_axis']['range']
        if not isinstance(self.y_range, list):
            self.y_range = [0, self.y_range]

        # Prepare a single axes for the spectrogram
        self.ax = self.widget.figure.axes[0]
        self.ax.set_facecolor(self.theme_colors['THEME_BG_DARK'])
        self.ax.set_xlabel(
            'Time (s)', color=self.theme_colors['THEME_TEXT_LIGHT'],
            fontsize=self.visualization_settings['y_axis']['label_size'])
        self.ax.set_ylabel(
            'Frequency (Hz)', color=self.theme_colors['THEME_TEXT_LIGHT'],
            fontsize=self.visualization_settings['y_axis']['label_size'])
        self.ax.spines['left'].set_visible(False)
        self.ax.spines['right'].set_visible(False)
        self.ax.spines['top'].set_visible(False)
        self.ax.spines['bottom'].set_visible(False)
        self.widget.figure.subplots_adjust(
            left=self.visualization_settings['plot_adjustment']['left'],
            right=self.visualization_settings['plot_adjustment']['right'],
            top=self.visualization_settings['plot_adjustment']['top'],
            bottom=self.visualization_settings['plot_adjustment']['bottom'])

        if self.visualization_settings['mode'] == 'clinical':
            self.marker = self.ax.axvline(x=0, color=self.marker_color,
                                          linewidth=self.marker_width)
            self.pointer = -1

        # Patches
        self.cmap = get_cmap(self.visualization_settings['color']['cmap'])
        self.patches = []
        for i in range(self.frequency_bands['label'].__len__()):
            patch_style = {'color': self.cmap.colors[i],
                           'alpha': 1}
            patch,_ = self.ax.fill([],[],[],**patch_style)
            self.patches.append(patch)

        # Set initial channel
        init_cha_label = self.visualization_settings['init_channel_label']
        init_cha = self.worker.receiver.get_channel_indexes_from_labels(init_cha_label)
        self.plot_menu.select_channel(init_cha)


        # Display initial array
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()
        self.ax.tick_params(
            axis='x', colors=self.theme_colors['THEME_TEXT_LIGHT'],
            labelsize=self.visualization_settings['x_axis']['tick_label_size'])
        self.ax.tick_params(
            axis='y', colors=self.theme_colors['THEME_TEXT_LIGHT'],
            labelsize=self.visualization_settings['y_axis']['tick_label_size'])
        self.widget.draw()

    def update_plot(self, chunk_times, chunk_signal):
        """
        Append the new data, then recalc and update the spectrogram.
        """
        try:
            # Init time
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if self.visualization_settings['mode'] == 'clinical':
                    self.ax.add_line(self.marker)
            # Temporal series are always plotted from zero.
            chunk_times = chunk_times - self.init_time
            # Append new data into our ring buffers
            t_in_graph, sig_in_graph = self.append_data(chunk_times, chunk_signal)
            time_window = self.signal_settings['spectrogram']['time_window'] \
                if len(t_in_graph) >= self.win_s_spec else len(t_in_graph) / self.fs

            # Chronological reordering of the signal
            if self.visualization_settings['mode'] == 'clinical':
                signal = np.vstack((sig_in_graph[np.argmax(t_in_graph)+1:],
                                       sig_in_graph[:np.argmax(t_in_graph)+1]))
            else:
                signal = sig_in_graph.copy()

            # Compute spectrogram
            spec, t, f = fourier_spectrogram(
                signal[:, self.curr_cha], self.fs,
                time_window=time_window,
                overlap_pct=self.signal_settings['spectrogram'][
                    'overlap_pct'],
                smooth=self.signal_settings['spectrogram'][
                    'smooth'],
                smooth_sigma=self.signal_settings['spectrogram'][
                    'smooth_sigma'],
                apply_detrend=self.signal_settings['spectrogram'][
                    'apply_detrend'],
                apply_normalization=self.signal_settings['spectrogram'][
                    'apply_normalization'],
                scale_to=self.signal_settings['spectrogram']['scale_to'])

            # Redefine the t_in_graph vector to match t dimensions
            interp_func = interpolate.interp1d(np.linspace(0, 1, len(t_in_graph)),
                                   t_in_graph, kind='linear',
                                   fill_value="extrapolate")
            t_in_graph_resampled = interp_func(np.linspace(0, 1, len(t)))

            # Limit t vector
            if len(t_in_graph_resampled) != spec.shape[1]:
                t_in_graph_resampled = t_in_graph_resampled[:spec.shape[1]]

            # Calculate x axis
            if self.visualization_settings['mode'] == 'geek':
                x = t_in_graph_resampled
            elif self.visualization_settings['mode'] == 'clinical':
                x = np.mod(t_in_graph_resampled, self.win_t)
                self.marker.set_xdata(
                    [np.mod(self.time_in_graph, self.win_t)[self.pointer]])

                # Reorder the spectrogram
                idx = np.argmax(t_in_graph_resampled)
                if idx < spec.shape[1] - 1:
                    spec = np.hstack((spec[:, -idx - 1:].copy(),
                                      spec[:, : -idx - 1].copy()))

            # Normalize each time bin
            spec_norm = spec / spec.sum(axis=0)
            # Calculate power distribution
            power_distribution = 0
            labels = []
            for i_b in range(self.frequency_bands['label'].__len__()):
                idx_min = np.absolute(f-self.frequency_bands['lower_limit'][i_b]).argmin()
                idx_max = np.absolute(f - self.frequency_bands['upper_limit'][i_b]).argmin()
                relative_power = spec_norm[idx_min:idx_max,:].sum(axis=0)*100
                power_distribution += relative_power

                labels.append(self.frequency_bands['label'][i_b])
                # Calculate each patch coordinates
                if i_b == 0:
                    # For the first band, the base is 0
                    patch_xy = np.column_stack(
                        (x, np.zeros_like(x)))  # Curve's base
                    patch_top = np.column_stack(
                        (x, power_distribution))  # Top of the curve
                else:
                    # For the rest, the base is the previous curve
                    patch_xy = np.column_stack(
                        (x, power_distribution - relative_power))  # Base
                    patch_top = np.column_stack((x,
                                                 power_distribution))  # Top

                # Set the patches
                self.patches[i_b].set_xy(
                    np.concatenate([patch_xy, patch_top[::-1]],
                                   axis=0))

            # Set the legend
            self.ax.legend(self.patches,labels,loc='upper right')


            self.draw_x_axis_ticks()
            self.draw_y_axis_ticks()

            # Redraw only if widget has nonzero size
            width, height = self.widget.get_width_height()
            if width > 0 and height > 0:
                self.widget.draw()

        except Exception as e:
            self.handle_exception(e)

    def clear_plot(self):
        """
        Clear the internal figure or re-init image.
        """
        self.ax.clear()
        width, height = self.widget.get_width_height()
        if width > 0 and height > 0:
            self.widget.draw()


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
    def check_signal(lsl_stream_info):
        if lsl_stream_info.medusa_type != 'EEG':
            raise ValueError('Wrong signal type %s. TopographyPlot only '
                             'supports EEG signals' %
                             (lsl_stream_info.medusa_type))
        return True



    @staticmethod
    def get_default_settings(stream_info=None):
        signal_settings = SettingsTree()
        signal_settings.add_item("update_rate", default_value=0.2, info="Update rate (s) of the plot", value_range=[0, None])
        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item("apply", default_value=True, info="Apply IIR filter in real-time")
        freq_filt.add_item("type", default_value="highpass", value_options=["highpass", "lowpass", "bandpass", "stopband"], info="Filter type")
        freq_filt.add_item("cutoff_freq", default_value=[1.0], info="List with one cutoff for highpass/lowpass, two for bandpass/stopband")
        freq_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item("apply", default_value=True, info="Apply notch filter to get rid of power line interference")
        notch_filt.add_item("freq", default_value=50.0, info="Center frequency to be filtered", value_range=[0, None])
        notch_filt.add_item("bandwidth", default_value=[-0.5, 0.5], info="List with relative limits of center frequency")
        notch_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item("apply", default_value=False, info="Change the reference of your signals")
        re_ref.add_item("type", default_value="car", value_options=["car", "channel"], info="Type of re-referencing: Common Average Reference or channel subtraction")
        if stream_info is not None:
            re_ref.add_item("channel", default_value=stream_info.l_cha[0], info="Channel label for re-referencing if channel is selected", value_options=stream_info.l_cha)
        else:
            re_ref.add_item("channel", default_value= "", info="Channel label for re-referencing if channel is selected")
        down_samp= signal_settings.add_item("downsampling")
        down_samp.add_item("apply", default_value=False, info="Reduce the sample rate of the incoming LSL stream")
        down_samp.add_item("factor", default_value=2.0, info="Downsampling factor", value_range=[0, None])
        psd = signal_settings.add_item("psd")
        psd.add_item("time_window", default_value=5.0, info="Time (s) in which the PSD will be estimated", value_range=[0, None])
        psd.add_item("welch_overlap_pct", default_value=25.0, info="Percentage of segment overlapping", value_range=[0, 100])
        psd.add_item("welch_seg_len_pct", default_value=50.0, info="Percentage of the window that will be used", value_range=[0, 100])
        psd.add_item("power_range", default_value=[8, 13], info="Frequency range of PSD")

        visualization_settings = SettingsTree()
        visualization_settings.add_item("title", default_value="<b>TopoPlot</b>", info="Title for the plot")
        visualization_settings.add_item("channel_standard", default_value="10-05", info="EEG channel standard", value_options=["10-20", "10-10", "10-05"])
        visualization_settings.add_item("head_radius", default_value=1.0, info="Head radius", value_range=[0, 1])
        visualization_settings.add_item("head_line_width", default_value=4.0, info="Line width for the head, ears and nose.", value_range=[0, None])
        visualization_settings.add_item("head_skin_color", default_value="#E8BEAC", info="Head skin color")
        visualization_settings.add_item("plot_channel_labels", default_value=False, info="Click to display the channel labels")
        visualization_settings.add_item("plot_channel_points", default_value=True, info="Click to display channel points")
        chan_radius_size = visualization_settings.add_item("channel_radius_size")
        chan_radius_size.add_item("auto", default_value=True, info="Click for automatic channel radius computation")
        chan_radius_size.add_item("value", default_value=0.0, info="Radius of the circle customized", value_range=[0, None])
        visualization_settings.add_item("interpolate", default_value=True, info="Click for interpolation in the visualization to occur")
        visualization_settings.add_item("extra_radius", default_value=0.29, info="Extra radius of the plot surface", value_range=[0, 1])
        visualization_settings.add_item("interp_neighbors", default_value=3, info="Number of nearest neighbors for interpolation", value_range=[1, None])
        visualization_settings.add_item("interp_points", default_value=100, info="Number of interpolation points", value_range=[0, None])
        visualization_settings.add_item("interp_contour_width", default_value=0.8, info="Line width of the contour lines", value_range=[0,None])
        visualization_settings.add_item("cmap", default_value="YlGnBu_r", info="Matplotlib colormap")
        clim = visualization_settings.add_item("clim")
        clim.add_item("auto", default_value=True, info="Click for automatic color bar limits computation")
        clim.add_item("values", default_value=[0.0, 1.0], info="Max and min bar limits customized")
        visualization_settings.add_item("label_color", default_value="w", info="Label color")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel").\
            edit_item(default_value=stream_info.l_cha[0], value_options=stream_info.l_cha)
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
        self.channel_set = (
            lsl_utils.lsl_channel_info_to_eeg_channel_set(
            self.lsl_stream_info.cha_info,
            discard_unlocated_channels=True))
        # Initialize
        if self.visualization_settings['channel_radius_size']['auto']:
            channel_radius_size = None
        else:
            channel_radius_size = self.visualization_settings['channel_radius_size']['value']
        if self.visualization_settings['clim']['auto']:
            clim = None
        else:
            clim = tuple(self.visualization_settings['clim']['values'])
        self.topo_plot = head_plots.TopographicPlot(
            axes=self.widget.figure.axes[0],
            channel_set=self.channel_set,
            head_radius=self.visualization_settings['head_radius'],
            head_line_width=self.visualization_settings['head_line_width'],
            head_skin_color=self.visualization_settings['head_skin_color'],
            plot_channel_labels=self.visualization_settings['plot_channel_labels'],
            plot_channel_points=self.visualization_settings['plot_channel_points'],
            channel_radius_size=channel_radius_size,
            interpolate=self.visualization_settings['interpolate'],
            extra_radius=self.visualization_settings['extra_radius'],
            interp_neighbors=self.visualization_settings['interp_neighbors'],
            interp_points=self.visualization_settings['interp_points'],
            interp_contour_width=self.visualization_settings['interp_contour_width'],
            cmap=self.visualization_settings['cmap'],
            clim=clim,
            label_color=self.visualization_settings['label_color'])
        # Signal processing
        self.win_s = int(self.signal_settings['psd']['time_window'] * self.fs)
        # Update view box menu
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.channel_set.n_cha])

    def update_plot(self, chunk_times, chunk_signal):
        try:
            # print('Chunk received at: %.6f' % time.time())
            # Append new data and get safe copy
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
    def check_signal(lsl_stream_info):
        if lsl_stream_info.medusa_type != 'EEG':
            raise ValueError('Wrong signal type %s. ConnectivityPlot only '
                             'supports EEG signals' %
                             (lsl_stream_info.medusa_type))
        return True

    @staticmethod
    def get_default_settings(stream_info=None):
        signal_settings = SettingsTree()
        signal_settings.add_item("update_rate", default_value=0.2, info="Update rate (s) of the plot", value_range=[0, None])
        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item("apply", default_value=True, info="Apply IIR filter in real-time")
        freq_filt.add_item("type", default_value="highpass", value_options=["highpass", "lowpass", "bandpass", "stopband"], info="Filter type")
        freq_filt.add_item("cutoff_freq", default_value=[1.0], info="List with one cutoff for highpass/lowpass, two for bandpass/stopband")
        freq_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item("apply", default_value=True, info="Apply notch filter to get rid of power line interference")
        notch_filt.add_item("freq", default_value=50.0, info="Center frequency to be filtered", value_range=[0, None])
        notch_filt.add_item("bandwidth", default_value=[-0.5, 0.5], info="List with relative limits of center frequency")
        notch_filt.add_item("order", default_value=5, info="Order of the filter (the higher, the greater computational cost)", value_range=[1, None])
        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item("apply", default_value=False, info="Change the reference of your signals")
        re_ref.add_item("type", default_value="car", value_options=["car", "channel"], info="Type of re-referencing: Common Average Reference or channel subtraction")
        if stream_info is not None:
            re_ref.add_item("channel", default_value=stream_info.l_cha[0],
                            info="Channel label for re-referencing if channel is selected",
                            value_options=stream_info.l_cha)
        else:
            re_ref.add_item("channel", default_value="", info="Channel label for re-referencing if channel is selected")
        down_samp= signal_settings.add_item("downsampling")
        down_samp.add_item("apply", default_value=False, info="Reduce the sample rate of the incoming LSL stream")
        down_samp.add_item("factor", default_value=2.0, info="Downsampling factor", value_range=[0, None])
        connectivity = signal_settings.add_item("connectivity")
        connectivity.add_item("time_window", default_value=2.0, info="Time (s) window size", value_range=[0, None])
        connectivity.add_item("conn_metric", default_value="aec", info="Connectivity metric", value_options=['aec','plv','pli','wpli'])
        connectivity.add_item("threshold", default_value=50.0, info="Threshold for connectivity", value_range=[0, None])
        connectivity.add_item("band_range", default_value=[8, 13], info="Frequency band")

        visualization_settings = SettingsTree()
        visualization_settings.add_item("title", default_value="<b>ConnectivityPlot</b>", info="Title for the plot")
        visualization_settings.add_item("channel_standard", default_value="10-05", info="EEG channel standard", value_options=["10-20", "10-10", "10-05"])
        visualization_settings.add_item("head_radius", default_value=1.0, info="Head radius", value_range=[0, 1])
        visualization_settings.add_item("head_line_width", default_value=4.0, info="Line width for the head, ears and nose.", value_range=[0, None])
        visualization_settings.add_item("head_skin_color", default_value="#E8BEAC", info="Head skin color")
        visualization_settings.add_item("plot_channel_labels", default_value=False, info="Click to display the channel labels")
        visualization_settings.add_item("plot_channel_points", default_value=True, info="Click to display channel points")
        chan_radius_size = visualization_settings.add_item("channel_radius_size")
        chan_radius_size.add_item("auto", default_value=False, info="Click for automatic channel radius computation")
        chan_radius_size.add_item("value", default_value=0.0, info="Radius of the circle customized", value_range=[0, None])
        visualization_settings.add_item("percentile_th", default_value=85.0, info="Value to establish a representation threshold")
        visualization_settings.add_item("cmap", default_value="RdBu", info="Matplotlib colormap")
        clim = visualization_settings.add_item("clim")
        clim.add_item("auto", default_value=True, info="Click for automatic color bar limits computation")
        clim.add_item("values", default_value=[0.0, 1.0], info="Max and min bar limits customized")
        visualization_settings.add_item("label_color", default_value="w", info="Label color")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel").\
            edit_item(default_value=stream_info.l_cha[0], value_options=stream_info.l_cha)
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
        self.channel_set = (
            lsl_utils.lsl_channel_info_to_eeg_channel_set(
                self.lsl_stream_info.cha_info,
                discard_unlocated_channels=True))
        # Initialize
        if self.visualization_settings['channel_radius_size']['auto']:
            channel_radius_size = None
        else:
            channel_radius_size = self.visualization_settings['channel_radius_size']['value']
        if self.visualization_settings['clim']['auto']:
            clim = None
        else:
            clim = tuple(self.visualization_settings['clim']['values'])
        self.conn_plot = head_plots.ConnectivityPlot(
            axes=self.widget.figure.axes[0],
            channel_set=self.channel_set,
            head_radius=self.visualization_settings['head_radius'],
            head_line_width=self.visualization_settings['head_line_width'],
            head_skin_color=self.visualization_settings['head_skin_color'],
            plot_channel_labels=self.visualization_settings['plot_channel_labels'],
            plot_channel_points=self.visualization_settings['plot_channel_points'],
            channel_radius_size=channel_radius_size,
            percentile_th=self.visualization_settings['percentile_th'],
            cmap=self.visualization_settings['cmap'],
            clim=clim,
            label_color=self.visualization_settings['label_color'],
        )
        # Signal processing
        self.win_s = int(
            self.signal_settings['connectivity']['time_window'] * self.fs)
        # Update view box menu
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.channel_set.n_cha])
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

# ------------------------- AUXILIARY CLASSES ----------------------

class SelectChannelMenu(QMenu):
    """This class inherits from GMenu and implements the menu that appears
    when right click is performed on a graph
    """

    def __init__(self, plot_handler):
        """Class constructor

        Parameters
        -----------
        spec_plot_handler: PlotWidget
            PyQtGraph PlotWidget class where the actions are performed
        """
        super().__init__()
        # Pointer to the psd_plot_handler
        self.plot_handler = plot_handler

    def get_channel_label(self):
        """
        Triggered when the user picks a channel from the menu.
        Finds the action's text, which is the channel label, then
        calls psd_plot_handler.select_channel(...) on the correct index.
        """
        cha_label = self.sender().text()
        for i in range(self.plot_handler.lsl_stream_info.n_cha):
            if self.plot_handler.lsl_stream_info.l_cha[i] == cha_label:
                self.select_channel(i)
                break

    def select_channel(self, cha):
        """ This function changes the channel used to compute the PSD displayed
        in the graph.

        :param cha: sample frequency in Hz
        """
        self.plot_handler.curr_cha = cha
        self.plot_handler.ax.set_title(
            f'{self.plot_handler.lsl_stream_info.l_cha[cha]}',
            color=self.plot_handler.theme_colors['THEME_TEXT_LIGHT'],
            fontsize=self.plot_handler.visualization_settings['title_label_size'])

    def set_channel_list(self):
        """
        Creates a QAction for each channel in the LSL stream
        and connects it to select_channel().
        """
        for i in range(self.plot_handler.lsl_stream_info.n_cha):
            label = self.plot_handler.lsl_stream_info.l_cha[i]
            channel_action = QAction(label, self)
            channel_action.triggered.connect(self.get_channel_label)
            self.addAction(channel_action)

class AutorangeMenu(QMenu):
    """ This class inherits from GMenu and implements the menu that appears
    when right click is performed on the graph
    """

    def __init__(self, view, type='time'):
        """ Class constructor

        Parameters
        ----------
        view: PlotWidget
            PyQtGraph PlotWidget class where the actions are performed
        type: string
            Type of plot. Allowed options: 'time' and 'PSD'
        """
        QMenu.__init__(self)
        # Keep weakref to view to avoid circular reference (don't know why,
        # but this prevents the ViewBox from crash)
        self.view = view
        # Some options
        self.setTitle("View options")
        if type == 'time':
            self.auto_range_action_time = QAction("Autorange", self)
            self.auto_range_action_time.triggered.connect(self.auto_range_time)
            self.addAction(self.auto_range_action_time)
        elif type == 'PSD':
            self.auto_range_action_spect = QAction("Autorange", self)
            self.auto_range_action_spect.triggered.connect(self.auto_range_spect)
            self.addAction(self.auto_range_action_spect)
        else:
            raise ValueError('Unknown plot type %s. Possible options: %s' %
                             (type, ['time','PSD']))

    def calculate_cha_separation(self, data):
        # Parameters
        sep_factor = 1.8
        robust_percentiles = (5, 95)

        # --- Estimate the signal amplitudes ---
        p_low, p_high = robust_percentiles
        lo = np.nanpercentile(data, p_low, axis=0)
        hi = np.nanpercentile(data, p_high, axis=0)
        vpp = np.maximum(hi - lo, 1e-12)  # avoid zeros
        base_sep = np.nanmedian(vpp)  # representative amplitude
        cha_sep = float(base_sep * sep_factor)  # channel separation

        # Update parameter
        self.view.cha_separation = cha_sep

    def auto_range_spect(self):
        if self.view.sig_in_graph.__len__() == 0 or self.view.curves is None or self.view.n_cha == 0:
            return

        welch_seg_len = np.round(
            self.view.visualization_settings['psd']['welch_seg_len_pct'] /
            100.0 * self.view.sig_in_graph.shape[0]).astype(int)
        welch_overlap = np.round(
            self.view.visualization_settings['psd']['welch_overlap_pct'] /
            100.0 * welch_seg_len).astype(int)
        x_in_graph, y_in_graph = scp_signal.welch(
            self.view.sig_in_graph, fs=self.view.fs,
            nperseg=welch_seg_len, noverlap=welch_overlap,
            nfft=welch_seg_len, axis=0)
        self.calculate_cha_separation(y_in_graph)
        ax = self.view.ax

        # --- Define offsets ---
        offsets = np.arange(self.view.n_cha)[::-1] * self.view.cha_separation
        Y = y_in_graph + offsets
        for i, line in enumerate(self.view.curves):
            line.set_data(x_in_graph,Y[:, i])

        ax.autoscale(enable=True, axis='x', tight=True)
        ax.autoscale(enable=False, axis='y')

        self.view.draw_y_axis_ticks()

        # Draw
        self.view.widget.draw()

    def auto_range_time(self):
        """
        Recalcula separación vertical y límites para un plot de EEG en tiempo real.

        sep_factor:     factor multiplicativo sobre una amplitud robusta (mediana de p95-p5).
        robust_percentiles: percentiles para estimar amplitud por canal.
        pad_frac:       fracción de la separación usada como margen en ylim.
        """
        if self.view.sig_in_graph.__len__() == 0 or self.view.curves is None or self.view.n_cha == 0:
            return

        self.calculate_cha_separation(self.view.sig_in_graph)
        ax = self.view.ax

        # --- Define offsets ---
        offsets = np.arange(self.view.n_cha)[::-1] * self.view.cha_separation
        Y = self.view.sig_in_graph + offsets
        for i, line in enumerate(self.view.curves):
            line.set_ydata(Y[:, i])

        ax.autoscale(enable=True, axis='x', tight=True)
        ax.autoscale(enable=False, axis='y')

        self.view.draw_y_axis_ticks()

        # Draw
        self.view.widget.draw()


__plots_info__ = [
    {
        'uid': 'Time (multi-channel)',
        'description': 'Time-domain multi-channel visualization. Each channel '
                       'is displayed with a vertical offset for better '
                       'visualization',
        'class': TimePlotMultichannel
    },
    {
        'uid': 'Time (single-channel)',
        'description': 'Time-domain single-channel visualization of a signal.',
        'class': TimePlotSingleChannel
    },
    {
        'uid': 'PSD (multi-channel)',
        'description': 'Power spectral density (PSD) multi-channel '
                       'visualization. Each channel is displayed with a '
                       'vertical offset for better visualization',
        'class': PSDPlotMultichannel
    },
    {
        'uid': 'PSD (single-channel)',
        'description': 'Power spectral density (PSD) single-channel '
                       'visualization of signal.',
        'class': PSDPlotSingleChannel
    },
    {
        'uid': 'Spectrogram',
        'description': 'Real-time spectrogram showing the time–frequency '
                       'representation of signals.',
        'class': SpectrogramPlot
    },
    {
        'uid': 'Power Distribution',
        'description': 'Distribution of signal power across custom frequency '
                       'bands.',
        'class': PowerDistributionPlot
    },
    {
        'uid': 'Topography',
        'description': 'Real-time topographic scalp map for EEG/MEG signals.',
        'class': TopographyPlot
    },
    {
        'uid': 'Connectivity',
        'description': 'Real-time functional connectivity map for EEG/MEG '
                       'signals.',
        'class': ConnectivityPlot
    }
]