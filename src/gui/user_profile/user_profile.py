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

    error_signal = QtCore.pyqtSignal(Exception)
    logout_signal = QtCore.pyqtSignal()
    delete_signal = QtCore.pyqtSignal()

    def __init__(self, user_session, theme_colors=None):
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
            self.setWindowTitle('PROFILE')
            # Variables
            self.user_session = user_session
            # Icon and title
            self.label_alias.setObjectName('profile-label-title')
            self.label_icon.setPixmap(medusa_icon.pixmap(
                QtCore.QSize(256, 256)))
            self.label_alias.setText(
                'Welcome %s!' % self.user_session.user_info['alias'])
            # User info
            self.label_name.setProperty("class", "profile-label")
            self.label_name.setText(self.user_session.user_info['name'])
            self.label_email.setProperty("class", "profile-label")
            self.label_email.setText(self.user_session.user_info['email'])
            # Forgot password
            self.label_goto_profile = WebsiteProfileQLabel(
                'Go to profile')
            self.label_goto_profile.setObjectName('login-forgot-password')
            self.label_goto_profile.setAlignment(Qt.AlignRight)
            self.label_goto_profile.clicked.connect(
                self.on_label_goto_profile_clicked)
            self.verticalLayout_form.addWidget(self.label_goto_profile)
            self.verticalLayout_form.addSpacerItem(
                QtWidgets.QSpacerItem(
                    0, 0, QtWidgets.QSizePolicy.Expanding,
                    QtWidgets.QSizePolicy.Expanding)
            )
            # Buttons
            self.pushButton_logout.clicked.connect(
                self.on_button_logout_clicked)
            self.pushButton_delete.clicked.connect(
                self.on_button_delete_clicked)
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
        self.user_session.logout()
        self.logout_signal.emit()
        self.close()

    def on_button_delete_clicked(self):
        """Go to sign up page"""
        self.user_session.logout()
        self.delete_signal.emit()
        self.close()

    def on_label_goto_profile_clicked(self):
        """Go to forgot password page"""
        webbrowser.open_new("http://www.medusabci.com/")


class WebsiteProfileQLabel(QtWidgets.QLabel):

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