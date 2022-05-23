# BUILT-IN MODULES
import json, os
import multiprocessing as mp
# EXTERNAL MODULES
from PyQt5 import uic
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
# MEDUSA MODULES
from gui.plots_panel import plots_panel_config, real_time_plots
import constants, exceptions
from acquisition import lsl_utils
from gui import gui_utils as gu


ui_plots_panel_widget = \
    uic.loadUiType('gui/ui_files/plots_panel_widget.ui')[0]


class PlotsPanelWidget(QWidget, ui_plots_panel_widget):
    
    def __init__(self, working_lsl_streams, plot_state, medusa_interface,
                 plots_config_file_path, theme_colors):
        super().__init__()
        self.setupUi(self)

        # TODO: Get current theme
        self.theme = 'dark'

        # Attributes
        self.working_lsl_streams = working_lsl_streams
        self.plot_state = plot_state
        self.medusa_interface = medusa_interface
        self.theme_colors = theme_colors
        self.plots_handlers = dict()
        self.undocked = False
        # Set up tool bar
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
                msg = '[ERROR] Corrupted file plots_panel_config.json. ' \
                      'The plots config could not be loaded'
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

    def set_undocked(self, undocked):
        self.undocked = undocked
        self.reset_tool_bar_plot_buttons()

    def reset_tool_bar_plot_buttons(self):
        # Creates QIcons for the app tool bar
        plot_start_icon = gu.get_icon("visibility.svg", theme=self.theme)
        plot_config_icon = gu.get_icon("settings.svg", theme=self.theme)
        plot_undock_icon = gu.get_icon("open_in_new.svg", theme=self.theme)

        # plot_start_icon = QIcon("%s/icons/plot_icon.png" % constants.IMG_FOLDER)
        # plot_config_icon = QIcon("%s/icons/gear.png" % constants.IMG_FOLDER)
        # undock_button_image = "dock_enabled_icon.png" if self.undocked else \
        #     "undock_enabled_icon.png"
        # plot_undock_icon = QIcon("%s/icons/%s" %
        #                          (constants.IMG_FOLDER, undock_button_image))

        # Set icons in buttons
        self.toolButton_plot_start.setIcon(plot_start_icon)
        self.toolButton_plot_config.setIcon(plot_config_icon)
        self.toolButton_plot_undock.setIcon(plot_undock_icon)

    def set_up_tool_bar_plot(self):
        """ This method creates the QAction buttons displayed in the toolbar
        """
        self.reset_tool_bar_plot_buttons()
        # Connect signals
        self.toolButton_plot_start.clicked.connect(self.plot_start)
        self.toolButton_plot_config.clicked.connect(self.plots_panel_config)

    def update_working_lsl_streams(self, working_lsl_streams):
        self.working_lsl_streams = working_lsl_streams
        self.update_plots_panel()

    def plots_panel_config(self):
        try:
            # Check errors
            if len(self.working_lsl_streams) == 0:
                ex = exceptions.MedusaException(
                    exceptions.NoLSLStreamsAvailable(),
                    importance='mild',
                    scope='plots',
                    origin='PlotsWidget/plot_panel_config'
                )
                ex.set_handled(True)
                raise ex
            # Dashboard config window
            self.plots_panel_config_dialog = \
                plots_panel_config.PlotsPanelConfigDialog(
                    self.working_lsl_streams,
                    self.plots_config_file_path,
                    config=self.plots_panel_config,
                    theme_colors=self.theme_colors)
            self.plots_panel_config_dialog.accepted.connect(
                self.set_plots_panel_config)
            self.plots_panel_config_dialog.rejected.connect(
                self.reset_plots_panel)
        except Exception as e:
            self.handle_exception(e)

    def set_plots_panel_config(self):
        try:
            self.plots_panel_config = self.plots_panel_config_dialog.get_config()
            self.update_plots_panel()
        except Exception as e:
            self.handle_exception(e)

    def reset_plots_panel(self):
        self.update_plots_panel()

    def update_plots_panel(self):
        try:
            # Check plots_panel_config
            if self.plots_panel_config is None:
                return
            # Clear previous config and load the new one
            self.clear_plots_grid()
            # Add grid cells
            count = 0
            for r in range(self.plots_panel_config['n_rows']):
                for c in range(self.plots_panel_config['n_cols']):
                    item = plots_panel_config.GridCell(count, [r, c])
                    self.gridLayout_plots.addWidget(item, r, c, 1, 1)
                    count += 1
            # Add plot frames
            for item in self.plots_panel_config['plots']:
                plot_uid = item['uid']
                plot_settings = \
                    self.plots_panel_config['plots_settings'][str(plot_uid)]
                plot_type = plot_settings['plot_uid']
                if plot_type is not None and item['configured']:
                    plot_info = real_time_plots.get_plot_info(plot_type)
                    try:
                        # Create plot
                        self.plots_handlers[plot_uid] = plot_info['class'](
                            plot_uid,
                            self.plot_state,
                            self.medusa_interface,
                            self.theme_colors)
                        # Set settings
                        self.plots_handlers[plot_uid].set_settings(
                            plot_settings['preprocessing_settings'],
                            plot_settings['visualization_settings'])
                        # Set receiver
                        lsl_stream_info = \
                            lsl_utils.LSLStreamWrapper.from_serializable_obj(
                                plot_settings['lsl_stream_info'])
                        self.check_lsl_stream(lsl_stream_info)
                        self.plots_handlers[plot_uid].set_receiver(
                            lsl_stream_info)
                        self.plots_handlers[plot_uid].init_plot()
                        self.plots_handlers[plot_uid].set_ready()
                    except exceptions.LSLStreamNotFound as e:
                        msg = 'Plot %i. %s' % \
                              (plot_uid, 'LSL stream not available, '
                                         'reconfigure')
                        ex = exceptions.MedusaException(
                            exceptions.LSLStreamNotFound(msg),
                            importance='mild',
                            scope='plots',
                            origin='PlotsWidget/update_plots_panel'
                        )
                        self.medusa_interface.error(ex)
                        continue
                    except Exception as e:
                        msg = 'Plot %i. %s' % (plot_uid, str(e))
                        ex = exceptions.MedusaException(
                            e, importance='unknown',
                            scope='plots',
                            origin='PlotsWidget/update_plots_panel'
                        )
                        self.medusa_interface.error(ex)
                        continue
                    # Add plot
                    self.gridLayout_plots.addWidget(
                        self.plots_handlers[plot_uid].get_widget(),
                        item['coordinates'][0],
                        item['coordinates'][1],
                        item['span'][0],
                        item['span'][1])
        except Exception as e:
            self.handle_exception(e)

    def check_lsl_stream(self, lsl_stream):
        for working_lsl_stream in self.working_lsl_streams:
            if lsl_stream.lsl_uid == working_lsl_stream.lsl_uid:
                return
        prop_dict = {
            'name': lsl_stream.lsl_name,
            'type': lsl_stream.lsl_type,
            'uid': lsl_stream.lsl_uid,
            'source_id': lsl_stream.lsl_source_id,
            'channel_count': lsl_stream.lsl_n_cha,
            'nominal_srate': lsl_stream.fs
        }
        raise exceptions.LSLStreamNotFound(prop_dict)

    def clear_plots_grid(self):
        try:
            # Delete widgets
            while self.gridLayout_plots.count() > 0:
                item = self.gridLayout_plots.takeAt(0)
                item.widget().deleteLater()
            # Reset plot handlers
            self.plots_handlers = dict()
        except Exception as e:
            self.handle_exception(e)

    def plot_start(self):
        """ This function gets the lsl stream to start getting data """
        try:
            if self.plot_state.value == constants.PLOT_STATE_OFF:
                # Update plot state. This will notify the action directly if
                # the plots are undocked
                self.plot_state.value = constants.PLOT_STATE_ON
                # Start plot
                n_ready_plots = 0
                for uid, plot_handler in self.plots_handlers.items():
                    if plot_handler.ready:
                        plot_handler.start()
                        n_ready_plots += 1
                if n_ready_plots == 0:
                    return
                # Update gui
                # undock_button_image = "dock_disabled_icon.png" \
                #     if self.undocked else "undock_disabled_icon.png"
                # plot_undock_icon = QIcon(
                #     "%s/icons/%s" %
                #     (constants.IMG_FOLDER, undock_button_image))
                icon_dock = "open_in_new.svg" if self.undocked else "close.svg"
                plot_undock_icon = gu.get_icon(icon_dock, theme=self.theme)
                self.toolButton_plot_undock.setIcon(
                    plot_undock_icon)
                self.toolButton_plot_undock.setDisabled(True)
                self.toolButton_plot_config.setIcon(
                    gu.get_icon("settings.svg", theme=self.theme, enabled=False)
                )
                self.toolButton_plot_config.setDisabled(True)
                self.toolButton_plot_start.setIcon(
                    gu.get_icon("visibility_off.svg", theme=self.theme)
                )
            else:
                if self.plot_state.value == constants.PLOT_STATE_ON:
                    # The change of state will notify the action directly
                    # if the plots are undocked
                    self.plot_state.value = constants.PLOT_STATE_OFF
                    self.reset_plots()
                    # Update gui
                    # undock_button_image = "dock_enabled_icon.png" \
                    #     if self.undocked else "undock_enabled_icon.png"
                    # plot_undock_icon = QIcon("%s/icons/%s" %
                    #                          (constants.IMG_FOLDER,
                    #                           undock_button_image))
                    icon_dock = "open_in_new.svg" if self.undocked else "close.svg"
                    plot_undock_icon = gu.get_icon(icon_dock, theme=self.theme)
                    self.toolButton_plot_undock.setIcon(
                        plot_undock_icon)
                    self.toolButton_plot_undock.setDisabled(False)
                    self.toolButton_plot_config.setIcon(
                        gu.get_icon("settings.svg", theme=self.theme))
                    self.toolButton_plot_config.setDisabled(False)
                    self.toolButton_plot_start.setIcon(
                        gu.get_icon("visibility.svg", theme=self.theme))
        except Exception as e:
            self.handle_exception(e)

    def reset_plots(self):
        # Reset the plots
        for uid, plot_handler in self.plots_handlers.items():
            plot_handler.destroy_plot()


class PlotsPanelWindow(QMainWindow):

    close_signal = pyqtSignal()

    def __init__(self, plots_panel_widget, theme_colors,
                 width=1200, height=900):
        super().__init__()
        # self.plots_panel_widget = plots_panel_widget
        self.theme_colors = theme_colors
        self.setCentralWidget(plots_panel_widget)
        gu.set_css_and_theme(self, self.theme_colors)
        # Resize plots window
        self.resize(width, height)
        self.show()

    def closeEvent(self, event):
        self.close_signal.emit()
        event.accept()

    def get_plots_panel_widget(self):
        return self.centralWidget()
