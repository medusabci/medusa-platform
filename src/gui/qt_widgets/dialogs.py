# Python imports
import os, time
# External imports
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
# Medusa imports
from gui import gui_utils


class MedusaDialog(QDialog):
    """Dialog skeleton for medusa, Inherit from this class to create custom
    dialogs with the proper style
    """
    def __init__(self, window_title, theme_colors=None, pos_x=300, pos_y=300,
                 width=400, heigh=200):
        try:
            super().__init__()
            # Set style
            self.theme_colors = gui_utils.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)
            self.setWindowIcon(QIcon('gui/images/medusa_task_icon.png'))
            self.setWindowTitle(window_title)
            self.setGeometry(pos_x, pos_y, width, heigh)

            layout = self.create_layout()
            if layout is None:
                raise ValueError('Layout is None')
            self.setLayout(layout)
        except Exception as ex:
            raise ex

    def create_layout(self):
        """Creates the layout of the dialog. Reimplement this method to create
        your custom layout.
        """
        label = QLabel('Empty layout')
        layout = QVBoxLayout()
        layout.addWidget(label)
        return layout


def confirmation_dialog(text, title, informative_text=None, theme_colors=None):
    """ Shows a confirmation dialog with 2 buttons that displays the input
    message.

    :param text: string
        Message to display
    :param title: string
        Window title
    """
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setText(text)
    if informative_text is not None:
        msg.setInformativeText(informative_text)
    msg.setWindowTitle(title)
    msg.setStandardButtons(QMessageBox.Yes| QMessageBox.No)
    msg.setWindowIcon(QIcon(os.getcwd() + '/gui/images/medusa_task_icon.png'))
    msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
    theme_colors = gui_utils.get_theme_colors('dark') if \
        theme_colors is None else theme_colors
    stl = gui_utils.set_css_and_theme(msg, theme_colors)
    res = msg.exec_()
    if res == QMessageBox.Yes:
        return True
    else:
        return False


def info_dialog(message, title, theme_colors=None):
    """ Shows an error dialog with an 'Ok' button that displays the input
    message.

    :param message: string
        Message to display
    :param title: string
        Window title
    """
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setText(message)
    msg.setWindowTitle(title)
    msg.setStandardButtons(QMessageBox.Ok)
    msg.setWindowIcon(QIcon(os.getcwd() + '/gui/images/medusa_task_icon.png'))
    msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
    theme_colors = gui_utils.get_theme_colors('dark') if \
        theme_colors is None else theme_colors
    stl = gui_utils.set_css_and_theme(msg, theme_colors)
    return msg.exec_()


def error_dialog(message, title, theme_colors=None):
    """ Shows an error dialog with an 'Ok' button that displays the input
    message.

    :param message: string
        Message to display
    :param title: string
        Window title
    """
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Critical)
    msg.setText(message)
    msg.setWindowTitle(title)
    msg.setStandardButtons(QMessageBox.Ok)
    msg.setWindowIcon(QIcon(os.getcwd() + '/gui/images/medusa_task_icon.png'))
    msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
    theme_colors = gui_utils.get_theme_colors('dark') if \
        theme_colors is None else theme_colors
    stl = gui_utils.set_css_and_theme(msg, theme_colors)
    return msg.exec_()


def warning_dialog(message, title, theme_colors=None):
    """ Shows a warning dialog with an 'Ok' button that displays the input
    message.

    :param message: string
        Message to display
    :param title: string
        Window title
    """
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Warning)
    msg.setText(message)
    msg.setWindowTitle(title)
    msg.setStandardButtons(QMessageBox.Ok)
    msg.setWindowIcon(QIcon(os.getcwd() + '/gui/images/medusa_task_icon.png'))
    msg.setWindowFlags(msg.windowFlags() | Qt.WindowStaysOnTopHint)
    theme_colors = gui_utils.get_theme_colors('dark') if \
        theme_colors is None else theme_colors
    stl = gui_utils.set_css_and_theme(msg, theme_colors)
    return msg.exec_()