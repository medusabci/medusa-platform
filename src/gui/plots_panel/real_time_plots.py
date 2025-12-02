# BUILT-IN MODULES
from abc import ABC, abstractmethod
import traceback
import time

# EXTERNAL MODULES
import numpy as np
from PySide6.QtCore import *
from PySide6.QtGui import QFont, QAction
from fontTools.merge.util import current_time
from scipy import signal as scp_signal, interpolate
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.cm import get_cmap
from matplotlib import transforms as mtransforms
from sklearn.externals.array_api_extra import apply_where
from statsmodels.stats.rates import nonequivalence_poisson_2indep

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
            "time_window",
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

    def add_spectrogram_settings(self):
        spectrogram = self.add_item("spectrogram")
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

    def add_grid_settings_to_axis(self, axis_item_key, default_step=1.0):
        axis_item = self.get_item(axis_item_key)
        grid_item = axis_item.add_item("grid")
        grid_item.add_item(
            "display",
            value=True,
            info="Visibility of the grid",
        )
        grid_item.add_item(
            "step",
            value=default_step,
            value_range=[0, None],
            info="Display grid's dimensions",
        )

    def add_autoscale_settings_to_axis(self, axis_item_key):
        axis_item = self.get_item(axis_item_key)
        auto_scale = axis_item.add_item("autoscale")
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

    def add_zaxis_settings(self, cmap, range):
        z_ax = self.add_item("z_axis")
        z_ax.add_item(
            "cmap",
            value=cmap,
            info="Matplotlib colormap used for the spectrogram.",
        )
        z_ax.add_item(
            "range",
            value=range,
            info="Range of the z-axis (clim).",
        )

    def add_head_settings(self):
        head_plot = self.add_item("head_plot")
        head_plot.add_item(
            "channel_standard",
            value="10-05",
            value_options=["10-20", "10-10", "10-05"],
            info="EEG electrode montage used to position channels on the scalp."
        )
        head_plot.add_item(
            "head_radius",
            value=1.0,
            value_range=[0, 1],
            info="Relative head radius in plot coordinates (0–1)."
        )
        head_plot.add_item(
            "head_line_width",
            value=4.0,
            value_range=[0, None],
            info="Line width used to draw the head outline, ears, and nose."
        )
        head_plot.add_item(
            "head_skin_color",
            value="#E8BEAC",
            info="Fill color used for the head (scalp) area."
        )
        head_plot.add_item(
            "plot_channel_labels",
            value=False,
            info="If True, display the channel labels on the plot."
        )
        head_plot.add_item(
            "label_color",
            value="w",
            info="Color used for channel label text."
        )
        head_plot.add_item(
            "plot_channel_points",
            value=True,
            info="If True, display channel marker points on the plot."
        )
        chan_radius_size = head_plot.add_item(
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
        self.background_color_dark = self.theme_colors['THEME_BG_DARK']
        self.background_color_mid = self.theme_colors['THEME_BG_MID']
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
        self.fig.patch.set_facecolor(self.background_color_dark)
        self.ax.set_facecolor(self.background_color_mid)
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
        # Set title
        self.set_title()
        # Set axis labels
        self.set_axis_labels()
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
        self._cached_elements = self.get_cache_elements()

    def set_title(self, cha_name=None):
        """Set titles and labels for the plot axes
        """
        # Figure title
        title_item = self.visualization_settings.get_item('title')
        if title_item.get_item_value('text') == 'auto':
            title_text = self.lsl_stream_info.lsl_stream.name()
            if cha_name is not None:
                title_text += f' ({cha_name})'
        else:
            title_text = title_item.get_item_value('text')
        self.ax.set_title(
            title_text,
            fontsize=title_item.get_item_value('fontsize'),
            color=self.text_color)

    def set_axis_labels(self):
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

    def check_if_redraw_needed(self):
        # Get current values
        current_elements = self.get_cache_elements()
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

    def update_plot_common(self, chunk_times, chunk_signal):
        # Initial setup at first call
        if self.init_time is None:
            self.init_time = chunk_times[0]
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

    @abstractmethod
    def get_cache_elements(self):
        """Get elements to be cached for blitting"""
        raise NotImplemented

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
        self.t_in_graph = None
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
                x_range = (self.x_in_graph[0], self.x_in_graph[-1])
                # Time ticks
                if disp_grid:
                    x_ticks_pos, x_ticks_val = _add_grid_ticks(
                        x_range, x_ticks_pos, x_ticks_val, disp_labels=True)
            elif mode == 'clinical':
                # Set timestamps
                # x = np.mod(self.x_in_graph, self.buffer_time)
                x = self.x_in_graph
                # Range
                n_win = self.t_in_graph.max() // self.buffer_time
                x_range = (x[0], self.buffer_time) if n_win == 0 else \
                    (self.x_in_graph[0], self.x_in_graph[-1])
                x_range_real = (0, self.buffer_time) if n_win == 0 else \
                    (self.t_in_graph[0], self.t_in_graph[-1])
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

    def get_window_cut_time(self, unrolled_t_in_graph):
        """Used in clinical mode"""
        # Useful params
        max_t = unrolled_t_in_graph.max(initial=0)
        # Get the cut time for the current window
        t_cut = self.buffer_time * np.floor(max_t / self.buffer_time)
        return max(t_cut, self.buffer_time)

    def roll_array(self, unrolled_t_in_graph, time_dist_array, time_axis=0):
        """
        Reorder `time_dist_array` so that samples with times > window_cut_time
        are moved to the beginning (preserving order), along `time_axis`.
        """
        # Shape check: time vector must match the selected axis length
        if unrolled_t_in_graph.shape[0] != time_dist_array.shape[time_axis]:
            raise ValueError(
                "Length of unrolled_t_in_graph must match "
                f"time_dist_array.shape[{time_axis}]"
            )
        # Boolean mask of overflow samples
        t_cut = self.get_window_cut_time(unrolled_t_in_graph)
        idx_overflow = unrolled_t_in_graph > t_cut
        # If nothing overflows, return as-is
        if not np.any(idx_overflow):
            return time_dist_array

        # Doesn't assume contiguity of overflow samples
        # # Build a single ordering index
        # overflow_idx = np.where(idx_overflow)[0]
        # non_overflow_idx = np.where(~idx_overflow)[0]
        # order = np.concatenate((overflow_idx, non_overflow_idx))
        # # Reorder along the time axis
        # return np.take(time_dist_array, order, axis=time_axis)

        # Assumes contiguity of overflow samples
        # Find first overflow index
        first_idx_overflow = np.argmax(idx_overflow)
        # Roll so that first_overflow becomes index 0
        shift = -first_idx_overflow
        return np.roll(time_dist_array, shift=shift, axis=time_axis)

    def add_marker(self):
        # Add marker line
        self.marker_line = self.ax.axvline(x=0, color=self.marker_color,
                                           linewidth=self.marker_width,
                                           animated=True)
        self.ax.add_line(self.marker_line)
        self.marker_pos = -1
        # Add marker label
        blend = mtransforms.blended_transform_factory(self.ax.transData,
                                                      self.ax.transAxes)
        self.marker_tick = self.ax.text(
            0, self.marker_y_pos, '', transform=blend,
            ha='center', va='top', color=self.text_color,
            clip_on=False, zorder=5, animated=True)

    def update_marker(self):
        # Update marker position
        self.marker_pos = np.argmax(self.t_in_graph)
        # Marker
        marker_x = self.x_in_graph[self.marker_pos]
        self.marker_line.set_xdata([marker_x, marker_x])
        # Position text under the marker line
        marker_time = self.t_in_graph[self.marker_pos]
        self.marker_tick.set_position((marker_x, self.marker_y_pos))
        self.marker_tick.set_text(f'{marker_time:.1f}')

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
        visualization_settings.add_autoscale_settings_to_axis("y_axis")
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

    def get_cache_elements(self):
        current_elements = {
            'xlim': self.ax.get_xlim(),
            'ylim': self.ax.get_ylim(),
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

    def draw_y_axis_ticks(self):
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
            self.t_in_graph = self.times_buffer
            self.x_in_graph = self.t_in_graph
            self.y_in_graph =  self.data_buffer
        else:
            self.t_in_graph = self.roll_array(self.times_buffer,
                                              self.times_buffer)
            self.x_in_graph = np.mod(self.t_in_graph, self.buffer_time)
            self.y_in_graph = self.roll_array(self.times_buffer,
                                              self.data_buffer)
            self.update_marker()
        for i in range(self.n_cha):
            temp = self.y_in_graph[:, self.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].set_data(self.x_in_graph, temp)
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
        visualization_settings.add_autoscale_settings_to_axis("y_axis")
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
        # Set title with channel
        self.set_title(cha_name=init_cha_label)
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

    def get_cache_elements(self):
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
        # Set data
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.t_in_graph = self.times_buffer
            self.x_in_graph = self.t_in_graph
            self.y_in_graph = self.data_buffer
        else:
            self.t_in_graph = self.roll_array(self.times_buffer,
                                              self.times_buffer)
            self.x_in_graph = np.mod(self.t_in_graph, self.buffer_time)
            self.y_in_graph = self.roll_array(self.times_buffer,
                                              self.data_buffer)
            self.update_marker()
        tmp = self.y_in_graph[:, self.curr_cha - 1]
        self.curves[0].set_data(self.x_in_graph, tmp)
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

    def compute_psd(self, cha_idx=None):
        # Get psd parameters
        seg_len_pct = self.signal_settings.get_item_value(
            'psd', 'welch_seg_len_pct')
        seg_overlap_pct = self.signal_settings.get_item_value(
            'psd', 'welch_overlap_pct')
        welch_seg_len = np.round(
            seg_len_pct / 100.0 * self.data_buffer.shape[0]).astype(int)
        welch_overlap = np.round(
            seg_overlap_pct / 100.0 * welch_seg_len).astype(int)
        apply_log = self.signal_settings.get_item_value('psd', 'log_power')
        # Select channels
        _data = self.data_buffer
        if cha_idx is not None:
            _data = _data[:, cha_idx]
        # Compute PSD
        x_in_graph, y_in_graph = scp_signal.welch(
            _data, fs=self.fs,
            nperseg=welch_seg_len,
            noverlap=welch_overlap,
            nfft=welch_seg_len, axis=0)
        if apply_log:
            y_in_graph = 10.0 * np.log10(np.maximum(y_in_graph, 1e-12))
        self.x_in_graph = x_in_graph
        self.y_in_graph = y_in_graph
        return x_in_graph, y_in_graph

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
        visualization_settings.add_autoscale_settings_to_axis("y_axis")
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
            'psd', 'time_window')

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

    def get_cache_elements(self):
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
        x_in_graph, y_in_graph = self.compute_psd()
        # Set data
        x = np.arange(x_in_graph.shape[0])
        for i in range(self.n_cha):
            temp = y_in_graph[:, self.n_cha - i - 1]
            temp = (temp + self.cha_separation * i)
            self.curves[i].set_data(x, temp)
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
        visualization_settings.add_autoscale_settings_to_axis("y_axis")
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
            'psd', 'time_window')

        # INIT FIGURE ==========================================================
        # Set title with channel
        self.set_title(cha_name=init_cha_label)
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

    def get_cache_elements(self):
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
        # Compute PSD
        x_in_graph, y_in_graph = self.compute_psd(cha_idx=self.curr_cha)
        # Set data
        self.curves[0].set_data(x_in_graph, y_in_graph)
        # Update y range (only if autoscale is activated)
        apply_autoscale = self.visualization_settings.get_item_value(
            'y_axis', 'autoscale', 'apply')
        if apply_autoscale:
            self.autoscale()


class SpectrogramBasedPlot(TimeBasedPlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        self.y_range = None

    def draw_y_axis_ticks(self):
        tick_sep = self.visualization_settings.get_item_value(
            'y_axis', 'grid', 'step')
        # Frequency ticks
        y_ticks_pos = np.arange(self.y_range[0], self.y_range[1]+1e-12,
                                step=tick_sep).tolist()
        y_ticks_val = [f'{val:.1f}' for val in y_ticks_pos]
        # Set limits, ticks, and labels
        self.ax.set_ylim(self.y_range[0], self.y_range[1])
        self.ax.set_yticks(y_ticks_pos)
        self.ax.set_yticklabels(y_ticks_val)

    def compute_spectrogram(self, cha_idx=None):
        # Spectrogram computation time window
        win_t_spec = self.signal_settings.get_item_value(
            'spectrogram', 'time_window')
        win_t_spec_s = (
            int(self.signal_settings.get_item_value(
                'spectrogram', 'time_window') * self.fs))
        # Get spectrogram time window
        curr_samples = len(self.times_buffer)
        time_window = win_t_spec if curr_samples >= win_t_spec_s else (
                curr_samples / self.fs)
        # Select channels
        _data_buffer = self.data_buffer
        if cha_idx is not None:
            _data_buffer = _data_buffer[:, cha_idx]
        # Compute spectrogram
        spec, t, f = fourier_spectrogram(
            _data_buffer, self.fs,
            time_window=time_window,
            overlap_pct=self.signal_settings.get_item_value(
                'spectrogram', 'overlap_pct'),
            smooth=self.signal_settings.get_item_value(
                'spectrogram', 'smooth'),
            smooth_sigma=self.signal_settings.get_item_value(
                'spectrogram', 'smooth_sigma'),
            apply_detrend=self.signal_settings.get_item_value(
                'spectrogram', 'apply_detrend'),
            apply_normalization=self.signal_settings.get_item_value(
                'spectrogram', 'apply_normalization'),
            scale_to=self.signal_settings.get_item_value(
                'spectrogram', 'scale_to')
        )
        # Optionally convert to log scale
        if self.signal_settings.get_item_value('spectrogram', 'log_power'):
            spec = 10 * np.log10(np.maximum(spec, 1e-12))
        # Get t_in_graph
        t_start = self.times_buffer[0]
        t_end = self.times_buffer[-1]
        t_in_graph = np.linspace(t_start, t_end, len(t))
        return spec, t_in_graph, f


class SpectrogramPlot(SpectrogramBasedPlot):
    """
    A real-time spectrogram widget for time-frequency visualization of incoming data.
    """

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)

        # Spectrogram variables
        self.im = None
        self.curr_cha = None
        self.spec_in_graph = None
        self.c_lim = None

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
        base = 1.1
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
        # Signal settings
        signal_settings = BaseSignalSettings()
        signal_settings.add_spectrogram_settings()

        # Visualization settings
        visualization_settings = BaseVisualizationSettings(
            include_mode=True
        )
        # Init channel
        visualization_settings.add_item(
            "init_channel_label",
            value="",
            info="Channel selected for initial visualization.",
        )
        # X-axis
        x_ax = visualization_settings.get_item("x_axis")
        x_ax.add_item(
            "seconds_displayed",
            value=30.0,
            value_range=[0, None],
            info="Time range (s) displayed on the X axis.",
        )
        visualization_settings.add_grid_settings_to_axis("x_axis")
        # Y-axis
        y_ax = visualization_settings.get_item("y_axis")
        y_ax.add_item(
            "range",
            value=[0, 30],
            info="Y-axis range (min, max).",
        )
        visualization_settings.add_grid_settings_to_axis(
            "y_axis", default_step=5.0)
        # Z-axis
        visualization_settings.add_zaxis_settings(cmap="inferno",
                                                  range=[0.0, 1.0])
        visualization_settings.add_autoscale_settings_to_axis("z_axis")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings,
                                           stream_info):
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
        # Check that the spectrogram time window shorter than the display time
        if signal_settings.get_item_value('spectrogram', 'time_window') > \
                visualization_settings.get_item_value(
                    'x_axis', 'seconds_displayed'):
            raise ValueError(
                'Spectrogram time window cannot be longer than the '
                'displayed time range.')

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

        # Get initial channel
        init_cha_label = self.visualization_settings.get_item_value(
            'init_channel_label')
        self.curr_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label)

        # Visualization time window
        self.buffer_time = self.visualization_settings.get_item_value(
            'x_axis', 'seconds_displayed')

        # INIT FIGURE ==========================================================
        # Set title with channel
        self.set_title(cha_name=init_cha_label)
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
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=True, labelbottom=True,
                right=False, labelright=False,
                top=False, labeltop=False
            )
        elif mode == 'clinical':
            self.add_marker()
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=False, labelbottom=False,
                right=False, labelright=False,
                top=False, labeltop=False
            )
        # Set axis limits
        self.y_range = self.visualization_settings.get_item_value(
            'y_axis', 'range')
        if not isinstance(self.y_range, list):
            self.y_range = [0, self.y_range]
        self.im.set_extent((0, self.buffer_time,
                            self.y_range[0], self.y_range[1]))
        clim = self.visualization_settings.get_item_value('z_axis', 'range')
        self.im.set_clim(clim[0], clim[1])
        # Draw ticks on the axes
        self.draw_x_axis_ticks()
        self.draw_y_axis_ticks()

    def get_cache_elements(self):
        current_elements = {
            'curr_cha': self.curr_cha,
            'c_lim': self.c_lim,
            'xlim': self.ax.get_xlim(),
            'ylim': self.ax.get_ylim(),
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

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
        # Compute spectrogram
        spec, t, f = self.compute_spectrogram(
            cha_idx=self.curr_cha)
        # Update the image
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.t_in_graph = t
            self.x_in_graph = self.t_in_graph
            self.y_in_graph = f
            self.spec_in_graph = spec
        else:
            self.t_in_graph = self.roll_array(self.times_buffer,
                                              self.times_buffer)
            self.x_in_graph = np.mod(self.t_in_graph, self.buffer_time)
            self.y_in_graph = f
            self.spec_in_graph = self.roll_array(t, spec, time_axis=1)
            self.update_marker()
        self.im.set_extent([self.x_in_graph[0], self.x_in_graph[-1],
                            self.y_in_graph[0], self.y_in_graph[-1]])
        self.im.set_data(self.spec_in_graph)
        # Autoscale and update clim
        apply_autoscale = self.visualization_settings.get_item_value(
            'z_axis', 'autoscale', 'apply')
        if apply_autoscale:
            self.autoscale()
        self.draw_x_axis_ticks()
        self.draw_y_axis_ticks()
        self.c_lim = self.im.get_clim()

    def update_plot_draw_animated_elements(self):
        mode = self.visualization_settings.get_item_value('mode')
        # Draw animated elements
        self.ax.draw_artist(self.im)
        if mode == 'clinical':
            self.ax.draw_artist(self.marker_line)
            self.ax.draw_artist(self.marker_tick)
        # Redraw grid on top
        # todo: I don't like this solution, but I haven't found another
        #  way for the moment. The grid lines should be drawn only if
        #  strictly necessary, as it can be computationally expensive.
        if self.visualization_settings.get_item_value(
                'x_axis', 'grid', 'display'):
            for line in self.ax.get_xgridlines():
                self.ax.draw_artist(line)
        if self.visualization_settings.get_item_value(
                'y_axis', 'grid', 'display'):
            for line in self.ax.get_ygridlines():
                self.ax.draw_artist(line)
        # Update only animated elements
        self.widget.blit(self.fig.bbox)


class PowerDistributionPlot(SpectrogramBasedPlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Power distribution variables
        self.frequency_bands = None
        self.cmap = None
        self.patches = None

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
        pass

    @staticmethod
    def get_default_settings():
        """
        Returns a tuple: (signal_settings, visualization_settings).
        Adjust or rename keys to your needs.
        """
        # Signal settings
        signal_settings = BaseSignalSettings()
        signal_settings.add_spectrogram_settings()

        power_dist = signal_settings.add_item("power_distribution")
        power_dist.add_item(
            'band_labels',
            value=['Delta', 'Theta', 'Alpha', 'Beta', 'Gamma'],
            info='List with a names of the frequency bands')
        power_dist.add_item(
            "band_freqs",
            value=[[1, 4], [4, 8], [8, 13], [13, 30], [30, 70]],
            info="List of frequency bands [min, max] in Hz")

        # Visualization settings
        visualization_settings = BaseVisualizationSettings(
            include_mode=True
        )
        # Init channel
        visualization_settings.add_item(
            "init_channel_label",
            value="",
            info="Channel selected for initial visualization.",
        )
        # X-axis
        x_ax = visualization_settings.get_item("x_axis")
        x_ax.add_item(
            "seconds_displayed",
            value=30.0,
            value_range=[0, None],
            info="Time range (s) displayed on the X axis.",
        )
        visualization_settings.add_grid_settings_to_axis("x_axis")
        # Y-axis
        y_ax = visualization_settings.get_item("y_axis")
        y_ax.add_item(
            "range",
            value=[0, 100],
            info="Y-axis range (min, max).",
        )
        visualization_settings.add_grid_settings_to_axis(
            "y_axis", default_step=20.0)
        # Z-axis
        visualization_settings.add_zaxis_settings(cmap="Accent",
                                                  range=[0.0, 1.0])
        visualization_settings.add_autoscale_settings_to_axis("z_axis")
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings, visualization_settings, stream_info):
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
        # Check that the spectrogram time window shorter than the display time
        if signal_settings.get_item_value('spectrogram', 'time_window') > \
                visualization_settings.get_item_value(
                    'x_axis', 'seconds_displayed'):
            raise ValueError(
                'Spectrogram time window cannot be longer than the '
                'displayed time range.')

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

        # Get initial channel
        init_cha_label = self.visualization_settings.get_item_value(
            'init_channel_label')
        self.curr_cha = self.worker.receiver.get_channel_indexes_from_labels(
            init_cha_label)

        # Visualization time window
        self.buffer_time = self.visualization_settings.get_item_value(
            'x_axis', 'seconds_displayed')

        # Update frequency bands dict
        self.frequency_bands = self.signal_settings.get_item(
            'power_distribution')

        # INIT FIGURE ==========================================================
        # Set title with channel
        self.set_title(cha_name=init_cha_label)
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
        # Ticks params
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=True, labelbottom=True,
                right=False, labelright=False,
                top=False, labeltop=False
            )
        elif mode == 'clinical':
            self.add_marker()
            self.ax.tick_params(
                left=True, labelleft=True,
                bottom=False, labelbottom=False,
                right=False, labelright=False,
                top=False, labeltop=False
            )
        # Set axis limits
        self.y_range = self.visualization_settings.get_item_value(
            'y_axis', 'range')
        if not isinstance(self.y_range, list):
            self.y_range = [0, self.y_range]
        # Draw ticks on the axes
        self.draw_y_axis_ticks()
        self.draw_x_axis_ticks()

    def get_cache_elements(self):
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
        # Compute spectrogram
        spec, t, f = self.compute_spectrogram(
            cha_idx=self.curr_cha)
        spec_norm = spec / spec.sum(axis=0)
        # Update data
        mode = self.visualization_settings.get_item_value('mode')
        if mode == 'geek':
            self.t_in_graph = t
            self.x_in_graph = self.t_in_graph
            self.y_in_graph = f
        else:
            self.t_in_graph = self.roll_array(self.times_buffer,
                                              self.times_buffer)
            self.x_in_graph = np.mod(self.t_in_graph, self.buffer_time)
            self.y_in_graph = f
            self.update_marker()
        # Redefine the t_in_graph vector to match t dimensions
        interp_func = interpolate.interp1d(
            np.linspace(0, 1, len(self.t_in_graph)),
            self.t_in_graph, kind='linear',
            fill_value="extrapolate")
        t_in_graph_resampled = interp_func(np.linspace(0, 1, len(t)))
        x = np.mod(t_in_graph_resampled, self.buffer_time)
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

    def update_plot_draw_animated_elements(self):
        mode = self.visualization_settings.get_item_value('mode')
        # Draw animated patches
        for patch in self.patches:
            self.ax.draw_artist(patch)
        # Marker
        if mode == 'clinical':
            self.ax.draw_artist(self.marker_line)
            self.ax.draw_artist(self.marker_tick)
        # Redraw grid on top
        # todo: I don't like this solution, but I haven't found another
        #  way for the moment. The grid lines should be drawn only if
        #  strictly necessary, as it can be computationally expensive.
        if self.visualization_settings.get_item_value(
                'x_axis', 'grid', 'display'):
            for line in self.ax.get_xgridlines():
                self.ax.draw_artist(line)
        if self.visualization_settings.get_item_value(
                'y_axis', 'grid', 'display'):
            for line in self.ax.get_ygridlines():
                self.ax.draw_artist(line)
        # Draw legend on top
        legend = self.ax.get_legend()
        self.ax.draw_artist(legend)
        # Update only animated elements
        self.widget.blit(self.fig.bbox)

class HeadBasedPlot(RealTimePlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        self.channel_set = None
        self.sel_channels = None
        self.win_s = None
        self.interp_p = None
        self.cmap = None
        self.show_channels = None
        self.show_clabel = None
        self.head_handles = None
        self.plot_handles = None
        self.power_in_graph = None

class TopographyPlot(HeadBasedPlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        self.topo_plot = None
        self.c_lim = None

    def show_context_menu(self, pos: QPoint):
        """
        Called automatically on right-click within the canvas.
        pos is in widget coordinates, so we map it to global coords.
        """
        menu = AutoscaleMenu(self)
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
        if self.visualization_settings.get_item_value(
                'z_axis', 'autoscale', 'apply'):
            return
        # Get current lims
        vmin, vmax = self.topo_plot.plot_handles['color-mesh'].get_clim()
        if not (np.isfinite(vmin) and np.isfinite(vmax)):
            return
        # Current center + span
        center = 0.5 * (vmin + vmax)
        span = max(vmax - vmin, 1e-12)
        # Determine zoom factor
        base = 1.1
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
        self.topo_plot.plot_handles['color-mesh'].set_clim(new_vmin, new_vmax)
        self.c_lim = (new_vmin, new_vmax)
        self.topo_plot.clim = self.c_lim

    @staticmethod
    def get_default_settings():
        # Signal settings
        signal_settings = BaseSignalSettings()
        signal_settings.add_psd_settings()

        signal_settings.add_item(
            "power_range", value=[8, 13],
            info="Frequency range to compute the power for the topographic map."
        )

        # Visualization settings
        visualization_settings = BaseVisualizationSettings()
        visualization_settings.add_head_settings()

        topography = visualization_settings.add_item("topography")
        topography.add_item(
            "interpolate",
            value=True,
            info="If True, interpolate between channels to generate a smooth "
                 "topographic map."
        )
        topography.add_item(
            "extra_radius",
            value=0.29,
            value_range=[0, 1],
            info="Additional radius beyond the head used for the interpolation "
                 "grid (0–1)."
        )
        topography.add_item(
            "interp_neighbors",
            value=3,
            value_range=[1, None],
            info="Number of nearest neighbors used for interpolation at each "
                 "grid point."
        )
        topography.add_item(
            "interp_points",
            value=100,
            value_range=[1, None],
            info="Number of interpolation points per axis for the topographic "
                 "grid."
        )
        topography.add_item(
            "interp_contour_width",
            value=0.8,
            value_range=[0, None],
            info="Line width used to draw contour lines over the topographic "
                 "map."
        )
        # Z-axis
        visualization_settings.add_zaxis_settings(cmap="inferno",
                                                  range=[0.0, 1.0])
        visualization_settings.add_autoscale_settings_to_axis("z_axis")
        visualization_settings.get_item(
            "z_axis", "autoscale", "apply").edit_item(value=True)
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel"). \
            edit_item(value=stream_info.l_cha[0],
                      value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_signal(lsl_stream_info):
        if lsl_stream_info.medusa_type != 'EEG':
            raise ValueError('Wrong signal type %s. TopographyPlot only '
                             'supports EEG signals' %
                             (lsl_stream_info.medusa_type))

    @staticmethod
    def check_settings(signal_settings, plot_settings):
        pass

    def init_plot(self):

        # INIT SIGNAL VARIABLES ================================================

        # Signal processing
        self.buffer_time = self.signal_settings.get_item_value(
            'psd', 'time_window')

        # Create channel set
        self.channel_set = (
            lsl_utils.lsl_channel_info_to_eeg_channel_set(
                self.lsl_stream_info.cha_info,
                discard_unlocated_channels=True))

        # INIT FIGURE ==========================================================

        # Set title with channel
        self.set_title()
        # Initialize topography plot
        if self.visualization_settings.get_item_value(
                'head_plot', 'channel_radius_size', 'auto'):
            channel_radius_size = None
        else:
            channel_radius_size = self.visualization_settings.get_item_value(
                'head_plot', 'channel_radius_size', 'value')
        auto_scale = self.visualization_settings.get_item_value(
            'z_axis', 'autoscale', 'apply')
        if auto_scale:
            self.c_lim = None
        else:
            self.c_lim = self.visualization_settings.get_item_value(
                'z_axis', 'range')
        self.topo_plot = head_plots.TopographicPlot(
            axes=self.ax,
            channel_set=self.channel_set,
            head_radius=self.visualization_settings.get_item_value('head_plot', 'head_radius'),
            head_line_width=self.visualization_settings.get_item_value('head_plot', 'head_line_width'),
            head_skin_color=self.visualization_settings.get_item_value('head_plot', 'head_skin_color'),
            plot_channel_labels=self.visualization_settings.get_item_value('head_plot', 'plot_channel_labels'),
            plot_channel_points=self.visualization_settings.get_item_value('head_plot', 'plot_channel_points'),
            channel_radius_size=channel_radius_size,
            interpolate=self.visualization_settings.get_item_value('topography', 'interpolate'),
            extra_radius=self.visualization_settings.get_item_value('topography', 'extra_radius'),
            interp_neighbors=self.visualization_settings.get_item_value('topography', 'interp_neighbors'),
            interp_points=self.visualization_settings.get_item_value('topography', 'interp_points'),
            interp_contour_width=self.visualization_settings.get_item_value('topography', 'interp_contour_width'),
            cmap=self.visualization_settings.get_item_value('z_axis', 'cmap'),
            clim=self.c_lim,
            label_color=self.visualization_settings.get_item_value('head_plot','label_color')
        )

    def get_cache_elements(self):
        current_elements = {
            'c_lim': self.c_lim,
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

    def draw_y_axis_ticks(self):
        pass

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
        # Checks
        if auto_scale.get_item_value('apply'):
            return
        # Statistics of the current spectrogram frame
        arr = np.asarray(self.power_in_graph)
        if arr.size == 0 or not np.any(np.isfinite(arr)):
            return  # nothing to do
        mean_val = np.nanmean(arr)
        std_val = np.nanstd(arr)
        # Safety fallback
        if std_val <= 0 or not np.isfinite(std_val):
            std_val = 1e-12
        # Current limits (might be NaN on first runs)
        old_vmin, old_vmax = self.topo_plot.plot_handles[
            'color-mesh'].get_clim()
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
        if self.signal_settings.get_item_value('psd', 'log_power'):
            new_vmin = max(new_vmin, -300)  # avoid insane log values
            new_vmax = min(new_vmax, 300)
        new_range = [float(new_vmin), float(new_vmax)]
        # Apply to image
        self.topo_plot.plot_handles['color-mesh'].set_clim(
            new_range[0], new_range[1])
        self.c_lim = new_range
        self.topo_plot.clim = self.c_lim

    def compute_power(self):
        # Get psd parameters
        seg_len_pct = self.signal_settings.get_item_value(
            'psd', 'welch_seg_len_pct')
        seg_overlap_pct = self.signal_settings.get_item_value(
            'psd', 'welch_overlap_pct')
        welch_seg_len = np.round(
            seg_len_pct / 100.0 * self.data_buffer.shape[0]).astype(int)
        welch_overlap = np.round(
            seg_overlap_pct / 100.0 * welch_seg_len).astype(int)
        apply_log = self.signal_settings.get_item_value('psd', 'log_power')
        # Select channels
        _data = self.data_buffer
        # Compute PSD
        f, psd = scp_signal.welch(
            _data, fs=self.fs,
            nperseg=welch_seg_len,
            noverlap=welch_overlap,
            nfft=welch_seg_len, axis=0)
        if apply_log:
            psd = 10.0 * np.log10(np.maximum(psd, 1e-12))
        psd = psd[np.newaxis, :, :]
        psd = medusa.transforms.normalize_psd(psd)
        # Compute band power
        power_values = spectral_parameteres.band_power(
            psd=psd, fs=self.fs,
            target_band=self.signal_settings.get_item_value('power_range')
        )
        self.power_in_graph = power_values
        return power_values

    def update_plot_data(self, chunk_times, chunk_signal):
        # Compute PSD
        power_values = self.compute_power()
        # Update topographic plot
        self.topo_plot.update(values=power_values)

    def update_plot_draw_animated_elements(self):
        self.widget.draw()


class ConnectivityPlot(HeadBasedPlot):

    def __init__(self, uid, plot_state, medusa_interface, theme_colors):
        super().__init__(uid, plot_state, medusa_interface, theme_colors)
        # Graph variables
        self.conn_plot = None
        self.c_lim = None

    def show_context_menu(self, pos: QPoint):
        """
        Called automatically on right-click within the canvas.
        pos is in widget coordinates, so we map it to global coords.
        """
        menu = AutoscaleMenu(self)
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
        if self.visualization_settings.get_item_value(
                'z_axis', 'autoscale', 'apply'):
            return
        # Get current lims
        vmin, vmax = self.topo_plot.plot_handles['color-mesh'].get_clim()
        if not (np.isfinite(vmin) and np.isfinite(vmax)):
            return
        # Current center + span
        center = 0.5 * (vmin + vmax)
        span = max(vmax - vmin, 1e-12)
        # Determine zoom factor
        base = 1.1
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
        self.conn_plot.plot_handles['color-mesh'].set_clim(new_vmin, new_vmax)
        self.c_lim = (new_vmin, new_vmax)
        self.conn_plot.clim = self.c_lim

    @staticmethod
    def get_default_settings():
        # Signal settings
        signal_settings = BaseSignalSettings()

        connectivity = signal_settings.add_item("connectivity")
        connectivity.add_item(
            "time_window", value=2.0,
            value_range=[0, None],
            info="Time (s) window size"
        )
        connectivity.add_item(
            "conn_metric", value="aec",
            value_options=['aec', 'plv', 'pli', 'wpli'],
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

        # Visualization settings
        visualization_settings = BaseVisualizationSettings()
        visualization_settings.add_head_settings()

        conn_vis = visualization_settings.add_item("connectivity")
        conn_vis.add_item(
            "percentile_th", value=85.0,
            info="Value to establish a representation threshold"
        )

        # Z-axis
        visualization_settings.add_zaxis_settings(cmap="inferno",
                                                  range=[0.0, 1.0])
        visualization_settings.add_autoscale_settings_to_axis("z_axis")
        visualization_settings.get_item(
            "z_axis", "autoscale", "apply").edit_item(value=True)
        return signal_settings, visualization_settings

    @staticmethod
    def update_lsl_stream_related_settings(signal_settings,
                                           visualization_settings, stream_info):
        signal_settings.get_item("re_referencing", "channel"). \
            edit_item(value=stream_info.l_cha[0],
                      value_options=stream_info.l_cha)
        return signal_settings, visualization_settings

    @staticmethod
    def check_signal(lsl_stream_info):
        if lsl_stream_info.medusa_type != 'EEG':
            raise ValueError('Wrong signal type %s. TopographyPlot only '
                             'supports EEG signals' %
                             (lsl_stream_info.medusa_type))

    @staticmethod
    def check_settings(signal_settings, plot_settings):
        allowed_conn_metrics = ['aec','plv','pli','wpli']
        if signal_settings.get_item_value('connectivity', 'conn_metric')\
                not in allowed_conn_metrics:
            raise ValueError("Connectivity metric selected not implemented."
                             "Please, select between the following:"
                             "aec, plv, pli or plv")

    def init_plot(self):
        # INIT SIGNAL VARIABLES ================================================

        # Signal processing
        self.buffer_time = self.signal_settings.get_item_value(
            'connectivity', 'time_window')

        # Create channel set
        self.channel_set = (
            lsl_utils.lsl_channel_info_to_eeg_channel_set(
                self.lsl_stream_info.cha_info,
                discard_unlocated_channels=True))

        # INIT FIGURE ==========================================================

        # Set title with channel
        self.set_title()
        # Initialize topography plot
        if self.visualization_settings.get_item_value(
                'head_plot', 'channel_radius_size', 'auto'):
            channel_radius_size = None
        else:
            channel_radius_size = self.visualization_settings.get_item_value(
                'head_plot', 'channel_radius_size', 'value')
        auto_scale = self.visualization_settings.get_item_value(
            'z_axis', 'autoscale', 'apply')
        if auto_scale:
            self.c_lim = None
        else:
            self.c_lim = self.visualization_settings.get_item_value(
                'z_axis', 'range')

        self.conn_plot = head_plots.ConnectivityPlot(
            axes=self.ax,
            channel_set=self.channel_set,
            head_radius=self.visualization_settings.get_item_value('head_plot','head_radius'),
            head_line_width=self.visualization_settings.get_item_value('head_plot', 'head_line_width'),
            head_skin_color=self.visualization_settings.get_item_value('head_plot', 'head_skin_color'),
            plot_channel_labels=self.visualization_settings.get_item_value('head_plot', 'plot_channel_labels'),
            plot_channel_points=self.visualization_settings.get_item_value('head_plot', 'plot_channel_points'),
            channel_radius_size=channel_radius_size,
            percentile_th=self.visualization_settings.get_item_value('connectivity', 'percentile_th'),
            cmap=self.visualization_settings.get_item_value('z_axis', 'cmap'),
            clim=self.c_lim,
            label_color=self.visualization_settings.get_item_value('head_plot','label_color')
        )

    def get_cache_elements(self):
        current_elements = {
            'c_lim': self.c_lim,
            'canvas_size': self.widget.get_width_height()
        }
        return current_elements

    def draw_y_axis_ticks(self):
        pass

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
        # Checks
        if auto_scale.get_item_value('apply'):
            return
        # Statistics of the current spectrogram frame
        arr = np.asarray(self.power_in_graph)
        if arr.size == 0 or not np.any(np.isfinite(arr)):
            return  # nothing to do
        mean_val = np.nanmean(arr)
        std_val = np.nanstd(arr)
        # Safety fallback
        if std_val <= 0 or not np.isfinite(std_val):
            std_val = 1e-12
        # Current limits (might be NaN on first runs)
        old_vmin, old_vmax = self.topo_plot.plot_handles[
            'color-mesh'].get_clim()
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
        if self.signal_settings.get_item_value('psd', 'log_power'):
            new_vmin = max(new_vmin, -300)  # avoid insane log values
            new_vmax = min(new_vmax, 300)
        new_range = [float(new_vmin), float(new_vmax)]
        # Apply to image
        self.conn_plot.plot_handles['color-mesh'].set_clim(
            new_range[0], new_range[1])
        self.c_lim = new_range
        self.conn_plot.clim = self.c_lim

    def update_plot_data(self, chunk_times, chunk_signal):
        # DATA OPERATIONS ==================================================
        # Compute connectivity
        conn_metric = self.signal_settings.get_item_value(
            'connectivity', 'conn_metric')
        if conn_metric == 'aec':
            adj_mat = amplitude_connectivity.aec(
                self.data_buffer).squeeze()
        else:
            adj_mat = phase_connectivity.phase_connectivity(
                self.data_buffer,
                conn_metric).squeeze()
        # Apply threshold
        conn_threshol = self.signal_settings.get_item_value(
            'connectivity', 'threshold')
        if conn_threshol is not None:
            th_idx = np.abs(adj_mat) > np.percentile(
                np.abs(adj_mat),
                conn_threshol)
            adj_mat = adj_mat * th_idx
        self.conn_plot.update(adj_mat=adj_mat)

    def update_plot_draw_animated_elements(self):
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
        # Get curr channel name
        channel_name = self.plot_handler.lsl_stream_info.l_cha[cha_index]
        # Set title
        self.plot_handler.set_title(cha_name=channel_name)

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