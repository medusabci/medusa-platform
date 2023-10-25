# Python imports
import multiprocessing
import os, time
from multiprocessing import Queue
# External imports
from PySide6.QtUiTools import loadUiType
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import *
# Medusa imports
from PySide6.QtWidgets import QDialog

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


def confirmation_dialog(text, title, informative_text=None, theme_colors=None,
                        icon_path=None):
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
    if icon_path is None:
        msg.setWindowIcon(QIcon(os.getcwd() +
                                '/gui/images/medusa_task_icon.png'))
    else:
        msg.setWindowIcon(QIcon(icon_path))
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

    done = Signal()

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
        self._finished = False

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
        self.ok_button = QPushButton('Ok')
        self.ok_button.setEnabled(False)
        self.ok_button.clicked.connect(self.on_ok_button_clicked)
        # Create layout
        layout = QVBoxLayout()
        # Add widgets
        layout.addWidget(self.action_label)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_box)
        layout.addWidget(self.ok_button)
        return layout

    def update_action(self, action):
        self.queue.put(('action', action))

    def __update_action(self, action):
        self.action_label.setText(action)

    def update_value(self, value):
        self.queue.put(('value', value))

    def __update_value(self, value):
        self.progress_bar.setValue(value)

    def update_log(self, message, style=None):
        self.queue.put(('log', [message, style]))

    def __update_log(self, message, style):
        # Default styles
        if isinstance(style, str):
            if style == 'error':
                style = {'color': self.theme_colors['THEME_RED']}
            elif style == 'warning':
                style = {'color': self.theme_colors['THEME_YELLOW']}
            else:
                raise ValueError('Custom style %s not recognized' % style)
        elif isinstance(style, dict):
            pass
        elif style is None:
            style = {}
        else:
            raise ValueError('Unrecognized style type')
        # Append message
        formatted_msg = self.format_log_msg(message, **style)
        self.log_box.append(formatted_msg)
        self.log_box.moveCursor(QTextCursor.End)

    def format_log_msg(self, msg, **kwargs):
        # Default style
        kwargs.setdefault('color', self.theme_colors['THEME_TEXT_LIGHT'])
        kwargs.setdefault('font-size', '9pt')
        # Format css
        style = ''
        for key, value in kwargs.items():
            if not isinstance(value, str):
                raise ValueError('Type of %s must be str' % key)
            style += '%s: %s;' % (key, value)
        return '<p style="margin:0;margin-top:2;%s"> >> %s </p>' % (style, msg)

    def on_ok_button_clicked(self, checked=None):
        self.close()

    def finish(self):
        self._finished = True
        self.ok_button.setEnabled(True)

    def closeEvent(self, event):
        if not self._finished:
            self.abort = True
            # todo: implement abort functionality
            error_dialog('The operation must finish before closing the '
                         'dialog', 'Wait')
            event.ignore()
            return
        self.listener.finish()
        self.done.emit()
        event.accept()

    class Listener(QThread):

        update_action_signal = Signal(str)
        update_value_signal = Signal(int)
        update_log_signal = Signal(str, object)

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
                    self.update_log_signal.emit(val[0], val[1])

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

