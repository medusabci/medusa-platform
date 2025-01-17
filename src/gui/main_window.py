# PYTHON MODULES
import glob
import os, sys
import multiprocessing as mp
import json, traceback
import ctypes
import threading
import webbrowser
import datetime
import pkg_resources

# EXTERNAL MODULES
from PySide6.QtUiTools import loadUiType
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

# MEDUSA general
import constants, resources, exceptions, accounts_manager, app_manager
import updates_manager
import utils
from gui import gui_utils as gu
from acquisition import lsl_utils
from gui.plots_panel import plots_panel
from gui.lsl_config import lsl_config
from gui.create_app import create_app
from gui.apps_panel import apps_panel
from gui.log_panel import log_panel
from gui.studies_panel import studies_panel
from gui.user_profile import login
from gui.user_profile import user_profile
from gui.qt_widgets.dialogs import *
from gui.qt_widgets.dialogs import ThreadProgressDialog

# Load the .ui file
gui_main_user_interface = loadUiType("gui/ui_files/main_window.ui")[0]


class GuiMainClass(QMainWindow, gui_main_user_interface):
    """ This class represents the main GUI of medusa. All the modules that are
    needed in the working flow are instantiated here, so this is the only class
    you have to change in order to add or change modules.
    """
    def __init__(self):
        QMainWindow.__init__(self)

        # Load versions info
        self.platform_release_info = self.get_platform_release_info()
        self.kernel_release_info = self.get_kernel_release_info()

        # Set application name so it can have its own icon
        medusaid = u'gib.medusa.' + self.platform_release_info['version']
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(medusaid)

        # Splash screen
        splash_screen = SplashScreen(self.platform_release_info)
        splash_screen.set_state(0, '')

        # ========================= PARAMS & TOOLS =========================== #
        # State constants shared across medusa. See constants.py for more info
        self.plot_state = mp.Value('i', constants.PLOT_STATE_OFF)
        self.app_state = mp.Value('i', constants.APP_STATE_OFF)
        self.run_state = mp.Value('i', constants.RUN_STATE_READY)

        # # Medusa interface
        self.interface_queue = self.MedusaInterfaceQueue()
        self.medusa_interface_listener = None
        self.set_up_medusa_interface_listener(self.interface_queue)
        self.medusa_interface = resources.MedusaInterface(self.interface_queue)

        splash_screen.set_state(25, '')

        # Load version and instantiate updates manager
        self.updates_manager = updates_manager.UpdatesManager(
            self.medusa_interface, self.platform_release_info,
            self.kernel_release_info)

        # Instantiate accounts manager
        self.accounts_manager = accounts_manager.AccountsManager()

        splash_screen.set_state(50, '')

        # ============================ GUI CONFIG ============================ #
        # Load gui config, set layout and theme
        self.screen_size = None
        self.display_size = None
        self.theme_colors = None
        self.gui_config = None
        self.setupUi(self)
        self.load_gui_config()
        self.build_layout()
        self.set_theme()

        # Reset panels
        self.lsl_config = None
        self.box_studies_panel = None
        self.studies_panel_widget = None
        self.apps_manager = None
        self.apps_panel_widget = None
        self.log_panel_widget = None
        self.plots_panel_widget = None
        self.reset_panels()

        # Menu and toolbar action initializing
        self.set_up_menu_bar_main()
        self.set_up_tool_bar_main()

        splash_screen.set_state(75, '')

        # Main window parameters
        icon = QIcon()
        icon.addPixmap('%s/medusa_task_icon.png' % constants.IMG_FOLDER)
        self.setWindowIcon(icon)
        self.setWindowTitle('MEDUSA© Platform %s [%s]' %
                            (self.platform_release_info['version'],
                             self.platform_release_info['name']))
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.set_status('Ready')
        self.set_window_config()

        splash_screen.set_state(100, '')

        # ============================== SHOW ================================ #
        # Hide splash screen and show window
        splash_screen.hide()
        self.show()
        # Set user account and check for updates
        self.set_up_user_account()

    @exceptions.error_handler(scope='general')
    def set_status(self, msg):
        """ Changes the status bar message.

        :param msg: basestring
            Status message.
        """
        self.statusBar().showMessage(msg)

    # ================================ SET UP ================================ #
    @exceptions.error_handler(scope='general')
    def build_layout(self):
        """This function builds the default layout"""
        # todo: configurable layout loaded from self.gui_config
        # Left widget
        self.widget_left_side = QWidget()
        self.widget_left_side.setLayout(QVBoxLayout())
        self.box_apps_panel = QGroupBox('APPS')
        self.box_apps_panel.setLayout(QVBoxLayout())
        self.widget_left_side.layout().addWidget(self.box_apps_panel)
        self.box_log_panel = QGroupBox('LOG')
        self.box_log_panel.setLayout(QVBoxLayout())
        self.splitter_2 = QSplitter(Qt.Orientation.Vertical)
        self.splitter_2.addWidget(self.box_apps_panel)
        self.splitter_2.addWidget(self.box_log_panel)
        self.widget_left_side.layout().addWidget(self.splitter_2)
        # Right widget
        self.widget_right_side = QWidget()
        self.widget_right_side.setLayout(QVBoxLayout())
        self.box_plots_panel = QGroupBox('REAL TIME PLOTS')
        self.box_plots_panel.setLayout(QVBoxLayout())
        self.widget_right_side.layout().addWidget(self.box_plots_panel)
        # Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.widget_left_side)
        self.splitter.addWidget(self.widget_right_side)
        # Add to main window
        self.setCentralWidget(self.splitter)

    @exceptions.error_handler(scope='general')
    def load_gui_config(self):
        # Get display environment
        current_screen = self.screen()
        screen_size = current_screen.availableGeometry().size()
        self.screen_size = [screen_size.width(), screen_size.height()]
        self.display_size = [0, 0]
        for screen in QApplication.instance().screens():
            screen_size = screen.geometry().size()
            self.display_size[0] += screen_size.width()
            self.display_size[1] += screen_size.height()

        # Load gui config
        gui_config_file_path = self.accounts_manager.wrap_path(
            constants.GUI_CONFIG_FILE)
        if os.path.isfile(gui_config_file_path):
            with open(gui_config_file_path, 'r') as f:
                self.gui_config = json.load(f)
                # todo: check config file , it can be corrupted (e.g., missing
                #  keys, incorrect values, etc)
                gui_config_fielfs = ['width', 'height', 'position',
                                     'splitter_ratio', 'splitter_2_ratio',
                                     'maximized', 'study_mode', 'theme']
                if not all(name in self.gui_config
                           for name in gui_config_fielfs):
                    # Corrupted gui_config.json file
                    self.set_default_gui_config()
                    raise exceptions.IncorrectSettingsConfig(
                        'Corrupted file gui_config.json. '
                        'Switching to default configuration.')
        else:
            self.set_default_gui_config()

    def set_default_gui_config(self):
        # Default configuration
        self.gui_config = dict()
        # Default window sizes
        self.gui_config['width'] = int(self.screen_size[0] * 0.75)
        self.gui_config['height'] = int(self.screen_size[1] * 0.75)
        self.gui_config['position'] = \
            [int(self.screen_size[0] * 0.125),
             int(self.screen_size[1] * 0.125)]
        self.gui_config['splitter_ratio'] = [0.36, 0.64]
        self.gui_config['splitter_2_ratio'] = [0.28, 0.72]
        self.gui_config['maximized'] = False
        self.gui_config['screen_idx'] = 0
        # Study mode
        self.gui_config['study_mode'] = False
        # Default theme
        self.gui_config['theme'] = 'dark'

    @exceptions.error_handler(scope='general')
    def save_gui_config(self):
        # Update values
        self.gui_config['width'] = self.width()
        self.gui_config['height'] = self.height()
        self.gui_config['splitter_ratio'] = [
            s/sum(self.splitter.sizes()) for s in self.splitter.sizes()]
        self.gui_config['splitter_2_ratio'] = [
            s/sum(self.splitter_2.sizes()) for s in self.splitter_2.sizes()]
        self.gui_config['position'] = [self.pos().x(), self.pos().y()]
        self.gui_config['maximized'] = self.isMaximized()
        self.gui_config['screen_idx'] = len(QApplication.instance().screens())
        # Save config
        gui_config_file_path = self.accounts_manager.wrap_path(
            constants.GUI_CONFIG_FILE)
        with open(gui_config_file_path, 'w') as f:
            json.dump(self.gui_config, f, indent=4)

    @exceptions.error_handler(scope='general')
    def set_theme(self):
        self.theme_colors = gu.get_theme_colors(self.gui_config['theme'])
        gu.set_css_and_theme(self, self.theme_colors)

    @exceptions.error_handler(scope='general')
    def set_window_config(self):
        # Define size and splitters
        self.resize(self.gui_config['width'], self.gui_config['height'])
        self.splitter.setSizes(
            [int(r * self.gui_config['width'])
             for r in self.gui_config['splitter_ratio']]
        )
        self.splitter_2.setSizes(
            [int(r * self.gui_config['height'])
             for r in self.gui_config['splitter_2_ratio']]
        )
        if self.gui_config['position'][0] < self.display_size[0] and \
                self.gui_config['position'][1] < self.display_size[1]:
            self.move(self.gui_config['position'][0],
                      self.gui_config['position'][1])
        if self.gui_config['maximized']:
            self.showMaximized()

    @exceptions.error_handler(scope='general')
    def reset_panels(self):
        # Log panel (set up first in case is used in other functions)
        self.set_up_log_panel()
        # LSL config
        self.set_up_lsl_config()
        # Apps panel
        self.apps_manager = app_manager.AppManager(
            self.accounts_manager, self.medusa_interface,
            self.platform_release_info)
        self.set_up_apps_panel()
        # Studies panel
        self.set_up_studies_panel()
        # Plots dashboard
        self.set_up_plots_panel()

    def check_updates(self, exclude_prereleases=True):

        # Check for available updates of MEDUSA Platform
        platform_update, platform_rejected, latest_version_info = \
            self.updates_manager.check_for_medusa_platform_updates(
                exclude_prereleases=exclude_prereleases)
        if platform_update:
            # Initialize progress dialog
            self.progress_dialog = ThreadProgressDialog(
                window_title='Updating MEDUSA\u00A9 Platform...',
                min_pbar_value=0, max_pbar_value=100,
                theme_colors=self.theme_colors)
            self.progress_dialog.done.connect(self.update_finished)
            self.progress_dialog.show()

            th = threading.Thread(
                target=self.updates_manager.update_platform,
                args=(latest_version_info, self.progress_dialog))
            th.start()
        # Check for available updates of MEDUSA Kernel
        kernel_update, kernel_rejected, latest_version_info = \
            self.updates_manager.check_for_medusa_kernel_updates(
                exclude_prereleases=exclude_prereleases)
        if kernel_update:
            # Initialize progress dialog
            self.progress_dialog = ThreadProgressDialog(
                window_title='Updating MEDUSA\u00A9 Kernel...',
                min_pbar_value=0, max_pbar_value=100,
                theme_colors=self.theme_colors)
            self.progress_dialog.done.connect(self.update_finished)
            self.progress_dialog.show()

            th = threading.Thread(
                target=self.updates_manager.update_kernel,
                args=('medusa-kernel==%s' % latest_version_info,
                      self.progress_dialog))
            th.start()
        return platform_update, platform_rejected, kernel_update, kernel_rejected

    @exceptions.error_handler(scope='general')
    def update_finished(self):
        utils.restart()

    @exceptions.error_handler(scope='general')
    def set_up_medusa_interface_listener(self, interface_queue):
        self.medusa_interface_listener = self.MedusaInterfaceListener(
            interface_queue)
        self.medusa_interface_listener.msg_signal.connect(
            self.print_log)
        self.medusa_interface_listener.exception_signal.connect(
            self.handle_exception)
        self.medusa_interface_listener.app_state_changed_signal.connect(
            self.on_app_state_changed)
        self.medusa_interface_listener.run_state_changed_signal.connect(
            self.on_run_state_changed)
        self.medusa_interface_listener.start()

    @exceptions.error_handler(scope='general')
    def set_up_studies_panel(self):
        # Add widget if study mode is on
        if self.gui_config['study_mode']:
            # Avoid multiple instances of the studies panel
            if self.box_studies_panel is not None:
                return
            # Group box
            self.box_studies_panel = QGroupBox('STUDIES')
            self.box_studies_panel.setLayout(QVBoxLayout())
            self.splitter_2.insertWidget(0, self.box_studies_panel)
            if len(self.gui_config['splitter_2_ratio']) != 3:
                self.gui_config['splitter_2_ratio'] = [0.25, 0.25, 0.5]
                self.splitter_2.setSizes(
                    [int(r * self.gui_config['height'])
                     for r in self.gui_config['splitter_2_ratio']])
            # Panel widget
            self.studies_panel_widget = studies_panel.StudiesPanelWidget(
                self.medusa_interface,
                self.accounts_manager.wrap_path(constants.STUDIES_CONFIG_FILE),
                self.theme_colors)
            self.studies_panel_widget.selection_signal.connect(
                self.on_studies_panel_selection)
            # Clear layout
            # while self.box_studies_panel.layout().count():
            #     child = self.box_studies_panel.layout().takeAt(0)
            #     if child.widget():
            #         child.widget().deleteLater()
            # Add widget
            self.box_studies_panel.layout().addWidget(self.studies_panel_widget)
            self.box_studies_panel.layout().setContentsMargins(0, 0, 0, 0)
            # Connect external actions
            self.studies_panel_widget.toolButton_studies_undock.clicked.connect(
                self.undock_studies_panel)
        else:
            # Clear layout
            if self.box_studies_panel is not None:
                self.box_studies_panel.deleteLater()
                self.box_studies_panel = None
        self.update_menu_action_study_mode()

    @exceptions.error_handler(scope='general')
    def on_studies_panel_selection(self):
        """Updates the study info. This function is called when there is a
        selection on the studies panel."""
        # Get selection information
        selected_item_type = self.studies_panel_widget.selected_item_type
        selected_item_tree = self.studies_panel_widget.selected_item_tree
        # Pass this information to the apps panel
        study = selected_item_tree[0] if len(selected_item_tree) > 0 else \
            {'item_name': None, 'item_data': None}
        subject = selected_item_tree[1] if len(selected_item_tree) > 1 else \
            {'item_name': None, 'item_data': None}
        session = selected_item_tree[2] if len(selected_item_tree) > 2 else \
            {'item_name': None, 'item_data': None}
        path = self.studies_panel_widget.get_element_dir(
            self.studies_panel_widget.studies_panel_config['root_path'],
            self.studies_panel_widget.selected_item_tree)
        # Set rec_info
        rec_info = self.apps_panel_widget.get_default_rec_info()
        rec_info['path'] = path
        rec_info['study_id'] = study['item_name']
        rec_info['subject_id'] = subject['item_name']
        rec_info['session_id'] = session['item_name']
        # Specific info, available only in study mode
        rec_info['study_info'] = {
            'selected_item_type': selected_item_type,
            'study_data': study['item_data'],
            'subject_data': subject['item_data'],
            'session_data': session['item_data'],
        }
        self.apps_panel_widget.set_rec_info(rec_info)

    @exceptions.error_handler(scope='general')
    def set_up_log_panel(self):
        # Instantiate Log layout
        self.log_panel_widget = log_panel.LogPanelWidget(
            self.medusa_interface,
            self.theme_colors)
        # Clear layout
        while self.box_log_panel.layout().count():
            child = self.box_log_panel.layout().takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        # Add widget
        self.box_log_panel.layout().addWidget(self.log_panel_widget)
        self.box_log_panel.layout().setContentsMargins(0, 0, 0, 0)
        # Connect external actions
        self.log_panel_widget.toolButton_log_undock.clicked.connect(
            self.undock_log_panel)

    @exceptions.error_handler(scope='general')
    def set_up_lsl_config(self):
        lsl_config_file_path = self.accounts_manager.wrap_path(
                constants.LSL_CONFIG_FILE)
        # Load last config (if available)
        working_lsl_streams = list()
        if os.path.isfile(lsl_config_file_path):
            try:
                with open(lsl_config_file_path, 'r') as f:
                    self.lsl_config = json.load(f)
                last_streams_info = self.lsl_config['working_streams']
                for lsl_stream_info_dict in last_streams_info:
                    try:
                        lsl_stream = \
                            lsl_utils.LSLStreamWrapper.from_serializable_obj(
                                lsl_stream_info_dict,
                                weak_search=self.lsl_config['weak_search'])
                        # Check uid
                        if not lsl_utils.check_if_medusa_uid_is_available(
                                working_lsl_streams, lsl_stream.medusa_uid):
                            error_dialog(
                                'Incorrect LSL configuration with duplicated '
                                'LSL stream UID %s. MEDUSA LSL UIDs must be '
                                'unique. Please reconfigure LSL.' %
                                lsl_stream.medusa_uid,
                                'Incorrect MEDUSA LSL UID')
                            working_lsl_streams = list()
                            break
                        working_lsl_streams.append(lsl_stream)
                        self.print_log('Connected to LSL stream: %s' %
                                       lsl_stream.medusa_uid)
                    except exceptions.LSLStreamNotFound as e:
                        self.print_log('No match for LSL stream "%s"' %
                                       lsl_stream_info_dict['medusa_uid'],
                                       style='warning')
                        # raise exceptions.MedusaException(
                        #     e, scope='acquisition', importance='mild')
                        continue
                    except exceptions.UnspecificLSLStreamInfo as e:
                        self.print_log('%s. Disable weak LSL search to avoid '
                                       'this error' % str(e), style='error')
                        continue
                self.lsl_config['working_streams'] = working_lsl_streams
            except Exception as e:
                # Message
                self.print_log('The LSL configuration file might be corrupted. '
                               'The reason might be an external modification '
                               'or a software update. Please, reconfigure.',
                               style='error')
                # Default configuration
                self.lsl_config = dict()
                self.lsl_config['weak_search'] = False
                self.lsl_config['working_streams'] = list()
        else:
            # Default configuration
            self.lsl_config = dict()
            self.lsl_config['weak_search'] = False
            self.lsl_config['working_streams'] = list()
        # Update menu action
        self.update_menu_action_lsl_search_mode()

    @exceptions.error_handler(scope='general')
    def set_up_apps_panel(self):
        self.apps_panel_widget = apps_panel.AppsPanelWidget(
            self.apps_manager,
            self.lsl_config['working_streams'],
            self.app_state,
            self.run_state,
            self.medusa_interface,
            self.accounts_manager.wrap_path('apps'),
            self.gui_config['study_mode'],
            self.theme_colors)
        # Connect signals
        self.apps_panel_widget.error_signal.connect(
            self.handle_exception)
        # Clear layout
        while self.box_apps_panel.layout().count():
            child = self.box_apps_panel.layout().takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        # Add widget
        self.box_apps_panel.layout().addWidget(self.apps_panel_widget)
        self.box_apps_panel.layout().setContentsMargins(0, 0, 0, 0)
        # Connect external actions
        self.apps_panel_widget.toolButton_app_undock.clicked.connect(
            self.undock_apps_panel)

    @exceptions.error_handler(scope='general')
    def set_up_plots_panel(self):
        # Create widget
        self.plots_panel_widget = plots_panel.PlotsPanelWidget(
            self.lsl_config,
            self.plot_state,
            self.medusa_interface,
            self.accounts_manager.wrap_path(constants.PLOTS_CONFIG_FILE),
            self.theme_colors)
        # Clear layout
        while self.box_plots_panel.layout().count():
            child = self.box_plots_panel.layout().takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        # Add widget
        self.box_plots_panel.layout().addWidget(self.plots_panel_widget)
        self.box_plots_panel.layout().setContentsMargins(0, 0, 0, 0)
        # Connect external actions
        self.plots_panel_widget.toolButton_plot_undock.clicked.connect(
            self.undock_plots_panel)

    def set_up_user_account(self):
        # Check session
        if not self.accounts_manager.check_session():
            self.open_login_window()
        else:
            self.check_updates()

    def keyPressEvent(self, key_event):
        # TODO: define some shortcuts
        # Receive the key in decimal ASCII
        # d_key = key_event.key()
        # self.print_log(d_key, style={'color': 'green'})
        pass

    @staticmethod
    def get_platform_release_info():
        try:
            with open('../version', 'r') as f:
                release_info = json.load(f)
        except Exception as e:
            release_info = {
                'date': str(datetime.date.today()),
                'tag_name': 'Dev.0.0',
                'version': 'Dev',
                'major_patch': 0,
                'minor_patch': 0,
                'name': 'Development',
            }
        return release_info

    @staticmethod
    def get_kernel_release_info():
        kernel_version = utils.get_python_package_version('medusa-kernel')
        kernel_version_split = kernel_version.split('.')
        release_info = dict()
        release_info['tag_name'] = kernel_version
        release_info['version'] = kernel_version_split[0]
        release_info['major_patch'] = kernel_version_split[1]
        release_info['minor_patch'] = kernel_version_split[2]
        return release_info

    # =============================== MENU BAR =============================== #
    @exceptions.error_handler(scope='general')
    def set_up_menu_bar_main(self):
        # Preferences
        # TODO: menuAction_view_integrated, menuAction_view_split
        # self.menuAction_color_dark.triggered.connect(
        #     self.set_dark_theme)
        # self.menuAction_color_light.triggered.connect(
        #     self.set_light_theme)
        self.menuAction_study_mode.triggered.connect(
            self.change_study_mode)
        # Lab streaming layer
        self.menuAction_lsl_doc.triggered.connect(
            self.open_lsl_doc)
        self.menuAction_lsl_repo.triggered.connect(
            self.open_lsl_repo)
        self.menuAction_lsl_settings.triggered.connect(
            self.open_lsl_config_window)
        self.menuAction_weak_search.triggered.connect(
            self.change_lsl_search_mode
        )
        # Developer tools
        self.menuAction_dev_tutorial.triggered.connect(
            self.open_dev_tutorial)
        self.menuAction_dev_create_app.triggered.connect(
            self.create_app_config_window)
        # Help
        self.menuAction_help_tutorials.triggered.connect(
            self.open_help_tutorials)
        self.menuAction_help_forum.triggered.connect(self.open_help_forum)
        self.menuAction_help_bugs.triggered.connect(self.open_help_bugs)
        self.menuAction_help_updates.triggered.connect(self.open_help_updates)
        self.menuAction_help_about.triggered.connect(self.open_help_about)

    # ============================== PREFERENCES ============================= #
    def set_dark_theme(self):
        self.gui_config['theme'] = 'dark'
        self.set_theme()
        self.reset_panels()

    def set_light_theme(self):
        self.gui_config['theme'] = 'light'
        self.set_theme()
        self.reset_panels()

    @exceptions.error_handler(scope='general')
    def change_study_mode(self, checked=None):
        self.gui_config['study_mode'] = not self.gui_config['study_mode']
        # Insert studies box and update apps panel
        self.set_up_studies_panel()
        self.apps_panel_widget.study_mode = self.gui_config['study_mode']
        rec_info = self.apps_panel_widget.get_default_rec_info()
        self.apps_panel_widget.set_rec_info(rec_info)

    @exceptions.error_handler(scope='general')
    def update_menu_action_study_mode(self):
        if self.gui_config['study_mode']:
            self.menuAction_study_mode.setText('Disable study mode')
        else:
            self.menuAction_study_mode.setText('Activate study mode')

    # =============================== TOOL BAR =============================== #
    @exceptions.error_handler(scope='general')
    def reset_tool_bar_main(self):
        # Create QAction buttons
        lsl_config_icon = gu.get_icon("link.svg", self.theme_colors)
        plots_icon = gu.get_icon("waves.svg", self.theme_colors)
        profile_icon = gu.get_icon("person.svg", self.theme_colors)
        # Create QToolButton
        self.toolButton_lsl_config.setIcon(lsl_config_icon)
        self.toolButton_lsl_config.setToolTip('Configure LSL streams')
        self.toolButton_profile.setIcon(profile_icon)
        self.toolButton_profile.setToolTip('User profile')
        # self.toolButton_analyzer.setIcon(plots_icon)
        # self.toolButton_analyzer.setToolTip('MEDUSA Analyzer')

    @exceptions.error_handler(scope='general')
    def set_up_tool_bar_main(self):
        # Create lsl config button
        self.toolButton_lsl_config = QToolButton(self.toolBar)
        self.setProperty("class", "main-toolbar-button")
        self.toolButton_lsl_config.clicked.connect(self.open_lsl_config_window)
        # Create plots button
        # self.toolButton_analyzer = QToolButton(self.toolBar)
        # self.setProperty("class", "main-toolbar-button")
        # self.toolButton_analyzer.clicked.connect(self.open_analyzer_window)
        # Create profile button
        self.toolButton_profile = QToolButton(self.toolBar)
        self.setProperty("class", "main-toolbar-button")
        self.toolButton_profile.clicked.connect(self.open_account_window)
        # Create spacer widget
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Add QActions to QToolBar
        self.toolBar.addWidget(self.toolButton_lsl_config)
        # self.toolBar.addWidget(self.toolButton_analyzer)
        self.toolBar.addWidget(spacer)
        self.toolBar.addWidget(self.toolButton_profile)
        # Set default
        self.reset_tool_bar_main()

    @exceptions.error_handler(scope='general')
    def open_analyzer_window(self):
        raise NotImplementedError('This functionality is still under '
                                  'development!')

    @exceptions.error_handler(scope='general')
    def open_account_window(self):
        if not self.accounts_manager.check_session():
            self.open_login_window()
        else:
            self.open_user_profile_window()

    # =========================== USER ACCOUNT =============================== #
    def open_login_window(self):
        # Login
        self.login_window = login.LoginDialog(
            user_session=self.accounts_manager.current_session,
            theme_colors=self.theme_colors)
        # Connect signals
        self.login_window.error_signal.connect(self.handle_exception)
        # Block execution
        self.login_window.exec()
        # Login actions
        if self.login_window.success:
            self.accounts_manager.on_login()
            self.reset_panels()
            self.check_updates()
        else:
            self.close()

    def open_user_profile_window(self):
        self.user_profile_window = user_profile.UserProfileDialog(
            user_session=self.accounts_manager.current_session,
            theme_colors=self.theme_colors)
        self.user_profile_window.error_signal.connect(self.handle_exception)
        self.user_profile_window.logout_signal.connect(self.on_user_logout)
        self.user_profile_window.delete_signal.connect(self.on_user_delete)
        self.user_profile_window.exec()

    def on_user_logout(self):
        self.accounts_manager.on_logout()
        self.open_login_window()

    def on_user_delete(self):
        try:
            self.accounts_manager.on_delete_account()
        except PermissionError as e:
            error_dialog(message='MEDUSA does not have permission to perform '
                                 'this operation. Try to run as administrator',
                         title='Permission error!',
                         theme_colors=self.theme_colors)
        self.open_login_window()

    # ======================== LAB-STREAMING LAYER =========================== #
    @exceptions.error_handler(scope='general')
    def open_lsl_doc(self, checked=None):
        return webbrowser.open(
            'https://labstreaminglayer.readthedocs.io/info/intro.html')

    @exceptions.error_handler(scope='general')
    def open_lsl_repo(self, checked=None):
        return webbrowser.open(
            'https://github.com/sccn/labstreaminglayer/')

    @exceptions.error_handler(scope='general')
    def open_lsl_config_window(self, checked=None):
        self.lsl_config_window = \
            lsl_config.LSLConfigDialog(
                self.lsl_config,
                self.accounts_manager.wrap_path(constants.LSL_CONFIG_FILE),
                theme_colors=self.theme_colors)
        self.lsl_config_window.accepted.connect(self.set_lsl_streams)
        self.lsl_config_window.rejected.connect(self.reset_lsl_streams)

    @exceptions.error_handler(scope='general')
    def change_lsl_search_mode(self, checked=None):
        self.lsl_config['weak_search'] = not self.lsl_config['weak_search']
        # Load current lsl config
        lsl_config_file_path = self.accounts_manager.wrap_path(
            constants.LSL_CONFIG_FILE)
        # Load last config (if available) and update only weak search field
        if os.path.isfile(lsl_config_file_path):
            with open(lsl_config_file_path, 'r') as f:
                last_lsl_config = json.load(f)
            last_lsl_config['weak_search'] = self.lsl_config['weak_search']
            with open(lsl_config_file_path, 'w') as f:
                json.dump(last_lsl_config, f, indent=4)
        else:
            with open(lsl_config_file_path, 'w') as f:
                json.dump(self.lsl_config, f, indent=4)
        self.update_menu_action_lsl_search_mode()

    @exceptions.error_handler(scope='general')
    def update_menu_action_lsl_search_mode(self):
        if self.lsl_config['weak_search']:
            self.menuAction_weak_search.setText('Disable weak search')
        else:
            self.menuAction_weak_search.setText('Activate weak search')

    @exceptions.error_handler(scope='general')
    def set_lsl_streams(self):
        # Set working streamsicon.png
        self.lsl_config = self.lsl_config_window.lsl_config
        # Update the working streams within the panels
        self.plots_panel_widget.update_lsl_config(
            self.lsl_config)
        self.apps_panel_widget.update_working_lsl_streams(
            self.lsl_config['working_streams'])
        # Print log info
        for lsl_stream_info in self.lsl_config['working_streams']:
            self.print_log('Connected to LSL stream: %s' %
                           lsl_stream_info.medusa_uid)

    @exceptions.error_handler(scope='general')
    def reset_lsl_streams(self):
        pass

    # ========================= DEVELOPER TOOLS ============================== #
    @exceptions.error_handler(scope='general')
    def open_dev_tutorial(self, checked=None):
        return webbrowser.open(
            'https://www.medusabci.com/solutions/get-started/#create-app')

    @exceptions.error_handler(scope='general')
    def create_app_config_window(self, checked=None):
        self.create_app_window = \
            create_app.CreateAppDialog(self.apps_manager,
                                       theme_colors=self.theme_colors)
        self.create_app_window.accepted.connect(self.update_apps_panel)

    @exceptions.error_handler(scope='general')
    def update_apps_panel(self):
        self.apps_panel_widget.update_apps_panel()

    # ========================= HELP ============================== #
    @exceptions.error_handler(scope='general')
    def open_help_tutorials(self, checked=None):
        return webbrowser.open(
            'https://www.medusabci.com/solutions/get-started/')

    @exceptions.error_handler(scope='general')
    def open_help_forum(self, checked=None):
        return webbrowser.open('https://discord.gg/G8dWPXtBsC')

    @exceptions.error_handler(scope='general')
    def open_help_bugs(self, checked=None):
        return webbrowser.open(
            'https://github.com/medusabci/medusa-platform/issues/')

    @exceptions.error_handler(scope='general')
    def open_help_updates(self, checked=None):
        check, exclude_prereleases = \
            self.updates_manager.show_check_for_updates_dialog()
        if check:
            res = self.check_updates(exclude_prereleases=exclude_prereleases)
            if all(not item for item in res):
                info_dialog('There are no available updates for MEDUSA\u00A9 '
                            '%s. Check our website to find more recent '
                            'versions' % self.platform_release_info['version'],
                            'No updates', theme_colors=self.theme_colors)
                return webbrowser.open(
                    'https://www.medusabci.com/solutions/medusa-platform/')

    @exceptions.error_handler(scope='general')
    def open_help_about(self, checked=None):
        dialog = AboutDialog(
            alias=self.accounts_manager.current_session.user_info['alias'],
            release_info=self.platform_release_info
        )
        dialog.exec()

    # ====================== APPS PANEL FUNCTIONS ======================== #

    @exceptions.error_handler(scope='general')
    def undock_apps_panel(self, checked=None):
        if not self.apps_panel_widget.undocked:
            # Get current dimensions
            window_height = self.height()
            apps_panel_width = self.apps_panel_widget.width()
            # Create main window
            self.apps_panel_window = apps_panel.AppsPanelWindow(
                self.apps_panel_widget, self.theme_colors,
                width=apps_panel_width, height=window_height)
            self.apps_panel_widget.set_undocked(True)
            self.apps_panel_window.close_signal.connect(
                self.dock_apps_panel)
            # Delete group box
            self.box_apps_panel.deleteLater()
        else:
            self.apps_panel_window.close()

    @exceptions.error_handler(scope='general')
    def dock_apps_panel(self, checked=None):
        # Update state
        self.apps_panel_widget.set_undocked(False)
        # Add widget
        self.box_apps_panel = QGroupBox('APPS')
        self.box_apps_panel.setLayout(QVBoxLayout())
        self.box_apps_panel.layout().addWidget(self.apps_panel_widget)
        self.box_apps_panel.layout().setContentsMargins(0, 0, 0, 0)
        self.splitter_2.insertWidget(self.splitter_2.count()-1,
                                     self.box_apps_panel)
        self.splitter_2.setSizes(
            [int(r * self.gui_config['height'])
             for r in self.gui_config['splitter_2_ratio']]
        )

    # ======================= PLOTS PANEL FUNCTIONS ========================== #
    @exceptions.error_handler(scope='general')
    def undock_plots_panel(self, checked=None):
        if not self.plots_panel_widget.undocked:
            # Get current dimensions
            window_height = self.height()
            plots_panel_width = self.plots_panel_widget.width()
            # Create new window
            self.plots_panel_window = plots_panel.PlotsPanelWindow(
                self.plots_panel_widget, self.theme_colors,
                plots_panel_width, window_height
            )
            self.plots_panel_widget.set_undocked(True)
            self.plots_panel_window.close_signal.connect(
                self.dock_plots_panel)
            # Delete group box
            self.box_plots_panel.deleteLater()
            self.widget_right_side.deleteLater()
        else:
            self.plots_panel_window.close()

    @exceptions.error_handler(scope='general')
    def dock_plots_panel(self, checked=None):
        # Update state
        self.plots_panel_widget.set_undocked(False)
        # Add widget
        self.widget_right_side = QWidget()
        self.widget_right_side.setLayout(QVBoxLayout())
        self.box_plots_panel = QGroupBox('REAL TIME PLOTS')
        self.box_plots_panel.setLayout(QVBoxLayout())
        self.widget_right_side.layout().addWidget(self.box_plots_panel)
        self.box_plots_panel.layout().addWidget(self.plots_panel_widget)
        self.box_plots_panel.layout().setContentsMargins(0, 0, 0, 0)
        self.splitter.insertWidget(self.splitter.count(), self.box_plots_panel)
        self.splitter.setSizes(
            [int(r * self.gui_config['width'])
             for r in self.gui_config['splitter_ratio']]
        )

    # ======================== LOG PANEL FUNCTIONS =========================== #
    @exceptions.error_handler(scope='general')
    def undock_log_panel(self, checked=None):
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
            # Delete group box
            self.box_log_panel.deleteLater()
        else:
            self.log_panel_window.close()

    @exceptions.error_handler(scope='general')
    def dock_log_panel(self, checked=None):
        # Update state
        self.log_panel_widget.set_undocked(False)
        # Add widget
        self.box_log_panel = QGroupBox('LOG')
        self.box_log_panel.setLayout(QVBoxLayout())
        self.box_log_panel.layout().addWidget(self.log_panel_widget)
        self.box_log_panel.layout().setContentsMargins(0, 0, 0, 0)
        self.splitter_2.insertWidget(self.splitter_2.count(),
                                     self.box_log_panel)
        self.splitter_2.setSizes(
            [int(r * self.gui_config['height'])
             for r in self.gui_config['splitter_2_ratio']]
        )

    # ====================== STUDIES PANEL FUNCTIONS ========================= #
    @exceptions.error_handler(scope='general')
    def undock_studies_panel(self, checked=None):
        if not self.studies_panel_widget.undocked:
            # Get current dimensions
            window_height = self.height()
            studies_panel_width = self.apps_panel_widget.width()
            # Create main window
            self.studies_panel_window = studies_panel.StudiesPanelWindow(
                self.studies_panel_widget, self.theme_colors,
                width=studies_panel_width, height=window_height)
            self.studies_panel_widget.set_undocked(True)
            self.studies_panel_window.close_signal.connect(
                self.dock_studies_panel)
            # Delete group box
            self.box_studies_panel.deleteLater()
        else:
            self.studies_panel_window.close()

    @exceptions.error_handler(scope='general')
    def dock_studies_panel(self, checked=None):
        # Update state
        self.studies_panel_widget.set_undocked(False)
        # Add box and widget
        self.box_studies_panel = QGroupBox('STUDIES')
        self.box_studies_panel.setLayout(QVBoxLayout())
        self.box_studies_panel.layout().addWidget(self.studies_panel_widget)
        self.box_studies_panel.layout().setContentsMargins(0, 0, 0, 0)
        self.splitter_2.insertWidget(0, self.box_studies_panel)
        self.splitter_2.setSizes(
            [int(r * self.gui_config['height'])
             for r in self.gui_config['splitter_2_ratio']]
        )

    # ========================== OTHER FUNCTIONS ============================= #
    @exceptions.error_handler(scope='general')
    def on_app_state_changed(self, app_state_value):
        """Called by MedusaInterfaceListener when it receives an
        app_state_changed message
        """
        if app_state_value == constants.APP_STATE_OFF:
            # Check impossible transitions
            if app_state_value == constants.APP_STATE_POWERING_OFF:
                ex = ValueError('Impossible state transition from '
                                'APP_STATE_OFF to APP_STATE_POWERING_OFF!')
                raise exceptions.MedusaException(ex)
            self.app_state.value = app_state_value
            self.apps_panel_widget.reset_tool_bar_app_buttons()
            self.on_run_state_changed(constants.RUN_STATE_READY)
            self.set_status('Ready')
            print('[GUiMain.on_app_state_changed]: APP_STATE_OFF')
        elif app_state_value == constants.APP_STATE_POWERING_ON:
            self.app_state.value = app_state_value
            self.set_status('Powering on...')
            print('[GUiMain.on_app_state_changed]: APP_STATE_POWERING_ON')
        elif app_state_value == constants.APP_STATE_POWERING_OFF:
            self.app_state.value = app_state_value
            self.set_status('Powering off...')
            print('[GUiMain.on_app_state_changed]: APP_STATE_POWERING_OFF')
        elif app_state_value == constants.APP_STATE_ON:
            if app_state_value == constants.APP_STATE_POWERING_ON:
                ex = ValueError('Impossible state transition from APP_STATE_ON '
                                'to APP_STATE_POWERING_ON!')
                raise exceptions.MedusaException(ex)
            self.app_state.value = app_state_value
            self.set_status('Running')
            print('[GUiMain.on_app_state_changed]: APP_STATE_ON')
        else:
            raise ValueError('Unknown app state: %s' %
                             str(self.app_state.value))

    @exceptions.error_handler(scope='general')
    def on_run_state_changed(self, run_state_value):
        """Called by MedusaInterfaceListener when it receives a
        run_state_changed message
        """
        if run_state_value == constants.RUN_STATE_READY:
            self.run_state.value = run_state_value
            print('[GUiMain.on_run_state_changed]: RUN_STATE_READY')
        elif run_state_value == constants.RUN_STATE_RUNNING:
            self.run_state.value = run_state_value
            print('[GUiMain.on_run_state_changed]: RUN_STATE_RUNNING')
        elif run_state_value == constants.RUN_STATE_PAUSED:
            self.run_state.value = run_state_value
            print('[GUiMain.on_run_state_changed]: RUN_STATE_PAUSED')
        elif run_state_value == constants.RUN_STATE_STOP:
            self.run_state.value = run_state_value
            print('[GUiMain.on_run_state_changed]: RUN_STATE_STOP')
        elif run_state_value == constants.RUN_STATE_FINISHED:
            self.run_state.value = run_state_value
            print('[GUiMain.on_run_state_changed]: RUN_STATE_FINISHED')
        else:
            raise ValueError('Unknown app state: %s' %
                             str(self.app_state.value))

    @exceptions.error_handler(scope='general')
    def print_log(self, msg, style=None, mode='append'):
        """ Prints in the application log."""
        # hasattr is needed because if an exception occurs before
        # log_panel_widget is initialized, the program enters an infinite
        # loop because of exception handling
        if hasattr(self, 'log_panel_widget'):
            self.log_panel_widget.print_log(msg, style, mode)

    # ====================== EXCEPTION HANDLER, CLOSE ======================== #
    def handle_exception(self, ex, mode='log'):
        """ This function handles all the exceptions in MEDUSA

        Parameters
        ----------
        ex: Exception or subclass
            Exception raised in medusa
        mode: str {'log', 'dialog}
            Mode to show the exception. If 'log', a summary will be displayed
            in the log panel. If dialog, the exception message will be
            displayed in a dialog.
        """
        try:
            # Check exception
            if not isinstance(ex, exceptions.MedusaException):
                ex = exceptions.MedusaException(
                    ex, msg='Exception generated automatically because a '
                            'non MedusaException exception reached '
                            'GuiMain.handle_exception. This situation should '
                            'be avoided!',
                    scope='general',
                    origin='GuiMain.handle_exception')
            # Print exception in stderr
            print('\nMEDUSA exception report:', file=sys.stderr)
            print('\tException in function %s' % ex.origin, file=sys.stderr)
            print('\tProcess: %s' % ex.process, file=sys.stderr)
            print('\tThread: %s' % ex.thread, file=sys.stderr)
            print('\tUID: %s' % ex.uid, file=sys.stderr)
            print('\tImportance: %s' % ex.importance, file=sys.stderr)
            print('\tCustom message: %s' % ex.msg, file=sys.stderr)
            print('\tScope: %s' % ex.scope, file=sys.stderr)
            print('\tException type: %s' % ex.exception_type.__name__,
                  file=sys.stderr)
            print('\tException msg: %s\n' % ex.exception_msg, file=sys.stderr)
            print(ex.traceback, file=sys.stderr)
            # Print exception in log panel
            if mode == 'log':
                self.print_log(ex.get_msg(verbose=True), style='error')
            elif mode == 'dialog':
                error_dialog(message=ex.get_msg(verbose=True),
                             title='ERROR!',
                             theme_colors=self.theme_colors)
            else:
                raise ValueError('Unknown display mode %s for exception.' %
                                 mode)
            # Take actions
            if ex.importance == 'critical' and not ex.handled:
                if ex.scope == 'app':
                    self.apps_panel_widget.terminate_app_process(kill=True)
                    self.reset_apps_panel()
                elif ex.scope == 'plots':
                    self.reset_plots_panel()
                elif ex.scope == 'log':
                    self.reset_log_panel()
                elif ex.scope == 'studies':
                    self.reset_studies_panel()
                elif ex.scope == 'general' or ex.scope is None:
                    self.apps_panel_widget.terminate_app_process(kill=True)
                    self.reset()
        except Exception as e:
            traceback.print_exc()
            self.print_log(str(e), style='error')

    @exceptions.error_handler(scope='general')
    def reset_apps_panel(self):
        """Stop and reset of the current application.
        """
        # Close current app and reset apps panel toolbars
        self.apps_panel_widget.terminate_app_process()
        self.apps_panel_widget.reset_tool_bar_app_buttons()
        # Update states
        self.on_app_state_changed(constants.APP_STATE_OFF)
        self.on_run_state_changed(constants.RUN_STATE_READY)

    @exceptions.error_handler(scope='general')
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

    @exceptions.error_handler(scope='general')
    def reset_log_panel(self):
        if self.log_panel_widget.undocked:
            self.log_panel_window.close()
        self.log_panel_widget.reset_tool_bar_log_buttons()

    @exceptions.error_handler(scope='general')
    def reset(self):
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

    @exceptions.error_handler(scope='general')
    def closeEvent(self, event):
        """This method is executed when the wants to close the application.
        All the processes and threads have to be closed
        """
        if self.app_state.value != constants.APP_STATE_OFF or \
                self.run_state.value != constants.RUN_STATE_READY:
            # Paradigm open. Not allowed to close Medusa
            info_dialog("Please, finish the current run pressing the stop "
                        "button before closing MEDUSA", "Warning!")
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
            # Close medusa interface queue
            self.medusa_interface_listener.terminate()
            self.interface_queue.close()
            # Save gui config
            self.save_gui_config()
            # Let the window close
            event.accept()

    class MedusaInterfaceQueue:

        """Communication queue between all medusa elements and the main gui
        """

        FLUSH = '#@flush@#'

        def __init__(self):
            self.queue = mp.Queue()
            self.closed = False

        def put(self, obj, block=True, timeout=None):
            self.queue.put(obj, block=block, timeout=timeout)

        def get(self, block=True, timeout=None):
            msg = self.queue.get(block, timeout)
            if self.is_flush(msg):
                return None
            else:
                return msg

        def flush(self):
            """If the Medusa interface listener"""
            self.put(self.FLUSH)

        def is_flush(self, msg):
            return True if msg == self.FLUSH else False

        def close(self):
            """This method must be used to close the queue
            """
            # self.flush()
            self.queue.close()
            self.queue.join_thread()
            self.closed = True

        def is_closed(self):
            return self.closed

    class MedusaInterfaceListener(QThread):
        """Class to receive messages from MedusaInterface

        This class that inherits from QThread listens for new messages received from
        the manager_process and emits a signal so the message will be displayed
        in the log of the main GUI

        Attributes
        ----------
        medusa_interface_queue : multiprocessing queue
        stop : boolean
               Parameter to stop the listener thread.
        """

        # Basic info types
        msg_signal = Signal(str, object, str)
        exception_signal = Signal(exceptions.MedusaException, str)
        # Plot info types
        plot_state_changed_signal = Signal(int)
        undocked_plots_closed = Signal()
        # Apps info types
        app_state_changed_signal = Signal(int)
        run_state_changed_signal = Signal(int)

        def __init__(self, medusa_interface_queue):
            """Class constructor

            Parameters
            ----------
            medusa_interface_queue : MedusaInterfaceQueue
                    Queue where the manager process puts the messages
            """
            QThread.__init__(self)
            self.medusa_interface_queue = medusa_interface_queue
            self.stop = False

        def run(self):
            """Main loop
            """
            while not self.stop:
                try:
                    # Check if queue is closed
                    if self.medusa_interface_queue.is_closed():
                        continue
                    # Wait for incoming messages
                    info = self.medusa_interface_queue.get()
                    # Check flush
                    if info is None:
                        continue
                    # Decode message
                    if info['info_type'] == \
                            resources.MedusaInterface.INFO_LOG:
                        mode = info['mode'] if 'mode' in info else 'append'
                        self.msg_signal.emit(info['info'], info['style'], mode)
                    elif info['info_type'] == \
                            resources.MedusaInterface.INFO_EXCEPTION:
                        mode = info['mode'] if 'mode' in info else 'log'
                        self.exception_signal.emit(info['info'], mode)
                    elif info['info_type'] == \
                            resources.MedusaInterface.INFO_APP_STATE_CHANGED:
                        self.app_state_changed_signal.emit(info['info'])
                    elif info['info_type'] == \
                            resources.MedusaInterface.INFO_RUN_STATE_CHANGED:
                        self.run_state_changed_signal.emit(info['info'])
                    elif info['info_type'] == \
                            resources.MedusaInterface.INFO_UNDOCKED_PLOTS_CLOSED:
                        self.undocked_plots_closed.emit()
                    else:
                        raise ValueError('Incorrect msg received in '
                                         'MedusaInterfaceListener')
                except (EOFError, BrokenPipeError, ValueError) as e:
                    # Broken pipe
                    ex = exceptions.MedusaException(
                        e, uid='MedusaInterfaceQueueError',
                        importance='critical',
                        msg='Catastrophic error in medusa interface '
                            'communication queue',
                        scope='general',
                        origin='MedusaInterfaceListener.run')
                    self.exception_signal.emit(ex, 'log')
                except Exception as e:
                    ex = exceptions.MedusaException(
                        e, uid='MedusaInterfaceError',
                        importance='critical',
                        msg='Catastrophic error in MedusaInterfaceListener',
                        scope='general',
                        origin='MedusaInterfaceListener.run')
                    self.exception_signal.emit(ex, 'log')

        def terminate(self):
            self.stop = True
            if not self.medusa_interface_queue.is_closed():
                self.medusa_interface_queue.flush()
            self.wait()


class SplashScreen:

    def __init__(self, release_info):
        """ Sets the initial splash screen while it loads things."""
        # Attaching the splash image
        self.release_info = release_info
        img_path = glob.glob('gui/images/medusa_splash.png')[0]
        splash_image = QPixmap(img_path)
        self.splash_screen = QSplashScreen(splash_image)
        self.splash_screen.setStyleSheet("QSplashScreen { margin-right: 0px; "
                                         "padding-right: 0px;}")
        self.splash_screen.setMask(splash_image.mask())

        # Creating the progress bar
        self.splash_progbar = QProgressBar(self.splash_screen)
        self.splash_progbar.setTextVisible(False)
        self.splash_progbar.setStyleSheet(
            "QProgressBar{ "
            "height: 7px; "
            "width: 100px;"
            "margin-right: -5px;"
            "padding-right: 0px;"
            "color: none; "
            "border: 1px solid transparent; "
            "background: rgba(0,0,0,0); "
            "margin-left: 370px; "
            "margin-top: 276px;"
            "}" +
            "QProgressBar::chunk{ background: #ffffff; }")

        # Creating the progress text
        self.splash_text = QLabel('Making a PhD thesis...')
        self.splash_text.setStyleSheet("color: #ffffff; "
                                       "font-size: 8pt; "
                                       "font-weight: bold; "
                                       "margin-top: 360px; "
                                       "margin-left: 500px; "
                                       "font-family: sans-serif, "
                                       "Helvetica, Arial; "
                                       "text-align: left;")

        # Creating the final layout
        splash_layout = QGridLayout()
        splash_layout.setContentsMargins(0, 0, 0, 0)
        splash_layout.addWidget(self.splash_progbar, 0, 0)
        splash_layout.addWidget(self.splash_text, 0, 0)
        self.splash_screen.setLayout(splash_layout)

        # Show in the corresponding screen if available
        # if 'screen_idx' in gui_config:
        #     screen_geometry = QApplication.desktop().screenGeometry(
        #         gui_config['screen_idx'])
        #     splash_width = splash_image.width()
        #     splash_height = splash_image.height()
        #     splash_x = int(screen_geometry.x() + screen_geometry.width() / 2 -
        #                    splash_width / 2)
        #     splash_y = int(screen_geometry.y() + screen_geometry.height() / 2 -
        #                    splash_height / 2)
        #     self.splash_screen.setGeometry(
        #         splash_x, splash_y, splash_width, splash_height)

        # Displaying the splash screen
        self.splash_screen.show()

    def set_state(self, prog_value, prog_text):
        self.splash_progbar.setValue(prog_value)
        self.splash_text.setText(prog_text)

    def hide(self, parent=None):
        # Hide splash screen
        self.splash_screen.finish(parent)
