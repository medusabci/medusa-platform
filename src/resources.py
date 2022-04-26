# Python modules
from abc import ABC, abstractmethod
import multiprocessing as mp
import threading as th
import os, time, json
# External modules
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import numpy as np
# Medusa modules
import constants, exceptions
from acquisition import lsl_utils
from gui.qt_widgets import dialogs
from gui import gui_utils


class AppSkeleton(mp.Process):
    """
    This class is the baseline for Medusa apps, providing an optimized
    structure for real-time biofeedback applications. Generally,
    it is composed by 3 different elements that run in parallel:

        1 - Manager thread. This thread receives events asynchronously,
        providing the necessary connection between the app gui and the
        biosignals. This thread should do the signal processing work.
        2 - LSL workers. Each worker is a thread that receives and stores new
        samples of each LSL stream configured in medusa. This recordings are
        accessible from the manager thread to provide biodfeedback in real-time.
        3 - Main process. Is the parent of the manager and lsl-workers,
        and executes the app gui.
    """

    def __init__(self, app_info, app_settings, medusa_interface,
                 app_state, run_state, working_lsl_streams_info):
        """Class constructor

        Parameters
        ----------
        app_info: dict
            Dict with the app information available
        app_settings: Settings
            App configuration
       medusa_interface: resources.Medusa_interface
            Interface to the main gui of medusa
        app_state: mp.Value
            App state
        run_state: mp.Value
            Run state
        working_lsl_streams_info: list of lsl_utils.LSLStreamWrapper
            List of the lsl streams connected to medusa
        """
        # Calling superclass constructor
        app_process_name = '%sProcess' % app_info['name']
        super().__init__(name=app_process_name)
        # -------------------------- CHECK ERRORS ---------------------------- #
        # ---------------------------- SETTINGS ------------------------------ #
        self.app_info = app_info
        self.app_settings = app_settings
        # --------------------- COMMUNICATION GUI-MANAGER -------------------- #
        # Interface
        self.medusa_interface = medusa_interface
        # -------------------------- MEDUSA STATES --------------------------- #
        # States are used in medusa to handle the work flow
        self.stop = False
        self.run_state = run_state
        self.app_state = app_state
        # --------------------------- LSL-STREAMS ---------------------------- #
        # Data receiver
        if not self.check_lsl_config(working_lsl_streams_info):
            raise exceptions.IncorrectLSLConfig()
        self.lsl_streams_info = working_lsl_streams_info
        self.lsl_workers = dict()
        # ----------------------------- MANAGER ------------------------------ #
        # Data receiver
        self.manager_thread = None

    @exceptions.error_handler(def_importance='critical', scope='app')
    def run(self):
        """Setup the working threads and the app. Any unhandled exception will
        kill the process.
        """
        # Working threads
        self.setup_lsl_workers()
        self.setup_manager_thread()
        # Main method (blocking)
        self.main()
        # Join the working threads
        self.lsl_workers_join()
        self.manager_thread.join()

    def setup_lsl_workers(self):
        """Creates and starts the working threads that receive the LSL streams.
        By default, it uses Python threads using the class LSLStreamAppWorker,
        storing the received data within this class to be used on demand.
        Some applications might need custom behaviour (e.g., real time plots
        that need to be updated when each sample is received). Override this
        method and use custom LSL workers in those cases.
        """
        # Data receiver
        self.lsl_streams_info = [
            lsl_utils.LSLStreamWrapper.from_serializable_obj(ser_lsl_str)
            for ser_lsl_str in self.lsl_streams_info
        ]
        for info in self.lsl_streams_info:
            if info.lsl_uid in self.lsl_workers:
                raise ValueError('Duplicated lsl stream uid %s' %
                                 info.lsl_uid)
            receiver = lsl_utils.LSLStreamReceiver(info)
            self.lsl_workers[info.medusa_uid] = \
                LSLStreamAppWorker(receiver, self.app_state,
                                   self.run_state,
                                   self.medusa_interface,
                                   preprocessor=None)
            self.lsl_workers[info.medusa_uid].start()

    def lsl_workers_join(self):
        for worker in self.lsl_workers.values():
            worker.join()

    def lsl_workers_stop(self):
        for worker in self.lsl_workers.values():
            worker.stop = True

    @exceptions.error_handler(
        def_importance='critical', scope='app',
        def_origin='AppSkeleton.manager_thread_worker')
    def manager_thread_wrapper(self):
        """This wrapper is just used to improve error handing"""
        self.manager_thread_worker()

    def setup_manager_thread(self):
        """Creates and starts the manager thread
        """
        # Move to thread
        manager_th_name = '%sManagerThread' % self.app_info['name']
        self.manager_thread = th.Thread(
            target=self.manager_thread_wrapper,
            name=manager_th_name)
        self.manager_thread.start()

    def stop_working_threads(self):
        """This function stops the working threads.
        """
        self.stop = True
        self.lsl_workers_stop()

    @abstractmethod
    def handle_exception(self, ex):
        """This function handles all the exceptions in this process

        Parameters
        ----------
        ex : Exception
             Exception or subclasses
        """
        raise NotImplemented

    @abstractmethod
    def check_lsl_config(self, working_lsl_streams_info):
        """This function has to check the LSL config. For example, some apps
        may require an LSL stream with a specific name, or a minimum of 2 LSL
        streams, etc. It must return if the lsl config is correct and the App
        can proceed, and false otherwise.
        """
        raise NotImplemented

    @abstractmethod
    def manager_thread_worker(self):
        """Method executed by the manager thread. It contains an infinite loop
        that waits for events, either from the app gui through  queue_from_gui
        or from medusa through app_state and run_state. App attribute stop must
        control when the thread must finish.

        If this method raises an unhandled exception and is terminated,
        the app cannot recover from the error. Thus the importance of unhandled
        exceptions in this method is CRITICAL. For correct error handling,
        decorate the method with:
            @exceptions.error_handler(importance=exceptions.EXCEPTION_CRITICAL)

        Basic scheme:

        @exceptions.error_handler(importance=exceptions.EXCEPTION_CRITICAL)
        def manager_thread_worker(self):
            while not self.stop:
                # Do stuff here
                pass
        """
        raise NotImplemented

    @abstractmethod
    def main(self):
        """Main method of the application. It has to return when the
        app is closed and all the information is saved. A basic scheme is
        provided, but custom pipelines can be implemented.

       Unhandled exceptions may not be critical in this method
            @exceptions.error_handler(importance=exceptions.EXCEPTION_CRITICAL)

        Basic scheme:

        @exceptions.error_handler()
        def manager_thread_worker(self):
            # 1 - Change app state to powering on
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_POWERING_ON)
            # 2 - Prepare app
            # 3 - Change app state to power on
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_ON)
            # 4 - Start app (blocking method)
            # 5 - Change app state to powering off
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_POWERING_OFF)
            # 6 - Save recording
            # 7 - Change app state to power off
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_OFF)
        """
        raise NotImplemented

    @abstractmethod
    def process_event(self, event):
        """Process event from other app process or thread. Used to receive data
        from GUIs.  This function is called by the manager thread when receives
        and event in queue from gui.

        Basic scheme:

        try:
            # Do stuff here
            pass
        except Exception as e:
            self.handle_exception(e)

        Parameters
        ----------
        event : object
            Event information. Recommended: dict with keys {event_type|data}
        """
        print("Override this method!! Event: " + str(event))

    @abstractmethod
    def close_app(self, force=False):
        """This function has to terminate the app and working threads,
        returning control to the main process. Take into account that,
        once the working threads are stopped, the app will not be able to
        receive events signal. Thus, make sure the app gui is correctly
        closed before calling self.stop_working_threads().

        Basic scheme:

        try:
            # Close app gui, returning control to main process
            # Close working threads
            self.stop_working_threads()
        except Exception as e:
            self.handle_exception(e)
        """
        raise NotImplemented


class LSLStreamAppWorker(th.Thread):
    """Thread that receives samples from a LSL stream and saves them.

    To read and process the data in a thread-safe way, use function get_data.
    """

    def __init__(self, receiver, app_state, run_state,
                 medusa_interface, preprocessor=None):
        """Class constructor for LSLStreamAppWorker

        Parameters
        ----------
        receiver: LSLStreamReceiver
            LSL stream receiver with the LSL inlet initialized, ready to go!
        app_state: mp.Value
            Medusa app state
        run_state: mp.Value
            Medusa run state
        medusa_interface: resources.Medusa_interface
            Interface to the main gui of medusa
        preprocessor: Preprocessor
            Preprocessor class that implements a preprocessing algorithm
            applied in real time to the signal. For most applications set to
            None.
        preprocessor: str {}
            Preprocessor class that implements a preprocessing algorithm
            applied in real time to the signal. For most applications set to
            None.
        """
        super().__init__()
        # Check errors
        if receiver.lsl_stream_info.lsl_stream_inlet is None:
            raise ValueError('Call function init_lsl_inlet of class '
                             'LSLStreamReceiver first!')
        # Init
        self.receiver = receiver
        self.app_state = app_state
        self.run_state = run_state
        self.preprocessor = preprocessor
        self.medusa_interface = medusa_interface
        self.stop = False
        self.lock = th.Lock()
        self.data = np.zeros((0, self.receiver.n_cha))
        self.timestamps = np.zeros((0,))

    def handle_exception(self, ex):
        pass

    @exceptions.error_handler(def_importance='important', scope='app')
    def run(self):
        """Method executed by the thread. It contains an infinite loop that
        receives and stores samples from a lsl receiver. The attribute
        stop controls when the thread must finish.
        """
        error_counter = 0
        while not self.stop:
            # Get data
            try:
                chunk_data, chunk_times = self.receiver.get_chunk()
            except exceptions.LSLStreamTimeout as e:
                error_counter += 1
                if error_counter > 5:
                    raise exceptions.MedusaException(
                        e, importance='important',
                        msg='LSLStreamAppWorker cannot receive signal from %s. '
                            'Is the device connected?' % self.receiver.name,
                        scope='app', origin='LSLStreamAppWorker.run')
                else:
                    continue
            # If the app is ON and the run is running, stack data
            if self.app_state.value == constants.APP_STATE_ON:
                if self.run_state.value == constants.RUN_STATE_RUNNING:
                    with self.lock:
                        if self.preprocessor is not None:
                            chunk_data = \
                                self.preprocessor.transform(chunk_data)
                        self.data = np.vstack((self.data, chunk_data))
                        self.timestamps = np.append(self.timestamps,
                                                    chunk_times)

    def get_data(self):
        with self.lock:
            timestamps = self.timestamps.copy()
            data = self.data.copy()
        return timestamps, data

    def reset_data(self):
        with self.lock:
            self.data = np.zeros((0, self.receiver.n_cha))
            self.timestamps = np.zeros((0,))


class MedusaInterface:
    """Class to send messages to medusa

    Attributes
    ----------
    queue_to_medusa : multiprocessing queue
        Queue to send messages to medusa.
    """

    # BASIC INFO TYPES
    INFO_LOG = "log_info"
    INFO_EXCEPTION = "exception"

    # PLOT INFO TYPES
    INFO_PLOT_STATE_CHANGED = "run_state_changed"
    INFO_UNDOCKED_PLOTS_CLOSED = "undocked_plots_terminated"

    # APP INFO TYPES
    INFO_APP_STATE_CHANGED = "app_state_changed"
    INFO_RUN_STATE_CHANGED = "run_state_changed"

    def __init__(self, queue_to_medusa):
        """Class constructor

        Parameters
        ----------
        queue_to_medusa : multiprocessing queue
                Queue where the manager process puts the messages to display
        """
        self.queue_to_medusa = queue_to_medusa

    def log(self, msg, style=None):
        """Prints a log message in medusa cmd

        Parameters
        ----------
        msg : str
            Message to print
        style: dict
            Dictionary with the desired CSS style.
            E.g., {'color':'white', 'font-style': 'italic'}
        """
        self.queue_to_medusa.put({'info_type': self.INFO_LOG,
                                  'info': msg,
                                  'style': style})

    def error(self, ex):
        """Notifies to medusa that an error has occurred in a plot

        Parameters
        ----------
        ex : exceptions.MedusaException or Exception
             Exception triggered in the app. This notification will shut down
             all plots.
        """
        # traceback.print_exc()
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(ex)
        self.queue_to_medusa.put(
            {'info_type': self.INFO_EXCEPTION, 'info': ex})

    def plot_state_changed(self, value):
        """Notifies to medusa that the plot state has changed. It has to be
        called when the plot state changes.

        Parameters
        ----------
        value : int
                App state value. Possible values are defined in constants module
        """
        self.queue_to_medusa.put(
            {'info_type': self.INFO_PLOT_STATE_CHANGED, 'info': value})

    def undocked_plots_window_closed(self):
        """Notifies to medusa that the undocked plots window has been closed

        Parameters
        ----------
        ex : Exception or subclass
             Exception triggered in the app. This notification will shut down
             all plots.
        """
        self.queue_to_medusa.put(
            {'info_type': self.INFO_UNDOCKED_PLOTS_CLOSED})

    def app_state_changed(self, value):
        """Notifies to medusa that the app state has changed. It has to be
        called when the app state changes.

        Parameters
        ----------
        value : int
                App state value. Possible values are defined in constants module
        """
        self.queue_to_medusa.put(
            {'info_type': self.INFO_APP_STATE_CHANGED, 'info': value})

    def run_state_changed(self, value):
        """Notifies to medusa that the run state has changed. It has to be
        called when the run state changes.

        Parameters
        ----------
        value : int
                Run state value. Possible values are defined in constants module
        """
        self.queue_to_medusa.put(
            {'info_type': self.INFO_RUN_STATE_CHANGED, 'info': value})


class SaveFileDialog(dialogs.MedusaDialog):
    """Default dialog to save files in apps. Implement your own class to create
    a custom dialog.
    """

    def __init__(self, app_ext, theme_colors=None):
        """Class constructor

        Parameters
        ----------
        app_ext: str
            App extension
        theme_colors: dict or None
            Theme colors
        """
        super().__init__(window_title='Save recording file',
                         theme_colors=theme_colors, pos_x=300, pos_y=300,
                         width=400, heigh=200)
        # Paths
        folder = os.path.abspath(
            os.path.abspath(os.curdir) + '../../data/')
        name = '%s.%s.bson' % \
               (time.strftime("%d-%m-%Y_%H%M%S", time.localtime()), app_ext)
        default_path = os.path.join(folder, name)

        # Default path
        self.folder = folder
        self.name = name
        self.app_ext = app_ext
        self.path = default_path

        # Default file name
        self.file_path_lineEdit.setText(name)

        # Show
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()

    def create_layout(self):
        # Fields
        self.subj_id_lineEdit = QLineEdit()
        self.subj_id_lineEdit.setProperty('class', 'file_dialog')
        self.subj_id_lineEdit.setPlaceholderText('Subject identifier')
        self.file_id_lineEdit = QLineEdit()
        self.file_id_lineEdit.setProperty('class', 'file_dialog')
        self.file_id_lineEdit.setPlaceholderText('Recording identifier')
        self.file_description_textEdit = QTextEdit()
        self.file_description_textEdit.setProperty(
            'class', 'file_dialog')
        self.file_description_textEdit.setPlaceholderText(
            'Recording description')

        # File path
        self.file_path_lineEdit = QLineEdit()
        self.file_path_lineEdit.setProperty('class', 'file_dialog')
        self.file_path_lineEdit.setEnabled(False)
        self.browse_button = QToolButton()
        self.browse_button.setText('...')
        self.browse_button.setProperty('class', 'file_dialog')
        self.browse_button.setCursor(QCursor(Qt.PointingHandCursor))
        self.browse_button.clicked.connect(self.on_browse_button_clicked)

        # Buttons
        QBtn = QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        self.buttonBox = QDialogButtonBox(QBtn)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        # Add the widgets to a layout
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.file_path_lineEdit)
        path_layout.addWidget(self.browse_button)

        layout = QVBoxLayout()
        layout.addWidget(self.subj_id_lineEdit)
        layout.addWidget(self.file_id_lineEdit)
        layout.addWidget(self.file_description_textEdit)
        layout.addLayout(path_layout)
        layout.addItem(QSpacerItem(40, 20, QSizePolicy.Minimum,
                                   QSizePolicy.Expanding))
        layout.addWidget(self.buttonBox)
        return layout

    def get_file_info(self):
        subj_id = self.subj_id_lineEdit.text()
        recording_id = self.file_id_lineEdit.text()
        file_description = self.file_description_textEdit.toPlainText()
        file_ext = self.name.split('.')[-1]
        return {'subject_id': subj_id,
                'recording_id': recording_id,
                'description': file_description,
                'path': self.path, 'extension': file_ext}

    def on_browse_button_clicked(self):
        # Delete the extension
        fdialog = QFileDialog()
        filter = 'Binary (*.bson);; Binary (*.mat);; Text (*.json)'
        path = fdialog.getSaveFileName(fdialog, 'Save recording file',
                                       self.path, filter=filter)[0]
        split_name = os.path.basename(path).split('.')
        if len(split_name) == 1:
            dialogs.error_dialog('Incorrect file name: %s. '
                                'The extension must be *.%s.%s' %
                                (os.path.basename(path),
                                 self.app_ext, split_name[-1]),
                                'Error')
        elif split_name[-2] != self.app_ext:
            dialogs.error_dialog('Incorrect file name: %s. '
                                 'The extension must be *.%s.%s' %
                                 (os.path.basename(path),
                                  self.app_ext, split_name[-1]),
                                 'Error')
        else:
            self.path = path
            self.name = os.path.basename(path)
            self.file_path_lineEdit.setText(os.path.basename(path))


class BasicConfigWindow(QMainWindow):
    """ This class provides graphical configuration for an app
    """

    close_signal = pyqtSignal(object)

    def __init__(self, sett, medusa_interface, working_lsl_streams_info,
                 theme_colors=None):
        """
        Config constructor.

        Parameters
        ----------
        sett: settings.Settings
            Instance of class Settings defined in settings.py in the app
            directory
        """
        super().__init__()
        self.original_settings = sett
        self.settings = sett

        # Initialize the gui application
        self.theme_colors = gui_utils.get_theme_colors('dark') if \
            theme_colors is None else theme_colors
        self.stl = gui_utils.set_css_and_theme(self, '../gui/style.css',
                                               self.theme_colors)
        self.setWindowIcon(QIcon('gui/images/medusa_favicon.png'))
        self.setWindowTitle('Default configuration window')
        self.changes_made = False

        # Create layout
        self.main_layout = QVBoxLayout()

        # Custom interface
        self.text_edit = QTextEdit()
        self.main_layout.addWidget(self.text_edit)

        # % IMPORTANT % Mandatory buttons
        self.buttons_layout = QVBoxLayout()
        self.button_reset = QPushButton('Reset')
        self.button_save = QPushButton('Save')
        self.button_load = QPushButton('Load')
        self.button_done = QPushButton('Done')
        self.buttons_layout.addWidget(self.button_reset)
        self.buttons_layout.addWidget(self.button_save)
        self.buttons_layout.addWidget(self.button_load)
        self.buttons_layout.addWidget(self.button_done)
        self.main_layout.addLayout(self.buttons_layout)

        # Add central widget
        self.central_widget = QWidget()
        self.central_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.central_widget)

        # % IMPORTANT % Connect signals
        self.button_reset.clicked.connect(self.reset)
        self.button_save.clicked.connect(self.save)
        self.button_load.clicked.connect(self.load)
        self.button_done.clicked.connect(self.done)
        self.text_edit.textChanged.connect(self.on_text_changed)

        # Set text
        self.text_edit.setText(json.dumps(sett.to_serializable_obj(), indent=4))

        # % IMPORTANT % Show application
        self.show()

    def on_text_changed(self):
        self.changes_made = True

    def reset(self):
        # Set default settings
        self.settings = self.original_settings
        self.text_edit.setText(json.dumps(
            self.settings.to_serializable_obj(), indent=4))

    def save(self):
        fdialog = QFileDialog()
        fname = fdialog.getSaveFileName(
            fdialog, 'Save settings', '../../../config/', 'JSON (*.json)')
        if fname[0]:
            self.settings = self.settings.from_serializable_obj(json.loads(
                self.text_edit.toPlainText()))
            self.settings.save(path=fname[0])

    def load(self):
        """ Opens a dialog to load a configuration file. """
        fdialog = QFileDialog()
        fname = fdialog.getOpenFileName(
            fdialog, 'Load settings', '../../../config/', 'JSON (*.json)')
        if fname[0]:
            self.settings = self.settings.load(fname[0])
            self.text_edit.setText(json.dumps(
                self.settings.to_serializable_obj(), indent=4))

    def done(self):
        """ Shows a confirmation dialog if non-saved changes has been made. """
        self.changes_made = False
        self.close()

    @staticmethod
    def close_dialog():
        """ Shows a confirmation dialog that asks the user if he/she wants to
        close the configuration window.

        Returns
        -------
        output value: QtWidgets.QMessageBox.No or QtWidgets.QMessageBox.Yes
            If the user do not want to close the window, and
            QtWidgets.QMessageBox.Yes otherwise.
        """
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowIcon(QIcon(os.path.join(
            os.path.dirname(__file__), '../gui/images/medusa_favicon.png')))
        msg.setText("Do you want to leave this window?")
        msg.setInformativeText("Non-saved changes will be discarded.")
        msg.setWindowTitle("Row-Col Paradigm")
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        return msg.exec_()

    def closeEvent(self, event):
        """ Overrides the closeEvent in order to show the confirmation dialog.
        """
        if self.changes_made:
            retval = self.close_dialog()
            if retval == QMessageBox.Yes:
                self.close_signal.emit(None)
                event.accept()
            else:
                event.ignore()
        else:
            sett = self.settings.from_serializable_obj(
                json.loads(self.text_edit.toPlainText()))
            self.close_signal.emit(sett)
            event.accept()
