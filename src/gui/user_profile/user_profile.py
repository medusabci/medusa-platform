# Built-in imports
import sys, os, json, traceback, webbrowser
# External imports
from PySide6.QtUiTools import loadUiType
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
# Medusa imports
from gui import gui_utils
from gui.qt_widgets import dialogs
from gui.qt_widgets.notifications import NotificationStack
from acquisition import lsl_utils
import exceptions
import constants
from medusa.plots import optimal_subplots

# Load the .ui files
ui_main_dialog = loadUiType('gui/ui_files/user_profile_dialog.ui')[0]


class UserProfileDialog(QtWidgets.QDialog, ui_main_dialog):
    """ Main dialog class of the LSL config panel
    """

    error_signal = QtCore.Signal(Exception)
    logout_signal = QtCore.Signal()
    delete_signal = QtCore.Signal()

    def __init__(self, user_session, theme_colors=None):
        """ Class constructor

        Parameters
        ----------
        theme_colors: dict
            Dict with the theme colors
        """
        try:
            super().__init__()
            self.setWindowFlags(
                self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
            self.setupUi(self)

            self.notifications = NotificationStack(parent=self)

            # Initialize the gui application
            self.dir = os.path.dirname(__file__)
            self.theme_colors = gui_utils.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)
            medusa_task_icon = QtGui.QIcon('%s/medusa_task_icon.png' %
                                      constants.IMG_FOLDER)
            self.setWindowIcon(medusa_task_icon)
            self.setWindowTitle('User profile')
            # Variables
            self.user_session = user_session
            self.label_alias.setText('Logged as <a '
                                     'href="www.medusabci.com/home" '
                                     'style="color:#55aa00;">@%s</a>' %
                                     self.user_session.user_info['alias'])
            # User info
            self.label_name.setText(self.user_session.user_info['name'])
            self.label_email.setText(self.user_session.user_info['email'])
            # Delete account
            self.label_delete_account = \
                WebsiteProfileQLabel('Delete my account from this computer')
            self.label_delete_account.setProperty("class", "profile-link")
            self.label_delete_account.setAlignment(Qt.AlignCenter)
            self.label_delete_account.clicked.connect(self.on_delete_clicked)
            self.login_container_layout.addWidget(self.label_delete_account)
            # Buttons
            self.pushButton_logout.clicked.connect(
                self.on_button_logout_clicked)
            # Connect the buttons
            self.setModal(True)
            self.show()
        except Exception as e:
            self.handle_exception(e)

    def handle_exception(self, mds_ex):
        # Send exception to gui main
        self.error_signal.emit(mds_ex)

    def on_button_logout_clicked(self):
        """User logout"""
        self.close()
        self.logout_signal.emit()

    def on_delete_clicked(self):
        """Go to sign up page"""
        resp = dialogs.confirmation_dialog(
            text='This will delete all user files and apps from '
                    'this computer. Are you sure you want to continue?',
            title='Delete account',
            theme_colors=self.theme_colors
        )
        if resp:
            self.close()
            self.delete_signal.emit()


class WebsiteProfileQLabel(QtWidgets.QLabel):

    clicked = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(QtGui.QCursor(Qt.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def enterEvent(self, event):
        f = self.font()
        f.setUnderline(True)
        self.setFont(f)

    def leaveEvent(self, event):
        f = self.font()
        f.setUnderline(False)
        self.setFont(f)


if __name__ == '__main__':
    pass