# Built-in imports
import sys, os, json, traceback, shutil
# External imports
from PyQt5 import QtCore, QtGui, QtWidgets, uic
# Medusa imports
from gui import gui_utils
from gui.qt_widgets import dialogs
from gui.qt_widgets.notifications import NotificationStack
from acquisition import lsl_utils
import exceptions
import constants
from medusa.plots import optimal_subplots

# Load the .ui files
create_app_dialog = \
    uic.loadUiType('gui/ui_files/create_app_dialog.ui')[0]


class CreateAppDialog(QtWidgets.QDialog, create_app_dialog):
    """ Main dialog class of the LSL config panel
    """
    def __init__(self, apps_manager, theme_colors=None):
        """ Class constructor

        Parameters
        ----------
        apps_manager: apps_manager.AppsManager
            Apps manager of medusa
        theme_colors: dict
            Dict with the theme colors
        """
        try:
            super().__init__()
            self.setupUi(self)
            # Initialize the gui application
            self.dir = os.path.dirname(__file__)
            self.theme_colors = gui_utils.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gui_utils.set_css_and_theme(self, 'gui/style.css',
                                                   self.theme_colors)
            self.setWindowIcon(QtGui.QIcon('%s/medusa_favicon.png' %
                               constants.IMG_FOLDER))
            self.setWindowTitle('Create app ')
            # Attributes
            self.apps_manager = apps_manager
            # Show the buttons
            self.setModal(True)
            self.show()
        except Exception as e:
            self.handle_exception(e)

    def handle_exception(self, ex):
        traceback.print_exc()
        dialogs.error_dialog(str(ex), 'Error', self.theme_colors)

    def accept(self):
        """ This function updates the lsl_streams.xml file and saves it
        """
        try:
            # Get id and check
            app_id = self.lineEdit_app_id.text()
            if len(app_id) == 0:
                raise ValueError('Please introduce the app id')
            if os.path.isdir('apps/%s' % app_id):
                raise ValueError('That app identifier already taken!')
            # Get app name
            app_name = self.lineEdit_app_name.text()
            if len(app_name) == 0:
                raise ValueError('Please introduce the app name')
            app_extension = self.lineEdit_app_extension.text()
            if len(app_name) == 0:
                raise ValueError('Please introduce the extension name')

            # Get template type
            app_template = self.listWidget_app_template.currentItem().text()
            if app_template == 'Empty project':
                app_template_path = 'templates/empty_template'
            elif app_template == 'Qt project':
                app_template_path = 'templates/qt_template'
            elif app_template == 'Unity project':
                app_template_path = 'templates/unity_template'
            else:
                raise ValueError('Unknown template!')

            # Install app
            self.apps_manager.install_app_template(
                app_id, app_name, app_extension, app_template_path)

            # Accept event and close
            super().accept()
        except Exception as e:
            self.handle_exception(e)

    def reject(self):
        """ This function cancels the creation of the app"""
        try:
            super().reject()
        except Exception as e:
            self.handle_exception(e)
