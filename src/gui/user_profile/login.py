# Built-in imports
import sys, os, json, traceback, webbrowser, pickle
# External imports
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import Qt
import requests
# Medusa imports
from gui import gui_utils
from gui.qt_widgets import dialogs
from gui.qt_widgets.notifications import NotificationStack
from acquisition import lsl_utils
import exceptions
import constants
from medusa.plots import optimal_subplots
import user_session

# Load the .ui files
ui_main_dialog = \
    uic.loadUiType('gui/ui_files/login_dialog.ui')[0]


class LoginDialog(QtWidgets.QDialog, ui_main_dialog):
    """ Dialog for Login to MEDUSA
    """

    error_signal = QtCore.pyqtSignal(Exception)

    def __init__(self, user_session, theme_colors=None):
        """ Class constructor

        Parameters
        ----------
        theme_colors: dict
            Dict with the theme colors
        """
        super().__init__()
        self.setupUi(self)
        self.resize(640, 256)
        # Initialize the gui application
        self.dir = os.path.dirname(__file__)
        self.theme_colors = gui_utils.get_theme_colors('dark') if \
            theme_colors is None else theme_colors
        self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)
        medusa_icon = QtGui.QIcon('%s/medusa_favicon.png' %
                                  constants.IMG_FOLDER)
        self.setWindowIcon(medusa_icon)
        self.setWindowTitle('LOGIN')
        # Icon and title
        self.label_title.setObjectName('login-label-title')
        self.label_icon.setPixmap(medusa_icon.pixmap(
            QtCore.QSize(256, 256)))
        # Form entries
        self.lineEdit_email.setProperty("class", "login-entry")
        self.lineEdit_password.setProperty("class", "login-entry")
        self.lineEdit_password.setEchoMode(QtWidgets.QLineEdit.Password)
        # Forgot password
        self.label_forgot_password = ForgotPasswordQLabel(
            'Forgot your password?')
        self.label_forgot_password.setObjectName('login-forgot-password')
        self.label_forgot_password.setAlignment(Qt.AlignRight)
        self.label_forgot_password.clicked.connect(
            self.on_label_forgot_password_clicked)
        self.verticalLayout_form.addWidget(self.label_forgot_password)
        self.verticalLayout_form.addSpacerItem(
            QtWidgets.QSpacerItem(
                0, 0, QtWidgets.QSizePolicy.Expanding,
                QtWidgets.QSizePolicy.Minimum)
        )
        # Error message
        self.label_error_msg = QtWidgets.QLabel()
        self.label_error_msg.setObjectName('login-error-msg')
        self.label_error_msg.setStyleSheet(
            "QLabel { color : %s; }" % self.theme_colors['THEME_RED'])
        self.verticalLayout_form.addWidget(self.label_error_msg)
        # Buttons
        self.pushButton_login.clicked.connect(
            self.on_button_login_clicked)
        self.pushButton_signup.clicked.connect(
            self.on_button_signup_clicked)
        # Initialization
        self.user_session = user_session
        self.success = False
        # Show
        self.setModal(True)
        self.show()

    def handle_exception(self, mds_ex):
        # Send exception to gui main
        self.error_signal.emit(mds_ex)

    @exceptions.error_handler(scope='general')
    def on_button_login_clicked(self, checked):
        """Query to medusa.com to log in"""
        # Reset error message
        self.label_error_msg.setText('')
        QtWidgets.qApp.processEvents()
        # Get data
        email = self.lineEdit_email.text()
        password = self.lineEdit_password.text()
        try:
            self.user_session.login(email, password)
            self.success = True
            self.close()
        except user_session.AuthenticationError as e:
            self.label_error_msg.setText('Incorrect email or password')
            self.success = False
        except requests.exceptions.ConnectionError as e:
            self.label_error_msg.setText('Host unreachable')
            self.success = False

    @exceptions.error_handler(scope='general')
    def on_button_signup_clicked(self, checked):
        """Go to sign up page"""
        webbrowser.open_new("http://www.medusabci.com/signup/")

    @exceptions.error_handler(scope='general')
    def on_label_forgot_password_clicked(self, checked):
        """Go to forgot password page"""
        webbrowser.open_new("http://www.medusabci.com/reset-password/")

    @exceptions.error_handler(scope='general')
    def closeEvent(self, event):
        if self.user_session is None:
            resp = dialogs.confirmation_dialog(
                message='Login is required. If you close this window, '
                        'MEDUSA will exit. Do you want to continue?',
                title='Login required',
                theme_colors=self.theme_colors
            )
            event.accept() if resp else event.ignore()
        else:
            event.accept()


class ForgotPasswordQLabel(QtWidgets.QLabel):

    clicked = QtCore.pyqtSignal()

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