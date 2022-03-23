# Built-in imports
import sys, os, json, traceback
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
main_widget = \
    uic.loadUiType('gui/ui_files/create_app_widget.ui')[0]


class CreateAppDialog(QtWidgets.QDialog, main_widget):
    """ Main dialog class of the LSL config panel
    """
    def __init__(self, theme_colors=None):
        """ Class constructor

        Parameters
        ----------
        working_streams: list of acquisition.lsl_utils.LSLStreamWrapper
            List with the current working LSL streams
        theme_colors: dict
            Dict with the theme colors
        """
        try:
            super().__init__()
            self.setupUi(self)
            self.notifications = NotificationStack(parent=self)
            # self.resize(600, 400)
            # Initialize the gui application
            self.dir = os.path.dirname(__file__)
            self.theme_colors = gui_utils.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gui_utils.set_css_and_theme(self, 'gui/style.css',
                                                   self.theme_colors)
            self.setWindowIcon(QtGui.QIcon('%s/medusa_favicon.png' %
                               constants.IMG_FOLDER))
            self.setWindowTitle('Create app ')
            # Set up tables

            # ToolButtons

            # First search

            # Show the buttons
            self.setModal(True)
            self.show()
        except Exception as e:
            self.handle_exception(e)

    def handle_exception(self, ex):
        traceback.print_exc()
        self.notifications.new_notification('[ERROR] %s' % str(ex))
