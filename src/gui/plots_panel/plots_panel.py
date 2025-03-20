# BUILT-IN MODULES
import json, os
import multiprocessing as mp
import time

# EXTERNAL MODULES
from PySide6.QtUiTools import loadUiType
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
# MEDUSA MODULES
import utils
from gui.plots_panel import plots_panel_config, real_time_plots
import constants, exceptions
from gui.qt_widgets import dialogs
from acquisition import lsl_utils
from gui import gui_utils as gu


class PlotsPanelWidget(QWidget):
    """ This widget implements the logic behind the plots panel.
    """
    def __init__(self, lsl_config, plot_state, medusa_interface,
                 plots_config_file_path, theme_colors):
        super().__init__()

        # Attributes
        self.lsl_config = lsl_config
        self.plot_state = plot_state
        self.medusa_interface = medusa_interface
        self.theme_colors = theme_colors
        self.plots_handlers = list()
        self.undocked = False
        # Toolbar layout
        main_layout = QVBoxLayout()
        toolbar_layout = QHBoxLayout()
        self.toolButton_plot_start = QToolButton()
        self.toolButton_plot_config = QToolButton()
        self.toolButton_plot_undock = QToolButton()
        toolbar_layout.addWidget(self.toolButton_plot_start)
        toolbar_layout.addWidget(self.toolButton_plot_config)
        toolbar_layout.addItem(QSpacerItem(
            0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum))
        toolbar_layout.addWidget(self.toolButton_plot_undock)
        main_layout.addLayout(toolbar_layout)
        # Grid layout
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)
        # Set up
        self.set_up_tool_bar_plot()
        # Initial configuration
        self.plots_panel_config = None
        self.plots_config_file_path = plots_config_file_path
        if os.path.isfile(self.plots_config_file_path):
            try:
                with open(self.plots_config_file_path, 'r') as f:
                    self.plots_panel_config = json.load(f)
                self.update_plots_panel()
            except json.decoder.JSONDecodeError as e:
                msg = '[ERROR] Corrupted file %s. The plots config could not ' \
                      'be loaded' % self.plots_config_file_path
                self.medusa_interface.log(msg)

    def handle_exception(self, ex):
        # Treat exception
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(
                ex, importance='unknown',
                scope='plots',
                origin='plots_panel/plots_panel/handle_exception')
        # Notify exception to gui main
        self.medusa_interface.error(ex)

    def add_tab(self, tab_name):
        grid_widget = QWidget()
        grid_layout = QGridLayout()
        grid_widget.setLayout(grid_layout)
        self.tab_widget.addTab(grid_widget, tab_name)
        return grid_layout

    def get_tab_grid_layout(self, tab_index):
        return self.tab_widget.widget(tab_index).layout()

    def on_tab_changed(self, current_tab_index):
        for tab_index, tab_plots_handlers in enumerate(self.plots_handlers):
            for uid, plot_handler in tab_plots_handlers.items():
                if tab_index == current_tab_index:
                    plot_handler.active = True
                else:
                    plot_handler.active = False

    @exceptions.error_handler(scope='plots')
    def set_undocked(self, undocked):
        self.undocked = undocked
        # Change icon and tooltip
        self.reset_tool_bar_plot_buttons()

    @exceptions.error_handler(scope='plots')
    def reset_tool_bar_plot_buttons(self):
        # Set icons in buttons
        self.toolButton_plot_start.setIcon(
            gu.get_icon("visibility.svg", self.theme_colors))
        self.toolButton_plot_start.setToolTip('Start plotting')
        self.toolButton_plot_config.setIcon(
            gu.get_icon("settings.svg", self.theme_colors))
        self.toolButton_plot_config.setToolTip('Configure plots')
        if self.undocked:
            self.toolButton_plot_undock.setIcon(
                gu.get_icon("open_in_new_down.svg", self.theme_colors))
            self.toolButton_plot_undock.setToolTip(
                'Redock in main window')
        else:
            self.toolButton_plot_undock.setIcon(
                gu.get_icon("open_in_new.svg", self.theme_colors))
            self.toolButton_plot_undock.setToolTip('Undock')

    @exceptions.error_handler(scope='plots')
    def set_up_tool_bar_plot(self):
        """ This method creates the QAction buttons displayed in the toolbar
        """
        self.reset_tool_bar_plot_buttons()
        # Connect signals
        self.toolButton_plot_start.clicked.connect(self.plot_start)
        self.toolButton_plot_config.clicked.connect(self.open_plots_panel_config_dialog)

    @exceptions.error_handler(scope='plots')
    def update_lsl_config(self, lsl_config):
        self.lsl_config = lsl_config
        self.update_plots_panel()

    @exceptions.error_handler(scope='plots')
    def open_plots_panel_config_dialog(self, checked=None):
        # Check errors
        if len(self.lsl_config['working_streams']) == 0:
            dialogs.error_dialog('No LSL streams available. Please, '
                                 'add at least 1 LSL stream to the workspace '
                                 'before configuring the real-time charts',
                                 'No LSL streams')
            return
        # Dashboard config window
        self.plots_panel_config_dialog = \
            plots_panel_config.PlotsPanelConfigDialog(
                self.lsl_config,
                self.plots_config_file_path,
                config=self.plots_panel_config,
                theme_colors=self.theme_colors)
        self.plots_panel_config_dialog.accepted.connect(
            self.set_plots_panel_config)
        self.plots_panel_config_dialog.rejected.connect(
            self.reset_plots_panel)

    @exceptions.error_handler(scope='plots')
    def set_plots_panel_config(self):
        self.plots_panel_config = \
            self.plots_panel_config_dialog.get_config()
        self.update_plots_panel()

    @exceptions.error_handler(scope='plots')
    def reset_plots_panel(self):
        self.update_plots_panel()

    @exceptions.error_handler(scope='plots')
    def update_plots_panel(self):
        # Check plots_panel_config
        if self.plots_panel_config is None:
            return
        # Clear previous config and load the new one
        self.clear_plots_grid()
        # Add tabs
        for tab_config in self.plots_panel_config:
            # Add new tab
            grid_layout = self.add_tab(tab_config['tab_name'])
            # Add grid cells
            count = 0
            for r in range(tab_config['n_rows']):
                for c in range(tab_config['n_cols']):
                    item = plots_panel_config.GridCell(count, [r, c])
                    grid_layout.addWidget(item, r, c, 1, 1)
                    count += 1
            # Add plot frames
            tab_plots_handlers = dict()
            for item in tab_config['plots']:
                plot_uid = item['uid']
                plot_settings = tab_config['plots_settings'][str(plot_uid)]
                plot_type = plot_settings['plot_uid']
                if plot_type is not None and item['configured']:
                    plot_info = real_time_plots.get_plot_info(plot_type)
                    try:
                        # Create plot
                        tab_plots_handlers[plot_uid] = plot_info['class'](
                            uid=plot_uid,
                            plot_state=self.plot_state,
                            medusa_interface=self.medusa_interface,
                            theme_colors=self.theme_colors)
                        # Set settings
                        tab_plots_handlers[plot_uid].set_settings(
                            plot_settings['signal_settings'],
                            plot_settings['visualization_settings'])
                        # Get the lsl stream from the working lsl streams
                        dict_data = plot_settings['lsl_stream_info']
                        if self.lsl_config['weak_search']:
                            working_lsl_stream = lsl_utils.find_lsl_stream(
                                lsl_streams=self.lsl_config['working_streams'],
                                force_one_stream=True,
                                medusa_uid=dict_data['medusa_uid'],
                                name=dict_data['lsl_name'],
                                type=dict_data['lsl_type'],
                                source_id=dict_data['lsl_source_id'],
                                channel_count=dict_data['lsl_n_cha'],
                                nominal_srate=dict_data['fs']
                            )
                        else:
                            working_lsl_stream = lsl_utils.find_lsl_stream(
                                lsl_streams=self.lsl_config['working_streams'],
                                force_one_stream=True,
                                uid=dict_data['lsl_uid'],
                                medusa_uid=dict_data['medusa_uid'],
                                name=dict_data['lsl_name'],
                                type=dict_data['lsl_type'],
                                source_id=dict_data['lsl_source_id'],
                                channel_count=dict_data['lsl_n_cha'],
                                nominal_srate=dict_data['fs']
                            )
                        # New instance to avoid pulling data from the same stream
                        # for several plots
                        lsl_stream = lsl_utils.LSLStreamWrapper(
                            working_lsl_stream.lsl_stream)
                        lsl_stream.set_inlet(
                            proc_clocksync=working_lsl_stream.lsl_proc_clocksync,
                            proc_dejitter=working_lsl_stream.lsl_proc_dejitter,
                            proc_monotonize=working_lsl_stream.lsl_proc_monotonize,
                            proc_threadsafe=working_lsl_stream.lsl_proc_threadsafe)
                        lsl_stream.update_medusa_parameters_from_lslwrapper(
                                        working_lsl_stream)
                        # Set receiver
                        tab_plots_handlers[plot_uid].set_lsl_worker(
                            lsl_stream)
                        tab_plots_handlers[plot_uid].init_plot()
                        tab_plots_handlers[plot_uid].set_ready()
                    except exceptions.LSLStreamNotFound as e:
                        msg = 'Plot %i. The LSL stream associated with this plot ' \
                              'is no longer available. Please, reconfigure' % \
                              (plot_uid)
                        self.medusa_interface.log(msg, style='warning')
                        continue
                    except exceptions.UnspecificLSLStreamInfo as e:
                        # If this exception occurs, the error has already been
                        # displayed by method set_up_lsl_config in main_window, so
                        # it is not necessary to repeat information
                        msg = 'Plot %i. There are more than one LSL stream that' \
                              'can be associated with this plot. Disable weak ' \
                              'search to avoid these issues. Please, ' \
                              'reconfigure' % (plot_uid)
                        self.medusa_interface.log(msg, style='warning')
                        continue
                    except KeyError as e:
                        msg = 'Plot %i. KeyError: %s The configuration of ' \
                              'this plot is not valid. This may be due to ' \
                              'a corrupted file or a software update. ' \
                              'Please, reset the configuration of this ' \
                              'plot.' % (plot_uid, str(e))
                        raise exceptions.IncorrectSettingsConfig(msg)
                    except Exception as e:
                        msg = type(e)('Plot %i. %s' % (plot_uid, str(e)))
                        ex = exceptions.MedusaException(
                            msg, importance='unknown',
                            scope='plots',
                            origin='PlotsWidget/update_plots_panel'
                        )
                        self.medusa_interface.error(ex)
                        continue
                    # Add plot
                    grid_layout.addWidget(
                        tab_plots_handlers[plot_uid].get_widget(),
                        item['coordinates'][0],
                        item['coordinates'][1],
                        item['span'][0],
                        item['span'][1])
                    self.plots_handlers.append(tab_plots_handlers)

    @exceptions.error_handler(scope='plots')
    def clear_plots_grid(self):
        """
        Clears the grid of the plots panel by removing all tabs and widgets.
        """
        # Remove all tabs and delete their content
        while self.tab_widget.count() > 0:
            # Always remove the first tab
            tab = self.tab_widget.widget(0)
            self.tab_widget.removeTab(0)
            if tab is not None:
                grid_layout = tab.layout()
                if grid_layout is not None:
                    while grid_layout.count() > 0:
                        item = grid_layout.takeAt(0)
                        if item is not None:
                            widget = item.widget()
                            if widget is not None:
                                widget.setParent(None)
                                widget.deleteLater()
                # Delete the tab widget itself
                tab.deleteLater()
        # Reset plot handlers
        self.plots_handlers.clear()

    @exceptions.error_handler(scope='plots')
    def plot_start(self, checked=None):
        """ This function is called when the plot_start button is clicked. Take
        into account that this button is called to start or to stop plotting,
        depending on the state of plot_state"""
        if self.plot_state.value == constants.PLOT_STATE_OFF:
            # Update plot state. This will notify the action directly if
            # the plots are undocked
            self.plot_state.value = constants.PLOT_STATE_ON
            # Start plot
            n_ready_plots = 0
            for tab_plots_handlers in self.plots_handlers:
                for uid, plot_handler in tab_plots_handlers.items():
                    # The plot is not ready if there has been some error during
                    # the initialization. Still, the other plots can work
                    if plot_handler.ready:
                        plot_handler.start()
                        n_ready_plots += 1
                # If none of the plots is correctly initialized
                if n_ready_plots == 0:
                    return
                # Update gui
                icon_dock = "open_in_new.svg" if self.undocked else "close.svg"
                plot_undock_icon = gu.get_icon(icon_dock, self.theme_colors)
                self.toolButton_plot_undock.setIcon(
                    plot_undock_icon)
                self.toolButton_plot_undock.setDisabled(True)
                self.toolButton_plot_config.setIcon(
                    gu.get_icon("settings.svg", self.theme_colors)
                )
                self.toolButton_plot_config.setDisabled(True)
                self.toolButton_plot_start.setIcon(
                    gu.get_icon("visibility_off.svg", self.theme_colors)
                )
        else:
            if self.plot_state.value == constants.PLOT_STATE_ON:
                # The change of state will notify the action directly
                # if the plots are undocked
                self.plot_state.value = constants.PLOT_STATE_OFF
                # time.sleep(0.5)
                self.reset_plots()
                # Update gui
                icon_dock = "open_in_new.svg" if self.undocked else "close.svg"
                plot_undock_icon = gu.get_icon(icon_dock, self.theme_colors)
                self.toolButton_plot_undock.setIcon(
                    plot_undock_icon)
                self.toolButton_plot_undock.setDisabled(False)
                self.toolButton_plot_config.setIcon(
                    gu.get_icon("settings.svg", self.theme_colors))
                self.toolButton_plot_config.setDisabled(False)
                self.toolButton_plot_start.setIcon(
                    gu.get_icon("visibility.svg", self.theme_colors))

    @exceptions.error_handler(scope='plots')
    def reset_plots(self):
        # Reset the plots
        for tab_plots_handlers in self.plots_handlers:
            for uid, plot_handler in tab_plots_handlers.items():
                if plot_handler.ready:
                    plot_handler.destroy_plot()


class PlotsPanelWindow(QMainWindow):

    """This window holds the plots panel widget in undocked mode"""

    close_signal = Signal()

    def __init__(self, plots_panel_widget, theme_colors,
                 width=1200, height=900):
        super().__init__()
        self.theme_colors = theme_colors
        self.setCentralWidget(plots_panel_widget)
        gu.set_css_and_theme(self, self.theme_colors)
        # Window title and icon
        self.setWindowIcon(QIcon('%s/medusa_task_icon.png' %
                                 constants.IMG_FOLDER))
        self.setWindowTitle('Real time plots panel')
        # Resize plots window
        self.resize(width, height)
        self.show()

    def closeEvent(self, event):
        self.close_signal.emit()
        event.accept()

    def get_plots_panel_widget(self):
        return self.centralWidget()
