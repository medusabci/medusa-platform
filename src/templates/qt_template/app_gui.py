# Python modules
import os, time
# External modules
from PyQt5 import QtGui, QtWidgets
from PyQt5.QtCore import *
# Medusa modules
from gui import gui_utils
from gui.qt_widgets import dialogs
import constants, exceptions


class AppGui(QtWidgets.QMainWindow):

    """ This class provides graphical configuration for the app """

    def __init__(self, app_settings, run_state, queue_from_manager,
                 queue_to_manager, theme_colors=None):
        """Class constructor

        Parameters
        ----------
        app_settings: settings.Settings
             instance of class Settings defined in settings.py in the app
             directory
        app_extension: string,
            Extension of the app to save files. It's a unique code which
            differentiates the files from each app
        run_state: multiprocessing.Value
            Run state of medusa
        queue_from_manager: multiprocessing.Queue
            Queue to receive messages from the manager thread
        queue_to_manager: multiprocessing.Queue
            Queue to send messages to the manager thread
        theme_colors: dict
            Theme colors
        """
        QtWidgets.QMainWindow.__init__(self)

        # Initialize the gui application
        self.theme_colors = gui_utils.get_theme_colors('dark') if \
            theme_colors is None else theme_colors
        self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)
        self.setWindowIcon(QtGui.QIcon('%s/medusa_favicon.png' %
                                       constants.IMG_FOLDER))
        self.setWindowTitle('Template of Qt app')

        # Class attributes
        self.app_settings = app_settings
        self.run_state = run_state
        self.queue_from_manager = queue_from_manager
        self.queue_to_manager = queue_to_manager
        self.is_close_forced = False

        # Create layout
        self.main_layout = QtWidgets.QVBoxLayout()

        # Label
        self.label = QtWidgets.QLabel('EEG samples')

        # Spin box
        self.spin_box = QtWidgets.QSpinBox()
        self.spin_box.setMinimum(0)
        self.spin_box.setMaximum(9999999)
        self.spin_box.setValue(0)

        # Add widgets
        self.main_layout.addWidget(self.label)
        self.main_layout.addWidget(self.spin_box)

        # Add central widget
        self.central_widget = QtWidgets.QWidget()
        self.central_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.central_widget)

        # Start working thread
        self.working_thread = AppGuiWorker(
            app_settings, run_state,
            self.queue_from_manager, self.queue_to_manager)
        self.working_thread.update_eeg_samples_signal_handler.connect(
            self.update_eeg_samples_signal_handler)
        self.working_thread.start()

        # Show application
        self.setWindowFlags(self.windowFlags() |
                            Qt.WindowStaysOnTopHint)
        self.show()

    def handle_exception(self, ex):
        # Treat exception
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/AppGui/handle_exception')
        # Notify exception to gui main
        self.queue_to_manager.put({'event_type': 'error', 'exception': ex})

    @pyqtSlot(int)
    def update_eeg_samples_signal_handler(self, eeg_samples):
        try:
            self.spin_box.setValue(eeg_samples)
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/AppGui/update_eeg_samples_signal_handler')
            self.handle_exception(ex)

    def close_forced(self):
        self.is_close_forced = True
        self.close()

    def closeEvent(self, event):
        """ This method is executed when the user wants to close the
        application. All the processes and threads have to be closed
        """
        try:
            if self.is_close_forced is False:
                # POWERING_OFF only if the user press the stop button.
                if self.run_state.value == constants.RUN_STATE_STOP:
                    self.working_thread.stop = True
                    event.accept()
                else:
                    dialogs.info_dialog(
                        message='Please, finish the current run '
                                'pressing the stop button',
                        title='Warning'
                    )
                    event.ignore()
            else:
                event.accept()
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/AppGui/closeEvent')
            self.handle_exception(ex)


class AppGuiWorker(QThread):

    update_eeg_samples_signal_handler = pyqtSignal(int)

    def __init__(self, app_settings, run_state, queue_from_manager,
                 queue_to_manager):
        super().__init__()
        self.app_settings = app_settings
        self.run_state = run_state
        self.queue_from_manager = queue_from_manager
        self.queue_to_manager = queue_to_manager
        self.stop = False

    def handle_exception(self, ex):
        # Treat exception
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/AppGuiWorker/handle_exception')
        # Notify exception to gui main
        self.queue_to_manager.put({'event_type': 'error', 'exception': ex})

    def run(self):
        try:
            while not self.stop:
                time.sleep(1/(self.app_settings.updates_per_min/60))
                if self.run_state.value == constants.RUN_STATE_RUNNING:
                    # print('[AppGuiWorker] Request update')
                    self.queue_to_manager.put({'event_type': 'update_request'})
                    resp = self.queue_from_manager.get()
                    # print('\t>> Response: ' + str(resp))
                    if resp['event_type'] == 'update_response':
                        self.update_eeg_samples_signal_handler.emit(
                            resp['data'])
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='rec/AppGuiWorker/run')
            self.handle_exception(ex)
