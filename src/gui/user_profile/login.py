# Built-in imports
import sys, os, json, traceback, webbrowser, pickle
# External imports
from PySide6.QtUiTools import loadUiType
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import Qt
import requests
# Medusa imports
from gui import gui_utils
from gui.qt_widgets import dialogs
import exceptions
import constants

# Load the .ui files
ui_main_dialog = loadUiType('gui/ui_files/login_dialog.ui')[0]


class LoginDialog(QtWidgets.QDialog, ui_main_dialog):
    """ Dialog for Login to MEDUSA
    """

    error_signal = QtCore.Signal(Exception)

    def __init__(self, user_session, theme_colors=None):
        """ Class constructor

        Parameters
        ----------
        theme_colors: dict
            Dict with the theme colors
        """
        super().__init__()
        self.setupUi(self)

        # Initialize the gui application
        self.dir = os.path.dirname(__file__)
        self.theme_colors = gui_utils.get_theme_colors('dark') if \
            theme_colors is None else theme_colors
        self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)

        medusa_task_icon = QtGui.QIcon('%s/medusa_task_icon.png' %
                                       constants.IMG_FOLDER)
        self.setWindowIcon(medusa_task_icon)
        self.setWindowTitle('Log in to MEDUSA©')

        # Form entries
        self.lineEdit_email.setProperty("class", "login-entry")
        self.lineEdit_password.setProperty("class", "login-entry")
        self.lineEdit_password.setEchoMode(QtWidgets.QLineEdit.Password)

        # Buttons
        self.pushButton_login.clicked.connect(self.on_button_login_clicked)
        # Show_password
        self.visibleIcon = gui_utils.get_icon(
            "visibility_login.svg",
            custom_color=self.theme_colors['THEME_BG_DARK'])
        self.hiddenIcon = gui_utils.get_icon(
            "visibility_login_off.svg",
            custom_color=self.theme_colors['THEME_BG_DARK'])
        self.togglepasswordAction = self.lineEdit_password.addAction(
            self.visibleIcon, QtWidgets.QLineEdit.TrailingPosition)
        # self.showPassAction.setCheckable(True)
        self.togglepasswordAction.triggered.connect(
            self.on_toggle_password_Action)
        self.password_shown = False

        # TODO: remember me button
        # self.radioButton_remember

        # Initialization
        self.user_session = user_session
        self.success = False

        # Show
        self.setModal(True)
        self.show()

    @exceptions.error_handler(scope='general')
    def on_toggle_password_Action(self):
        if not self.password_shown:
            self.lineEdit_password.setEchoMode(QtWidgets.QLineEdit.Normal)
            self.password_shown = True
            self.togglepasswordAction.setIcon(self.hiddenIcon)
        else:
            self.lineEdit_password.setEchoMode(QtWidgets.QLineEdit.Password)
            self.password_shown = False
            self.togglepasswordAction.setIcon(self.visibleIcon)

    def handle_exception(self, mds_ex):
        # Send exception to gui main
        self.error_signal.emit(mds_ex)

    @exceptions.error_handler(scope='general')
    def on_button_login_clicked(self):
        """Query to www.medusabci.com to log in"""
        # Reset error message
        self.label_error_msg.setText('')
        QtWidgets.QApplication.instance().processEvents()
        # Get data
        email = self.lineEdit_email.text()
        password = self.lineEdit_password.text()
        try:
            self.user_session.login(email, password)
            self.success = True
            self.close()
        except exceptions.AuthenticationError as e:
            self.label_error_msg.setText('Incorrect email or password')
            self.success = False
        except requests.exceptions.ConnectionError as e:
            self.label_error_msg.setText('Host unreachable')
            self.success = False

    @exceptions.error_handler(scope='general')
    def closeEvent(self, event):
        if self.user_session is None:
            resp = dialogs.confirmation_dialog(
                text='Login is required. If you close this window, MEDUSA©  '
                     'Platform will exit. Do you want to continue?',
                title='Login required',
                theme_colors=self.theme_colors
            )
            event.accept() if resp else event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    pass
