# PYTHON MODULES
import glob
import sys
import json
import importlib
import threading
import time
import warnings
import os
import queue
import logging
import urllib
import webbrowser
from logging.handlers import QueueHandler
# EXTERNAL MODULES
from PySide6.QtUiTools import loadUiType
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
# MEDUSA MODULES
import resources
from gui import gui_utils as gu
from gui.qt_widgets import dialogs
import constants, exceptions
from gui.qt_widgets.dialogs import ThreadProgressDialog

ui_plots_panel_widget = loadUiType('gui/ui_files/apps_panel_widget.ui')[0]


class AppsPanelWidget(QWidget, ui_plots_panel_widget):

    error_signal = Signal(Exception)

    def __init__(self, apps_manager, working_lsl_streams, app_state, run_state,
                 medusa_interface, apps_folder, study_mode, theme_colors):
        super().__init__()
        self.setupUi(self)
        # Attributes
        self.screen_size = self.screen().geometry().size()
        self.apps_manager = apps_manager
        self.working_lsl_streams = working_lsl_streams
        self.app_state = app_state
        self.run_state = run_state
        self.medusa_interface = medusa_interface
        self.apps_folder = apps_folder
        self.study_mode = study_mode
        self.theme_colors = theme_colors
        self.undocked = False
        self.apps_panel_grid_widget = None
        self.rec_info = self.get_default_rec_info()
        self.app_process = None
        self.app_settings = None
        self.current_app_key = None
        self.progress_dialog = None
        self.session_plan = None
        self.fake_user = None
        # Create apps panel grid scroll area
        self.set_up_apps_area()
        # Set up tool bar
        self.set_up_tool_bar_app()

    def handle_exception(self, mds_ex):
        # Send exception to gui main
        # self.medusa_interface.error(ex)
        self.error_signal.emit(mds_ex)

    def set_up_tool_bar_app(self):
        """ This method creates the QAction buttons displayed in the toolbar
        """
        # Create run buttons
        self.toolButton_app_power = QToolButton()
        self.toolButton_app_power.setIconSize(QSize(20, 20))
        self.toolButton_app_power.clicked.connect(self.app_power)
        self.horizontalLayout_apps_toolbar.addWidget(self.toolButton_app_power)
        self.toolButton_app_play = QToolButton()
        self.toolButton_app_play.setIconSize(QSize(20, 20))
        self.toolButton_app_play.clicked.connect(self.app_play)
        self.horizontalLayout_apps_toolbar.addWidget(self.toolButton_app_play)
        self.toolButton_app_stop = QToolButton()
        self.toolButton_app_stop.setIconSize(QSize(20, 20))
        self.toolButton_app_stop.clicked.connect(self.app_stop)
        self.horizontalLayout_apps_toolbar.addWidget(self.toolButton_app_stop)
        self.toolButton_app_config = QToolButton()
        self.toolButton_app_config.setIconSize(QSize(20, 20))
        self.toolButton_app_config.clicked.connect(self.app_config)
        self.horizontalLayout_apps_toolbar.addWidget(self.toolButton_app_config)
        self.toolButton_app_install = QToolButton()
        self.toolButton_app_install.setIconSize(QSize(20, 20))
        self.toolButton_app_install.clicked.connect(self.install_app)
        self.horizontalLayout_apps_toolbar.addWidget(
            self.toolButton_app_install)
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        self.horizontalLayout_apps_toolbar.addWidget(separator)
        # Create session buttons
        self.toolButton_session_load = QToolButton()
        self.toolButton_session_load.setIconSize(QSize(20, 20))
        self.toolButton_session_load.clicked.connect(self.load_session)
        self.horizontalLayout_apps_toolbar.addWidget(
            self.toolButton_session_load)
        self.toolButton_session_play = QToolButton()
        self.toolButton_session_play.setIconSize(QSize(20, 20))
        self.toolButton_session_play.clicked.connect(self.play_session)
        self.horizontalLayout_apps_toolbar.addWidget(
            self.toolButton_session_play)
        self.toolButton_session_config = QToolButton()
        self.toolButton_session_config.setIconSize(QSize(20, 20))
        self.toolButton_session_config.clicked.connect(self.config_session)
        self.horizontalLayout_apps_toolbar.addWidget(
            self.toolButton_session_config)
        self.toolButton_session_create = QToolButton()
        self.toolButton_session_create.setIconSize(QSize(20, 20))
        self.toolButton_session_create.clicked.connect(self.create_session)
        self.horizontalLayout_apps_toolbar.addWidget(
            self.toolButton_session_create)
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        self.horizontalLayout_apps_toolbar.addWidget(separator)
        # Recording info buttons
        self.toolButton_edit_rec_info = QToolButton()
        self.toolButton_edit_rec_info.setIconSize(QSize(20, 20))
        self.toolButton_edit_rec_info.clicked.connect(self.config_rec_info)
        self.horizontalLayout_apps_toolbar.addWidget(
            self.toolButton_edit_rec_info)
        # Create panel buttons
        hspacer = QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout_apps_toolbar.addItem(hspacer)
        self.toolButton_app_undock = QToolButton()
        self.toolButton_app_undock.setIconSize(QSize(20, 20))
        self.horizontalLayout_apps_toolbar.addWidget(
            self.toolButton_app_undock)
        # Set buttons icons
        self.reset_tool_bar_app_buttons()

    def reset_tool_bar_app_buttons(self):
        # Run icons
        self.toolButton_app_power.setIcon(
            gu.get_icon("power.svg", self.theme_colors))
        self.toolButton_app_power.setToolTip('Start selected app')
        self.toolButton_app_play.setIcon(
            gu.get_icon("play.svg", custom_color=self.theme_colors['THEME_GREEN']))
        self.toolButton_app_play.setToolTip('Play selected app')
        self.toolButton_app_stop.setIcon(
            gu.get_icon("stop.svg", custom_color=self.theme_colors['THEME_RED']))
        self.toolButton_app_stop.setToolTip('Stop selected app')
        self.toolButton_app_config.setIcon(
            gu.get_icon("settings.svg", self.theme_colors))
        self.toolButton_app_config.setToolTip('Configure selected app')
        self.toolButton_app_install.setIcon(
            gu.get_icon("add.svg", self.theme_colors))
        self.toolButton_app_install.setToolTip('Install new app')
        # Session icons
        if self.fake_user is None:
            self.toolButton_session_load.setIcon(
                gu.get_icon("route.svg", self.theme_colors))
            self.toolButton_session_load.setToolTip('Load session')
            self.toolButton_session_play.setIcon(
                gu.get_icon("fast_forward.svg", self.theme_colors))
            self.toolButton_session_play.setToolTip('Play session')
            self.toolButton_session_config.setIcon(
                gu.get_icon("settings.svg", self.theme_colors))
            self.toolButton_session_config.setToolTip('Configure session')
            self.toolButton_session_create.setIcon(
                gu.get_icon("add.svg", self.theme_colors))
            self.toolButton_session_create.setToolTip('Create session')
            # Recording info icons
            self.toolButton_edit_rec_info.setIcon(
                gu.get_icon("save_as.svg", self.theme_colors))
            self.toolButton_edit_rec_info.setToolTip('Edit recording info')
        # Set panel icons
        if self.undocked:
            self.toolButton_app_undock.setIcon(
                gu.get_icon("open_in_new_down.svg", self.theme_colors))
            self.toolButton_app_undock.setToolTip(
                'Redock in main window')
        else:
            self.toolButton_app_undock.setIcon(
                gu.get_icon("open_in_new.svg", self.theme_colors))
            self.toolButton_app_undock.setToolTip('Undock')
        # Set button states
        if self.apps_panel_grid_widget.get_selected_app() is None:
            self.toolButton_app_power.setDisabled(True)
            self.toolButton_app_config.setDisabled(True)
        else:
            self.toolButton_app_power.setDisabled(False)
            self.toolButton_app_config.setDisabled(False)
        self.toolButton_app_play.setDisabled(True)
        self.toolButton_app_stop.setDisabled(True)
        if self.session_plan is None:
            self.toolButton_session_play.setDisabled(True)
            self.toolButton_session_config.setDisabled(True)
        else:
            self.toolButton_session_play.setDisabled(False)
            self.toolButton_session_config.setDisabled(False)

    def set_up_apps_area(self):
        self.apps_panel_grid_widget = AppsPanelGridWidget(
            min_app_widget_width=int(0.1 * min(self.screen_size.width(),
                                               self.screen_size.height())),
            apps_folder=self.apps_folder,
            theme_colors=self.theme_colors)
        self.fill_apps_panel()
        self.apps_panel_grid_widget.arrange_panel(568)
        # Create scroll area
        self.scrollArea_apps = QScrollArea()
        self.scrollArea_apps.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff)
        self.scrollArea_apps.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded)
        self.scrollArea_apps.setWidget(self.apps_panel_grid_widget)
        self.scrollArea_apps.setWidgetResizable(True)
        self.verticalLayout_apps_panel.addWidget(self.scrollArea_apps)

    def get_app_module(self, app_key, module):
        app_module = '%s.%s.%s' % \
                     (self.apps_folder.replace('/', '.'), app_key, module)
        return app_module

    @exceptions.error_handler(scope='general')
    def wait_until_app_closed(self, interval=0.1, timeout=1):
        success = True
        start = time.time()
        while self.app_process.is_alive():
            if time.time() - start > timeout:
                success = False
                break
            time.sleep(interval)
        return success

    @exceptions.error_handler(scope='general')
    def terminate_app_process(self, kill=False):
        """Terminates the app process. Kill should be True only if it is
        critical to close the app"""
        success = False
        if self.app_process is not None:
            # The app cannot be closed nicely because lives in other process!
            # Try to close the app nicely
            # self.app_process.close_app()
            # success = self.wait_until_app_closed(interval=0.05, timeout=2)
            # Kill the app
            if not success and kill:
                warnings.warn('Killing the app. This should not be '
                              'necessary if all exceptions are handled '
                              'correctly!')
                self.app_process.terminate()
                self.app_process.join()
                success = True
        return success

    def fill_apps_panel(self):
        # Create and fill apps panel
        self.apps_panel_grid_widget.reset()
        for app_key, app_params in self.apps_manager.apps_dict.items():
            widget = self.apps_panel_grid_widget.add_app_widget(
                app_key, app_params)
            widget.app_selected.connect(self.on_app_selected)
            widget.app_about.connect(self.about_app)
            widget.app_doc.connect(self.documentation_app)
            widget.app_update.connect(self.update_app)
            widget.app_package.connect(self.package_app)
            widget.app_uninstall.connect(self.uninstall_app)

    @exceptions.error_handler(scope='general')
    def on_app_selected(self, checked=None):
        self.toolButton_app_power.setDisabled(False)
        self.toolButton_app_config.setDisabled(False)

    @exceptions.error_handler(scope='general')
    def update_apps_panel(self):
        self.fill_apps_panel()
        self.apps_panel_grid_widget.arrange_panel(
            self.apps_panel_grid_widget.width())

    @exceptions.error_handler(scope='general')
    def update_working_lsl_streams(self, working_lsl_streams):
        self.working_lsl_streams = working_lsl_streams

    @exceptions.error_handler(scope='general')
    def resizeEvent(self, event):
        # w = event.size().width()
        w_scr = self.scrollArea_apps.width()
        self.apps_panel_grid_widget.arrange_panel(w_scr)

    def set_undocked(self, undocked):
        self.undocked = undocked
        self.reset_tool_bar_app_buttons()

    @exceptions.error_handler(scope='general')
    def app_power(self, checked=None):
        """ This function starts the paradigm. Once the paradigm is powered, it
        can only be stopped with stop button
        """
        # Check LSL streams
        if len(self.working_lsl_streams) == 0:
            resp = dialogs.confirmation_dialog(
                text='There are no LSL streams available. Do you want to '
                     'continue?',
                title='No LSL streams',
                theme_colors=self.theme_colors)
            if not resp:
                return
        # Check app selected
        current_app_key = self.apps_panel_grid_widget.get_selected_app()
        if current_app_key is None:
            raise ValueError('Select an app to start!')
        # Start app
        if self.app_state.value is constants.APP_STATE_OFF:
            # Get selected app modules
            app_process_mdl = importlib.import_module(
                self.get_app_module(current_app_key, 'main'))
            app_settings_mdl = importlib.import_module(
                self.get_app_module(current_app_key, 'settings'))
            # Get app settings
            if self.app_settings is None or \
                    not isinstance(self.app_settings,
                                   app_settings_mdl.Settings):
                self.app_settings = app_settings_mdl.Settings()
            # Serialize working_lsl_streams
            ser_lsl_streams = [lsl_str.to_serializable_obj() for
                               lsl_str in self.working_lsl_streams]
            # Get app manager
            self.app_process = app_process_mdl.App(
                app_info=self.apps_manager.apps_dict[current_app_key],
                app_settings=self.app_settings,
                medusa_interface=self.medusa_interface,
                app_state=self.app_state,
                run_state=self.run_state,
                working_lsl_streams_info=ser_lsl_streams,
                rec_info=self.rec_info
            )
            self.app_process.start()
            # Enabling, disabling and changing the buttons in the toolbar
            self.toolButton_app_power.setDisabled(True)
            self.toolButton_app_power.setIcon(
                gu.get_icon("power.svg", self.theme_colors))
            self.toolButton_app_play.setDisabled(False)
            self.toolButton_app_play.setIcon(
                gu.get_icon("play.svg", custom_color=self.theme_colors[
                    'THEME_GREEN']))
            self.toolButton_app_stop.setDisabled(False)
            self.toolButton_app_stop.setIcon(
                gu.get_icon("stop.svg", custom_color=self.theme_colors[
                    'THEME_RED']))
            self.run_state.value = constants.RUN_STATE_READY
            self.current_app_key = current_app_key

    @exceptions.error_handler(scope='general')
    def app_play(self, checked=None):
        """ Starts a run with specified settings. The run will be recorded"""
        if self.app_state.value is constants.APP_STATE_ON and \
                self.run_state.value is not constants.RUN_STATE_FINISHED:
            if self.run_state.value is constants.RUN_STATE_READY:
                self.run_state.value = constants.RUN_STATE_RUNNING
                self.toolButton_app_play.setIcon(
                    gu.get_icon("pause.svg", self.theme_colors, enabled=True))
                # Feedback
                self.medusa_interface.log("Run started")
            elif self.run_state.value is constants.RUN_STATE_RUNNING:
                self.run_state.value = constants.RUN_STATE_PAUSED
                self.toolButton_app_play.setIcon(
                    gu.get_icon("play.svg", custom_color=self.theme_colors[
                        'THEME_GREEN']))
                # Feedback
                self.medusa_interface.log("Run paused")
            elif self.run_state.value is constants.RUN_STATE_PAUSED:
                self.run_state.value = constants.RUN_STATE_RUNNING
                self.toolButton_app_play.setIcon(
                    gu.get_icon("pause.svg", self.theme_colors, enabled=True))
                # Feedback
                self.medusa_interface.log("Run resumed")

    @exceptions.error_handler(scope='general')
    def app_stop(self, checked=None):
        """ Stops the run"""
        if self.app_state.value is constants.APP_STATE_ON:
            # Change state
            self.run_state.value = constants.RUN_STATE_STOP
            # Feedback
            self.medusa_interface.log("Run stopped")
            # Enabling, disabling and changing the buttons in the toolbar
            self.toolButton_app_power.setDisabled(False)
            self.toolButton_app_power.setIcon(
                gu.get_icon("power.svg", self.theme_colors, enabled=True))
            self.toolButton_app_play.setDisabled(True)
            self.toolButton_app_play.setIcon(
                gu.get_icon("play.svg", custom_color=self.theme_colors[
                    'THEME_GREEN']))
            self.toolButton_app_stop.setDisabled(True)
            self.toolButton_app_stop.setIcon(
                gu.get_icon("stop.svg", custom_color=self.theme_colors[
                    'THEME_RED']))

    @exceptions.error_handler(scope='general')
    def app_config(self, checked=None):
        """ Launches the config UI for the selected run """
        # Check app selected
        current_app_key = self.apps_panel_grid_widget.get_selected_app()
        if current_app_key is None:
            dialogs.error_dialog(message='Please, select an app to config.',
                                 title='Error!',
                                 theme_colors=self.theme_colors)
        app_settings_mdl = importlib.import_module(
            self.get_app_module(current_app_key, 'settings'))
        try:
            app_config_mdl = importlib.import_module(
                self.get_app_module(current_app_key, 'config'))
            conf_window = app_config_mdl.Config
        except ModuleNotFoundError as e:
            self.error_signal.emit(exceptions.MedusaException(e))
            conf_window = resources.BasicConfigWindow
        if self.app_settings is None or not isinstance(
                self.app_settings, app_settings_mdl.Settings):
            self.app_settings = app_settings_mdl.Settings()
        self.app_config_window = conf_window(
            self.app_settings,
            medusa_interface=self.medusa_interface,
            working_lsl_streams_info=self.working_lsl_streams,
            theme_colors=self.theme_colors
        )
        self.app_config_window.close_signal.connect(
            self.on_config_window_close_event)

    @exceptions.error_handler(scope='general')
    def on_config_window_close_event(self, settings):
        """ This method is called when config window is closed. See
        on_new_settings_button_clicked function
        """
        if settings is not None:
            self.app_settings = settings

    @exceptions.error_handler(scope='general')
    def installation_finished(self):
        # Update apps panel
        self.update_apps_panel()

    @exceptions.error_handler(scope='general')
    def install_app(self, checked=None):
        # Get app file
        filt = "MEDUSA app (*.app)"
        directory = "../"
        if not os.path.exists(directory):
            os.makedirs(directory)
        app_file = QFileDialog.getOpenFileName(caption="MEDUSA app",
                                               dir=directory,
                                               filter=filt)[0]
        if app_file != '':

            # Initialize progress dialog
            self.progress_dialog = ThreadProgressDialog(
                window_title='Installing app...',
                min_pbar_value=0, max_pbar_value=100,
                theme_colors=self.theme_colors)
            self.progress_dialog.done.connect(self.installation_finished)
            self.progress_dialog.show()

            # Install
            th = threading.Thread(target=self.apps_manager.install_app_bundle,
                                  args=(app_file, self.progress_dialog))
            th.start()

    @exceptions.error_handler(scope='general')
    def about_app(self, app_key):
        dialogs.info_dialog(
            '%s' % json.dumps(self.apps_manager.apps_dict[app_key], indent=4),
            'About %s' % self.apps_manager.apps_dict[app_key]['name'],
            self.theme_colors)

    @exceptions.error_handler(scope='general')
    def documentation_app(self, app_key):
        response = None
        url = f"https://medusabci.com/market/{app_key}/"
        try:
            response = urllib.request.urlopen(url)
        except urllib.error.HTTPError as e:
            dialogs.warning_dialog(
                'There is no app with the following  id: \n %s' %
                app_key, 'Documentation', self.theme_colors)
        if response:
            webbrowser.open(url)

    @exceptions.error_handler(scope='general')
    def update_app(self, app_key):
        dialogs.warning_dialog(
            'No available updates for %s' %
            self.apps_manager.apps_dict[app_key]['name'],
            'Update', self.theme_colors)

    @exceptions.error_handler(scope='general')
    def package_app(self, app_key):
        # Choose path
        filt = "MEDUSA app (*.zip)"
        directory = "../%s.zip" % app_key
        app_file = QFileDialog.getSaveFileName(caption="Make app bundle",
                                               directory=directory,
                                               filter=filt)[0]
        if len(app_file) > 0:
            dir_name = os.path.dirname(app_file)
            base_name = os.path.basename(app_file).split('.zip')[0]
            output_path = '%s/%s' % (dir_name, base_name)

            # Create queue logger
            log_queue = queue.Queue(-1)
            queue_handler = QueueHandler(log_queue)
            logger = logging.getLogger("package_app")
            logger.setLevel(logging.INFO)
            logger.addHandler(queue_handler)

            # Initialize progress dialog
            self.progress_dialog = ThreadProgressDialog(
                window_title='Packaging app...',
                min_pbar_value=0, max_pbar_value=100,
                theme_colors=self.theme_colors)
            self.progress_dialog.done.connect(self.installation_finished)
            self.progress_dialog.show()

            # Package function
            th = threading.Thread(
                target=self.apps_manager.package_app,
                args=(app_key, output_path, logger, self.progress_dialog))
            th.start()

    @exceptions.error_handler(scope='general')
    def uninstall_app(self, app_key):
        # Confirm dialog
        if not dialogs.confirmation_dialog(
                'Are you sure you want to uninstall %s? ' %
                self.apps_manager.apps_dict[app_key]['name'],
                'Uninstall', theme_colors=self.theme_colors):
            return
        # Uninstall directory
        try:
            self.apps_manager.uninstall_app(app_key)
        except PermissionError as e:
            dialogs.error_dialog(
                message='MEDUSA does not have permission to perform '
                        'this operation. Try to run as administrator',
                title='Permission error!',
                theme_colors=self.theme_colors)
        # Update apps panel
        self.update_apps_panel()

    @exceptions.error_handler(scope='general')
    def load_session(self, checked=None):
        # Get app file
        filt = "Session plan (*.session)"
        directory = "../config"
        if not os.path.exists(directory):
            os.makedirs(directory)
        session_plan = QFileDialog.getOpenFileName(caption="Session plan",
                                                   directory=directory,
                                                   filter=filt)[0]
        if len(session_plan) > 0:
            with open(session_plan, 'r') as f:
                self.session_plan = json.load(f)
            # Enable session buttons
            self.toolButton_session_play.setDisabled(False)
            self.toolButton_session_config.setDisabled(False)

    @exceptions.error_handler(scope='general')
    def play_session(self, checked=None):
        if self.fake_user is None:
            self.fake_user = FakeUser(
                self.medusa_interface, self.app_state, self.run_state,
                self.session_plan)
            self.fake_user.app_power.connect(self.on_play_session_app_power)
            self.fake_user.app_play.connect(self.app_play)
            self.fake_user.app_stop.connect(self.app_stop)
            self.fake_user.session_finished.connect(
                self.on_play_session_finished)
            self.fake_user.start()
            self.toolButton_session_play.setIcon(
                gu.get_icon("stop.svg",
                            custom_color=self.theme_colors['THEME_RED']))
        else:
            self.app_stop()
            self.fake_user.stop = True
            self.fake_user = None
            # Wait cannot be used because it blocks the main thread. Is it
            # safe to assume that the thread will close? Not sure
            # self.fake_user.wait()

    @exceptions.error_handler(scope='general')
    def on_play_session_app_power(self, run):
        # Update rec info
        self.rec_info['rec_id'] = run['rec_id']
        self.rec_info['file_ext'] = run['file_ext']
        # Select app
        self.apps_panel_grid_widget.find_app(run['app_id'])
        # Load settings
        current_app_key = self.apps_panel_grid_widget.get_selected_app()
        app_settings_mdl = importlib.import_module(
            self.get_app_module(current_app_key, 'settings'))
        if os.path.isfile(run['settings_path']):
            self.app_settings = app_settings_mdl.Settings.load(
                run['settings_path'])
        # App power
        self.app_power()

    @exceptions.error_handler(scope='general')
    def on_play_session_finished(self, checked=None):
        self.toolButton_session_play.setIcon(
            gu.get_icon("fast_forward.svg", self.theme_colors))

    @exceptions.error_handler(scope='general')
    def config_session(self, checked=None):
        self.config_session_dialog = ConfigSessionDialog(
            apps_manager=self.apps_manager,
            session_plan=self.session_plan,
            theme_colors=self.theme_colors)
        self.config_session_dialog.accepted.connect(
            self.on_session_config_dialog_accepted)
        self.config_session_dialog.rejected.connect(
            self.on_session_config_dialog_rejected)
        self.config_session_dialog.exec_()

    @exceptions.error_handler(scope='general')
    def create_session(self, checked=None):
        self.config_session_dialog = ConfigSessionDialog(
            apps_manager=self.apps_manager,
            theme_colors=self.theme_colors
        )
        self.config_session_dialog.accepted.connect(
            self.on_session_config_dialog_accepted)
        self.config_session_dialog.rejected.connect(
            self.on_session_config_dialog_rejected)
        self.config_session_dialog.exec_()

    @exceptions.error_handler(scope='general')
    def on_session_config_dialog_accepted(self, checked=None):
        self.session_plan = self.config_session_dialog.session_plan
        if len(self.session_plan) > 0:
            self.toolButton_session_play.setDisabled(False)
            self.toolButton_session_config.setDisabled(False)
        self.config_session_dialog = None

    @exceptions.error_handler(scope='general')
    def on_session_config_dialog_rejected(self, checked=None):
        self.session_plan = None
        self.toolButton_session_play.setDisabled(True)
        self.toolButton_session_config.setDisabled(True)
        self.config_session_dialog = None

    @exceptions.error_handler(scope='general')
    def config_rec_info(self, checked=None):
        self.edit_rec_info_dialog = ConfigureRecInfoDialog(
            study_mode=self.study_mode,
            rec_info=self.rec_info,
            theme_colors=self.theme_colors
        )
        self.edit_rec_info_dialog.accepted.connect(
            self.on_edit_rec_info_dialog_accepted)
        self.edit_rec_info_dialog.rejected.connect(
            self.on_edit_rec_info_dialog_rejected)
        self.edit_rec_info_dialog.exec_()

    @exceptions.error_handler(scope='general')
    def on_edit_rec_info_dialog_accepted(self, checked=None):
        self.rec_info = self.edit_rec_info_dialog.rec_info

    @exceptions.error_handler(scope='general')
    def on_edit_rec_info_dialog_rejected(self, checked=None):
        self.rec_info = None

    @exceptions.error_handler(scope='general')
    def set_rec_info(self, rec_info):
        self.rec_info = rec_info
        session_plans = glob.glob('%s/*.session' % rec_info['path'])
        if len(session_plans) == 1:
            if dialogs.confirmation_dialog(
                    'There is a session plan available for '
                    'this subject, do you want to load it?',
                    title='Session plan available'):

                with open(session_plans[0], 'r') as f:
                    self.session_plan = json.load(f)
                    # Enable session buttons
                    self.toolButton_session_play.setDisabled(False)
                    self.toolButton_session_config.setDisabled(False)

    @staticmethod
    def get_default_rec_info():
        rec_info = {
            'rec_id': None,
            'file_ext': 'bson',
            'path': os.path.abspath('../data'),
            'study_id': None,
            'subject_id': None,
            'session_id': None,
            'study_info': None
        }
        return rec_info


class AppsPanelGridWidget(QWidget):

    def __init__(self, min_app_widget_width, apps_folder, theme_colors):
        super().__init__()
        # Init attributes
        self.min_app_widget_width = min_app_widget_width
        self.apps_folder = apps_folder
        self.theme_colors = theme_colors
        # Create main layout
        main_layout = QVBoxLayout()
        # Create search bar
        search_bar_layout = QHBoxLayout()
        self.lineEdit_app_search = QLineEdit()
        self.lineEdit_app_search.setObjectName('lineEdit_app_search')
        self.lineEdit_app_search.textChanged.connect(self.app_search)
        self.lineEdit_app_search.addAction(
            gu.get_icon("search.svg", self.theme_colors),
            QLineEdit.TrailingPosition)
        # self.toolButton_app_search = QToolButton()
        # self.toolButton_app_search.setObjectName('toolButton_app_search')
        # # self.toolButton_app_search.setIconSize(QSize(20, 20))
        # self.toolButton_app_search.setIcon(
        #     gu.get_icon("search.svg", self.theme_colors))
        # self.toolButton_app_search.setToolTip('Search apps')
        search_bar_layout.addWidget(self.lineEdit_app_search)
        # search_bar_layout.addWidget(self.toolButton_app_search)
        main_layout.addLayout(search_bar_layout)
        # Create Grid
        self.grid = QGridLayout()
        self.grid.setSpacing(2)
        main_layout.addLayout(self.grid)
        # Create space
        spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        main_layout.addItem(spacer)
        # self.grid.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        # Create wrappers
        # self.v_layout = QVBoxLayout()
        # self.v_layout.addLayout(self.grid)
        # self.v_layout.addItem(
        #     QSpacerItem(0, 0, QSizePolicy.Ignored, QSizePolicy.Expanding))

        # self.h_layout = QHBoxLayout()
        # self.h_layout.addLayout(self.v_layout)
        # self.h_layout.addItem(
        #     QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Ignored))
        # Size policy
        # self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        # Init
        self.items = []
        self.n_items = 0
        self.n_cols = None
        self.selected_app_key = None
        # Add layout
        self.setObjectName("apps-panel-widget")
        self.setLayout(main_layout)
        # Size policy
        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    @exceptions.error_handler(scope='general')
    def app_search(self, checked=None):
        curr_text = self.lineEdit_app_search.text()
        self.find_app(curr_text)

    def get_selected_app(self):
        return self.selected_app_key

    def add_app_widget(self, app_key, app_params):
        widget = AppWidget(self.min_app_widget_width, app_key, app_params,
                           self.apps_folder, self.theme_colors)
        widget.app_selected.connect(self.on_app_selected)
        self.items.append(widget)
        self.n_items = len(self.items)
        return widget

    def on_app_selected(self, app_key):
        for item in self.items:
            if item.app_key == app_key:
                gu.modify_property(
                    item, "background-color",
                    self.theme_colors['THEME_MENU_SELECTED'])
            else:
                gu.modify_property(
                    item, "background-color",
                    self.theme_colors['THEME_BG_DARK'])
        self.selected_app_key = app_key

    def arrange_panel(self, width):
        if self.n_cols is not None:
            if (width // self.n_cols) > 1.5 * self.min_app_widget_width or \
                    (width // self.n_cols) < 1.5 * self.min_app_widget_width:
                # self.n_cols += 1
                self.n_cols = width // self.min_app_widget_width
                self.set_app_widgets_on_grid()
            else:
                self.n_cols = self.n_cols
        else:
            self.n_cols = width // self.min_app_widget_width
            self.set_app_widgets_on_grid()
        # Check n_cols
        self.n_cols = self.n_cols if self.n_cols > 1 else 1

    def set_app_widgets_on_grid(self):
        # Clear grid
        # self.clear()
        # Add widgets
        row, col = 0, 0
        for item in self.items:
            self.grid.addWidget(item, row, col)
            row, col = (row + 1, 0) if col >= self.n_cols - 1 else (
                row, col + 1)

    def find_app(self, text):
        """ Finds an application based on a provided text. If a single application
        is found, it is selected.
        """
        text = text.lower()
        found_items = list()
        for item in self.items:
            if text in item.app_params['name'].lower() or \
                    text in item.app_params['id'].lower():
                found_items.append(item)
        if len(found_items) == 1:
            found_items[0].select()

    def clear(self):
        try:
            while self.grid.count() > 0:
                item = self.grid.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                self.grid.removeItem(item)
        except Exception as e:
            self.handle_exception(e)

    def reset(self):
        self.clear()
        self.items = []
        self.n_items = 0
        self.n_cols = None


class AppWidget(QFrame):

    app_selected = Signal(str)
    app_about = Signal(str)
    app_doc = Signal(str)
    app_update = Signal(str)
    app_package = Signal(str)
    app_uninstall = Signal(str)

    def __init__(self, min_widget_width, app_key, app_params, apps_folder,
                 theme_colors):
        super().__init__()
        self.min_widget_width = min_widget_width
        self.app_key = app_key
        self.app_params = app_params
        self.apps_folder = apps_folder
        self.theme_colors = theme_colors
        self.pixmap_path = self.get_icon_path()
        self.main_layout = QVBoxLayout()
        # Icon
        self.pix_map = QPixmap(self.pixmap_path)
        self.icon = QLabel()
        self.icon.setPixmap(self.pix_map.scaledToWidth(
            int(0.75 * min_widget_width),
            Qt.TransformationMode.SmoothTransformation))
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setMargin(0)
        self.icon.setContentsMargins(0, 0, 0, 0)
        # Label
        self.title = QLabel(app_params['name'])
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setMargin(0)
        self.title.setContentsMargins(0, 0, 0, 0)
        gu.set_point_size(self.title, 8)
        # Restrictions
        self.setMinimumWidth(self.min_widget_width)
        self.setMaximumHeight(
            int(1.1 * self.min_widget_width))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        # Add layout
        self.main_layout.addWidget(self.icon)
        self.main_layout.addWidget(self.title)
        self.main_layout.addItem(
            QSpacerItem(0, 0, QSizePolicy.Ignored, QSizePolicy.Expanding))
        self.setProperty("class", "app-widget")
        # self.setCursor(QCursor(Qt.PointingHandCursor))
        # gu.modify_property(self, "background-color", '#00a05f')
        self.setLayout(self.main_layout)

    class AppMenu(QMenu):

        def __init__(self, is_in_development):
            super().__init__()
            # Create actions
            if is_in_development:
                self.about_action = QAction('About')
                self.package_action = QAction('Package')
                self.uninstall_action = QAction('Uninstall')
                # Add actions
                self.addAction(self.about_action)
                self.addAction(self.package_action)
                self.addAction(self.uninstall_action)
            else:
                self.about_action = QAction('About')
                self.doc_action = QAction('Documentation')
                self.update_action = QAction('Update')
                self.uninstall_action = QAction('Uninstall')
                # Add actions
                self.addAction(self.about_action)
                self.addAction(self.doc_action)
                self.addAction(self.update_action)
                self.addAction(self.uninstall_action)

    def get_icon_path(self):
        return '%s/%s/icon.png' % (self.apps_folder, self.app_key)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.select()
        elif event.button() == Qt.RightButton:
            # Check if we have to create the development or normal version of
            # the menu
            is_in_development = \
                self.app_params['compilation-date'] == 'development'
            menu = self.AppMenu(is_in_development=is_in_development)
            if is_in_development:
                menu.about_action.triggered.connect(self.about)
                menu.package_action.triggered.connect(self.package)
                menu.uninstall_action.triggered.connect(self.uninstall)
                menu.exec_(event.globalPos())
            else:
                menu.about_action.triggered.connect(self.about)
                menu.doc_action.triggered.connect(self.documentation)
                menu.update_action.triggered.connect(self.update)
                menu.uninstall_action.triggered.connect(self.uninstall)
                menu.exec_(event.globalPos())

    def select(self):
        self.app_selected.emit(self.app_key)

    def about(self):
        self.app_about.emit(self.app_key)

    def documentation(self):
        self.app_doc.emit(self.app_key)

    def update(self):
        self.app_update.emit(self.app_key)

    def package(self):
        self.app_package.emit(self.app_key)

    def uninstall(self):
        self.app_uninstall.emit(self.app_key)


class AppsPanelWindow(QMainWindow):

    """This window holds the plots panel widget in undocked mode"""

    close_signal = Signal()

    def __init__(self, apps_panel_widget, theme_colors,
                 width=1200, height=900):
        super().__init__()
        self.theme_colors = theme_colors
        self.setCentralWidget(apps_panel_widget)
        gu.set_css_and_theme(self, self.theme_colors)
        # Window title and icon
        self.setWindowIcon(QIcon('%s/medusa_task_icon.png' %
                                 constants.IMG_FOLDER))
        self.setWindowTitle('Apps panel')
        # Resize plots window
        self.resize(width, height)
        self.show()

    def closeEvent(self, event):
        self.close_signal.emit()
        event.accept()

    def get_plots_panel_widget(self):
        return self.centralWidget()


class ConfigureRecInfoDialog(dialogs.MedusaDialog):

    def __init__(self, study_mode, rec_info, theme_colors=None):
        self.study_mode = study_mode
        self.rec_info = rec_info
        # Key layout elements
        self.rec_line_edit = None
        self.file_ext_combo_box = None
        self.path_line_edit = None
        self.study_line_edit = None
        self.subject_line_edit = None
        self.session_line_edit = None
        self.study_info_text_edit = None
        super().__init__('Configure recording info',
                         theme_colors=theme_colors)
        screen = QDesktopWidget().screenGeometry()
        width = max(screen.width() // 4, 640)
        height = max(screen.height() // 3, 360)
        self.resize(width, height)
        # Init
        self.init_layout_elements()

    def create_layout(self):
        # Main layout
        main_layout = QVBoxLayout()

        # Main params group box
        self.rec_line_edit = QLineEdit()
        self.file_ext_combo_box = QComboBox()
        self.file_ext_combo_box.addItems(['bson', 'mat', 'json'])
        self.path_line_edit = QLineEdit()
        search_action = QAction(
            gu.get_icon("search.svg", self.theme_colors), 'Search', self)
        search_action.triggered.connect(self.on_search_path)
        self.path_line_edit.addAction(search_action,
                                      QLineEdit.TrailingPosition)

        rec_params_box = QGroupBox('Recording params')
        rec_params_layout = QFormLayout()
        rec_params_layout.addRow(QLabel('Rec id'), self.rec_line_edit)
        rec_params_layout.addRow(QLabel('File ext'), self.file_ext_combo_box)
        rec_params_layout.addRow(QLabel('Path'), self.path_line_edit)
        rec_params_box.setLayout(rec_params_layout)
        main_layout.addWidget(rec_params_box)

        # Study params group box
        self.study_line_edit = QLineEdit()
        self.subject_line_edit = QLineEdit()
        self.session_line_edit = QLineEdit()
        self.study_info_text_edit = QTextEdit()

        study_params_box = QGroupBox('Study params')
        study_params_layout = QFormLayout()
        study_params_layout.addRow(QLabel('Study id'), self.study_line_edit)
        study_params_layout.addRow(QLabel('Subject id'), self.subject_line_edit)
        study_params_layout.addRow(QLabel('Session id'), self.session_line_edit)
        study_params_layout.addRow(QLabel('Study info'), self.study_info_text_edit)
        study_params_box.setLayout(study_params_layout)
        main_layout.addWidget(study_params_box)

        # Buttons
        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        buttonBox = QDialogButtonBox(QBtn)
        buttonBox.accepted.connect(self.on_accept)
        buttonBox.rejected.connect(self.on_cancel)
        main_layout.addWidget(buttonBox)

        return main_layout

    def init_layout_elements(self):
        # Set rec info
        if self.rec_info is not None:
            if self.rec_info['rec_id'] is not None:
                self.rec_line_edit.setText(self.rec_info['path'])
            if self.rec_info['file_ext'] is not None:
                for i in range(self.file_ext_combo_box.count()):
                    if self.file_ext_combo_box.itemText(i) == \
                            self.rec_info['file_ext']:
                        self.file_ext_combo_box.setCurrentIndex(i)
                        break
                self.path_line_edit.setText(self.rec_info['path'])
            if self.rec_info['path'] is not None:
                self.path_line_edit.setText(self.rec_info['path'])
            if self.rec_info['study_id'] is not None:
                self.study_line_edit.setText(self.rec_info['study_id'])
            if self.rec_info['subject_id'] is not None:
                self.subject_line_edit.setText(self.rec_info['subject_id'])
            if self.rec_info['session_id'] is not None:
                self.session_line_edit.setText(self.rec_info['session_id'])
            if self.rec_info['study_info'] is not None:
                study_info_str = json.dumps(self.rec_info['study_info'],
                                            indent=4)
                self.study_info_text_edit.setText(study_info_str)
        # Study mode
        if self.study_mode:
            self.study_line_edit.setReadOnly(True)
            self.subject_line_edit.setReadOnly(True)
            self.session_line_edit.setReadOnly(True)
            self.study_info_text_edit.setReadOnly(True)

    def on_search_path(self):
        directory = self.path_line_edit.text()
        path = QFileDialog.getExistingDirectory(caption="Recording path",
                                                directory=directory)
        if path != '':
            self.path_line_edit.setText(path)

    def get_rec_info(self):
        rec_info = dict()
        rec_info['rec_id'] = self.rec_line_edit.text()
        rec_info['file_ext'] = self.file_ext_combo_box.currentText()
        rec_info['path'] = self.path_line_edit.text()
        rec_info['study_id'] = self.study_line_edit.text()
        rec_info['subject_id'] = self.subject_line_edit.text()
        rec_info['session_id'] = self.session_line_edit.text()
        try:
            study_info = json.loads(self.study_info_text_edit.toPlainText())
        except json.JSONDecodeError as e:
            study_info = self.study_info_text_edit.toPlainText()
        rec_info['study_info'] = study_info
        print(rec_info)
        return rec_info

    def on_accept(self):
        self.rec_info = self.get_rec_info()
        self.accept()

    def on_cancel(self):
        self.rec_info = None
        self.reject()


class ConfigSessionDialog(dialogs.MedusaDialog):

    def __init__(self, apps_manager, session_plan=None,
                 theme_colors=None):
        self.apps_manager = apps_manager
        self.session_plan = session_plan
        # Key layout elements
        self.study_line_edit = None
        self.subject_line_edit = None
        self.session_line_edit = None
        self.path_line_edit = None
        self.session_plan_table = None
        super().__init__('Configure session', theme_colors=theme_colors)
        screen_geometry = self.screen().availableGeometry()
        width = max(screen_geometry.width() // 3, 640)
        height = max(screen_geometry.height() // 3, 360)
        self.resize(width, height)
        if self.session_plan is not None:
            self.session_plan_table.load_session_plan(session_plan)

    def create_layout(self):
        # Main layout
        main_layout = QVBoxLayout()
        # Session plan table
        table_layout = QHBoxLayout()
        self.session_plan_table = self.TableWidget(self.apps_manager,
                                                   self.theme_colors)
        table_layout.addWidget(self.session_plan_table)
        # Table buttons
        buttons_layout = QVBoxLayout()
        add_row_button = QToolButton()
        add_row_button.setIconSize(QSize(20, 20))
        add_row_button.setIcon(gu.get_icon("add.svg", self.theme_colors))
        add_row_button.clicked.connect(self.add_run)
        buttons_layout.addWidget(add_row_button)
        remove_row_button = QToolButton()
        remove_row_button.setIconSize(QSize(20, 20))
        remove_row_button.setIcon(gu.get_icon(
            "remove.svg", custom_color=self.theme_colors['THEME_RED']))
        remove_row_button.clicked.connect(self.remove_run)
        buttons_layout.addWidget(remove_row_button)
        save_session_button = QToolButton()
        save_session_button.setIconSize(QSize(20, 20))
        save_session_button.setIcon(gu.get_icon(
            "save_as.svg", self.theme_colors))
        save_session_button.clicked.connect(self.save_session_plan)
        buttons_layout.addWidget(save_session_button)
        spacer = QSpacerItem(0, 0, QSizePolicy.Minimum,
                             QSizePolicy.Expanding)
        buttons_layout.addItem(spacer)
        table_layout.addLayout(buttons_layout)
        main_layout.addLayout(table_layout)

        # Bottom buttons
        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        buttonBox = QDialogButtonBox(QBtn)
        buttonBox.accepted.connect(self.on_accept)
        buttonBox.rejected.connect(self.on_cancel)
        main_layout.addWidget(buttonBox)

        return main_layout

    def add_run(self):
        self.session_plan_table.add_row()

    def remove_run(self):
        self.session_plan_table.remove_row()

    def save_session_plan(self):
        session_plan = self.session_plan_table.get_session_plan()
        if not self.check_session_plan(session_plan):
            return
        self.session_plan = session_plan
        # Save file
        filt = "Session plan (*.session)"
        directory = "../config"
        file_path = QFileDialog.getSaveFileName(caption="Session plan",
                                                directory=directory,
                                                filter=filt)[0]
        if file_path != '':
            with open(file_path, 'w') as f:
                json.dump(self.session_plan, f, indent=4)

    def check_session_plan(self, session_plan):
        # todo: check rec file paths to avoid unwanted loss of information if
        #  the file already exists
        # Check app ids
        for i, run in enumerate(session_plan):
            if run['app_id'] is None:
                dialogs.error_dialog(
                    'Please, select an app in row %i' % (i + 1),
                    'Error!', theme_colors=self.theme_colors)
                return False
        return True

    def on_accept(self):
        # Get session plan and check
        session_plan = self.session_plan_table.get_session_plan()
        if not self.check_session_plan(session_plan):
            return
        self.session_plan = session_plan
        # Trigger accept event
        self.accept()

    def on_cancel(self):
        self.session_plan = None
        self.reject()

    class TableWidget(QWidget):

        def __init__(self, apps_manager, theme_colors):

            super().__init__()
            self.apps_manager = apps_manager
            self.theme_colors = theme_colors
            main_layout = QVBoxLayout()
            # Create table
            self.tableWidget = QTableWidget(self)
            self.tableWidget.setColumnCount(5)
            self.tableWidget.setHorizontalHeaderLabels(
                ['RUN ID', 'APP ID', 'SETTINGS FILE', 'MAX TIME (s)',
                 'FILE EXT'])
            self.tableWidget.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Minimum)
            self.tableWidget.horizontalHeader().setSectionResizeMode(
                QHeaderView.Stretch)
            # self.tableWidget.horizontalHeader().setSectionResizeMode(
            #     0, QHeaderView.Stretch)
            # self.tableWidget.horizontalHeader().setSectionResizeMode(
            #     1, QHeaderView.Stretch)
            self.tableWidget.setSelectionBehavior(
                QAbstractItemView.SelectRows)
            main_layout.addWidget(self.tableWidget)
            # Set layout
            self.setLayout(main_layout)

        def add_row(self, checked=None, rec_id=None, app_id=None,
                    settings_path=None, max_time=None, file_ext=None):
            row_position = self.tableWidget.rowCount()
            self.tableWidget.insertRow(row_position)
            # Add run line edit widget to col 0
            rec_line_edit = QLineEdit()
            if rec_id is None:
                rec_id = 'R%i' % row_position
            rec_line_edit.setText(rec_id)
            self.tableWidget.setCellWidget(row_position, 0, rec_line_edit)
            # Add combo box to col 1
            cond_combo_box = QComboBox()
            cond_combo_box.addItem('Selection')
            for app_info in self.apps_manager.apps_dict.values():
                opt_text = '%s (%s)' % (app_info['name'],
                                        app_info['id'])
                opt_data = app_info['id']
                cond_combo_box.addItem(opt_text, userData=opt_data)
            self.tableWidget.setCellWidget(row_position, 1, cond_combo_box)
            if app_id is not None:
                for i in range(cond_combo_box.count()):
                    if cond_combo_box.itemData(i) == app_id:
                        cond_combo_box.setCurrentIndex(i)
                        break
            # Add settings line edit widget to col 2
            settings_line_edit = QLineEdit()
            settings_line_edit.setProperty("class", "line-edit-table")
            settings_line_edit.setSizePolicy(QSizePolicy.Expanding,
                                    QSizePolicy.Expanding)
            search_action = QAction(
                gu.get_icon("search.svg", self.theme_colors), 'Search', self)
            search_action.triggered.connect(
                lambda: self.on_search_settings_file(row_position))
            settings_line_edit.addAction(search_action,
                                         QLineEdit.TrailingPosition)
            self.tableWidget.setCellWidget(row_position, 2, settings_line_edit)
            if settings_path is not None:
                settings_line_edit.setText(settings_path)
            # Add lineEdit widget to col 3
            only_int_val = QIntValidator()
            only_int_val.setRange(0, 99999)
            max_time_line_edit = QLineEdit()
            max_time_line_edit.setValidator(only_int_val)
            self.tableWidget.setCellWidget(row_position, 3, max_time_line_edit)
            if max_time is not None:
                max_time_line_edit.setText(str(max_time))
            # Add extension widget to col 4
            file_ext_combo_box = QComboBox()
            file_ext_combo_box.addItems(['bson', 'mat', 'json'])
            if file_ext is not None:
                for i in range(file_ext_combo_box.count()):
                    if file_ext_combo_box.itemText(i) == file_ext:
                        file_ext_combo_box.setCurrentIndex(i)
                        break
            self.tableWidget.setCellWidget(row_position, 4, file_ext_combo_box)

        def remove_row(self):
            row_position = self.tableWidget.currentRow()
            if row_position >= 0:
                self.tableWidget.removeRow(row_position)

        def on_search_settings_file(self, row_position):
            directory = "../config"
            file = QFileDialog.getOpenFileName(caption="App settings",
                                               directory=directory)[0]
            if file != '':
                line_edit = self.tableWidget.cellWidget(row_position, 2)
                line_edit.setText(file)

        def get_session_plan(self):
            session_plan = list()
            for i in range(self.tableWidget.rowCount()):
                # Get run id
                rec_id_line_edit = self.tableWidget.cellWidget(i, 0)
                rec_id = rec_id_line_edit.text()
                # Get app
                app_combo_box = self.tableWidget.cellWidget(i, 1)
                app_id = app_combo_box.currentData(Qt.UserRole)
                # Get settings
                settings_line_edit = self.tableWidget.cellWidget(i, 2)
                settings_path = settings_line_edit.text()
                # Max time
                max_time_line_edit = self.tableWidget.cellWidget(i, 3)
                max_time = max_time_line_edit.text()
                max_time = int(max_time) if len(max_time) > 0 else None
                # File extension
                file_ext_combo_box = self.tableWidget.cellWidget(i, 4)
                file_ext = file_ext_combo_box.currentText()
                # Append to session plan
                run = dict()
                run['rec_id'] = rec_id
                run['app_id'] = app_id
                run['settings_path'] = settings_path
                run['max_time'] = max_time
                run['file_ext'] = file_ext
                session_plan.append(run)
            return session_plan

        def load_session_plan(self, session_plan):
            for run in session_plan:
                self.add_row(rec_id=run['rec_id'],
                             app_id=run['app_id'],
                             settings_path=run['settings_path'],
                             max_time=run['max_time'],
                             file_ext=run['file_ext'])


class FakeUser(QThread):

    app_power = Signal(dict)
    app_play = Signal()
    app_stop = Signal()
    session_finished = Signal()

    def __init__(self, medusa_interface, app_state, run_state, session_plan):
        super().__init__()
        self.medusa_interface = medusa_interface
        self.app_state = app_state
        self.run_state = run_state
        self.session_plan = session_plan
        self.stop = False

    def handle_exception(self, ex):
        # Treat exception
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(
                ex, importance='unknown', scope='app',
                origin='studies_panel/studies_panel/handle_exception')
        # # Notify exception to gui main
        self.medusa_interface.error(ex)

    def run(self):
        try:
            for run in self.session_plan:
                continue_to_next_run = False
                while self.app_state.value != constants.APP_STATE_OFF:
                    # Check stop session
                    if self.stop:
                        break
                    time.sleep(0.1)
                # Check stop session
                if self.stop:
                    break
                self.app_power.emit(run)
                # Wait until the app is ON
                while self.app_state.value != constants.APP_STATE_ON:
                    # Check stop session
                    if self.stop:
                        break
                    time.sleep(0.1)
                # Check stop session
                if self.stop:
                    break
                self.app_play.emit()
                play_time = time.time()
                # Wait until the run has finished
                while self.run_state.value != constants.RUN_STATE_FINISHED:
                    # Check stop session
                    if self.stop:
                        break
                    # Check max time
                    if run['max_time'] is not None:
                        if time.time() - play_time > run['max_time']:
                            break
                    # Check manual interactions
                    if self.run_state.value == constants.RUN_STATE_STOP:
                        continue_to_next_run = True
                        break
                    time.sleep(0.1)
                # Check stop session
                if self.stop:
                    break
                if continue_to_next_run:
                    continue
                self.app_stop.emit()
                # Wait until the app is OFF
                while self.app_state.value != constants.APP_STATE_OFF:
                    # Check stop session
                    if self.stop:
                        break
                    time.sleep(0.1)
                # Check stop session
                if self.stop:
                    break

            # Wait until the app is OFF
            while self.app_state.value != constants.APP_STATE_OFF:
                time.sleep(0.1)

            self.session_finished.emit()

        except Exception as e:
            self.handle_exception(e)
            self.session_finished.emit()

    def debug_app_state(self):
        print('\nStep 0 --------')
        print('App state: %i' % self.app_state.value)
        print('Run state: %i' % self.app_state.value)


