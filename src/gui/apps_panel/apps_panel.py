# PYTHON MODULES
import sys
import json
import importlib
import glob
import time
import warnings
import os
import zipfile
import tempfile
import shutil
from datetime import datetime
# EXTERNAL MODULES
from PyQt5 import uic
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
# MEDUSA MODULES
import resources
from gui import gui_utils
from gui.qt_widgets import dialogs
import constants, exceptions


ui_plots_panel_widget = \
    uic.loadUiType('gui/ui_files/apps_panel_widget.ui')[0]


class AppsPanelWidget(QWidget, ui_plots_panel_widget):

    error_signal = pyqtSignal(Exception)

    def __init__(self, working_lsl_streams, app_state, run_state,
                 medusa_interface, theme_colors):
        super().__init__()
        self.setupUi(self)
        self.set_up_tool_bar_app()
        # Attributes
        self.working_lsl_streams = working_lsl_streams
        self.app_state = app_state
        self.run_state = run_state
        self.medusa_interface = medusa_interface
        self.theme_colors = theme_colors
        self.app_process = None
        self.app_settings = None
        self.current_app_key = None
        # Get installed apps
        self.apps_dict = None
        self.get_apps_dict()
        # Set scroll area
        self.apps_panel_grid_widget = AppsPanelGridWidget(
            min_app_widget_width=110, theme_colors=theme_colors)
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

    def handle_exception(self, ex):
        # Treat exception
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='apps_panel/apps_panel/handle_exception')
        # Notify exception to gui main
        self.medusa_interface.error(ex)

    def get_apps_dict(self):
        if os.path.isfile(constants.APPS_CONFIG_FILE):
            with open(constants.APPS_CONFIG_FILE, 'r') as f:
                self.apps_dict = json.load(f)
        else:
            self.apps_dict = {}

    def wait_until_app_closed(self, interval=0.1, timeout=1):
        success = True
        start = time.time()
        while self.app_process.is_alive():
            if time.time() - start > timeout:
                success = False
                break
            time.sleep(interval)
        return success

    def terminate_app_process(self, kill=False):
        """Terminates the app process. Kill should be True only if it is
        critical to close the app"""
        success = False
        if self.app_process is not None:
            # Try to close the app nicely
            self.app_process.close_app()
            success = self.wait_until_app_closed(interval=0.05, timeout=2)
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
        for app_key, app_params in self.apps_dict.items():
            widget = self.apps_panel_grid_widget.add_app_widget(
                app_key, app_params)
            widget.app_about.connect(self.about_app)
            widget.app_doc.connect(self.documentation_app)
            widget.app_update.connect(self.update_app)
            widget.app_uninstall.connect(self.uninstall_app)

    def update_working_lsl_streams(self, working_lsl_streams):
        self.working_lsl_streams = working_lsl_streams

    def resizeEvent(self, event):
        # w = event.size().width()
        w_scr = self.scrollArea_apps.width()
        self.apps_panel_grid_widget.arrange_panel(w_scr)

    def reset_tool_bar_app_buttons(self):
        try:
            # Creates QIcons for the app tool bar
            power_icon = QIcon("%s/icons/power_enabled_icon.png" %
                               constants.IMG_FOLDER)
            play_icon = QIcon("%s/icons/play_disabled_icon.png" %
                              constants.IMG_FOLDER)
            stop_icon = QIcon("%s/icons/stop_disabled_icon.png" %
                              constants.IMG_FOLDER)
            config_icon = QIcon("%s/icons/gear.png" % constants.IMG_FOLDER)
            search_icon = QIcon("%s/icons/search.png" % constants.IMG_FOLDER)
            install_icon = QIcon("%s/icons/plus.png" % constants.IMG_FOLDER)

            # Set icons in buttons
            self.toolButton_app_power.setIcon(power_icon)
            self.toolButton_app_play.setIcon(play_icon)
            self.toolButton_app_stop.setIcon(stop_icon)
            self.toolButton_app_config.setIcon(config_icon)
            self.toolButton_app_search.setIcon(search_icon)
            self.toolButton_app_install.setIcon(install_icon)

            self.toolButton_app_power.setToolTip('Start app run')
            self.toolButton_app_config.setToolTip('Config app run')
            self.toolButton_app_install.setToolTip('Install new app')

            # Set button states
            self.toolButton_app_power.setDisabled(False)
            self.toolButton_app_play.setDisabled(True)
            self.toolButton_app_stop.setDisabled(True)
        except Exception as e:
            self.handle_exception(e)

    def set_up_tool_bar_app(self):
        """ This method creates the QAction buttons displayed in the toolbar
        """
        try:
            # Set buttons icons
            self.reset_tool_bar_app_buttons()
            # Connects signals to a functions
            self.toolButton_app_power.clicked.connect(self.app_power)
            self.toolButton_app_play.clicked.connect(self.app_play)
            self.toolButton_app_stop.clicked.connect(self.app_stop)
            self.toolButton_app_config.clicked.connect(self.app_config)
            self.lineEdit_app_search.textChanged.connect(self.app_search)
            self.toolButton_app_install.clicked.connect(self.install_app)
        except Exception as e:
            self.handle_exception(e)

    def app_power(self):
        """ This function starts the paradigm. Once the paradigm is powered, it
        can only be stopped with stop button
        """
        try:
            # Check errors
            if len(self.working_lsl_streams) == 0:
                self.medusa_interface.log('No LSL streams available!')
                return
            # Check app selected
            current_app_key = self.apps_panel_grid_widget.get_selected_app()
            if current_app_key is None:
                raise ValueError('Select an app to start!')
            # Start app
            if self.app_state.value is constants.APP_STATE_OFF:
                # Enabling, disabling and changing the buttons in the toolbar
                self.toolButton_app_power.setDisabled(True)
                self.toolButton_app_power.setIcon(
                    QIcon("%s/icons/power_disabled_icon.png" %
                          constants.IMG_FOLDER))
                self.toolButton_app_play.setDisabled(False)
                self.toolButton_app_play.setIcon(
                    QIcon("%s/icons/play_enabled_icon.png" %
                          constants.IMG_FOLDER))
                self.toolButton_app_stop.setDisabled(False)
                self.toolButton_app_stop.setIcon(
                    QIcon("%s/icons/stop_enabled_icon.png" %
                          constants.IMG_FOLDER))
                # Get selected app modules
                app_process_mdl = importlib.import_module('apps.%s.main' %
                                                          current_app_key)
                app_settings_mdl = importlib.import_module('apps.%s.settings' %
                                                           current_app_key)
                # Get app settings
                if self.app_settings is None or \
                        not isinstance(self.app_settings,
                                       app_settings_mdl.Settings):
                    self.app_settings = app_settings_mdl.Settings()
                # Serialize working_lsl_streams
                ser_lsl_streams = [lsl_str.to_serializable_obj() for
                                   lsl_str in self.working_lsl_streams]
                # Get app extension
                with open(constants.APPS_CONFIG_FILE, 'r') as f:
                    apps_dict = json.load(f)
                ext = apps_dict[current_app_key]['extension']
                # Get app manager
                self.app_process = app_process_mdl.App(
                    app_settings=self.app_settings,
                    app_extension=ext,
                    medusa_interface=self.medusa_interface,
                    app_state=self.app_state,
                    run_state=self.run_state,
                    working_lsl_streams_info=ser_lsl_streams
                )
                self.app_process.start()
                self.run_state.value = constants.RUN_STATE_READY
                self.current_app_key = current_app_key
        except Exception as e:
            self.handle_exception(e)

    def app_play(self):
        """ Starts a run with specified settings. The run will be recorded"""
        try:
            if self.app_state.value is constants.APP_STATE_ON and \
                    self.run_state.value is not constants.RUN_STATE_FINISHED:
                if self.run_state.value is constants.RUN_STATE_READY:
                    self.run_state.value = constants.RUN_STATE_RUNNING
                    self.toolButton_app_play.setIcon(
                        QIcon("%s/icons/pause_icon.png" % constants.IMG_FOLDER))
                    # Feedback
                    self.medusa_interface.log("Run started")
                elif self.run_state.value is constants.RUN_STATE_RUNNING:
                    self.run_state.value = constants.RUN_STATE_PAUSED
                    self.toolButton_app_play.setIcon(
                        QIcon("%s/icons/play_enabled_icon.png" %
                              constants.IMG_FOLDER))
                    # Feedback
                    self.medusa_interface.log("Run paused")
                elif self.run_state.value is constants.RUN_STATE_PAUSED:
                    self.run_state.value = constants.RUN_STATE_RUNNING
                    self.toolButton_app_play.setIcon(
                        QIcon("%s/icons/pause_icon.png" % constants.IMG_FOLDER))
                    # Feedback
                    self.medusa_interface.log("Run resumed")
        except Exception as e:
            self.handle_exception(e)

    def app_stop(self):
        """ Stops the run"""
        try:
            if self.app_state.value is constants.APP_STATE_ON:
                # Change state
                self.run_state.value = constants.RUN_STATE_STOP
                # Feedback
                self.medusa_interface.log("Run stopped")
                # Enabling, disabling and changing the buttons in the toolbar
                self.toolButton_app_power.setDisabled(False)
                self.toolButton_app_power.setIcon(
                    QIcon("%s/icons/power_enabled_icon.png" %
                          constants.IMG_FOLDER))
                self.toolButton_app_play.setDisabled(True)
                self.toolButton_app_play.setIcon(
                    QIcon("%s/icons/play_disabled_icon.png" %
                          constants.IMG_FOLDER))
                self.toolButton_app_stop.setDisabled(True)
                self.toolButton_app_stop.setIcon(
                    QIcon("%s/icons/stop_disabled_icon.png" %
                          constants.IMG_FOLDER))
        except Exception as e:
            self.handle_exception(e)

    def app_config(self):
        """ Launches the config UI for the selected run """
        try:
            # Check app selected
            current_app_key = self.apps_panel_grid_widget.get_selected_app()
            if current_app_key is None:
                raise ValueError('Select an app to start!')
            app_settings_mdl = importlib.import_module('apps.%s.settings' %
                                                       current_app_key)
            try:
                app_config_mdl = importlib.import_module('apps.%s.config' %
                                                         current_app_key)
                conf_window = app_config_mdl.Config
            except ModuleNotFoundError as e:
                conf_window = resources.BasicConfigWindow
            if self.app_settings is None or not isinstance(
                    self.app_settings, app_settings_mdl.Settings):
                self.app_settings = app_settings_mdl.Settings()
            self.app_config_window = conf_window(
                self.app_settings,
                medusa_interface=self.medusa_interface,
                working_lsl_streams_info=self.working_lsl_streams
            )
            self.app_config_window.close_signal.connect(
                self.on_config_window_close_event)
        except Exception as e:
            self.handle_exception(e)

    def on_config_window_close_event(self, settings):
        """ This method is called when config window is closed. See
        on_new_settings_button_clicked function
        """
        try:
            if settings is not None:
                self.app_settings = settings
        except Exception as e:
            self.handle_exception(e)

    def app_search(self):
        try:
            curr_text = self.lineEdit_app_search.text()
            self.apps_panel_grid_widget.find_app(curr_text)
        except Exception as e:
            self.handle_exception(e)

    def install_app(self):
        # Get app file
        filt = "MEDUSA app (*.app)"
        directory = "../../"
        if not os.path.exists(directory):
            os.makedirs(directory)
        app_file = QFileDialog.getOpenFileName(caption="MEDUSA app",
                                               directory=directory,
                                               filter=filt)[0]
        # Install app (extract zip)
        with zipfile.ZipFile(app_file) as bundle:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Extract app
                bundle.extractall(temp_dir)
                with open('%s/info' % temp_dir, 'r') as f:
                    info = json.load(f)
                if info['id'] in self.apps_dict:
                    raise Exception('App %s is already installed' % info['key'])
                dest_dir = 'apps/%s' % info['id']
                shutil.move(temp_dir, dest_dir)
            # Update installed apps file
            info['installation-date'] =\
                datetime.today().strftime('%Y-%m-%d %H:%M:%S')
            self.apps_dict[info['id']] = info
            with open(constants.APPS_CONFIG_FILE, 'w') as f:
                json.dump(self.apps_dict, f, indent=4)
            # Update apps panel
            self.fill_apps_panel()
            self.apps_panel_grid_widget.arrange_panel(
                self.apps_panel_grid_widget.width())

    def about_app(self, app_key):
        dialogs.info_dialog(
            '%s' % json.dumps(self.apps_dict[app_key], indent=4),
            'About %s' % self.apps_dict[app_key]['name'], self.theme_colors)

    def documentation_app(self, app_key):
        dialogs.warning_dialog(
            'No available documentation for %s' % self.apps_dict[app_key]['name'],
            'Documentation', self.theme_colors)

    def update_app(self, app_key):
        dialogs.warning_dialog(
            'No available updates for %s' % self.apps_dict[app_key]['name'],
            'Update', self.theme_colors)

    def uninstall_app(self, app_key):
        # Confirm dialog
        if not dialogs.confirmation_dialog(
                'Are you sure you want to uninstall %s? ' %
                self.apps_dict[app_key]['name'],
                'Uninstall', self.theme_colors):
            return
        # Remove directory
        shutil.rmtree('apps/%s' % app_key)
        # Update installed apps file
        self.apps_dict.pop(app_key)
        with open(constants.APPS_CONFIG_FILE, 'w') as f:
            json.dump(self.apps_dict, f, indent=4)
        # Update apps panel
        self.fill_apps_panel()
        self.apps_panel_grid_widget.arrange_panel(
            self.apps_panel_grid_widget.width())


class AppsPanelGridWidget(QWidget):

    def __init__(self, min_app_widget_width, theme_colors):
        super().__init__()
        # Init attributes
        self.min_app_widget_width = min_app_widget_width
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
                           self.theme_colors)
        widget.app_selected.connect(self.on_app_selected)
        self.items.append(widget)
        self.n_items = len(self.items)
        return widget

    def on_app_selected(self, app_key):
        for item in self.items:
            if item.app_key == app_key:
                gui_utils.modify_property(
                    item, "background-color",
                    self.theme_colors['THEME_MENU_SELECTED'])
            else:
                gui_utils.modify_property(
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
            row, col = (row + 1, 0) if col >= self.n_cols-1 else (row, col + 1)

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
    app_uninstall = pyqtSignal(str)

    def __init__(self, min_widget_width, app_key, app_params,
                 theme_colors):
        super().__init__()
        self.min_widget_width = min_widget_width
        self.app_key = app_key
        self.app_params = app_params
        self.theme_colors = theme_colors
        self.pixmap_path = self.get_icon_path()
        self.main_layout = QVBoxLayout()
        # Icon
        self.pix_map = QPixmap(self.pixmap_path)
        self.icon = QLabel()
        self.icon.setPixmap(self.pix_map.scaledToWidth(
            int(0.75 * min_widget_width)))
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
        # gui_utils.modify_property(self, "background-color", '#00a05f')
        self.setLayout(self.main_layout)

    class AppMenu(QMenu):

        def __init__(self):
            super().__init__()
            # Create actions
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
        return 'apps/%s/icon.png' % self.app_key

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.select()
        elif event.button() == Qt.RightButton:
            menu = self.AppMenu()
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
