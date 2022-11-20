# PYTHON MODULES
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

from PyQt5 import uic
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
# MEDUSA MODULES
import resources
from gui import gui_utils as gu
from gui.qt_widgets import dialogs
import constants, exceptions
from gui.qt_widgets.dialogs import ThreadProgressDialog

ui_plots_panel_widget = \
    uic.loadUiType('gui/ui_files/apps_panel_widget.ui')[0]


class AppsPanelWidget(QWidget, ui_plots_panel_widget):
    error_signal = pyqtSignal(Exception)

    def __init__(self, apps_manager, working_lsl_streams, app_state, run_state,
                 medusa_interface, apps_folder, theme_colors):
        super().__init__()
        self.is_loaded = False
        self.setupUi(self)
        # Attributes
        self.apps_manager = apps_manager
        self.working_lsl_streams = working_lsl_streams
        self.app_state = app_state
        self.run_state = run_state
        self.medusa_interface = medusa_interface
        self.apps_folder = apps_folder
        self.theme_colors = theme_colors
        self.app_process = None
        self.app_settings = None
        self.current_app_key = None
        self.progress_dialog = None

        self.set_up_tool_bar_app()
        # Set scroll area
        self.apps_panel_grid_widget = AppsPanelGridWidget(
            min_app_widget_width=110, apps_folder=self.apps_folder,
            theme_colors=theme_colors)
        self.fill_apps_panel()
        self.apps_panel_grid_widget.arrange_panel(568)
        self.scrollArea_apps = QScrollArea()
        self.scrollArea_apps.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff)
        self.scrollArea_apps.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded)
        self.scrollArea_apps.setWidget(self.apps_panel_grid_widget)
        self.scrollArea_apps.setWidgetResizable(True)
        self.verticalLayout_apps_panel.addWidget(self.scrollArea_apps)
        self.is_loaded = True

    def handle_exception(self, mds_ex):
        # Send exception to gui main
        # self.medusa_interface.error(ex)
        self.error_signal.emit(mds_ex)

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
            widget.app_about.connect(self.about_app)
            widget.app_doc.connect(self.documentation_app)
            widget.app_update.connect(self.update_app)
            widget.app_package.connect(self.package_app)
            widget.app_uninstall.connect(self.uninstall_app)

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

    def reset_tool_bar_app_buttons(self):
        # Creates QIcons for the app tool bar
        power_icon = gu.get_icon("power.svg", self.theme_colors)
        play_icon = gu.get_icon("play.svg", custom_color=self.theme_colors[
            'THEME_GREEN'])
        stop_icon = gu.get_icon("stop.svg", custom_color=self.theme_colors[
            'THEME_RED'])
        config_icon = gu.get_icon("settings.svg", self.theme_colors)
        search_icon = gu.get_icon("search.svg", self.theme_colors)
        install_icon = gu.get_icon("add.svg", self.theme_colors)

        # Set icons in buttons
        self.toolButton_app_power.setIcon(power_icon)
        self.toolButton_app_play.setIcon(play_icon)
        self.toolButton_app_stop.setIcon(stop_icon)
        self.toolButton_app_config.setIcon(config_icon)
        self.toolButton_app_search.setIcon(search_icon)
        self.toolButton_app_install.setIcon(install_icon)

        self.toolButton_app_search.setToolTip('Search apps')
        self.toolButton_app_play.setToolTip('Play')
        self.toolButton_app_stop.setToolTip('Stop')
        self.toolButton_app_power.setToolTip('Start selected app')
        self.toolButton_app_config.setToolTip('Configure selected app')
        self.toolButton_app_install.setToolTip('Install a new app')

        # Set button states
        self.toolButton_app_power.setDisabled(False)
        self.toolButton_app_play.setDisabled(True)
        self.toolButton_app_stop.setDisabled(True)

    def set_up_tool_bar_app(self):
        """ This method creates the QAction buttons displayed in the toolbar
        """
        # Set buttons icons
        self.reset_tool_bar_app_buttons()
        # Connects signals to a functions
        self.toolButton_app_power.clicked.connect(self.app_power)
        self.toolButton_app_play.clicked.connect(self.app_play)
        self.toolButton_app_stop.clicked.connect(self.app_stop)
        self.toolButton_app_config.clicked.connect(self.app_config)
        self.lineEdit_app_search.textChanged.connect(self.app_search)
        self.toolButton_app_install.clicked.connect(self.install_app)

    @exceptions.error_handler(scope='general')
    def app_power(self, checked=None):
        """ This function starts the paradigm. Once the paradigm is powered, it
        can only be stopped with stop button
        """
        # Check LSL streams
        if len(self.working_lsl_streams) == 0:
            resp = dialogs.confirmation_dialog(
                text='No LSL streams available. Do you want to continue?',
                title='No LSL streams',
                theme_colors=self.theme_colors
            )
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
                working_lsl_streams_info=ser_lsl_streams
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
            raise ValueError('Select an app to start!')
        app_settings_mdl = importlib.import_module(
            self.get_app_module(current_app_key, 'settings'))
        try:
            app_config_mdl = importlib.import_module(
                self.get_app_module(current_app_key, 'config'))
            conf_window = app_config_mdl.Config
        except ModuleNotFoundError as e:
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
    def app_search(self, checked=None):
        curr_text = self.lineEdit_app_search.text()
        self.apps_panel_grid_widget.find_app(curr_text)

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
                                               directory=directory,
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


class AppsPanelGridWidget(QWidget):

    def __init__(self, min_app_widget_width, apps_folder, theme_colors):
        super().__init__()
        # Init attributes
        self.min_app_widget_width = min_app_widget_width
        self.apps_folder = apps_folder
        self.theme_colors = theme_colors
        # Create Grid
        self.grid = QGridLayout()
        self.grid.setSpacing(2)
        # self.grid.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        # Create wrappers
        self.v_layout = QVBoxLayout()
        self.v_layout.addLayout(self.grid)
        # self.v_layout.addItem(
        #     QSpacerItem(0, 0, QSizePolicy.Ignored, QSizePolicy.Expanding))

        self.h_layout = QHBoxLayout()
        self.h_layout.addLayout(self.v_layout)
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
        self.setLayout(self.h_layout)
        # Size policy
        # self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

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
        text = text.lower()
        found_items = list()
        for item in self.items:
            app_name = item.app_params['name'].lower()
            if text in app_name:
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
    app_selected = pyqtSignal(str)
    app_about = pyqtSignal(str)
    app_doc = pyqtSignal(str)
    app_update = pyqtSignal(str)
    app_package = pyqtSignal(str)
    app_uninstall = pyqtSignal(str)

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
        # Restrictions
        self.setMinimumWidth(self.min_widget_width)
        self.setMaximumHeight(
            int(1.25 * self.min_widget_width))
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


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        # Set central widget
        # self.setMaximumWidth(200)
        self.apps_panel_widget = AppsPanelGridWidget()
        self.setCentralWidget(self.apps_panel_widget)
        self.show()


if __name__ == '__main__':
    """ Example of use of the GuiMainClass() """
    application = QApplication(sys.argv)
    main_window = MainWindow()
    sys.exit(application.exec_())
