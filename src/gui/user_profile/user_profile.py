# Built-in imports
import sys, os, json, traceback, webbrowser
# External imports
from PyQt5 import QtCore, QtGui, QtWidgets, uic
from PyQt5.QtCore import Qt
# Medusa imports
from gui import gui_utils
from gui.qt_widgets import dialogs
from gui.qt_widgets.notifications import NotificationStack
from acquisition import lsl_utils
import exceptions
import constants
from medusa.plots import optimal_subplots

# Load the .ui files
ui_main_dialog = \
    uic.loadUiType('gui/ui_files/user_profile_dialog.ui')[0]


class UserProfileDialog(QtWidgets.QDialog, ui_main_dialog):
    """ Main dialog class of the LSL config panel
    """
    def __init__(self, theme_colors=None):
        """ Class constructor

        Parameters
        ----------
        theme_colors: dict
            Dict with the theme colors
        """
        try:
            super().__init__()
            self.setupUi(self)
            self.notifications = NotificationStack(parent=self)
            self.resize(640, 256)
            # Initialize the gui application
            self.dir = os.path.dirname(__file__)
            self.theme_colors = gui_utils.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gui_utils.set_css_and_theme(self, 'gui/style.css',
                                                   self.theme_colors)
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
                    QtWidgets.QSizePolicy.Expanding)
            )
            # Buttons
            self.pushButton_login.clicked.connect(
                self.on_button_login_clicked)
            self.pushButton_signup.clicked.connect(
                self.on_button_signup_clicked)
            # Connect the buttons
            self.setModal(True)
            self.show()
        except Exception as e:
            self.handle_exception(e)

    def on_button_login_clicked(self):
        """Query to medusa.com to log in"""
        raise NotImplementedError()

    def on_button_signup_clicked(self):
        """Go to sign up page"""
        webbrowser.open_new("http://www.qtcentre.org")

    def on_label_forgot_password_clicked(self):
        """Go to forgot password page"""
        webbrowser.open_new("http://www.qtcentre.org")

    def handle_exception(self, ex):
        traceback.print_exc()
        self.notifications.new_notification('[ERROR] %s' % str(ex))


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