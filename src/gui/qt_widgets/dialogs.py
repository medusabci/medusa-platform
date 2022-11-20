# Python imports
import multiprocessing
import os, time
from multiprocessing import Queue
# External imports
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtGui import QIcon, QTextCursor
from PyQt5.QtWidgets import *
# Medusa imports
from PyQt5.QtWidgets import QDialog

import constants
from gui import gui_utils


class MedusaDialog(QDialog):
    """Dialog skeleton for medusa, Inherit from this class to create custom
    dialogs with the proper style
    """
    def __init__(self, window_title, theme_colors=None, width=400, heigh=200,
                 pos_x=None, pos_y=None):
        try:
            super().__init__()
            # Set style
            self.theme_colors = gui_utils.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)
            self.setWindowIcon(QIcon('gui/images/medusa_task_icon.png'))
            self.setWindowTitle(window_title)
            if pos_x is not None and pos_y is not None:
                self.move(pos_x, pos_y)
            if width is not None and heigh is not None:
                self.resize(width, heigh)

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
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
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


class ThreadProgressDialog(MedusaDialog):
    """ This class implements a progress bar dialog. The dialog does not block
    the main process and can be controlled through several functions. It is
    designed to be used with a working thread that updates the values of the
    dialog.

    Examples
    --------
    Usage example:

    def update(progress_dialog):
        value = 0
        while True:
            time.sleep(0.5)
            value += 1
            progress_dialog.update_value(value)
            progress_dialog.update_action('Action %i' % (value // 5))
            progress_dialog.update_log('Action %i' % (value // 2))

            if progress_dialog.abort:
                break

        print('Thread terminated')

    # Show dialog
    progress_dialog = ThreadProgressDialog('Progress bar test', 0, 100)
    progress_dialog.show()

    # Start working thread
    th = threading.Thread(target=update, args=(progress_dialog, ))
    th.start()
    """

    done = pyqtSignal()

    def __init__(self, window_title, min_pbar_value, max_pbar_value,
                 theme_colors=None):
        """Class constructor.

        Parameters
        ----------
        min_pbar_value: int
            Minimum value of the progress bar
        max_pbar_value: int
            Maximum value of the progress bar
        theme_colors: dict or None
            Theme colors
        """
        # Attributes
        self.min_pbar_value = min_pbar_value
        self.max_pbar_value = max_pbar_value
        self.queue = multiprocessing.Queue()
        self.abort = False

        # Set layout
        super().__init__(window_title, theme_colors)

        # Start listener
        self.listener = self.Listener(self.queue)
        self.listener.update_action_signal.connect(self.__update_action)
        self.listener.update_value_signal.connect(self.__update_value)
        self.listener.update_log_signal.connect(self.__update_log)
        self.listener.start()

        # Show
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setModal(True)

    def create_layout(self):
        # Create widgets
        self.action_label = QLabel('Action')
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(self.min_pbar_value, self.max_pbar_value)
        self.log_box = QTextBrowser()
        # Create layout
        layout = QVBoxLayout()
        # Add widgets
        layout.addWidget(self.action_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_box)
        return layout

    def update_action(self, action):
        self.queue.put(('action', action))

    def __update_action(self, action):
        self.action_label.setText(action)

    def update_value(self, value):
        self.queue.put(('value', value))

    def __update_value(self, value):
        self.progress_bar.setValue(value)

    def update_log(self, message):
        self.queue.put(('log', message))

    def __update_log(self, message):
        self.log_box.append(message)
        self.log_box.moveCursor(QTextCursor.End)

    def closeEvent(self, event):
        self.abort = True
        self.listener.finish()
        self.done.emit()
        event.accept()

    class Listener(QThread):

        update_action_signal = pyqtSignal(str)
        update_value_signal = pyqtSignal(int)
        update_log_signal = pyqtSignal(str)

        def __init__(self, queue):
            super().__init__()
            self.queue = queue
            self.stop = False

        def run(self):
            while not self.stop:
                el, val = self.queue.get()
                if el == 'action':
                    self.update_action_signal.emit(val)
                elif el == 'value':
                    self.update_value_signal.emit(val)
                elif el == 'log':
                    self.update_log_signal.emit(val)

        def finish(self):
            self.stop = True
            self.queue.put((None, None))
            self.wait()


if __name__ == '__main__':
    import sys, threading

    def update(progress_dialog):
        value = 0
        while True:
            time.sleep(0.1)
            value += 1
            progress_dialog.update_value(value)
            progress_dialog.update_log('Operation #%i' % value)
            if value % 5 == 0:
                progress_dialog.update_action('Action %i' % (value // 5))

            if progress_dialog.abort:
                break

        print('Thread terminated')

    application = QApplication(sys.argv)
    # Show dialog
    progress_dialog = ThreadProgressDialog('Progress bar test', 0, 100)
    progress_dialog.show()
    # Start thread
    th = threading.Thread(target=update, args=(progress_dialog, ))
    th.start()
    sys.exit(application.exec_())

