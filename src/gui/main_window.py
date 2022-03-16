# PYTHON MODULES
import os, sys, time
import multiprocessing as mp
import json

# EXTERNAL MODULES
from PyQt5 import uic
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

# MEDUSA general
import constants, resources, exceptions
from gui import gui_utils
from acquisition import lsl_utils
from gui.plots_panel import plots_panel
from gui.lsl_config import lsl_config
from gui.apps_panel import apps_panel
from gui.log_panel import log_panel
from gui.user_profile import user_profile

# Load the .ui file
gui_main_user_interface = uic.loadUiType("gui/ui_files/main_window.ui")[0]


class GuiMainClass(QMainWindow, gui_main_user_interface):
    """ This class represents the main GUI of medusa. All the modules that are
    needed in the working flow are instantiated here, so this is the only class
    you have to change in order to add or change modules.
    """
    def __init__(self):
        QMainWindow.__init__(self)
        self.setupUi(self)
        # Initial sizes
        self.default_width = 1600
        self.default_height = 900
        self.default_splitter_ratio = 0.36
        self.default_splitter_2_ratio = 0.28
        self.reset_sizes()

        # Splash screen
        # splash_screen = self.set_splash_screen()

        # Initialize the application
        self.theme_colors = gui_utils.get_theme_colors('dark')
        gui_utils.set_css_and_theme(self, 'gui/style.css', self.theme_colors)
        self.setWindowIcon(QIcon('%s/medusa_icon.png' % constants.IMG_FOLDER))
        self.setWindowTitle('Medusa %s' % constants.MEDUSA_VERSION)
        self.setFocusPolicy(Qt.StrongFocus)
        # self.setWindowFlags(Qt.FramelessWindowHint)

        # Menu and toolbar action initializing
        self.set_up_menu_bar_main()
        self.set_up_tool_bar_main()

        # State constants shared across medusa. See constants.py for more info
        self.plot_state = mp.Value('i', constants.PLOT_STATE_OFF)
        self.app_state = mp.Value('i', constants.APP_STATE_OFF)
        self.run_state = mp.Value('i', constants.RUN_STATE_READY)

        # Medusa interface
        self.interface_queue = mp.Queue()
        self.medusa_interface_listener = None
        self.set_up_medusa_interface_listener(self.interface_queue)
        self.medusa_interface = resources.MedusaInterface(self.interface_queue)

        # Log panel (set up first in case any exception is raised in other
        # functions)
        self.log_panel_widget = None
        self.set_up_log_panel()

        # LSL config
        self.working_lsl_streams = None
        self.set_up_lsl_config()

        # Apps panel
        self.apps_panel_widget = None
        self.set_up_apps_panel()

        # Plots dashboard
        self.plots_panel_widget = None
        self.set_up_plots_panel()

        # Set up
        self.set_status('Ready')
        self.show()
        # splash_screen.finish(self)  # Close the SplashScreen

    def reset_sizes(self):
        # Define size and splitters
        self.resize(self.default_width, self.default_height)
        self.splitter.setSizes(
            [int(self.default_splitter_ratio * self.default_width),
             int((1-self.default_splitter_ratio) * self.default_width)])
        self.splitter_2.setSizes(
            [int(self.default_splitter_2_ratio * self.default_height),
             int((1 - self.default_splitter_2_ratio) * self.default_height)])

    @staticmethod
    def set_splash_screen():
        """ Sets the initial splash screen while it loads things. """
        # Attaching the splash image
        splash_image = QPixmap('gui/images/medusa_splash_v1.png')
        splash_screen = QSplashScreen(splash_image, Qt.WindowStaysOnTopHint)
        splash_screen.setMask(splash_image.mask())

        # Creating the progress bar
        splash_progbar = QProgressBar(splash_screen)
        splash_progbar.setStyleSheet(
            "QProgressBar{ "
            "height: 10px; "
            "color: none; "
            "border: 1px solid transparent; "
            "background: rgba(0,0,0,0); "
            "margin-left: 320px; "
            "margin-right: 32px; "
            "margin-top: 250px;"
            "}" +
            "QProgressBar::chunk{ background: white; }")
        # Creating the progress text
        splash_text = QLabel('Making a PhD thesis...')
        splash_text.setStyleSheet("color: white; "
                                  "font-size: 8pt; "
                                  "font-weight: bold; "
                                  "margin-top: 280px; "
                                  "margin-left: 318px; "
                                  "margin-right: 32px; "
                                  "font-family: sans-serif, "
                                  "Helvetica, Arial; "
                                  "text-align: left;")

        # Creating the final layout
        splash_layout = QGridLayout()
        splash_layout.addWidget(splash_progbar, 0, 0)
        splash_layout.addWidget(splash_text, 0, 0)
        splash_screen.setLayout(splash_layout)

        # Displaying the splash screen
        splash_screen.show()

        # Showing progress
        for i in range(0, 100):
            splash_progbar.setValue(i)
            if i < 20:
                splash_text.setText("Reading articles...")
            elif i < 40:
                splash_text.setText("Writing an article...")
            elif i < 60:
                splash_text.setText("Waiting for the review...")
            elif i < 80:
                splash_text.setText("Tiding up the desk...")
            elif i < 100:
                splash_text.setText("Writing the PhD thesis...")
            # Simulate something that takes time
            time.sleep(0.01)
        time.sleep(1)

        return splash_screen

    def set_status(self, msg):
        """ Changes the status bar message.

        :param msg: basestring
            Status message.
        """
        try:
            self.statusBar().showMessage(msg)
        except Exception as e:
            self.handle_exception(e)

    # ================================ SET UP ================================ #
    def set_up_medusa_interface_listener(self, interface_queue):
        try:
            self.medusa_interface_listener = resources.MedusaInterfaceListener(
                interface_queue)
            self.medusa_interface_listener.msg_signal.connect(self.print_log)
            self.medusa_interface_listener.exception_signal.connect(
                self.handle_exception)
            self.medusa_interface_listener.app_state_changed_signal.connect(
                self.on_app_state_changed)
            self.medusa_interface_listener.run_state_changed_signal.connect(
                self.on_run_state_changed)
            self.medusa_interface_listener.start()
        except Exception as e:
            self.handle_exception(e)

    def set_up_log_panel(self):
        try:
            self.log_panel_widget = log_panel.LogPanelWidget(
                self.medusa_interface,
                self.theme_colors)
            # Add widget
            self.box_log_panel.layout().addWidget(self.log_panel_widget)
            self.box_log_panel.layout().setContentsMargins(0, 0, 0, 0)
            # Connect external actions
            self.log_panel_widget.toolButton_log_undock.clicked.connect(
                self.undock_log_panel)
        except Exception as e:
            self.handle_exception(e)

    def set_up_lsl_config(self):
        try:
            self.working_lsl_streams = list()
            if os.path.isfile(constants.LSL_CONFIG_FILE):
                with open(constants.LSL_CONFIG_FILE, 'r') as f:
                    last_streams = json.load(f)
                for lsl_stream_info_dict in last_streams:
                    try:
                        lsl_stream_info = \
                            lsl_utils.LSLStreamWrapper.from_serializable_obj(
                                lsl_stream_info_dict)
                    except exceptions.LSLStreamNotFound as e:
                        self.print_log('LSL stream %s not found' %
                                       lsl_stream_info_dict['medusa_uid'])
                        continue
                    self.working_lsl_streams.append(lsl_stream_info)
                    self.print_log('Connected to LSL stream: %s' %
                                   lsl_stream_info.medusa_uid)
        except Exception as e:
            self.handle_exception(e)

    def set_up_apps_panel(self):
        try:
            self.apps_panel_widget = apps_panel.AppsPanelWidget(
                self.working_lsl_streams,
                self.app_state,
                self.run_state,
                self.medusa_interface,
                self.theme_colors)
            # Add widget
            self.box_apps_panel.layout().addWidget(self.apps_panel_widget)
            self.box_apps_panel.layout().setContentsMargins(0, 0, 0, 0)
        except Exception as e:
            self.handle_exception(e)

    def set_up_plots_panel(self):
        try:
            # Create widget
            self.plots_panel_widget = plots_panel.PlotsPanelWidget(
                self.working_lsl_streams,
                self.plot_state,
                self.medusa_interface,
                self.theme_colors)
            # Add widget
            self.box_plots_panel.layout().addWidget(self.plots_panel_widget)
            self.box_plots_panel.layout().setContentsMargins(0, 0, 0, 0)
            # Connect external actions
            self.plots_panel_widget.toolButton_plot_undock.clicked.connect(
                self.undock_plots_panel)
        except Exception as e:
            self.handle_exception(e)

    # =============================== MENU BAR =============================== #
    def set_up_menu_bar_main(self):
        # Preferences
        # TODO: menuAction_view_intergated, menuAction_view_split,
        #  menuAction_color_dark, menuAction_color_light
        # Lab streaming layer
        # TODO: menuAction_lsl_doc, menuAction_lsl_repo, menuAction_lsl_about
        self.menuAction_lsl_settings.triggered.connect(
            self.open_lsl_config_window)
        # Developer tools
        # TODO: menuAction_dev_tutorial, menuAction_dev_new_empty_app,
        #   menuAction_dev_new_qt_app, menuAction_dev_new_unity_app,
        #   menuAction_dev_new_app_from
        # Developer tools
        # TODO: menuAction_help_support, menuAction_help_bug,
        #  menuAction_help_update, menuAction_help_about

    # =============================== TOOL BAR =============================== #
    def reset_tool_bar_main(self):
        try:
            # Create QAction buttons
            lsl_config_icon = QIcon("%s/icons/link_enabled_icon.png" %
                                    constants.IMG_FOLDER)
            plots_icon = QIcon("%s/icons/signal_enabled_icon.png" %
                               constants.IMG_FOLDER)
            profile_icon = QIcon("%s/icons/user_enabled.png" %
                                 constants.IMG_FOLDER)
            # Create QToolButton
            self.toolButton_lsl_config.setIcon(lsl_config_icon)
            self.toolButton_analyzer.setIcon(plots_icon)
            self.toolButton_profile.setIcon(profile_icon)
        except Exception as e:
            self.handle_exception(e)

    def set_up_tool_bar_main(self):
        try:
            # Create lsl config button
            self.toolButton_lsl_config = QToolButton(self.toolBar)
            self.setProperty("class", "main-toolbar-button")
            self.toolButton_lsl_config.clicked.connect(self.open_lsl_config_window)
            # Create plots button
            self.toolButton_analyzer = QToolButton(self.toolBar)
            self.setProperty("class", "main-toolbar-button")
            self.toolButton_analyzer.clicked.connect(self.open_analyzer_window)
            # Create profile button
            self.toolButton_profile = QToolButton(self.toolBar)
            self.setProperty("class", "main-toolbar-button")
            self.toolButton_profile.clicked.connect(self.open_user_profile_window)
            # Create spacer widget
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            # Add QActions to QToolBar
            self.toolBar.addWidget(self.toolButton_lsl_config)
            self.toolBar.addWidget(self.toolButton_analyzer)
            self.toolBar.addWidget(spacer)
            self.toolBar.addWidget(self.toolButton_profile)
            # Set default
            self.reset_tool_bar_main()
        except Exception as e:
            print(e)
            self.handle_exception(e)

    def open_analyzer_window(self):
        pass

    def open_user_profile_window(self, event):
        try:
            self.user_profile_window = user_profile.UserProfileDialog(
                theme_colors=self.theme_colors)
            # menu = QMenu(self)
            # menu.addAction("Profile")
            # menu.addAction("Close session")
            # menu.exec_(QCursor.pos())
        except Exception as e:
            self.handle_exception(e)

    # ======================== LAB-STREAMING LAYER =========================== #
    def open_lsl_config_window(self):
        try:
            self.user_profile_window = \
                lsl_config.LSLConfig(self.working_lsl_streams,
                                     theme_colors=self.theme_colors)
            self.user_profile_window.accepted.connect(self.set_lsl_streams)
            self.user_profile_window.rejected.connect(self.reset_lsl_streams)
        except Exception as e:
            self.handle_exception(e)

    def set_lsl_streams(self):
        try:
            # Set working streams
            self.working_lsl_streams = self.user_profile_window.working_streams
            # Update the working streams within the panels
            self.plots_panel_widget.update_working_lsl_streams(
                self.working_lsl_streams)
            self.apps_panel_widget.update_working_lsl_streams(
                self.working_lsl_streams)
            # Print log info
            for lsl_stream_info in self.working_lsl_streams:
                self.print_log('Connected to LSL stream: %s' %
                               lsl_stream_info.medusa_uid)
        except Exception as e:
            self.handle_exception(e)

    def reset_lsl_streams(self):
        try:
            pass
        except Exception as e:
            self.handle_exception(e)

    # ======================= PLOTS PANEL FUNCTIONS ========================== #
    def undock_plots_panel(self):
        try:
            if not self.plots_panel_widget.undocked:
                # Get current dimensions
                window_height = self.height()
                plots_panel_width = self.plots_panel_widget.width()
                apps_panel_width = self.apps_panel_widget.width()
                # Create main window
                self.plots_panel_window = plots_panel.PlotsPanelWindow(
                    self.plots_panel_widget, self.theme_colors,
                    plots_panel_width, window_height
                )
                self.plots_panel_widget.set_undocked(True)
                self.plots_panel_window.close_signal.connect(
                    self.dock_plots_panel)
                # Hide group box and set splitter
                self.widget_right_side.hide()
                self.resize(apps_panel_width, window_height)
                self.splitter.setSizes([apps_panel_width, 0])
            else:
                self.plots_panel_window.close()
        except Exception as e:
            self.handle_exception(e)

    def dock_plots_panel(self):
        # Get current dimensions
        window_height = self.height()
        window_width = self.width()
        plots_panel_width = self.plots_panel_widget.width()
        apps_panel_width = self.apps_panel_widget.width()
        # Update state
        self.plots_panel_widget.set_undocked(False)
        # Reset sizes
        # self.resize(apps_panel_width + plots_panel_width, window_height)
        self.splitter.setSizes(
            [int(self.default_splitter_ratio*window_width),
             int((1-self.default_splitter_ratio)*window_width)])
        # Add widget
        self.box_plots_panel.layout().addWidget(self.plots_panel_widget)
        self.box_plots_panel.layout().setContentsMargins(0, 0, 0, 0)
        self.widget_right_side.show()

    # ======================== LOG PANEL FUNCTIONS =========================== #
    def undock_log_panel(self):
        try:
            if not self.log_panel_widget.undocked:
                # Get current dimensions
                window_height = self.height()
                log_panel_width = self.apps_panel_widget.width()
                # Create main window
                self.log_panel_window = log_panel.LogPanelWindow(
                    self.log_panel_widget, self.theme_colors,
                    width=log_panel_width, height=window_height)
                self.log_panel_widget.set_undocked(True)
                self.log_panel_window.close_signal.connect(
                    self.dock_log_panel)
                # Hide group box and set splitter
                self.box_log_panel.hide()
                self.splitter_2.setSizes([log_panel_width, 0])
            else:
                self.log_panel_window.close()
        except Exception as e:
            self.handle_exception(e)

    def dock_log_panel(self):
        # Get current dimensions
        window_height = self.height()
        # Update state
        self.log_panel_widget.set_undocked(False)
        # Reset sizes
        # self.resize(window_width, apps_panel_height + log_panel_height)
        self.splitter_2.setSizes(
            [int(self.default_splitter_2_ratio * window_height),
             int((1 - self.default_splitter_2_ratio) * window_height)])
        # Add widget
        self.box_log_panel.layout().addWidget(self.log_panel_widget)
        self.box_log_panel.layout().setContentsMargins(0, 0, 0, 0)
        self.box_log_panel.show()

    # ========================== OTHER FUNCTIONS ============================= #
    def on_app_state_changed(self, app_state_value):
        """Called by MedusaInterfaceListener when it receives an
        app_state_changed message
        """
        try:
            self.app_state.value = app_state_value
            if self.app_state.value == constants.APP_STATE_OFF:
                self.apps_panel_widget.reset_tool_bar_app_buttons()
                self.on_run_state_changed(constants.RUN_STATE_READY)
                self.set_status('Ready')
                print('[GUiMain.on_app_state_changed]: APP_STATE_OFF')
            elif self.app_state.value == constants.APP_STATE_POWERING_ON:
                self.set_status('Powering on...')
                print('[GUiMain.on_app_state_changed]: APP_STATE_POWERING_ON')
            elif self.app_state.value == constants.APP_STATE_POWERING_OFF:
                self.set_status('Powering off...')
                print('[GUiMain.on_app_state_changed]: APP_STATE_POWERING_OFF')
            elif self.app_state.value == constants.APP_STATE_ON:
                self.set_status('Running')
                print('[GUiMain.on_app_state_changed]: APP_STATE_ON')
            else:
                raise ValueError('Unknown app state: %s' %
                                 str(self.app_state.value))
        except Exception as e:
            self.handle_exception(e)

    def on_run_state_changed(self, run_state_value):
        """Called by MedusaInterfaceListener when it receives a
        run_state_changed message
        """
        self.run_state.value = run_state_value
        if self.run_state.value == constants.RUN_STATE_READY:
            print('[GUiMain.on_run_state_changed]: RUN_STATE_READY')
        elif self.run_state.value == constants.RUN_STATE_RUNNING:
            print('[GUiMain.on_run_state_changed]: RUN_STATE_RUNNING')
        elif self.run_state.value == constants.RUN_STATE_PAUSED:
            print('[GUiMain.on_run_state_changed]: RUN_STATE_PAUSED')
        elif self.run_state.value == constants.RUN_STATE_STOP:
            print('[GUiMain.on_run_state_changed]: RUN_STATE_STOP')
        elif self.run_state.value == constants.RUN_STATE_FINISHED:
            print('[GUiMain.on_run_state_changed]: RUN_STATE_FINISHED')
        else:
            raise ValueError('Unknown app state: %s' %
                             str(self.app_state.value))

    def print_log(self, msg, style=None):
        """ Prints in the application log."""
        try:
            self.log_panel_widget.print_log(msg, style)
        except Exception as e:
            self.handle_exception(e)

    # ====================== EXCEPTION HANDLER, CLOSE ======================== #
    def handle_exception(self, ex):
        """ This function handles all the exceptions in MEDUSA

        Parameters
        ----------
        ex: Exception or subclass
            Exception raised in medusa
        """
        try:
            # Check exception
            if not isinstance(ex, exceptions.MedusaException):
                ex = exceptions.MedusaException(
                    ex, importance=exceptions.EXCEPTION_UNKNOWN,
                    scope='general',
                    origin='GuiMain/handle_exception')
            # Print exception message
            print(ex.get_msg(verbose=True))
            print(ex.traceback)
            self.print_log(ex.get_msg(verbose=True),
                           style={'color': self.theme_colors['THEME_RED']})
            # Take actions
            if ex.importance == exceptions.EXCEPTION_CRITICAL:
                if ex.scope == 'app':
                    self.apps_panel_widget.terminate_app_process(kill=True)
                    self.reset_apps_panel()
                elif ex.scope == 'plots':
                    self.reset_plots_panel()
                elif ex.scope == 'general' or ex.scope is None:
                    self.apps_panel_widget.terminate_app_process(kill=True)
                    self.reset()
        except Exception as e:
            self.print_log(
                str(e), style={'color': self.theme_colors['THEME_RED']})

    def reset_apps_panel(self):
        """Stop and reset of the current application.
        """
        # Close current app and reset apps panel toolbars
        self.apps_panel_widget.terminate_app_process()
        self.apps_panel_widget.reset_tool_bar_app_buttons()
        # Update states
        self.on_app_state_changed(constants.APP_STATE_OFF)
        self.on_run_state_changed(constants.RUN_STATE_READY)

    def reset_plots_panel(self):
        # Close current plots
        self.plot_state.value = constants.PLOT_STATE_OFF
        if self.plots_panel_widget.undocked:
            self.plots_panel_window.close()
            # self.undocked_plot_process.terminate()
            # self.undocked_plot_process.join()
            # self.undocked_plot_process = None
        self.plots_panel_widget.reset_tool_bar_plot_buttons()
        self.plots_panel_widget.reset_plots_panel()

    def reset_log_panel(self):
        if self.log_panel_widget.undocked:
            self.log_panel_window.close()
        self.log_panel_widget.reset_tool_bar_log_buttons()

    def reset(self):
        try:
            """ This function resets MEDUSA to its initial state. Usually is
            called after an exception has occurred.
            """
            # Reset states
            self.reset_apps_panel()
            self.reset_plots_panel()
            self.reset_log_panel()
            # Close medusa_interface_listener
            if self.medusa_interface_listener is not None:
                self.medusa_interface_listener.terminate()
                self.set_up_medusa_interface_listener(self.interface_queue)
            # Update status
            self.set_status('App state off')
        except Exception as e:
            self.handle_exception(e)

    def closeEvent(self, event):
        try:
            """This method is executed when the wants to close the application. 
            All the processes and threads have to be closed 
            """
            if self.app_state.value != constants.APP_STATE_OFF or \
                    self.run_state.value != constants.RUN_STATE_READY:
                # Paradigm open. Not allowed to close Medusa
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Information)
                msg.setText("Please, finish the current run pressing the stop "
                            "button before closing MEDUSA")
                msg.setWindowTitle("Warning!")
                msg.setStandardButtons(QMessageBox.Ok)
                msg.exec_()
                event.ignore()
            else:
                # Close current app
                self.app_state.value = constants.APP_STATE_OFF
                self.run_state.value = constants.RUN_STATE_READY
                self.apps_panel_widget.terminate_app_process()
                # Close current plots
                self.plot_state.value = constants.PLOT_STATE_OFF
                if self.plots_panel_widget.undocked:
                    self.plots_panel_window.close()
                # Close log panel
                if self.log_panel_widget.undocked:
                    self.log_panel_window.close()
                # let the window close
                event.accept()
        except Exception as e:
            self.handle_exception(e)
