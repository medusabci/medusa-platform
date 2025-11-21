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
from matplotlib import transforms as mtransforms
from sklearn.externals.array_api_extra import apply_where

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


class BaseSignalSettings(SettingsTree):

    def __init__(self):
        super().__init__()
        # Min update time
        self.add_item(
            "min_update_time",
            value=0.1,
            value_range=[0, None],
            info=(
                "Minimum update interval (s) for refreshing the plot. This "
                "value may automatically increase to prevent system overload, "
                "depending on your hardware performance and the complexity of "
                "the plots panel configuration"
            ),
        )
        # Channel selection (updated later)
        self.add_item(
            "channel_selection",
            value=[],
            info="List of selected channel for this plot"
        )
        # Frequency filter
        freq_filt = self.add_item("frequency_filter")
        freq_filt.add_item(
            "apply",
            value=True,
            info="Apply IIR filter in real-time",
        )
        freq_filt.add_item(
            "type",
            value="highpass",
            value_options=["highpass", "lowpass", "bandpass", "stopband"],
            info="Filter type",
        )
        freq_filt.add_item(
            "cutoff_freq",
            value=[1],
            info=(
                "List with one cutoff for highpass/lowpass, two for "
                "bandpass/stopband"
            ),
        )
        freq_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "Order of the filter (the higher, the greater computational "
                "cost)"
            ),
        )
        # Notch filter
        notch_filt = self.add_item("notch_filter")
        notch_filt.add_item(
            "apply",
            value=True,
            info="Apply notch filter to get rid of power line interference",
        )
        notch_filt.add_item(
            "freq",
            value=50.0,
            value_range=[0, None],
            info="Center frequency to be filtered",
        )
        notch_filt.add_item(
            "bandwidth",
            value=[-0.5, 0.5],
            info="List with relative limits of center frequency",
        )
        notch_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "Order of the filter (the higher, the greater computational "
                "cost)"
            ),
        )

        # Referencing
        re_ref = self.add_item("re_referencing")
        re_ref.add_item(
            "apply",
            value=False,
            info="Change the reference of your signals",
        )
        re_ref.add_item(
            "type",
            value="car",
            value_options=["car", "channel"],
            info=(
                "Type of re-referencing: Common Average Reference or channel "
                "subtraction"
            ),
        )
        re_ref.add_item(
            "channel",
            value="",
            info="Channel label for re-referencing if channel is selected",
        )

        # Downsampling
        down_samp = self.add_item("downsampling")
        down_samp.add_item(
            "apply",
            value=False,
            info="Reduce the sample rate of the incoming LSL stream",
        )
        down_samp.add_item(
            "factor",
            value=2.0,
            value_range=[0, None],
            info="Downsampling factor",
        )

    def add_psd_settings(self):
        psd = self.add_item("psd")
        psd.add_item(
            "time_window_seconds",
            value=5.0,
            value_range=[0, None],
            info="Window length (s) used to estimate the PSD.",
        )
        psd.add_item(
            "welch_overlap_pct",
            value=25.0,
            value_range=[0, 100],
            info="Segment overlap for Welch’s method (%).",
        )
        psd.add_item(
            "welch_seg_len_pct",
            value=50.0,
            value_range=[0, 100],
            info="Segment length as a percentage of the window length (%).",
        )
        psd.add_item(
            "log_power", value=False,
            info="If True, display PSD in dB (10 * log10)."
        )

class BaseVisualizationSettings(SettingsTree):

    def __init__(self, include_mode=False):
        super().__init__()
        # Mode (optional)
        if include_mode:
            self.add_item(
                "mode",
                value="clinical",
                value_options=["clinical", "geek"],
                info=("Determine how events are visualized. "
                      "Clinical: sweeping update, computationally efficient. "
                      "Geek: signal appears continuously."
                )
            )
        # Title
        title = self.add_item("title")
        title.add_item(
            "text",
            value="auto",
            info="Title for the plot. If auto, the title will be set "
                 "automatically.",
        )
        title.add_item(
            "fontsize",
            value=12,
            info="Font size for the title"
        )
        # X-axis
        x_ax = self.add_item("x_axis")
        x_axis_label = x_ax.add_item("label")
        x_axis_label.add_item(
            "text",
            value="Time",
            info="Label for x-axis"
        )
        x_axis_label.add_item(
            "fontsize",
            value=10,
            info="Font size for x-axis label"
        )
        # Y-axis
        y_ax = self.add_item("y_axis")
        y_axis_label = y_ax.add_item("label")
        y_axis_label.add_item(
            "text",
            value="",
            info="Label for y-axis"
        )
        y_axis_label.add_item(
            "fontsize",
            value=10,
            info="Font size for y-axis label"
        )

    def add_grid_settings_to_axis(self, axis_item_key):
        axis_item = self.get_item(axis_item_key)
        grid_item = axis_item.add_item("grid")
        grid_item.add_item(
            "display",
            value=True,
            info="Visibility of the grid",
        )
        grid_item.add_item(
            "step",
            value=1.0,
            value_range=[0, None],
            info="Display grid's dimensions",
        )

    def add_zaxis_settings(self, cmap, clim):
        z_ax = self.add_item("z_axis")
        z_ax.add_item('cmap')



class RealTimePlot(ABC):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__()
        # Parameters
        self.uid = uid
        self.plot_state = plot_state
        self.medusa_interface = medusa_interface
        self.theme_colors = theme_colors
        # Style and  theme
        self.curve_color = self.theme_colors['THEME_SIGNAL_CURVE']
        self.grid_color = self.theme_colors['THEME_SIGNAL_GRID']
        self.marker_color = self.theme_colors['THEME_SIGNAL_MARKER']
        self.background_color = self.theme_colors['THEME_BG_DARK']
        self.text_color = self.theme_colors['THEME_TEXT_LIGHT']
        self.curve_width = 1
        self.grid_width = 1
        self.marker_width = 2
        self.marker_y_pos = -0.005
        # Init variables
        self.ready = False
        self.signal_settings = None
        self.visualization_settings = None
        self.lsl_stream_info = None
        self.worker = None
        self.init_time = None
        self.fs = None
        self.widget = None
        self.fig = None
        self.ax = None
        self.times_buffer = None
        self.data_buffer = None
        self.buffer_time = None
        self.x_in_graph = None
        self.y_in_graph = None
        self.l_cha = None
        self.n_cha = None
        self.cha_idx = None
        self.marker_line = None
        self.marker_tick = None
        self.marker_pos = None
        # Blitting
        self._bg_cache = None
        self._cached_elements = None
        # Init widget
        self.init_widget()

    def handle_exception(self, ex):
        self.medusa_interface.error(ex)

    def set_ready(self):
        self.ready = True

    def set_settings(self, signal_settings, plot_settings):
        self.check_settings(signal_settings, plot_settings)
        self.signal_settings = signal_settings
        self.visualization_settings = plot_settings

    def set_lsl_worker(self, lsl_stream_info):
        """Create a new lsl worker for each plot

        Parameters
        ----------
        lsl_stream_info: lsl_utils.LSLStreamWrapper
            LSL stream (medusa wrapper)
        """
        # Check signal
        self.check_signal(lsl_stream_info)
        # Save lsl info
        self.lsl_stream_info = lsl_stream_info
        # Set worker
        self.worker = RealTimePlotWorker(
            self.plot_state,
            self.lsl_stream_info,
            self.signal_settings,
            self.medusa_interface)
        self.worker.update.connect(self.update_plot_common,
                                   type=Qt.BlockingQueuedConnection)
        self.worker.error.connect(self.handle_exception)
        self.worker.finished.connect(self.destroy_plot)
        self.fs = self.worker.get_effective_fs()

    def get_widget(self):
        return self.widget

    def start(self):
        self.worker.start()

    def destroy_plot(self):
        # self.worker.wait()
        self.init_time = None
        self.clear_plot()
        self.init_plot_common()

    @classmethod
    def update_lsl_stream_related_settings_common(cls, signal_settings,
                                                  visualization_settings,
                                                  stream_info):
        # Update default re-referencing channel
        signal_settings.get_item("re_referencing", "channel"). \
            edit_item(value=stream_info.l_cha[0],
                      value_options=stream_info.l_cha)
        # Update channel list
        signal_settings.get_item("channel_selection").edit_item(
            value=stream_info.l_cha)
        # Custom updates
        return cls.update_lsl_stream_related_settings(
            signal_settings, visualization_settings, stream_info)

    def init_widget(self):
        # Init figure
        self.fig = Figure(figsize=(1, 1), dpi=90)
        self.ax = self.fig.add_subplot(111)
        self.fig.set_layout_engine('constrained', rect=[0, 0, 1, 1])
        # fig.subplots_adjust(left=0.005, right=0.995, bottom=0.005, top=0.995)
        self.fig.patch.set_facecolor(self.background_color)
        self.ax.set_facecolor(self.background_color)
        # Init widget
        self.widget = FigureCanvasQTAgg(self.fig)
        self.widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.widget.customContextMenuRequested.connect(self.show_context_menu)
        self.widget.wheelEvent = self.mouse_wheel_event

    def init_plot_common(self):
        # Channel selection
        self.l_cha = self.signal_settings.get_item_value('channel_selection')
        self.n_cha = len(self.l_cha)
        self.cha_idx = [i for i, label in enumerate(
            self.lsl_stream_info.l_cha) if label in self.l_cha]
        # Buffers
        self.times_buffer = np.zeros([0])
        self.data_buffer = np.zeros([0, self.n_cha])
        # Plot data
        self.x_in_graph = np.zeros([0])
        self.y_in_graph = np.zeros([0, self.n_cha])
        # Set titles
        self.set_titles()
        # Set grid for the x-axes
        try:
            x_grid_item = self.visualization_settings.get_item(
                'x_axis', 'grid')
            if x_grid_item and x_grid_item.get_item_value('display'):
                self.ax.grid(True, axis='x',
                             color=self.grid_color,
                             linewidth=self.grid_width)
        except KeyError:
            pass
        # Set grid for the y-axes
        try:
            y_grid_item = self.visualization_settings.get_item(
                'y_axis', 'grid')
            if y_grid_item and y_grid_item.get_item_value('display'):
                self.ax.grid(True, axis='y',
                             color=self.grid_color,
                             linewidth=self.grid_width)
        except KeyError:
            pass
        # Ticks and spines
        for s in self.ax.spines.values():
            s.set_color(self.text_color)
        self.ax.tick_params(
            labelcolor=self.text_color)
        # Custom init plot
        self.init_plot()
        # Check mandatory initializations
        if self.buffer_time is None:
            raise ValueError('The variable buffer_time must be initialized in'
                             ' function init_plot')
        # Refresh the plot
        self.widget.draw()
        # Blitting setup
        self._bg_cache = self.widget.copy_from_bbox(self.fig.bbox)
        self._cached_elements = self._get_cache_elements()

    def set_titles(self, title_text_auto='lsl_stream'):
        """Set titles and labels for the plot axes
        """
        # Figure title
        title_item = self.visualization_settings.get_item('title')
        if title_item.get_item_value('text') == 'auto' and \
            title_text_auto == 'lsl_stream':
                title_text = self.lsl_stream_info.lsl_stream.name()
        elif title_item.get_item_value('text') == 'auto' and \
                title_text_auto == 'channel':
                title_text = self.l_cha[0]
        else:
            title_text = title_item.get_item_value('text')
        self.ax.set_title(
            title_text,
            fontsize=title_item.get_item_value('fontsize'),
            color=self.text_color)
        # X-axis label
        x_label_item = self.visualization_settings.get_item(
            'x_axis', 'label')
        if len(x_label_item.get_item_value('text')) > 0:
            self.ax.set_xlabel(
                x_label_item.get_item_value('text'),
                fontsize=x_label_item.get_item_value('fontsize'),
                color=self.text_color)
        # Y-axis label
        y_label_item = self.visualization_settings.get_item(
            'y_axis', 'label')
        if len(y_label_item.get_item_value('text')) > 0:
            self.ax.set_ylabel(
                y_label_item.get_item_value('text'),
                fontsize=y_label_item.get_item_value('fontsize'),
                color=self.text_color)

    def add_marker(self):
        self.marker_line = self.ax.axvline(x=0, color=self.marker_color,
                                           linewidth=self.marker_width,
                                           animated=True)
        # Set coordinate system of marker tick
        blend = mtransforms.blended_transform_factory(self.ax.transData,
                                                      self.ax.transAxes)
        self.marker_tick = self.ax.text(
            0, self.marker_y_pos, '', transform=blend,
            ha='center', va='top', color=self.text_color,
            clip_on=False, zorder=5, animated=True)
        # Marker initial position
        self.marker_pos = -1

    def check_if_redraw_needed(self):
        # Get current values
        current_elements = self._get_cache_elements()
        # Check if redraw is needed
        for key, cached_value in self._cached_elements.items():
            if cached_value != current_elements[key]:
                # Update cache
                self._cached_elements = current_elements
                return True
        return False

    def update_plot_buffers(self, chunk_times, chunk_signal):
        # Shift times so that they are relative to init_time
        rel_times = chunk_times - self.init_time
        # Append data to buffers
        self.times_buffer = np.hstack((self.times_buffer, rel_times))
        self.data_buffer = np.vstack((self.data_buffer, chunk_signal))
        # Remove old data from buffers
        min_t = self.times_buffer[-1] - self.buffer_time
        idx_to_keep = self.times_buffer >= min_t
        self.times_buffer = self.times_buffer[idx_to_keep]
        self.data_buffer = self.data_buffer[idx_to_keep, :]

    def get_circular_buffers(self):
        # Checks
        if self.marker_pos is None:
            raise ValueError('The variable marker_pos must be initialized '
                             'before using get_circular_buffers')
        # Useful params
        max_t = self.times_buffer.max(initial=0)
        # Get the time cut for the current window
        t_cut = self.buffer_time * np.floor(max_t / self.buffer_time)
        t_cut = max(t_cut, self.buffer_time)
        idx_cut = self.times_buffer > t_cut
        # Init circular buffers
        times_circular_buffer = self.times_buffer.copy()
        data_circular_buffer = self.data_buffer.copy()
        # Check overflow
        if np.any(idx_cut):
            # Append the overflowed samples at the beginning
            times_circular_buffer = np.concatenate(
                (times_circular_buffer[idx_cut],
                 times_circular_buffer[~idx_cut])
            )
            data_circular_buffer = np.concatenate(
                (data_circular_buffer[idx_cut],
                 data_circular_buffer[~idx_cut])
            )
        # Update marker position
        self.marker_pos = np.argmax(times_circular_buffer)
        return times_circular_buffer, data_circular_buffer

    def update_plot_common(self, chunk_times, chunk_signal):
        # Initial setup at first call
        if self.init_time is None:
            self.init_time = chunk_times[0]
            # Custom initial operations
            self.update_plot_initial_operations(chunk_times, chunk_signal)
        # Append data to buffers
        self.update_plot_buffers(chunk_times, chunk_signal)
        # Return if not visible to save resources
        if not self.widget.isVisible():
            return
        # Update plot data
        self.update_plot_data(chunk_times, chunk_signal)
        # Restore static elements from cache if possible
        if self.check_if_redraw_needed():
            self.widget.draw()
            self._bg_cache = self.widget.copy_from_bbox(self.fig.bbox)
        else:
            # Restore static background
            self.widget.restore_region(self._bg_cache)
        # Draw animated elements
        self.update_plot_draw_animated_elements()

    def clear_plot(self):
        self.ax.clear()
        width, height = self.widget.get_width_height()
        if width > 0 and height > 0:
            self.widget.draw()

    @staticmethod
    @abstractmethod
    def get_default_settings():
        """Create de default settings dict"""
        raise NotImplemented

    @staticmethod
    @abstractmethod
    def update_lsl_stream_related_settings(
            signal_settings, visualization_settings, stream_info):
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
    def show_context_menu(self, pos: QPoint):
        """Show context menu on right-click"""
        raise NotImplemented

    @abstractmethod
    def mouse_wheel_event(self, event):
        """Handle mouse wheel events for zooming or other interactions"""
        raise NotImplemented

    @abstractmethod
    def init_plot(self):
        """Init the plot. It's called before starting the worker"""
        raise NotImplemented

    @abstractmethod
    def update_plot_initial_operations(self, chunk_times, chunk_signal):
        """Operations to be done only at the first update call"""
        raise NotImplemented

    @abstractmethod
    def update_plot_data(self, chunk_times, chunk_signal):
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
    def update_plot_draw_animated_elements(self):
        raise NotImplemented


class TimeBasedPlot(RealTimePlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        self.curves = None

    def draw_x_axis_ticks(self):
        # Grid ticks
        def _add_grid_ticks(x_range, x_ticks_pos, x_ticks_val, disp_labels):
            step = self.visualization_settings.get_item_value(
                'x_axis', 'grid', 'step')
            grid_ticks_pos = np.arange(
                x_range[0], x_range[-1],step=step).tolist()
            grid_tick_labels = ['%.1f' % v for v in grid_ticks_pos] if (
                disp_labels) else ['' for _ in grid_ticks_pos]
            x_ticks_pos += grid_ticks_pos
            x_ticks_val += grid_tick_labels
            return x_ticks_pos, x_ticks_val
        # Params
        mode = self.visualization_settings.get_item_value('mode')
        disp_grid = self.visualization_settings.get_item_value(
            'x_axis', 'grid', 'display')
        # Init x-axis ticks
        x_ticks_pos = []
        x_ticks_val = []
        if len(self.x_in_graph) > 0:
            if mode == 'geek':
                # Get range
                x = self.x_in_graph
                x_range = (x[0], x[-1])
                # Time ticks
                if disp_grid:
                    x_ticks_pos, x_ticks_val = _add_grid_ticks(
                        x_range, x_ticks_pos, x_ticks_val, disp_labels=True)
            elif mode == 'clinical':
                # Set timestamps
                x = np.mod(self.x_in_graph, self.buffer_time)
                # Range
                n_win = self.x_in_graph.max() // self.buffer_time
                x_range = (0, self.buffer_time) if n_win == 0 else (x[0], x[-1])
                x_range_real = (0, self.buffer_time) if n_win == 0 else \
                    (self.x_in_graph[0], self.x_in_graph[-1])
                # Add invisible ticks to avoid movement of the axis
                x_ticks_pos += x_range
                x_ticks_val += ['\u00A0\u00A0\u00A0' for v in x_range_real]
                # Visualization grid
                if disp_grid:
                    x_ticks_pos, x_ticks_val = _add_grid_ticks(
                        x_range, x_ticks_pos, x_ticks_val, disp_labels=False)
        else:
            # Get range
            x_range = (0, self.buffer_time)
            # Add range ticks
            x_ticks_pos += x_range
            x_ticks_val += ['%.1f' % v for v in x_range]
            # Grid
            if disp_grid:
                x_ticks_pos, x_ticks_val = _add_grid_ticks(
                    x_range, x_ticks_pos, x_ticks_val, disp_labels=False)
        # Set ticks
        self.ax.set_xticks(x_ticks_pos)
        self.ax.set_xticklabels(x_ticks_val)
        self.ax.set_xlim(x_range[0], x_range[1])

    def update_plot_initial_operations(self, chunk_times, chunk_signal):
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'clinical':
            if mode == 'clinical':
                self.ax.add_line(self.marker_line)

    def update_plot_draw_animated_elements(self):
        mode = self.visualization_settings.get_item_value('mode')
        # Draw animated elements
        for line in self.curves:
            self.ax.draw_artist(line)
        if mode == 'clinical':
            self.ax.draw_artist(self.marker_line)
            self.ax.draw_artist(self.marker_tick)
        # Update only animated elements
        self.widget.blit(self.fig.bbox)

class TimePlotMultichannel(TimeBasedPlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)

        # Graph variables
        self.curves = None
        self.cha_separation = None

    def show_context_menu(self, pos: QPoint):
        """
        Called automatically on right-click within the canvas.
        pos is in widget coordinates, so we map it to global coords.
        """
        menu = AutoscaleMenu(self)
        global_pos = self.widget.mapToGlobal(pos)
        menu.exec_(global_pos)

    def mouse_wheel_event(self, event):
        if self.visualization_settings.get_item_value(
            'y_axis', 'autoscale', 'apply'):
            return
        if event.angleDelta().y() > 0:
            self.cha_separation /= 1.5
        else:
            self.cha_separation *= 1.5
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings():
        # Signal settings
        signal_settings = BaseSignalSettings()
        # Visualization settings
        visualization_settings = BaseVisualizationSettings(
            include_mode=True
        )
        # X-axis
        x_ax = visualization_settings.get_item("x_axis")
        x_ax.add_item(
            "seconds_displayed",
            value=10.0,
            value_range=[0, None],
            info="The time range (s) displayed",
        )
        visualization_settings.add_grid_settings_to_axis("x_axis")
        # Y-axis
        y_ax = visualization_settings.get_item("y_axis")
        y_ax.add_item(
            "cha_separation",
            value=1.0,
            value_range=[0, None],
            info="Initial separation between channels in the y-axis",
        )
        visualization_settings.add_grid_settings_to_axis("y_axis")
        auto_scale = y_ax.add_item("autoscale")
        auto_scale.add_item(
            "apply",
            value=False,
            info="Automatically scale the y-axis",
        )
        auto_scale.add_item(
            "n_std_tolerance",
            value=1.25,
            value_range=[0, None],
            info=(
                "Autoscale limit: if the signal exceeds this value, the scale "
                "is re-adjusted"
            ),
        )
        auto_scale.add_item(
            "n_std_separation",
            value=5.0,
            value_range=[0, None],
            info="Separation between channels (in std)",
        )
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings,
                                           stream_info):
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        # Visualization modes
        possible_modes = ['geek', 'clinical']
        if visualization_settings.get_item_value('mode') not in possible_modes:
            raise ValueError('Unknown plot mode %s. Possible options: %s' %
                             (visualization_settings.get_item_value('mode'),
                              possible_modes))
        # Channel separation
        if visualization_settings.get_item_value(
            'y_axis', 'cha_separation') <= 0:
            raise ValueError('y_axis/cha_separation must be greater than 0')

    @staticmethod
    def check_signal(lsl_stream_info):
        pass

    def init_plot(self):
        """
        This function changes the time of signal plotted in the graph. It
        depends on the sample frequency.
        """
        # INIT SIGNAL VARIABLES ================================================
        # Update variables
        self.cha_separation = self.visualization_settings.get_item_value(
            'y_axis', 'cha_separation')
        self.buffer_time = self.visualization_settings.get_item_value(
            'x_axis', 'seconds_displayed')

        # INIT FIGURE ==========================================================
        # Place curves in plot
        curve_style = {'color': self.curve_color,
                       'linewidth': self.curve_width}
        self.curves = []
        for i in range(self.n_cha):
            curve, = self.ax.plot([], [],
                                  animated=True,
                                  **curve_style)
            self.curves.append(curve)
        # Mode dependent initialization
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=True, labelbottom=True,
                right=False, labelright=False,
                top=False, labeltop=False)
        elif mode == 'clinical':
            self.add_marker()
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=False, labelbottom=False,
                right=False, labelright=False,
                top=False, labeltop=False)
        # Set axis limits
        self.ax.set_xlim(0, self.buffer_time)
        self.ax.set_ylim(-self.cha_separation * (self.n_cha / 2),
                         self.cha_separation * (self.n_cha / 2))
        # Draw ticks on the axes
        self.draw_x_axis_ticks()
        self.draw_y_axis_ticks()

    def _get_cache_elements(self):
        current_elements = {
            'xlim': self.ax.get_xlim(),
            'ylim': self.ax.get_ylim(),
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

    def draw_y_axis_ticks(self):
        # Draw y axis ticks (channel labels)
        y_ticks_pos = np.arange(self.n_cha) * self.cha_separation
        y_ticks_labels = self.l_cha[::-1]
        self.ax.set_yticks(y_ticks_pos)
        self.ax.set_yticklabels(y_ticks_labels)
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.n_cha * self.cha_separation
        if self.n_cha > 1:
            self.ax.set_ylim(y_min, y_max)

    def autoscale(self):
        scaling_sett = self.visualization_settings.get_item(
            'y_axis', 'autoscale')
        y_std = np.std(self.data_in_graph)
        std_tol = scaling_sett.get_item_value('n_std_tolerance')
        std_factor = scaling_sett.get_item_value('n_std_separation')
        if y_std > self.cha_separation * std_tol or \
                y_std < self.cha_separation / std_tol:
            self.cha_separation = std_factor * y_std
            self.draw_y_axis_ticks()

    def update_plot_data(self, chunk_times, chunk_signal):
        """This function updates the data in the graph. Notice that channel 0 is
        drawn up in the chart, whereas the last channel is in the bottom.
        """
        # Set data
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.times_in_graph, self.data_in_graph = (
                self.times_buffer, self.data_buffer)
            x = self.times_in_graph
        else:
            self.times_in_graph, self.data_in_graph = (
                self.get_circular_buffers())
            x = np.mod(self.times_in_graph, self.buffer_time)
            # Marker
            marker_x = x[self.marker_pos]
            self.marker_line.set_xdata([marker_x, marker_x])
            # Update marker text
            marker_time = self.times_in_graph[self.marker_pos]
            # Position text under the marker line
            self.marker_tick.set_position((marker_x, self.marker_y_pos))
            self.marker_tick.set_text(f'{marker_time:.1f}')
        for i in range(self.n_cha):
            temp = self.data_in_graph[:, self.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].set_data(x, temp)
        # Update y range (only if autoscale is activated)
        apply_autoscale = self.visualization_settings.get_item_value(
            'y_axis', 'autoscale', 'apply')
        if apply_autoscale:
            self.autoscale()
        # Update x range
        self.draw_x_axis_ticks()


class TimePlotSingleChannel(TimeBasedPlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        self.curr_cha = None
        self.y_range = None

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
        if self.visualization_settings.get_item_value(
            'y_axis', 'autoscale', 'apply'):
            return
        if event.angleDelta().y() > 0:
            self.y_range = [r / 1.5 for r in self.y_range]
        else:
            self.y_range = [r * 1.5 for r in self.y_range]
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings():
        # Signal settings
        signal_settings = BaseSignalSettings()
        # Visualization settings
        visualization_settings = BaseVisualizationSettings(
            include_mode=True
        )
        # Initial channel
        visualization_settings.add_item(
            "init_channel_label",
            value="",
            info="Channel selected for initial visualization.",
        )
        # X-axis
        x_ax = visualization_settings.get_item("x_axis")
        x_ax.add_item(
            "seconds_displayed",
            value=10.0,
            value_range=[0, None],
            info="The time range (s) displayed",
        )
        visualization_settings.add_grid_settings_to_axis("x_axis")
        # Y-axis
        y_ax = visualization_settings.get_item("y_axis")
        y_ax.add_item(
            "range",
            value=1.0,
            info="Range of the y-axis",
        )
        visualization_settings.add_grid_settings_to_axis("y_axis")
        auto_scale = y_ax.add_item("autoscale")
        auto_scale.add_item(
            "apply",
            value=False,
            info="Automatically scale the y-axis",
        )
        auto_scale.add_item(
            "n_std_tolerance",
            value=1.25,
            value_range=[0, None],
            info=(
                "Autoscale limit: if the signal exceeds this value, the scale "
                "is re-adjusted"
            ),
        )
        auto_scale.add_item(
            "n_std_separation",
            value=5.0,
            value_range=[0, None],
            info="Separation between channels (in std)",
        )
        return signal_settings, visualization_settings


    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings, stream_info):
        visualization_settings.get_item("init_channel_label"). \
            edit_item(value=stream_info.l_cha[0],
                      value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        # Check mode
        possible_modes = ['geek', 'clinical']
        if visualization_settings.get_item_value('mode') not in possible_modes:
            raise ValueError('Unknown plot mode %s. Possible options: %s' %
                             (visualization_settings.get_item_value('mode'),
                              possible_modes))

    @staticmethod
    def check_signal(lsl_stream_info):
        pass

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frequency.
        """
        # INIT SIGNAL VARIABLES ================================================
        init_cha_label = self.visualization_settings.get_item_value(
            'init_channel_label')
        self.curr_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label)
        self.buffer_time = self.visualization_settings.get_item_value(
            'x_axis', 'seconds_displayed')

        # INIT FIGURE ==========================================================
        # Place curves in plot
        curve_style = {'color': self.curve_color,
                       'linewidth': self.curve_width}
        curve, = self.ax.plot([], [], animated=True, **curve_style)
        self.curves = [curve]
        # Mode dependent initialization
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=True, labelbottom=True,
                right=False, labelright=False,
                top=False, labeltop=False)
        elif mode == 'clinical':
            self.add_marker()
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=False, labelbottom=False,
                right=False, labelright=False,
                top=False, labeltop=False)
        # Set axis limits
        self.y_range = self.visualization_settings.get_item_value(
            'y_axis', 'range')
        if not isinstance(self.y_range, list):
            self.y_range = [-self.y_range, self.y_range]
        self.ax.set_xlim(0, self.buffer_time)
        self.ax.set_ylim(self.y_range[0], self.y_range[1])
        # Draw ticks on the axes
        self.draw_x_axis_ticks()
        self.draw_y_axis_ticks()

    def _get_cache_elements(self):
        current_elements = {
            'curr_cha': self.curr_cha,
            'xlim': self.ax.get_xlim(),
            'ylim': self.ax.get_ylim(),
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

    def draw_y_axis_ticks(self):
        self.ax.set_ylim(self.y_range[0], self.y_range[1])

    def autoscale(self):
        # Get statistics
        y_mean = np.mean(self.data_in_graph[:, self.curr_cha - 1])
        y_std = np.std(self.data_in_graph)
        # Current limits
        curr_min, curr_max = self.y_range
        curr_span = max(curr_max - curr_min, 1e-12)
        # New limits
        auto_node = self.visualization_settings.get_item(
            'y_axis', 'autoscale')
        std_tol = auto_node.get_item_value('n_std_tolerance')
        std_factor = auto_node .get_item_value('n_std_separation')
        new_span = std_factor * y_std
        # Decide if rescale is needed
        do_rescale = (
                new_span > curr_span * std_tol or
                new_span < curr_span / std_tol
        )
        if not do_rescale:
            return
        # New range centered at mean
        new_min = y_mean - 0.5 * new_span
        new_max = y_mean + 0.5 * new_span
        # Optional small padding
        pad = 0.05 * new_span
        new_min -= pad
        new_max += pad
        # Update internal range and axes
        self.y_range = [new_min, new_max]
        self.ax.set_ylim(new_min, new_max)
        self.draw_y_axis_ticks()

    def update_plot_data(self, chunk_times, chunk_signal):
        # Calculate x axis
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.times_in_graph, self.data_in_graph = (
                self.times_buffer, self.data_buffer)
            x = self.times_in_graph
        else:
            self.times_in_graph, self.data_in_graph = (
                self.get_circular_buffers())
            x = np.mod(self.times_in_graph, self.buffer_time)
            # Marker
            marker_x = x[self.marker_pos]
            self.marker_line.set_xdata([marker_x, marker_x])
            # Update marker text
            marker_time = self.times_in_graph[self.marker_pos]
            # Position text under the marker line
            self.marker_tick.set_position((marker_x, self.marker_y_pos))
            self.marker_tick.set_text(f'{marker_time:.1f}')
        tmp = self.data_in_graph[:, self.curr_cha - 1]
        self.curves[0].set_data(x, tmp)
        # Update y range (only if autoscale is activated)
        apply_autoscale = self.visualization_settings.get_item_value(
            'y_axis', 'autoscale', 'apply')
        if apply_autoscale:
            self.autoscale()
        # Update x range
        self.draw_x_axis_ticks()


class FreqBasedPlot(RealTimePlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        self.curves = None

    def draw_x_axis_ticks(self):
        x_range = self.visualization_settings.get_item_value('x_axis', 'range')
        self.ax.set_xlim(x_range)

    def update_plot_initial_operations(self, chunk_times, chunk_signal):
        pass

    def update_plot_draw_animated_elements(self):
        # Draw animated elements
        for line in self.curves:
            self.ax.draw_artist(line)
        # Update only animated elements
        self.widget.blit(self.fig.bbox)


class PSDPlotMultichannel(FreqBasedPlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        self.curves = None
        self.cha_separation = None

    def show_context_menu(self, pos: QPoint):
        """
        Called automatically on right-click within the canvas.
        pos is in widget coordinates, so we map it to global coords.
        """
        menu = AutoscaleMenu(self)
        global_pos = self.widget.mapToGlobal(pos)
        menu.exec_(global_pos)

    def mouse_wheel_event(self, event):
        if self.visualization_settings.get_item_value(
            'y_axis', 'autoscale', 'apply'):
            return
        if event.angleDelta().y() > 0:
            self.cha_separation /= 1.5
        else:
            self.cha_separation *= 1.5
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings():
        # Signal settings
        signal_settings = BaseSignalSettings()
        signal_settings.add_psd_settings()

        # Visualization settings
        visualization_settings = BaseVisualizationSettings()
        # X-axis
        x_ax = visualization_settings.get_item("x_axis")
        x_ax.get_item("label").edit_item("text", "Frequency (Hz)")
        x_ax.add_item(
            "range",
            value=[0.1, 30.0],
            info="X-axis range (min, max) in Hz.",
        )
        visualization_settings.add_grid_settings_to_axis("x_axis")
        # Y-axis
        y_ax = visualization_settings.get_item("y_axis")
        y_ax.add_item(
            "cha_separation",
            value=1.0,
            value_range=[0, None],
            info="Initial vertical separation / limits for the Y axis.",
        )
        visualization_settings.add_grid_settings_to_axis("y_axis")
        auto_scale = y_ax.add_item("autoscale")
        auto_scale.add_item(
            "apply",
            value=False,
            info="Automatically scale the Y axis.",
        )
        auto_scale.add_item(
            "n_std_tolerance",
            value=1.25,
            value_range=[0, None],
            info=(
                "Tolerance factor: rescale when global STD leaves "
                "[sep/τ, sep*τ], where τ = this value."
            ),
        )
        auto_scale.add_item(
            "n_std_separation",
            value=5.0,
            value_range=[0, None],
            info="Channel separation in units of global standard deviation.",
        )
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings, stream_info):
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        # Channel separation
        if visualization_settings.get_item_value(
            'y_axis', 'cha_separation') <= 0:
            raise ValueError('y_axis/cha_separation must be greater than 0')

    @staticmethod
    def check_signal(lsl_stream_info):
       pass

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frequency.
        """
        # INIT SIGNAL VARIABLES ================================================
        # Update variables
        self.cha_separation = \
            self.visualization_settings.get_item_value(
                'y_axis', 'cha_separation')
        self.buffer_time = self.signal_settings.get_item_value(
            'psd', 'time_window_seconds')

        # INIT FIGURE ==========================================================
        # Set the style for the curves
        curve_style = {'color': self.curve_color,
                       'linewidth': self.curve_width}
        # Place curves in plot
        self.curves = []
        for i in range(self.n_cha):
            curve, = self.ax.plot([], [],
                                  animated=True,
                                  **curve_style)
            self.curves.append(curve)
        # Draw ticks on the axes
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()

    def _get_cache_elements(self):
        current_elements = {
            'xlim': self.ax.get_xlim(),
            'ylim': self.ax.get_ylim(),
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

    def draw_y_axis_ticks(self):
        # Draw y-axis ticks (channel labels)
        y_ticks_pos = np.arange(self.n_cha) * self.cha_separation
        y_ticks_labels = self.l_cha[::-1]
        self.ax.set_yticks(y_ticks_pos)
        self.ax.set_yticklabels(y_ticks_labels)
        # Set y axis range
        y_min = - self.cha_separation
        y_max = self.n_cha * self.cha_separation
        if self.n_cha > 1:
            self.ax.set_ylim(y_min, y_max)

    def autoscale(self):
        scaling_sett = self.visualization_settings.get_item(
            'y_axis', 'autoscale')
        y_std = np.std(self.y_in_graph)
        std_tol = scaling_sett.get_item_value('n_std_tolerance')
        std_factor = scaling_sett.get_item_value('n_std_separation')
        if y_std > self.cha_separation * std_tol or \
                y_std < self.cha_separation / std_tol:
            self.cha_separation = std_factor * y_std
            self.draw_y_axis_ticks()

    def update_plot_data(self, chunk_times, chunk_signal):
        """
        This function updates the data in the graph. Notice that channel 0 is
        drawn up in the chart, whereas the last channel is in the bottom.
        """
        # Compute PSD
        seg_len_pct = self.signal_settings.get_item_value(
            'psd', 'welch_seg_len_pct')
        seg_overlap_pct = self.signal_settings.get_item_value(
            'psd', 'welch_overlap_pct')
        welch_seg_len = np.round(
            seg_len_pct / 100.0 * self.data_buffer.shape[0]).astype(int)
        welch_overlap = np.round(
            seg_overlap_pct /  100.0 * welch_seg_len).astype(int)
        x_in_graph, y_in_graph = scp_signal.welch(
            self.data_buffer, fs=self.fs,
            nperseg=welch_seg_len, noverlap=welch_overlap,
            nfft=welch_seg_len, axis=0)
        apply_log = self.signal_settings.get_item_value('psd', 'log_power')
        if apply_log:
            y_in_graph = 10.0 * np.log10(np.maximum(y_in_graph, 1e-12))
        # Set data
        x = np.arange(x_in_graph.shape[0])
        for i in range(self.n_cha):
            temp = y_in_graph[:, self.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].set_data(x, temp)
        self.x_in_graph = x_in_graph
        self.y_in_graph = y_in_graph
        # Update y range (only if autoscale is activated)
        apply_autoscale = self.visualization_settings.get_item_value(
            'y_axis', 'autoscale', 'apply')
        if apply_autoscale:
            self.autoscale()


class PSDPlotSingleChannel(FreqBasedPlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        self.curr_cha = None
        self.y_range = None

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
        if self.visualization_settings.get_item_value(
            'y_axis', 'autoscale', 'apply'):
            return
        if event.angleDelta().y() > 0:
            self.y_range = [r / 1.5 for r in self.y_range]

        else:
            self.y_range = [r * 1.5 for r in self.y_range]
        self.draw_y_axis_ticks()

    @staticmethod
    def get_default_settings():
        # Signal settings
        signal_settings = BaseSignalSettings()
        signal_settings.add_psd_settings()

        # Visualization settings
        visualization_settings = BaseVisualizationSettings()
        # Init channel
        visualization_settings.add_item(
            "init_channel_label",
            value="",
            info="Channel selected for initial visualization.",
        )
        # X-axis
        x_ax = visualization_settings.get_item("x_axis")
        x_ax.get_item("label").edit_item("text", "Frequency (Hz)")
        x_ax.add_item(
            "range",
            value=[0.1, 30.0],
            value_range=[None, None],
            info="X-axis range (min, max) in Hz.",
        )
        visualization_settings.add_grid_settings_to_axis("x_axis")
        # Y-axis
        y_ax = visualization_settings.get_item("y_axis")
        y_ax.get_item("label").edit_item("text", "PSD")
        y_ax.add_item(
            "range",
            value=[0.0, 1.0],
            value_range=[None, None],
            info="Initial vertical separation / limits for the Y axis.",
        )
        visualization_settings.add_grid_settings_to_axis("y_axis")
        auto_scale = y_ax.add_item("autoscale")
        auto_scale.add_item(
            "apply",
            value=False,
            info="Automatically scale the Y axis.",
        )
        auto_scale.add_item(
            "n_std_tolerance",
            value=1.25,
            value_range=[0, None],
            info=(
                "Tolerance factor: rescale when global STD leaves "
                "[sep/τ, sep*τ], where τ = this value."
            ),
        )
        auto_scale.add_item(
            "n_std_separation",
            value=5.0,
            value_range=[0, None],
            info="Channel separation in units of global standard deviation.",
        )
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(
            signal_settings, visualization_settings, stream_info):
        visualization_settings.get_item("init_channel_label").\
            edit_item(value=stream_info.l_cha[0],
                      value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        pass

    @staticmethod
    def check_signal(lsl_stream_info):
        pass

    def init_plot(self):
        """ This function changes the time of signal plotted in the graph. It
        depends on the sample frecuency.
        """
        # INIT SIGNAL VARIABLES ================================================
        init_cha_label = self.visualization_settings.get_item_value(
            'init_channel_label')
        self.curr_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label)
        self.buffer_time = self.signal_settings.get_item_value(
            'psd', 'time_window_seconds')

        # INIT FIGURE ==========================================================
        # Set the style for the curves
        curve_style = {'color': self.curve_color,
                       'linewidth': self.curve_width}
        curve, = self.ax.plot([], [], animated=True, **curve_style)
        self.curves = [curve]
        # Set axis limits
        self.y_range = self.visualization_settings.get_item_value(
            'y_axis', 'range')
        if not isinstance(self.y_range, list):
            self.y_range = [0, self.y_range]
        # Draw ticks on the axes
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()

    def _get_cache_elements(self):
        current_elements = {
            'curr_cha': self.curr_cha,
            'xlim': self.ax.get_xlim(),
            'ylim': self.ax.get_ylim(),
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

    def draw_y_axis_ticks(self):
        self.ax.set_ylim(self.y_range[0], self.y_range[1])

    def autoscale(self):
        scaling_sett = self.visualization_settings.get_item(
            'y_axis', 'autoscale')
        y_std = np.std(self.y_in_graph)
        std_tol = scaling_sett.get_item_value('n_std_tolerance')
        std_factor = scaling_sett.get_item_value('n_std_separation')
        if y_std > self.y_range[1] * std_tol or \
                y_std < self.y_range[1] / std_tol:
            self.y_range[1] = std_factor * y_std
            self.draw_y_axis_ticks()

    def update_plot_data(self, chunk_times, chunk_signal):
        """
        This function updates the data in the graph. Notice that channel 0 is
        drew up in the chart, whereas the last channel is in the bottom.
        """
        # DATA OPERATIONS ==================================================
        # Compute PSD
        welch_seg_len_pct = self.signal_settings.get_item_value(
            'psd', 'welch_seg_len_pct')
        welch_overlap_pct = self.signal_settings.get_item_value(
            'psd', 'welch_overlap_pct')
        welch_seg_len = np.round(
            welch_seg_len_pct / 100.0 * self.data_buffer.shape[0])
        welch_overlap = np.round(
            welch_overlap_pct / 100.0 * welch_seg_len)
        x_in_graph, y_in_graph = scp_signal.welch(
            self.data_buffer[:, self.curr_cha], fs=self.fs,
            nperseg=welch_seg_len, noverlap=welch_overlap,
            nfft=welch_seg_len, axis=0)
        apply_log = self.signal_settings.get_item_value(
            'psd', 'log_power')
        if apply_log:
            y_in_graph = 10.0 * np.log10(np.maximum(y_in_graph, 1e-12))
        # Set data
        self.curves[0].set_data(x_in_graph, y_in_graph)
        self.x_in_graph = x_in_graph
        self.y_in_graph = y_in_graph
        # Update y range (only if autoscale is activated)
        apply_autoscale = self.visualization_settings.get_item_value(
            'y_axis', 'autoscale', 'apply')
        if apply_autoscale:
            self.autoscale()


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
        self.spec_in_graph = None
        self.c_lim = None
        self.marker = None

        # Style and  theme
        self.curve_color = self.theme_colors['THEME_SIGNAL_CURVE']
        self.grid_color = self.theme_colors['THEME_SIGNAL_GRID']
        self.marker_color = self.theme_colors['THEME_SIGNAL_MARKER']
        self.background_color = self.theme_colors['THEME_BG_DARK']
        self.text_color = self.theme_colors['THEME_TEXT_LIGHT']
        self.curve_width = 1
        self.grid_width = 1
        self.marker_width = 2
        self.marker_y_pos = -0.005

        # Widget variables
        self.widget = self.init_widget()
        self.fig = self.widget.figure
        self.ax = self.fig.axes[0]
        self.im = None
        self._bg_cache = None
        self._cached_elements = None

    def init_widget(self):
        # Init figure
        fig = Figure(figsize=(1, 1), dpi=90)
        ax = fig.add_subplot(111)
        fig.set_layout_engine('constrained', rect=[0, 0, 1, 1])
        # fig.subplots_adjust(left=0.005, right=0.995, bottom=0.005, top=0.995)
        fig.patch.set_facecolor(self.background_color)
        ax.set_facecolor(self.background_color)
        # Init widget
        widget = FigureCanvasQTAgg(fig)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        widget.setContextMenuPolicy(Qt.CustomContextMenu)
        widget.customContextMenuRequested.connect(self.show_context_menu)
        widget.wheelEvent = self.mouse_wheel_event

        return widget

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
        """
        Interactive zoom of the spectrogram amplitude range (color limits).
        Behavior:
          - Wheel up   → zoom in   (reduce span)
          - Wheel down → zoom out  (increase span)
          - Ctrl  + wheel  → fine zoom
          - Shift + wheel  → coarse zoom

        Additional features:
          - Automatically disables autoscaling when the user zooms manually.
          - Synchronizes the updated CLIM with visualization_settings['z_axis']['range'].
        """
        # Checks
        if self.im is None:
            return
        if self.visualization_settings.get_item_value(
            'z_axis', 'autoscale', 'apply'):
            return
        # Get current lims
        vmin, vmax = self.im.get_clim()
        if not (np.isfinite(vmin) and np.isfinite(vmax)):
            return
        # Current center + span
        center = 0.5 * (vmin + vmax)
        span = max(vmax - vmin, 1e-12)
        # Determine zoom factor
        base = 1.2
        mods = event.modifiers()
        if mods & Qt.ControlModifier:
            base = 1.05  # fine zoom
        elif mods & Qt.ShiftModifier:
            base = 1.5  # coarse zoom
        # Determine new span
        zoom_in = event.angleDelta().y() > 0
        new_span = span / base if zoom_in else span * base
        # Reconstruct new clim around center
        new_vmin = center - 0.5 * new_span
        new_vmax = center + 0.5 * new_span
        # Ensure valid ordering and non-zero span
        if new_vmax <= new_vmin:
            eps = max(1e-12, abs(vmax - vmin) * 1e-6)
            new_vmax = new_vmin + eps
        # Apply to image
        self.im.set_clim(new_vmin, new_vmax)
        self.c_lim = (new_vmin, new_vmax)

    @staticmethod
    def get_default_settings():
        """
        Returns a tuple: (signal_settings, visualization_settings).
        Adjust or rename keys to your needs.
        """
        # Basic signal-processing settings
        signal_settings = SettingsTree()
        signal_settings.add_item(
            "min_update_time",
            value=0.1,
            value_range=[0, None],
            info=(
                "Minimum update interval (s) for refreshing the plot. This value may "
                "automatically increase to prevent system overload, depending on your "
                "hardware performance and the complexity of the plots panel "
                "configuration."
            ),
        )

        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item(
            "apply",
            value=True,
            info="Apply an IIR filter in real time.",
        )
        freq_filt.add_item(
            "type",
            value="highpass",
            value_options=["highpass", "lowpass", "bandpass", "stopband"],
            info="Filter type.",
        )
        freq_filt.add_item(
            "cutoff_freq",
            value=[1.0],
            info=(
                "Cutoff frequencies. One value for high/low-pass; two values for "
                "band/stop-band."
            ),
        )
        freq_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "IIR filter order. Higher orders yield steeper responses but raise "
                "computational cost and latency."
            ),
        )

        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item(
            "apply",
            value=False,
            info="Apply a notch filter to attenuate power-line interference.",
        )
        notch_filt.add_item(
            "freq",
            value=50.0,
            value_range=[0, None],
            info="Notch center frequency (Hz).",
        )
        notch_filt.add_item(
            "bandwidth",
            value=[-0.5, 0.5],
            info=(
                "Relative limits around the center frequency to define the notch "
                "band."
            ),
        )
        notch_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "Notch filter order. Higher values increase selectivity and cost."
            ),
        )

        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item(
            "apply",
            value=False,
            info="Enable re-referencing of the signals.",
        )
        re_ref.add_item(
            "type",
            value="car",
            value_options=["car", "channel"],
            info=(
                "Re-referencing method. 'car' applies Common Average Reference; "
                "'channel' subtracts a specific channel."
            ),
        )
        re_ref.add_item(
            "channel",
            value="",
            info="Channel label used when the type is 'channel'.",
        )

        down_samp = signal_settings.add_item("downsampling")
        down_samp.add_item(
            "apply",
            value=False,
            info="Reduce the sample rate of the incoming LSL stream.",
        )
        down_samp.add_item(
            "factor",
            value=2.0,
            value_range=[0, None],
            info="Downsampling factor (e.g., 2 halves the sample rate).",
        )

        spectrogram = signal_settings.add_item("spectrogram")
        spectrogram.add_item(
            "time_window",
            value=5.0,
            value_range=[0, None],
            info="Duration (s) of data kept in the rolling buffer.",
        )
        spectrogram.add_item(
            "overlap_pct",
            value=90.0,
            value_range=[0, 100],
            info="Segment overlap (%) used in the STFT/Welch computation.",
        )
        spectrogram.add_item(
            "scale_to",
            value="psd",
            value_options=["psd", "magnitude"],
            info=(
                "Output scaling for the spectrogram: power spectral density ('psd') "
                "or linear magnitude ('magnitude')."
            ),
        )
        spectrogram.add_item(
            "smooth",
            value=True,
            info="Apply a Gaussian filter to smooth the spectrogram.",
        )
        spectrogram.add_item(
            "smooth_sigma",
            value=2.0,
            value_range=[0, None],
            info="Sigma of the Gaussian smoothing kernel (in pixels).",
        )
        spectrogram.add_item(
            "apply_detrend",
            value=True,
            info="Apply linear detrending before the STFT.",
        )
        spectrogram.add_item(
            "apply_normalization",
            value=True,
            info=(
                "Normalize the signal to unit standard deviation before the STFT to "
                "reduce scale variability."
            ),
        )
        spectrogram.add_item(
            "log_power",
            value=True,
            info="Display power on a logarithmic scale (log-power).",
        )

        visualization_settings = SettingsTree()
        visualization_settings.add_item(
            "mode",
            value="clinical",
            value_options=["clinical", "geek"],
            info=(
                "Visualization mode. 'clinical' uses sweeping updates; 'geek' "
                "shows a continuously growing trace."
            ),
        )
        visualization_settings.add_item(
            "init_channel_label",
            value="",
            info="Channel selected for initial visualization.",
        )
        visualization_settings.add_item(
            "title_label_size",
            value=10.0,
            value_range=[0, None],
            info="Title font size (pt).",
        )

        x_ax = visualization_settings.add_item("x_axis")
        x_ax.add_item(
            "seconds_displayed",
            value=30.0,
            value_range=[0, None],
            info="Time range (s) displayed on the X axis.",
        )
        x_ax.add_item(
            "tick_label_size",
            value=8.0,
            value_range=[0, None],
            info="Font size (pt) for X-axis tick labels.",
        )
        x_ax.add_item(
            "label",
            value="Time (s)",
            info="Label for the X axis (HTML allowed).",
        )
        x_ax.add_item(
            "label_size",
            value=8.0,
            value_range=[0, None],
            info="Font size (pt) for the X-axis label.",
        )
        x_ax.add_item(
            "display_grid",
            value=True,
            info="Show grid lines on the x-axis.",
        )
        x_ax.add_item(
            "line_separation",
            value=5.0,
            value_range=[0, None],
            info="Separation between Y-axis ticks (Hz).",
        )

        y_ax = visualization_settings.add_item("y_axis")
        y_ax.add_item(
            "range",
            value=[0, 30],
            info="Y-axis range (min, max).",
        )
        y_ax.add_item(
            "tick_label_size",
            value=8.0,
            value_range=[0, None],
            info="Font size (pt) for Y-axis tick labels.",
        )
        y_ax.add_item(
            "label",
            value="Frequency (Hz)",
            info="Label for the Y axis (HTML allowed).",
        )
        y_ax.add_item(
            "label_size",
            value=8.0,
            value_range=[0, None],
            info="Font size (pt) for the Y-axis label.",
        )
        y_ax.add_item(
            "display_grid",
            value=True,
            info="Show grid lines on the y-axis.",
        )
        y_ax.add_item(
            "line_separation",
            value=5.0,
            value_range=[0, None],
            info="Separation between Y-axis ticks (Hz).",
        )

        z_ax = visualization_settings.add_item("z_axis")
        z_ax.add_item(
            "cmap",
            value="inferno",
            info="Matplotlib colormap used for the spectrogram.",
        )
        z_ax.add_item(
            "range",
            value=[0.0, 1.0],
            info="Range of the z-axis (clim).",
        )

        auto_scale = z_ax.add_item("autoscale")
        auto_scale.add_item(
            "apply",
            value=False,
            info="Automatically scale the z-axis.",
        )
        auto_scale.add_item(
            "n_std_tolerance",
            value=1.25,
            value_range=[0, None],
            info=(
                "Autoscale limit: if the signal exceeds this value, the scale "
                "is re-adjusted."
            ),
        )
        auto_scale.add_item(
            "n_std_separation",
            value=5.0,
            value_range=[0, None],
            info="Separation between channels (in standard deviations).",
        )
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings,
                                           stream_info):
        signal_settings.get_item("re_referencing", "channel").\
            edit_item(value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        visualization_settings.get_item("init_channel_label").\
            edit_item(value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, visualization_settings):
        """Validate incoming settings if needed."""
        possible_modes = ['geek', 'clinical']
        if visualization_settings.get_item_value('mode') not in possible_modes:
            raise ValueError('Unknown plot mode %s. Possible options: %s' %
                             (visualization_settings.get_item_value('mode'),
                              possible_modes))

    @staticmethod
    def check_signal(lsl_stream_info):
        """Checks that the incoming signal is compatible."""
        pass

    def init_plot(self):
        """
        Initialize the spectrogram plot, figure, axes, etc.
        This is called once, when the stream is first set up.
        """

        # INIT SIGNAL VARIABLES ================================================

        # Get channel
        init_cha_label = self.visualization_settings.get_item_value(
            'init_channel_label')
        self.curr_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label)

        # Inherit the main time-window size from the settings
        self.win_t = self.visualization_settings.get_item_value(
            'x_axis', 'seconds_displayed')
        self.win_s = int(self.win_t * self.fs)

        # Spectrogram window
        self.win_t_spec = self.signal_settings.get_item_value(
            'spectrogram', 'time_window')
        self.win_s_spec = (
            int(self.signal_settings.get_item_value(
                'spectrogram', 'time_window') * self.fs))

        # Initialize buffers
        self.time_in_graph = np.zeros(0)
        self.sig_in_graph = np.zeros((0, self.lsl_stream_info.n_cha))

        # INIT FIGURE ==========================================================
        # Set titles
        self.ax.set_xlabel(
            self.visualization_settings.get_item_value('x_axis', 'label'),
            color=self.text_color)
        self.ax.set_ylabel(
            self.visualization_settings.get_item_value('y_axis', 'label'),
            color=self.text_color)
        self.ax.set_title(
            self.lsl_stream_info.l_cha[self.curr_cha],
            color=self.text_color,
            fontsize=self.visualization_settings.get_item_value(
                'title_label_size'))
        # Display initial array
        height, width = 1, 1
        rgb_tuple = gui_utils.hex_to_rgb(
            self.theme_colors['THEME_BG_MID'], scale=True)
        solid_color = np.ones((height, width, 3)) * rgb_tuple
        self.im = self.ax.imshow(
            solid_color,
            aspect='auto',
            origin='lower',
            animated=True,
            zorder=0)
        # Ticks params
        for s in self.ax.spines.values():
            s.set_color(self.text_color)
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=True, labelbottom=True,
                right=False, labelright=False,
                top=False, labeltop=False,
                labelcolor=self.text_color,
                labelsize=self.visualization_settings.get_item_value(
                    'x_axis', 'tick_label_size')
            )
        elif mode == 'clinical':
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=False, labelbottom=False,
                right=False, labelright=False,
                top=False, labeltop=False,
                labelcolor=self.text_color)
        # Marker for clinical mode
        if mode == 'clinical':
            self.marker = self.ax.axvline(x=0, color=self.marker_color,
                                          linewidth=self.marker_width,
                                          animated=True)
            # x in DATA coords, y in AXES coords
            blend = mtransforms.blended_transform_factory(self.ax.transData,
                                                          self.ax.transAxes)
            self.marker_tick = self.ax.text(
                0, self.marker_y_pos, '', transform=blend,
                ha='center', va='top', color=self.text_color,
                clip_on=False, zorder=10, animated=True)
            self.pointer = -1
        # Set axis limits
        self.y_range = self.visualization_settings.get_item_value(
            'y_axis', 'range')
        if not isinstance(self.y_range, list):
            self.y_range = [0, self.y_range]
        self.im.set_extent((0, self.win_t, self.y_range[0], self.y_range[1]))
        clim = self.visualization_settings.get_item_value('z_axis', 'range')
        self.im.set_clim(clim[0], clim[1])
        # Draw ticks on the axes
        self.draw_x_axis_ticks()
        self.draw_y_axis_ticks()
        # Refresh the plot
        self.widget.draw()
        # Blitting setup
        self._bg_cache = self.widget.copy_from_bbox(self.fig.bbox)
        self._cached_elements = self._get_cache_elements()

    def _get_cache_elements(self):
        current_elements = {
            'curr_cha': self.curr_cha,
            'c_lim': self.c_lim,
            'xlim': self.ax.get_xlim(),
            'ylim': self.ax.get_ylim(),
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

    def check_if_redraw_needed(self):
        # Get current values
        current_elements = self._get_cache_elements()
        # Check if redraw is needed
        for key, cached_value in self._cached_elements.items():
            if cached_value != current_elements[key]:
                # Update cache
                self._cached_elements = current_elements
                return True
        return False

    def draw_y_axis_ticks(self):
        # Settings
        disp_grid = self.visualization_settings.get_item_value(
            'y_axis', 'display_grid')
        tick_sep = self.visualization_settings.get_item_value(
            'y_axis', 'line_separation')
        # Frequency ticks
        y_ticks_pos = np.arange(self.y_range[0], self.y_range[1]+1e-12,
                                step=tick_sep).tolist()
        y_ticks_val = [f'{val:.1f}' for val in y_ticks_pos]
        # Set limits, ticks, and labels
        self.ax.set_ylim(self.y_range[0], self.y_range[1])
        self.ax.set_yticks(y_ticks_pos)
        self.ax.set_yticklabels(y_ticks_val)
        self.ax.grid(visible=disp_grid, axis='y', color=self.text_color,
                     linestyle='-', linewidth=0.5, zorder=10)

    def draw_x_axis_ticks(self):
        # Grid ticks
        def _add_grid_ticks(x_range, x_ticks_pos, x_ticks_val, disp_labels):
            step = self.visualization_settings.get_item_value(
                'x_axis', 'line_separation')
            grid_ticks_pos = np.arange(
                x_range[0], x_range[-1], step=step).tolist()
            grid_tick_labels = ['%.1f' % v for v in grid_ticks_pos] if (
                disp_labels) else ['' for _ in grid_ticks_pos]
            x_ticks_pos += grid_ticks_pos
            x_ticks_val += grid_tick_labels
            return x_ticks_pos, x_ticks_val

        # Params
        mode = self.visualization_settings.get_item_value('mode')
        disp_grid = self.visualization_settings.get_item_value(
            'x_axis', 'display_grid')
        # Init x-axis ticks
        x_ticks_pos = []
        x_ticks_val = []
        if len(self.time_in_graph) > 0:
            if mode == 'geek':
                # Get range
                x = self.time_in_graph
                x_range = (x[0], x[-1])
                # Time ticks
                if disp_grid:
                    x_ticks_pos, x_ticks_val = _add_grid_ticks(
                        x_range, x_ticks_pos, x_ticks_val, disp_labels=True)
            elif mode == 'clinical':
                # Set timestamps
                x = np.mod(self.time_in_graph, self.win_t)
                # Range
                n_win = self.time_in_graph.max() // self.win_t
                x_range = (0, self.win_t) if n_win == 0 else (x[0], x[-1])
                x_range_real = (0, self.win_t) if n_win == 0 else \
                    (self.time_in_graph[0], self.time_in_graph[-1])
                # Add invisible ticks to avoid movement of the axis
                x_ticks_pos += x_range
                x_ticks_val += ['\u00A0\u00A0\u00A0' for v in x_range_real]
                # Visualization grid
                if disp_grid:
                    x_ticks_pos, x_ticks_val = _add_grid_ticks(
                        x_range, x_ticks_pos, x_ticks_val, disp_labels=False)
        else:
            # Get range
            x_range = (0, self.win_t)
            # Add range ticks
            x_ticks_pos += x_range
            x_ticks_val += ['%.1f' % v for v in x_range]
            # Grid
            if disp_grid:
                x_ticks_pos, x_ticks_val = _add_grid_ticks(
                    x_range, x_ticks_pos, x_ticks_val,
                    disp_labels=False)

        # Set ticks
        self.ax.set_xticks(x_ticks_pos)
        self.ax.set_xticklabels(x_ticks_val)
        self.ax.set_xlim(x_range[0], x_range[1])
        self.ax.grid(visible=disp_grid, axis='x', color=self.text_color,
                     linestyle='-', linewidth=0.5, zorder=10)

    def append_data(self, chunk_times, chunk_signal):
        if self.visualization_settings.get_item_value('mode') == 'geek':
            self.time_in_graph = np.hstack((self.time_in_graph, chunk_times))
            self.sig_in_graph = np.vstack((self.sig_in_graph, chunk_signal))
            abs_time_in_graph = self.time_in_graph - self.time_in_graph[0]
            if abs_time_in_graph[-1] >= self.win_t:
                cut_idx = np.argmin(
                    np.abs(abs_time_in_graph -
                           (abs_time_in_graph[-1] - self.win_t)))
                self.time_in_graph = self.time_in_graph[cut_idx:]
                self.sig_in_graph = self.sig_in_graph[cut_idx:]
        elif self.visualization_settings.get_item_value('mode') == 'clinical':
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
        return self.time_in_graph, self.sig_in_graph

    def autoscale(self):
        """
        Automatically adjust spectrogram color limits (clim) based on the
        statistics of the current frame.

        Settings used (visualization_settings -> z_axis):
            - range: [vmin, vmax]        # manual/default clim
            - autoscale.apply: bool      # enable/disable autoscale
            - autoscale.n_std_tolerance: float
            - autoscale.n_std_separation: float
        """

        # --- Get autoscale settings ---
        auto_scale = self.visualization_settings.get_item('z_axis', 'autoscale')
        # Statistics of the current spectrogram frame
        arr = np.asarray(self.spec_in_graph)
        if arr.size == 0 or not np.any(np.isfinite(arr)):
            return  # nothing to do
        mean_val = np.nanmean(arr)
        std_val = np.nanstd(arr)
        # Safety fallback
        if std_val <= 0 or not np.isfinite(std_val):
            std_val = 1e-12
        # Current limits (might be NaN on first runs)
        old_vmin, old_vmax = self.im.get_clim()
        if not np.isfinite(old_vmin) or not np.isfinite(old_vmax):
            # Initialize from configured range
            old_vmin, old_vmax = self.visualization_settings.get_item_value(
                'z_axis', 'range')
        old_span = max(old_vmax - old_vmin, 1e-12)
        # Autoscale params
        std_tol = auto_scale.get_item_value('n_std_tolerance')
        std_factor = auto_scale.get_item_value('n_std_separation')
        # Expected span based on current spec
        new_span = std_factor * std_val
        # decide if reescale needed
        do_rescale = (
                new_span > old_span * std_tol or  # too large for current scale
                new_span < old_span / std_tol  # too small for current scale
        )
        if not do_rescale:
            return
        # New limits
        new_vmin = mean_val - 0.5 * new_span
        new_vmax = mean_val + 0.5 * new_span
        # Optional padding
        pad = 0.05 * new_span
        new_vmin -= pad
        new_vmax += pad
        # Safety for log-power spectrograms
        if self.signal_settings.get_item_value('spectrogram', 'log_power'):
            new_vmin = max(new_vmin, -300)  # avoid insane log values
            new_vmax = min(new_vmax, 300)
        new_range = [float(new_vmin), float(new_vmax)]
        # Apply to image
        self.im.set_clim(new_range[0], new_range[1])
        self.c_lim = new_range

    def update_plot_data(self, chunk_times, chunk_signal):
        """
        Append the new data, then recalc and update the spectrogram.
        """
        try:
            # INITIAL OPERATIONS ===============================================
            mode = self.visualization_settings.get_item_value('mode')
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if mode == 'clinical':
                    self.ax.add_line(self.marker)

            # DATA OPERATIONS ==================================================
            # Temporal series are always plotted from zero.
            chunk_times = chunk_times - self.init_time
            # Append new data into our ring buffers
            t_in_graph, sig_in_graph = self.append_data(chunk_times, chunk_signal)
            time_window = self.signal_settings.get_item_value('spectrogram', 'time_window') \
                if len(t_in_graph) >= self.win_s_spec else len(t_in_graph) / self.fs

            # Chronological reordering of the signal
            if self.visualization_settings.get_item_value('mode') == 'clinical':
                signal = np.vstack((sig_in_graph[np.argmax(t_in_graph)+1:],
                                       sig_in_graph[:np.argmax(t_in_graph)+1]))
            else:
                signal = sig_in_graph.copy()

            # Compute spectrogram
            spec, t, f = fourier_spectrogram(
                signal[:, self.curr_cha], self.fs,
                time_window=time_window,
                overlap_pct=self.signal_settings.get_item_value('spectrogram', 'overlap_pct'),
                smooth=self.signal_settings.get_item_value('spectrogram', 'smooth'),
                smooth_sigma=self.signal_settings.get_item_value('spectrogram', 'smooth_sigma'),
                apply_detrend=self.signal_settings.get_item_value('spectrogram', 'apply_detrend'),
                apply_normalization=self.signal_settings.get_item_value('spectrogram', 'apply_normalization'),
                scale_to=self.signal_settings.get_item_value('spectrogram', 'scale_to'))
            # Optionally convert to log scale
            if self.signal_settings.get_item_value('spectrogram', 'log_power'):
                spec = 10 * np.log10(spec + 1e-12)
            # Update the image
            if mode == 'clinical':
                # Update the time marker
                x = np.mod(self.time_in_graph, self.win_t)
                # Marker
                marker_x = x[self.pointer]
                self.marker.set_xdata([marker_x, marker_x])
                # Ùpdate marker text
                marker_time = self.time_in_graph[self.pointer]
                # Position text under the marker line
                self.marker_tick.set_position((marker_x, self.marker_y_pos))
                self.marker_tick.set_text(f'{marker_time:.1f}')
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
            elif mode == 'geek':
                self.im.set_extent([t_in_graph[0], t_in_graph[-1], f[0], f[-1]])

            # Data
            self.spec_in_graph = spec
            self.im.set_data(spec)
            self.draw_x_axis_ticks()
            self.draw_y_axis_ticks()

            # Autoscale and update clim
            apply_autoscale = self.visualization_settings.get_item_value(
                'z_axis', 'autoscale', 'apply')
            if apply_autoscale:
                self.autoscale()
            self.c_lim = self.im.get_clim()

            # UPDATE PLOT ======================================================
            if not self.widget.isVisible():
                return
            if self.check_if_redraw_needed():
                # If axis limits have changed, re-draw everything
                self.widget.draw()
                self._bg_cache = self.widget.copy_from_bbox(self.fig.bbox)
            else:
                # Restore static background
                self.widget.restore_region(self._bg_cache)
            # Draw animated elements
            self.ax.draw_artist(self.im)
            if mode == 'clinical':
                self.ax.draw_artist(self.marker)
                self.ax.draw_artist(self.marker_tick)
            # Redraw grid on top
            # todo: I don't like this solution, but I haven't found another
            #  way for the moment. The grid lines should be drawn only if
            #  strictly necessary, as it can be computationally expensive.
            if self.visualization_settings.get_item_value(
                    'x_axis', 'display_grid'):
                for line in self.ax.get_xgridlines():
                    self.ax.draw_artist(line)
            if self.visualization_settings.get_item_value(
                'y_axis', 'display_grid'):
                for line in self.ax.get_ygridlines():
                    self.ax.draw_artist(line)
            # Update only animated elements
            self.widget.blit(self.fig.bbox)

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

    def mouse_wheel_event(self, event):
        pass

    @staticmethod
    def get_default_settings():
        """
        Returns a tuple: (signal_settings, visualization_settings).
        Adjust or rename keys to your needs.
        """
        # Basic signal-processing settings
        # Basic signal-processing settings
        signal_settings = SettingsTree()
        signal_settings.add_item(
            "min_update_time",
            value=0.1,
            value_range=[0, None],
            info=(
                "Minimum update interval (s) for refreshing the plot. This value may "
                "automatically increase to prevent system overload, depending on your "
                "hardware performance and the complexity of the plots panel "
                "configuration."
            ),
        )

        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item(
            "apply",
            value=True,
            info="Apply an IIR filter in real time.",
        )
        freq_filt.add_item(
            "type",
            value="highpass",
            value_options=["highpass", "lowpass", "bandpass", "stopband"],
            info="Filter type.",
        )
        freq_filt.add_item(
            "cutoff_freq",
            value=[1.0],
            info=(
                "Cutoff frequencies. One value for high/low-pass; two values for "
                "band/stop-band."
            ),
        )
        freq_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "IIR filter order. Higher orders yield steeper responses but raise "
                "computational cost and latency."
            ),
        )

        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item(
            "apply",
            value=False,
            info="Apply a notch filter to attenuate power-line interference.",
        )
        notch_filt.add_item(
            "freq",
            value=50.0,
            value_range=[0, None],
            info="Notch center frequency (Hz).",
        )
        notch_filt.add_item(
            "bandwidth",
            value=[-0.5, 0.5],
            info=(
                "Relative limits around the center frequency to define the notch "
                "band."
            ),
        )
        notch_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "Notch filter order. Higher values increase selectivity and cost."
            ),
        )

        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item(
            "apply",
            value=False,
            info="Enable re-referencing of the signals.",
        )
        re_ref.add_item(
            "type",
            value="car",
            value_options=["car", "channel"],
            info=(
                "Re-referencing method. 'car' applies Common Average Reference; "
                "'channel' subtracts a specific channel."
            ),
        )
        re_ref.add_item(
            "channel",
            value="",
            info="Channel label used when the type is 'channel'.",
        )

        down_samp = signal_settings.add_item("downsampling")
        down_samp.add_item(
            "apply",
            value=False,
            info="Reduce the sample rate of the incoming LSL stream.",
        )
        down_samp.add_item(
            "factor",
            value=2.0,
            value_range=[0, None],
            info="Downsampling factor (e.g., 2 halves the sample rate).",
        )

        spectrogram = signal_settings.add_item("spectrogram")
        spectrogram.add_item(
            "time_window",
            value=5.0,
            value_range=[0, None],
            info="Duration (s) of data kept in the rolling buffer.",
        )
        spectrogram.add_item(
            "overlap_pct",
            value=90.0,
            value_range=[0, 100],
            info="Segment overlap (%) used in the STFT/Welch computation.",
        )
        spectrogram.add_item(
            "scale_to",
            value="psd",
            value_options=["psd", "magnitude"],
            info=(
                "Output scaling for the spectrogram: power spectral density ('psd') "
                "or linear magnitude ('magnitude')."
            ),
        )
        spectrogram.add_item(
            "smooth",
            value=True,
            info="Apply a Gaussian filter to smooth the spectrogram.",
        )
        spectrogram.add_item(
            "smooth_sigma",
            value=2.0,
            value_range=[0, None],
            info="Sigma of the Gaussian smoothing kernel (in pixels).",
        )
        spectrogram.add_item(
            "apply_detrend",
            value=True,
            info="Apply linear detrending before the STFT.",
        )
        spectrogram.add_item(
            "apply_normalization",
            value=True,
            info=(
                "Normalize the signal to unit standard deviation before the STFT to "
                "reduce scale variability."
            ),
        )
        spectrogram.add_item(
            "log_power",
            value=True,
            info="Display power on a logarithmic scale (log-power).",
        )

        power_dist = signal_settings.add_item("power_distribution")
        power_dist.add_item(
            'band_labels',
            value=['Delta', 'Theta', 'Alpha', 'Beta 1', 'Beta 2'],
            info='List with a names of the frequency bands')
        power_dist.add_item(
            "band_freqs",
            value=[[0.5, 4], [4, 8], [8, 13], [13, 30], [30, 100]],
            info="List of frequency bands [min, max] in Hz")

        visualization_settings = SettingsTree()
        visualization_settings.add_item(
            "mode",
            value="clinical",
            value_options=["clinical", "geek"],
            info=(
                "Visualization mode. 'clinical' uses sweeping updates; 'geek' "
                "shows a continuously growing trace."
            ),
        )
        visualization_settings.add_item(
            "init_channel_label",
            value="",
            info="Channel selected for initial visualization.",
        )
        visualization_settings.add_item(
            "title_label_size",
            value=10.0,
            value_range=[0, None],
            info="Title font size (pt).",
        )

        x_ax = visualization_settings.add_item("x_axis")
        x_ax.add_item(
            "seconds_displayed",
            value=30.0,
            value_range=[0, None],
            info="Time range (s) displayed on the X axis.",
        )
        x_ax.add_item(
            "tick_label_size",
            value=8.0,
            value_range=[0, None],
            info="Font size (pt) for X-axis tick labels.",
        )
        x_ax.add_item(
            "label",
            value="Time (s)",
            info="Label for the X axis (HTML allowed).",
        )
        x_ax.add_item(
            "label_size",
            value=8.0,
            value_range=[0, None],
            info="Font size (pt) for the X-axis label.",
        )
        x_ax.add_item(
            "display_grid",
            value=True,
            info="Show grid lines on the x-axis.",
        )
        x_ax.add_item(
            "line_separation",
            value=5.0,
            value_range=[0, None],
            info="Separation between Y-axis ticks (Hz).",
        )

        y_ax = visualization_settings.add_item("y_axis")
        y_ax.add_item(
            "range",
            value=[0, 30],
            info="Y-axis range (min, max).",
        )
        y_ax.add_item(
            "tick_label_size",
            value=8.0,
            value_range=[0, None],
            info="Font size (pt) for Y-axis tick labels.",
        )
        y_ax.add_item(
            "label",
            value="Frequency (Hz)",
            info="Label for the Y axis (HTML allowed).",
        )
        y_ax.add_item(
            "label_size",
            value=8.0,
            value_range=[0, None],
            info="Font size (pt) for the Y-axis label.",
        )
        y_ax.add_item(
            "display_grid",
            value=True,
            info="Show grid lines on the y-axis.",
        )
        y_ax.add_item(
            "line_separation",
            value=5.0,
            value_range=[0, None],
            info="Separation between Y-axis ticks (Hz).",
        )

        z_ax = visualization_settings.add_item("z_axis")
        z_ax.add_item(
            "cmap",
            value="Accent",
            info="Matplotlib colormap used for the spectrogram.",
        )
        z_ax.add_item(
            "range",
            value=[0.0, 1.0],
            info="Range of the z-axis (clim).",
        )

        auto_scale = z_ax.add_item("autoscale")
        auto_scale.add_item(
            "apply",
            value=False,
            info="Automatically scale the z-axis.",
        )
        auto_scale.add_item(
            "n_std_tolerance",
            value=1.25,
            value_range=[0, None],
            info=(
                "Autoscale limit: if the signal exceeds this value, the scale "
                "is re-adjusted."
            ),
        )
        auto_scale.add_item(
            "n_std_separation",
            value=5.0,
            value_range=[0, None],
            info="Separation between channels (in standard deviations).",
        )
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel").\
            edit_item(value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        visualization_settings.get_item("init_channel_label").\
            edit_item(value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    def init_plot(self):
        """
        Initialize the spectrogram plot, figure, axes, etc.
        This is called once, when the stream is first set up.
        """
        # INIT SIGNAL VARIABLES ================================================

        # Get channel
        init_cha_label = self.visualization_settings.get_item_value(
            'init_channel_label')
        self.curr_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label)

        # Inherit the main time-window size from the settings
        self.win_t = self.visualization_settings.get_item_value(
            'x_axis', 'seconds_displayed')
        self.win_s = int(self.win_t * self.fs)

        # Spectrogram window
        self.win_t_spec = self.signal_settings.get_item_value(
            'spectrogram', 'time_window')
        self.win_s_spec = (
            int(self.signal_settings.get_item_value(
                'spectrogram', 'time_window') * self.fs))

        # Update frequency bands dict
        self.frequency_bands = self.signal_settings.get_item(
            'power_distribution')

        # Initialize buffers
        self.time_in_graph = np.zeros(0)
        self.sig_in_graph = np.zeros((0, self.lsl_stream_info.n_cha))

        # INIT FIGURE ==========================================================
        # Set titles
        self.ax.set_xlabel(
            self.visualization_settings.get_item_value('x_axis', 'label'),
            color=self.text_color)
        self.ax.set_ylabel(
            self.visualization_settings.get_item_value('y_axis', 'label'),
            color=self.text_color)
        self.ax.set_title(
            self.lsl_stream_info.l_cha[self.curr_cha],
            color=self.text_color,
            fontsize=self.visualization_settings.get_item_value(
                'title_label_size'))

        # Initial patches
        self.cmap = get_cmap(
            self.visualization_settings.get_item_value('z_axis', 'cmap'))
        self.patches = []
        band_labels = self.frequency_bands.get_item_value('band_labels')
        for i in range(len(band_labels)):
            patch_style = {'color': self.cmap.colors[i],
                           'alpha': 1}
            patch, _ = self.ax.fill([], [], [], 
                                    animated=True, 
                                    **patch_style)
            self.patches.append(patch)
        # Set the legend
        legend = self.ax.legend(self.patches, band_labels, loc='upper right')
        legend.set_animated(True)
        # Set grid for the axes
        if self.visualization_settings.get_item_value('x_axis', 'display_grid'):
            self.ax.grid(True, axis='x',
                         color=self.grid_color,
                         linewidth=self.grid_width)
        if self.visualization_settings.get_item_value('y_axis', 'display_grid'):
            self.ax.grid(True, axis='y',
                         color=self.grid_color,
                         linewidth=self.grid_width)
        # Ticks and spines
        for s in self.ax.spines.values():
            s.set_color(self.text_color)
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=True, labelbottom=True,
                right=False, labelright=False,
                top=False, labeltop=False,
                labelcolor=self.text_color,
                labelsize=self.visualization_settings.get_item_value(
                    'x_axis', 'tick_label_size')
            )
        elif mode == 'clinical':
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=False, labelbottom=False,
                right=False, labelright=False,
                top=False, labeltop=False,
                labelcolor=self.text_color)
        # Marker for clinical mode
        if mode == 'clinical':
            self.marker = self.ax.axvline(x=0, color=self.marker_color,
                                          linewidth=self.marker_width,
                                          animated=True)
            # x in DATA coords, y in AXES coords
            blend = mtransforms.blended_transform_factory(self.ax.transData,
                                                          self.ax.transAxes)
            self.marker_tick = self.ax.text(
                0, self.marker_y_pos, '', transform=blend,
                ha='center', va='top', color=self.text_color,
                clip_on=False, animated=True)
            self.pointer = -1
        # Set axis limits
        self.y_range = self.visualization_settings.get_item_value(
            'y_axis', 'range')
        if not isinstance(self.y_range, list):
            self.y_range = [0, self.y_range]

        # Display initial array
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()

        # Refresh the plot
        self.widget.draw()
        
        # Blitting setup
        self._bg_cache = self.widget.copy_from_bbox(self.fig.bbox)
        self._cached_elements = self._get_cache_elements()

    def _get_cache_elements(self):
        current_elements = {
            'curr_cha': self.curr_cha,
            'xlim': self.ax.get_xlim(),
            'ylim': self.ax.get_ylim(),
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

    def autoscale(self):
        pass

    def update_plot_data(self, chunk_times, chunk_signal):
        """
        Append the new data, then recalc and update the spectrogram.
        """
        try:
            # INITIAL OPERATIONS ===============================================
            mode = self.visualization_settings.get_item_value('mode')
            if self.init_time is None:
                self.init_time = chunk_times[0]
                if mode == 'clinical':
                    self.ax.add_line(self.marker)

            # DATA OPERATIONS ==================================================
            # Temporal series are always plotted from zero.
            chunk_times = chunk_times - self.init_time
            # Append new data into our ring buffers
            t_in_graph, sig_in_graph = self.append_data(chunk_times,
                                                        chunk_signal)
            time_window = self.signal_settings.get_item_value('spectrogram',
                                                              'time_window') \
                if len(t_in_graph) >= self.win_s_spec else len(
                t_in_graph) / self.fs

            # Chronological reordering of the signal
            if self.visualization_settings.get_item_value('mode') == 'clinical':
                signal = np.vstack((sig_in_graph[np.argmax(t_in_graph) + 1:],
                                    sig_in_graph[:np.argmax(t_in_graph) + 1]))
            else:
                signal = sig_in_graph.copy()

            # Compute spectrogram
            spec, t, f = fourier_spectrogram(
                signal[:, self.curr_cha], self.fs,
                time_window=time_window,
                overlap_pct=self.signal_settings.get_item_value('spectrogram', 'overlap_pct'),
                smooth=self.signal_settings.get_item_value('spectrogram', 'smooth'),
                smooth_sigma=self.signal_settings.get_item_value('spectrogram', 'smooth_sigma'),
                apply_detrend=self.signal_settings.get_item_value('spectrogram', 'apply_detrend'),
                apply_normalization=self.signal_settings.get_item_value('spectrogram', 'apply_normalization'),
                scale_to=self.signal_settings.get_item_value('spectrogram', 'scale_to'))
            # Optionally convert to log scale
            if self.signal_settings.get_item_value('spectrogram', 'log_power'):
                spec = 10 * np.log10(spec + 1e-12)
            # Redefine the t_in_graph vector to match t dimensions
            interp_func = interpolate.interp1d(np.linspace(0, 1, len(t_in_graph)),
                                   t_in_graph, kind='linear',
                                   fill_value="extrapolate")
            t_in_graph_resampled = interp_func(np.linspace(0, 1, len(t)))
            # Limit t vector
            if len(t_in_graph_resampled) != spec.shape[1]:
                t_in_graph_resampled = t_in_graph_resampled[:spec.shape[1]]
            # Calculate x axis
            mode = self.visualization_settings.get_item_value('mode')
            if mode == 'geek':
                x = t_in_graph_resampled
            elif mode == 'clinical':
                x = np.mod(t_in_graph_resampled, self.win_t)
                x_t = np.mod(self.time_in_graph, self.win_t)
                # Marker
                marker_x = x_t[self.pointer]
                self.marker.set_xdata([marker_x, marker_x])
                # Ùpdate marker text
                marker_time = self.time_in_graph[self.pointer]
                # Position text under the marker line
                self.marker_tick.set_position((marker_x, self.marker_y_pos))
                self.marker_tick.set_text(f'{marker_time:.1f}')
                # Reorder the spectrogram
                idx = np.argmax(t_in_graph_resampled)
                if idx < spec.shape[1] - 1:
                    spec = np.hstack((spec[:, -idx - 1:].copy(),
                                      spec[:, : -idx - 1].copy()))
            # Normalize each time bin
            spec_norm = spec / spec.sum(axis=0)
            # Calculate power distribution
            cumulative_power = np.zeros(spec.shape[1])
            band_labels = self.frequency_bands.get_item_value('band_labels')
            band_freqs = self.frequency_bands.get_item_value('band_freqs')
            for i_b in range(len(band_labels)):
                idx_min = np.argmin(np.abs(f - band_freqs[i_b][0]))
                idx_max = np.argmin(np.abs(f - band_freqs[i_b][1]))
                relative_power = spec_norm[idx_min:idx_max, :].sum(axis=0) * 100
                # Calculate patch coordinates
                patch_base = np.column_stack([x, cumulative_power])
                cumulative_power += relative_power
                patch_top = np.column_stack([x, cumulative_power])
                # Set the patch
                self.patches[i_b].set_xy(
                    np.concatenate([patch_base, patch_top[::-1]], axis=0))
            # Draw axis
            self.draw_x_axis_ticks()
            self.draw_y_axis_ticks()

            # UPDATE PLOT ======================================================
            if not self.widget.isVisible():
                return

            if self.check_if_redraw_needed():
                # If axis limits have changed, re-draw everything
                self.widget.draw()
                self._bg_cache = self.widget.copy_from_bbox(self.fig.bbox)
            else:
                # Restore static background
                self.widget.restore_region(self._bg_cache)
            # Draw animated patches
            for patch in self.patches:
                self.ax.draw_artist(patch)
            # Marker
            if mode == 'clinical':
                self.ax.draw_artist(self.marker)
                self.ax.draw_artist(self.marker_tick)
            # Redraw grid on top
            # todo: I don't like this solution, but I haven't found another
            #  way for the moment. The grid lines should be drawn only if
            #  strictly necessary, as it can be computationally expensive.
            if self.visualization_settings.get_item_value(
                    'x_axis', 'display_grid'):
                for line in self.ax.get_xgridlines():
                    self.ax.draw_artist(line)
            if self.visualization_settings.get_item_value(
                    'y_axis', 'display_grid'):
                for line in self.ax.get_ygridlines():
                    self.ax.draw_artist(line)
            # Draw legend on top
            legend = self.ax.get_legend()
            self.ax.draw_artist(legend)
            # Update only animated elements
            self.widget.blit(self.fig.bbox)

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

        # Style and  theme
        self.background_color = self.theme_colors['THEME_BG_DARK']
        self.text_color = self.theme_colors['THEME_TEXT_LIGHT']

        # Widget variables
        self.widget = self.init_widget()
        self.fig = self.widget.figure
        self.ax = self.fig.axes[0]
        self.topo_plot = None

    def init_widget(self):
        # Init figure
        fig = Figure(figsize=(1, 1), dpi=90)
        ax = fig.add_subplot(111)
        fig.set_layout_engine('constrained', rect=[0, 0, 1, 1])
        # fig.subplots_adjust(left=0.005, right=0.995, bottom=0.005, top=0.995)
        fig.patch.set_facecolor(self.background_color)
        ax.set_facecolor(self.background_color)
        # Init widget
        widget = FigureCanvasQTAgg(fig)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # widget.setContextMenuPolicy(Qt.CustomContextMenu)
        # widget.customContextMenuRequested.connect(self.show_context_menu)
        # widget.wheelEvent = self.mouse_wheel_event
        return widget

    @staticmethod
    def check_signal(lsl_stream_info):
        if lsl_stream_info.medusa_type != 'EEG':
            raise ValueError('Wrong signal type %s. TopographyPlot only '
                             'supports EEG signals' %
                             (lsl_stream_info.medusa_type))
        pass

    @staticmethod
    def get_default_settings():
        signal_settings = SettingsTree()
        signal_settings.add_item(
            "min_update_time",
            value=0.1,
            value_range=[0, None],
            info=(
                "Minimum update interval (s) for refreshing the plot. This "
                "value may automatically increase to prevent system overload, "
                "depending on your hardware performance and the complexity of "
                "the plots panel configuration"
            ),
        )

        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item(
            "apply",
            value=True,
            info="Apply IIR filter in real-time",
        )
        freq_filt.add_item(
            "type",
            value="highpass",
            value_options=["highpass", "lowpass", "bandpass", "stopband"],
            info="Filter type",
        )
        freq_filt.add_item(
            "cutoff_freq",
            value=[1],
            info=(
                "List with one cutoff for highpass/lowpass, two for "
                "bandpass/stopband"
            ),
        )
        freq_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "Order of the filter (the higher, the greater computational "
                "cost)"
            ),
        )

        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item(
            "apply",
            value=True,
            info="Apply notch filter to get rid of power line interference",
        )
        notch_filt.add_item(
            "freq",
            value=50.0,
            value_range=[0, None],
            info="Center frequency to be filtered",
        )
        notch_filt.add_item(
            "bandwidth",
            value=[-0.5, 0.5],
            info="List with relative limits of center frequency",
        )
        notch_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "Order of the filter (the higher, the greater computational "
                "cost)"
            ),
        )

        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item(
            "apply",
            value=False,
            info="Change the reference of your signals",
        )
        re_ref.add_item(
            "type",
            value="car",
            value_options=["car", "channel"],
            info=(
                "Type of re-referencing: Common Average Reference or channel "
                "subtraction"
            ),
        )
        re_ref.add_item(
            "channel",
            value="",
            info="Channel label for re-referencing if channel is selected",
        )

        down_samp = signal_settings.add_item("downsampling")
        down_samp.add_item(
            "apply",
            value=False,
            info="Reduce the sample rate of the incoming LSL stream",
        )
        down_samp.add_item(
            "factor",
            value=2.0,
            value_range=[0, None],
            info="Downsampling factor",
        )

        psd = signal_settings.add_item("psd")
        psd.add_item(
            "time_window_seconds",
            value=5.0,
            value_range=[0, None],
            info="Window length (s) used to estimate the PSD.",
        )
        psd.add_item(
            "welch_overlap_pct",
            value=25.0,
            value_range=[0, 100],
            info="Segment overlap for Welch’s method (%).",
        )
        psd.add_item(
            "welch_seg_len_pct",
            value=50.0,
            value_range=[0, 100],
            info="Segment length as a percentage of the window length (%).",
        )
        psd.add_item(
            "log_power", value=False,
            info="If True, display PSD in dB (10 * log10)."
        )
        psd.add_item(
            "power_range", value=[8, 13],
            info="Frequency range to compute the power of the PSD"
        )

        visualization_settings = SettingsTree()

        title = visualization_settings.add_item('title')
        title.add_item(
            "text",
            value="Power topography",
            info="Title displayed above the topographic map."
        )
        title.add_item(
            "font_size",
            value=12.0,
            value_range=[0, None],
            info="Title font size (pt).",
        )

        visualization_settings.add_item(
            "channel_standard",
            value="10-05",
            value_options=["10-20", "10-10", "10-05"],
            info="EEG electrode montage used to position channels on the scalp."
        )

        visualization_settings.add_item(
            "head_radius",
            value=1.0,
            value_range=[0, 1],
            info="Relative head radius in plot coordinates (0–1)."
        )

        visualization_settings.add_item(
            "head_line_width",
            value=4.0,
            value_range=[0, None],
            info="Line width used to draw the head outline, ears, and nose."
        )

        visualization_settings.add_item(
            "head_skin_color",
            value="#E8BEAC",
            info="Fill color used for the head (scalp) area."
        )

        visualization_settings.add_item(
            "plot_channel_labels",
            value=False,
            info="If True, display the channel labels on the plot."
        )

        visualization_settings.add_item(
            "plot_channel_points",
            value=True,
            info="If True, display channel marker points on the plot."
        )

        chan_radius_size = visualization_settings.add_item(
            "channel_radius_size")
        chan_radius_size.add_item(
            "auto",
            value=True,
            info="If True, automatically compute the radius of channel markers."
        )
        chan_radius_size.add_item(
            "value",
            value=0.0,
            value_range=[0, None],
            info="Custom radius for channel markers when automatic sizing is disabled."
        )

        visualization_settings.add_item(
            "interpolate",
            value=True,
            info="If True, interpolate between channels to generate a smooth topographic map."
        )

        visualization_settings.add_item(
            "extra_radius",
            value=0.29,
            value_range=[0, 1],
            info="Additional radius beyond the head used for the interpolation grid (0–1)."
        )

        visualization_settings.add_item(
            "interp_neighbors",
            value=3,
            value_range=[1, None],
            info="Number of nearest neighbors used for interpolation at each grid point."
        )

        visualization_settings.add_item(
            "interp_points",
            value=100,
            value_range=[1, None],
            info="Number of interpolation points per axis for the topographic grid."
        )

        visualization_settings.add_item(
            "interp_contour_width",
            value=0.8,
            value_range=[0, None],
            info="Line width used to draw contour lines over the topographic map."
        )

        visualization_settings.add_item(
            "label_color",
            value="w",
            info="Color used for channel label text."
        )

        z_ax = visualization_settings.add_item("z_axis")
        z_ax.add_item(
            "cmap",
            value="inferno",
            info="Matplotlib colormap used for the spectrogram.",
        )
        clim = z_ax.add_item("clim")
        clim.add_item(
            "auto", value=True,
            info="Check for automatic color bar limits computation")
        clim.add_item(
            "values", value=[0.0, 1.0],
            info="Max and min bar limits customized")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel").\
            edit_item(value=stream_info.l_cha[0], value_options=stream_info.l_cha)
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

        # INIT SIGNAL VARIABLES ================================================

        # Signal processing
        self.win_t = self.signal_settings.get_item_value(
            'psd', 'time_window_seconds')
        self.win_s = int(self.win_t * self.fs)
        # Create channel set
        self.channel_set = (
            lsl_utils.lsl_channel_info_to_eeg_channel_set(
                self.lsl_stream_info.cha_info,
                discard_unlocated_channels=True))
        # Initialize buffers
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.channel_set.n_cha])

        # INIT FIGURE ==========================================================

        # Set title
        self.ax.set_title(
            self.visualization_settings.get_item_value('title', 'text'),
            fontsize=self.visualization_settings.get_item_value('title', 'font_size'),
            color=self.text_color)

        # Initialize topography plot
        if self.visualization_settings.get_item_value('channel_radius_size', 'auto'):
            channel_radius_size = None
        else:
            channel_radius_size = self.visualization_settings.get_item_value('channel_radius_size', 'value')
        if self.visualization_settings.get_item_value('z_axis', 'clim', 'auto'):
            clim = None
        else:
            clim = tuple(self.visualization_settings.get_item_value('z_axis', 'clim', 'values'))
        self.topo_plot = head_plots.TopographicPlot(
            axes=self.ax,
            channel_set=self.channel_set,
            head_radius=self.visualization_settings.get_item_value('head_radius'),
            head_line_width=self.visualization_settings.get_item_value('head_line_width'),
            head_skin_color=self.visualization_settings.get_item_value('head_skin_color'),
            plot_channel_labels=self.visualization_settings.get_item_value('plot_channel_labels'),
            plot_channel_points=self.visualization_settings.get_item_value('plot_channel_points'),
            channel_radius_size=channel_radius_size,
            interpolate=self.visualization_settings.get_item_value('interpolate'),
            extra_radius=self.visualization_settings.get_item_value('extra_radius'),
            interp_neighbors=self.visualization_settings.get_item_value('interp_neighbors'),
            interp_points=self.visualization_settings.get_item_value('interp_points'),
            interp_contour_width=self.visualization_settings.get_item_value('interp_contour_width'),
            cmap=self.visualization_settings.get_item_value('z_axis', 'cmap'),
            clim=clim,
            label_color=self.visualization_settings.get_item_value('label_color'))

        # Refresh the plot
        self.widget.draw()

    def update_plot_data(self, chunk_times, chunk_signal):
        try:
            # DATA OPERATIONS ==================================================
            # print('Chunk received at: %.6f' % time.time())
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            # Compute PSD
            welch_seg_len = np.round(
                self.signal_settings.get_item_value('psd', 'welch_seg_len_pct') / 100.0
                * sig_in_graph.shape[0]).astype(int)
            welch_overlap = np.round(
                self.signal_settings.get_item_value('psd', 'welch_overlap_pct') / 100.0
                * welch_seg_len).astype(int)
            welch_ndft = welch_seg_len
            _, psd = scp_signal.welch(
                sig_in_graph, fs=self.fs,
                nperseg=welch_seg_len, noverlap=welch_overlap,
                nfft=welch_ndft, axis=0)
            # Compute power
            power_values = spectral_parameteres.band_power(
                psd=psd[np.newaxis, :, :], fs=self.fs,
                target_band=self.signal_settings.get_item_value('psd', 'power_range'))

            # UPDATE PLOT ======================================================
            if not self.widget.isVisible():
                return
            # todo: blitting
            self.topo_plot.update(values=power_values)
            width, height = self.widget.get_width_height()
            if width > 0 and height > 0:
                # Update plot
                self.widget.draw()

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

        # Style and  theme
        self.background_color = self.theme_colors['THEME_BG_DARK']
        self.text_color = self.theme_colors['THEME_TEXT_LIGHT']

        # Widget variables
        self.widget = self.init_widget()
        self.fig = self.widget.figure
        self.ax = self.fig.axes[0]
        self.conn_plot = None

    def init_widget(self):
        # Init figure
        fig = Figure(figsize=(1, 1), dpi=90)
        ax = fig.add_subplot(111)
        fig.set_layout_engine('constrained', rect=[0, 0, 1, 1])
        # fig.subplots_adjust(left=0.005, right=0.995, bottom=0.005, top=0.995)
        fig.patch.set_facecolor(self.background_color)
        ax.set_facecolor(self.background_color)
        # Init widget
        widget = FigureCanvasQTAgg(fig)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # widget.setContextMenuPolicy(Qt.CustomContextMenu)
        # widget.customContextMenuRequested.connect(self.show_context_menu)
        # widget.wheelEvent = self.mouse_wheel_event
        return widget

    @staticmethod
    def check_signal(lsl_stream_info):
        if lsl_stream_info.medusa_type != 'EEG':
            raise ValueError('Wrong signal type %s. ConnectivityPlot only '
                             'supports EEG signals' %
                             (lsl_stream_info.medusa_type))
        pass

    @staticmethod
    def get_default_settings():
        signal_settings = SettingsTree()
        signal_settings.add_item(
            "min_update_time",
            value=0.1,
            value_range=[0, None],
            info=(
                "Minimum update interval (s) for refreshing the plot. This "
                "value may automatically increase to prevent system overload, "
                "depending on your hardware performance and the complexity of "
                "the plots panel configuration"
            ),
        )

        freq_filt = signal_settings.add_item("frequency_filter")
        freq_filt.add_item(
            "apply",
            value=True,
            info="Apply IIR filter in real-time",
        )
        freq_filt.add_item(
            "type",
            value="highpass",
            value_options=["highpass", "lowpass", "bandpass", "stopband"],
            info="Filter type",
        )
        freq_filt.add_item(
            "cutoff_freq",
            value=[1],
            info=(
                "List with one cutoff for highpass/lowpass, two for "
                "bandpass/stopband"
            ),
        )
        freq_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "Order of the filter (the higher, the greater computational "
                "cost)"
            ),
        )

        notch_filt = signal_settings.add_item("notch_filter")
        notch_filt.add_item(
            "apply",
            value=True,
            info="Apply notch filter to get rid of power line interference",
        )
        notch_filt.add_item(
            "freq",
            value=50.0,
            value_range=[0, None],
            info="Center frequency to be filtered",
        )
        notch_filt.add_item(
            "bandwidth",
            value=[-0.5, 0.5],
            info="List with relative limits of center frequency",
        )
        notch_filt.add_item(
            "order",
            value=5,
            value_range=[1, None],
            info=(
                "Order of the filter (the higher, the greater computational "
                "cost)"
            ),
        )

        re_ref = signal_settings.add_item("re_referencing")
        re_ref.add_item(
            "apply",
            value=False,
            info="Change the reference of your signals",
        )
        re_ref.add_item(
            "type",
            value="car",
            value_options=["car", "channel"],
            info=(
                "Type of re-referencing: Common Average Reference or channel "
                "subtraction"
            ),
        )
        re_ref.add_item(
            "channel",
            value="",
            info="Channel label for re-referencing if channel is selected",
        )

        down_samp = signal_settings.add_item("downsampling")
        down_samp.add_item(
            "apply",
            value=False,
            info="Reduce the sample rate of the incoming LSL stream",
        )
        down_samp.add_item(
            "factor",
            value=2.0,
            value_range=[0, None],
            info="Downsampling factor",
        )

        connectivity = signal_settings.add_item("connectivity")
        connectivity.add_item(
            "time_window_seconds", value=2.0,
            value_range=[0, None],
            info="Time (s) window size"
        )
        connectivity.add_item(
            "conn_metric", value="aec",
            value_options=['aec','plv','pli','wpli'],
            info="Connectivity metric"
        )
        connectivity.add_item(
            "threshold", value=50.0,
            value_range=[0, None],
            info="Threshold for connectivity"
        )
        connectivity.add_item(
            "band_range", value=[8, 13],
            info="Frequency band"
        )

        visualization_settings = SettingsTree()

        title = visualization_settings.add_item('title')
        title.add_item(
            "text",
            value="Connectivity",
            info="Title displayed above the topographic map."
        )
        title.add_item(
            "font_size",
            value=12.0,
            value_range=[0, None],
            info="Title font size (pt).",
        )

        visualization_settings.add_item(
            "channel_standard",
            value="10-05",
            value_options=["10-20", "10-10", "10-05"],
            info="EEG electrode montage used to position channels on the scalp."
        )

        visualization_settings.add_item(
            "head_radius",
            value=1.0,
            value_range=[0, 1],
            info="Relative head radius in plot coordinates (0–1)."
        )

        visualization_settings.add_item(
            "head_line_width",
            value=4.0,
            value_range=[0, None],
            info="Line width used to draw the head outline, ears, and nose."
        )

        visualization_settings.add_item(
            "head_skin_color",
            value="#E8BEAC",
            info="Fill color used for the head (scalp) area."
        )

        visualization_settings.add_item(
            "plot_channel_labels",
            value=False,
            info="If True, display the channel labels on the plot."
        )

        visualization_settings.add_item(
            "plot_channel_points",
            value=True,
            info="If True, display channel marker points on the plot."
        )

        chan_radius_size = visualization_settings.add_item(
            "channel_radius_size")
        chan_radius_size.add_item(
            "auto",
            value=True,
            info="If True, automatically compute the radius of channel markers."
        )
        chan_radius_size.add_item(
            "value",
            value=0.0,
            value_range=[0, None],
            info="Custom radius for channel markers when automatic sizing is disabled."
        )

        visualization_settings.add_item(
            "percentile_th", value=85.0,
            info="Value to establish a representation threshold"
        )

        visualization_settings.add_item(
            "label_color",
            value="w",
            info="Color used for channel label text."
        )

        z_ax = visualization_settings.add_item("z_axis")
        z_ax.add_item(
            "cmap",
            value="inferno",
            info="Matplotlib colormap used for the spectrogram.",
        )
        clim = z_ax.add_item("clim")
        clim.add_item(
            "auto", value=True,
            info="Check for automatic color bar limits computation")
        clim.add_item(
            "values", value=[0.0, 1.0],
            info="Max and min bar limits customized")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel").\
            edit_item(value=stream_info.l_cha[0], value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_settings(signal_settings, plot_settings):
        allowed_conn_metrics = ['aec','plv','pli','wpli']
        if signal_settings.get_item_value('connectivity', 'conn_metric')\
                not in allowed_conn_metrics:
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
        # INIT SIGNAL VARIABLES ================================================

        # Signal processing
        self.win_t = self.signal_settings.get_item_value(
            'connectivity', 'time_window_seconds')
        self.win_s = int(self.win_t * self.fs)
        # Create channel set
        self.channel_set = (
            lsl_utils.lsl_channel_info_to_eeg_channel_set(
                self.lsl_stream_info.cha_info,
                discard_unlocated_channels=True))
        # Initialize buffers
        self.time_in_graph = np.zeros(1)
        self.sig_in_graph = np.zeros([1, self.channel_set.n_cha])

        # INIT FIGURE ==========================================================

        # Set title
        self.ax.set_title(
            self.visualization_settings.get_item_value('title', 'text'),
            fontsize=self.visualization_settings.get_item_value('title',
                                                                'font_size'),
            color=self.text_color)

        # Initialize topography plot
        if self.visualization_settings.get_item_value('channel_radius_size','auto'):
            channel_radius_size = None
        else:
            channel_radius_size = self.visualization_settings.get_item_value(
                'channel_radius_size', 'value')
        if self.visualization_settings.get_item_value('z_axis', 'clim', 'auto'):
            clim = None
        else:
            clim = tuple(self.visualization_settings.get_item_value('z_axis', 'clim','values'))

        self.conn_plot = head_plots.ConnectivityPlot(
            axes=self.widget.figure.axes[0],
            channel_set=self.channel_set,
            head_radius=self.visualization_settings.get_item_value('head_radius'),
            head_line_width=self.visualization_settings.get_item_value('head_line_width'),
            head_skin_color=self.visualization_settings.get_item_value('head_skin_color'),
            plot_channel_labels=self.visualization_settings.get_item_value('plot_channel_labels'),
            plot_channel_points=self.visualization_settings.get_item_value('plot_channel_points'),
            channel_radius_size=channel_radius_size,
            percentile_th=self.visualization_settings.get_item_value('percentile_th'),
            cmap=self.visualization_settings.get_item_value('z_axis', 'cmap'),
            clim=clim,
            label_color=self.visualization_settings.get_item_value('label_color'),
        )

    def update_plot_data(self, chunk_times, chunk_signal):
        try:
            # DATA OPERATIONS ==================================================
            # Append new data and get safe copy
            x_in_graph, sig_in_graph = \
                self.append_data(chunk_times, chunk_signal)
            # Compute connectivity
            conn_metric = self.signal_settings.get_item_value(
                'connectivity', 'conn_metric')
            if conn_metric == 'aec':
                adj_mat = amplitude_connectivity.aec(sig_in_graph).squeeze()
            else:
                adj_mat = phase_connectivity.phase_connectivity(
                    sig_in_graph,
                    conn_metric).squeeze()
            # Apply threshold
            conn_threshol = self.signal_settings.get_item_value(
                'connectivity', 'threshold')
            if conn_threshol is not None:
                th_idx = np.abs(adj_mat) > np.percentile(
                    np.abs(adj_mat),
                    conn_threshol)
                adj_mat = adj_mat * th_idx

            # UPDATE PLOT ======================================================
            if not self.widget.isVisible():
                return
            # todo: blitting
            self.conn_plot.update(adj_mat=adj_mat)
            width, height = self.widget.get_width_height()
            if width > 0 and height > 0:
                # Update plot
                self.widget.draw()
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
        # Get minimum chunk size to comply with the update rate
        self.update_rate = self.signal_settings.get_item_value(
            'min_update_time')
        min_chunk_size = int(self.update_rate * self.fs)
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

    def handle_exception(self, ex):
        self.medusa_interface.error(ex)

    def get_effective_fs(self):
        if self.signal_settings.get_item_value('downsampling', 'apply'):
            fs = self.fs // self.signal_settings.get_item_value('downsampling', 'factor')
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

class PlotsRealTimePreprocessor:

    """Class that implements real time preprocessing functions for plotting,
    keeping it simple: band-pass filter and notch filter. For more advanced
    pre-processing, implement another class"""

    def __init__(self, preprocessing_settings, **kwargs):
        # Settings
        super().__init__(**kwargs)
        self.freq_filt_settings = preprocessing_settings.get_item('frequency_filter')
        self.notch_filt_settings = preprocessing_settings.get_item('notch_filter')
        self.re_referencing_settings = preprocessing_settings.get_item('re_referencing')
        self.downsampling_settings = preprocessing_settings.get_item('downsampling')
        self.apply_freq_filt = self.freq_filt_settings.get_item_value('apply')
        self.apply_notch = self.notch_filt_settings.get_item_value('apply')
        self.apply_re_referencing = self.re_referencing_settings.get_item_value('apply')
        self.apply_downsampling = self.downsampling_settings.get_item_value('apply')
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
                order=self.freq_filt_settings.get_item_value('order'),
                cutoff=self.freq_filt_settings.get_item_value('cutoff_freq'),
                btype=self.freq_filt_settings.get_item_value('type'),
                filt_method='sosfilt',
                axis=0)
            self.freq_filt.fit(self.fs, self.n_cha)
        # Notch filter
        if self.apply_notch:
            cutoff = [
                self.notch_filt_settings.get_item_value('freq') +
                self.notch_filt_settings.get_item_value('bandwidth')[0],
                self.notch_filt_settings.get_item_value('freq') +
                self.notch_filt_settings.get_item_value('bandwidth')[1]
            ]
            self.notch_filt = medusa.IIRFilter(
                order=self.notch_filt_settings.get_item_value('order'),
                cutoff=cutoff,
                btype='bandstop',
                filt_method='sosfilt',
                axis=0)
            self.notch_filt.fit(self.fs, self.n_cha)
        # Re-referencing
        if self.apply_re_referencing:
            if self.re_referencing_settings.get_item_value('type') not in ['car', 'channel']:
                raise ValueError('Incorrect re-referencing type. Allowed '
                                 'values: {car, channel}')
        # Downsampling
        if self.apply_downsampling:
            if self.freq_filt_settings.get_item_value('type') not in ['bandpass', 'lowpass']:
                raise ValueError('Incorrect frequency filter btype. Only '
                                 'bandpass and lowpass are available if '
                                 'downsampling is applied.')
            nyquist_cutoff = self.fs / 2 / self.downsampling_settings.get_item_value('factor')
            if self.freq_filt_settings.get_item_value('type') == 'lowpass':
                if self.freq_filt_settings.get_item_value('cutoff_freq') > nyquist_cutoff:
                    raise ValueError(
                        'Incorrect frequency filter for downsampling factor '
                        '%i. The upper cutoff must be less than %.2f to '
                        'comply with Nyquist criterion' %
                        (self.downsampling_settings.get_item_value('factor'), nyquist_cutoff))
            elif self.freq_filt_settings.get_item_value('type') == 'bandpass':
                if self.freq_filt_settings.get_item_value('cutoff_freq')[1] > nyquist_cutoff:
                    raise ValueError(
                        'Incorrect frequency filter for downsampling factor '
                        '%i. The upper cutoff must be less than %.2f to '
                        'comply with Nyquist criterion' %
                        (self.downsampling_settings.get_item_value('factor'), nyquist_cutoff))

            # Check downsampling factor
            if min_chunk_size <= 1:
                raise ValueError(
                    'Downsampling is not allowed with the current values of '
                    'update and sample rates. Increase the update rate to '
                    'apply downsampling.')
            elif min_chunk_size // self.downsampling_settings.get_item_value('factor') < 1:
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
            if self.re_referencing_settings.get_item_value('type') == 'car':
                chunk_data = medusa.car(chunk_data)
            elif self.re_referencing_settings.get_item_value('type') == 'channel':
                cha_idx = self.l_cha.index(
                    self.re_referencing_settings.get_item_value('channel'))
                chunk_data = chunk_data - chunk_data[:, [cha_idx]]
        if self.apply_downsampling:
            down_factor = int(
                self.downsampling_settings.get_item_value('factor'))
            chunk_times = chunk_times[0::down_factor]
            chunk_data = chunk_data[0::down_factor, :]
        return chunk_times, chunk_data


def get_plot_info(plot_uid):
    for plot in __plots_info__:
        if plot['uid'] == plot_uid:
            return plot

# ------------------------- AUXILIARY CLASSES ----------------------

class AutoscaleMenu(QMenu):
    """ This class inherits from GMenu and implements the menu that appears
    when right click is performed on the graph
    """

    def __init__(self, plot_handler):
        """ Class constructor

        Parameters
        ----------
        plot_handler: Widget
            Widget class where the actions are performed
        """
        QMenu.__init__(self)
        # Keep weakref to view to avoid circular reference (don't know why,
        # but this prevents the ViewBox from crash)
        self.plot_handler = plot_handler
        # Actions
        self.autoscale_action = QAction("Autoscale", self)
        self.autoscale_action.triggered.connect(self.on_autoscale)
        self.addAction(self.autoscale_action)

    def on_autoscale(self):
        self.plot_handler.autoscale()
        self.plot_handler.draw_y_axis_ticks()
        self.plot_handler.widget.draw()

class SelectChannelMenu(AutoscaleMenu):
    """
    Context menu that includes autoscaling and channel-selection options.
    """

    def __init__(self, plot_handler):
        """
        Parameters
        ----------
        plot_handler : RealTimePlot
            Widget where the actions are performed.
        """
        super().__init__(plot_handler)

        # Submenu to select channel
        self.channel_submenu = QMenu("Select channel", self)
        self.addMenu(self.channel_submenu)

    def get_channel_label(self):
        """
        Triggered when the user picks a channel from the submenu.
        Finds the QAction text (the channel label), locates its index,
        and updates the plot handler's current channel.
        """
        label = self.sender().text()
        l_cha = self.plot_handler.lsl_stream_info.l_cha
        cha_index = l_cha.index(label)
        self.select_channel(cha_index)

    def select_channel(self, cha_index):
        """
        Changes the active channel displayed by the spectrogram.

        Parameters
        ----------
        cha_index : int
            Index of the selected EEG channel.
        """
        self.plot_handler.curr_cha = cha_index

        # Update axis title
        channel_name = self.plot_handler.lsl_stream_info.l_cha[cha_index]
        self.plot_handler.ax.set_title(
            channel_name,
            color=self.plot_handler.theme_colors['THEME_TEXT_LIGHT'],
            fontsize=self.plot_handler.visualization_settings.get_item_value(
                'title_label_size')
        )

    def set_channel_list(self):
        """
        Populates the channel submenu with one QAction per channel.
        """
        self.channel_submenu.clear()

        for label in self.plot_handler.lsl_stream_info.l_cha:
            action = QAction(label, self)
            action.triggered.connect(self.get_channel_label)
            self.channel_submenu.addAction(action)

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