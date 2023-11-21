# Python modules
from abc import abstractmethod
import multiprocessing as mp
import threading as th
import os, time, json
# External modules
from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *
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
                 app_state, run_state, working_lsl_streams_info, rec_info):
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
        working_lsl_streams_info: dict
            Dictionary with the working LSL streams as serializable objects
        rec_info: None or dict
            Dictionary with information that can be used to save files
            automatically
        """
        # Calling superclass constructor
        app_process_name = '%s-process' % app_info['id']
        super().__init__(name=app_process_name)
        # -------------------------- CHECK ERRORS ---------------------------- #
        # ---------------------------- SETTINGS ------------------------------ #
        self.check_settings_config(app_settings)
        self.app_info = app_info
        self.app_settings = app_settings
        self.rec_info = rec_info
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
        self.check_lsl_config(working_lsl_streams_info)
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
            lsl_utils.LSLStreamWrapper.from_serializable_obj(
                ser_lsl_str)
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

    def get_file_path_from_rec_info(self):
        """This function builds a path to save the recording using the rec_info
        dict. It can be overwritten to implement custom behaviour.
        """
        # Check
        if self.rec_info['path'] is None or \
                not os.path.isdir(self.rec_info['path']):
            return None
        if self.rec_info['file_ext'] is None or \
                not self.rec_info['file_ext'] in ['bson', 'mat', 'json']:
            return None
        if self.rec_info['rec_id'] is None or \
                len(self.rec_info['rec_id']) == 0:
            return None
        # Get rec path
        file_path = '%s/%s.%s.%s' % (os.path.abspath(self.rec_info['path']),
                                     self.rec_info['rec_id'],
                                     self.app_info['extension'],
                                     self.rec_info['file_ext'])
        # Check if already exists
        if os.path.exists(file_path):
            return None
        return file_path

    @abstractmethod
    def handle_exception(self, ex):
        """This function handles all the exceptions in this process

        Parameters
        ----------
        ex : Exception
             Exception or subclasses
        """
        raise NotImplementedError

    @abstractmethod
    def check_lsl_config(self, working_lsl_streams_info):
        """This function has to check the LSL config. For example, some apps
        may require an LSL stream with a specific name, or a minimum of 2 LSL
        streams, etc. It must return True if the lsl config is correct and
        the App can proceed, and False otherwise.

        Parameters
        ----------
        working_lsl_streams_info: dict
            Dict with the LSL streams information available on MEDUSA

        Returns
        -------
        check: bool
            True if everything is correct, False otherwise
        """
        raise NotImplementedError

    @abstractmethod
    def check_settings_config(self, app_settings):
        """This function has to check the run settings if needed.

        Parameters
        ----------
        app_settings: settings.Settings
            Class with the app settings for this run

        Returns
        -------
        check: bool
            True if everything is correct, False otherwise
        """
        raise NotImplementedError

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
        raise NotImplementedError

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
            # 6 - Stop working threads
            # 7 - Save recording
            # 8 - Change app state to power off
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_OFF)
        """
        raise NotImplementedError

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
        if receiver.lsl_stream.lsl_stream_inlet is None:
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
        self.receiver.flush_stream()
        while not self.stop:
            # Get data
            try:
                chunk_data, chunk_times = self.receiver.get_chunk()
            except exceptions.LSLStreamTimeout as e:
                error_counter += 1
                if error_counter > 5:
                    raise exceptions.MedusaException(
                        e, importance='important',
                        msg='LSLStreamAppWorker is not receiving signal from '
                            '%s. Is the device connected?' % self.receiver.name,
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

    def log(self, msg, style=None, mode='append'):
        """Prints a log message in medusa cmd

        Parameters
        ----------
        msg : str
            Message to print
        style: dict
            Dictionary with the desired CSS style.
            E.g., {'color':'white', 'font-style': 'italic'}
        mode: str {'append', 'replace'}
            Mode append cretes a new message in the log panel. Mode replace
            removes the last line and place the new one. This mode is designed
            for repetitive messages.
        """
        self.queue_to_medusa.put({'info_type': self.INFO_LOG,
                                  'info': msg,
                                  'style': style,
                                  'mode': mode})

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

    def __init__(self, rec_info, app_ext, theme_colors=None):
        """Class constructor

        Parameters
        ----------
        app_ext: str
            App extension
        theme_colors: dict or None
            Theme colors
        """
        super().__init__(window_title='Save recording file',
                         theme_colors=theme_colors)
        self.rec_info = rec_info
        self.app_ext = app_ext
        # Check path
        if not os.path.exists(self.rec_info['path']):
            self.rec_info['path'] = os.path.abspath('../data')
        # Check recording id
        if self.rec_info['rec_id'] is None or \
                len(self.rec_info['rec_id']) == 0:
            self.rec_info['rec_id'] = self.get_default_date_format()
        # File name
        self.file_name = '%s.%s.%s' % (self.rec_info['rec_id'], app_ext,
                                       self.rec_info['file_ext'])
        self.path = os.path.join(self.rec_info['path'], self.file_name)

        # Default file name
        self.file_path_lineEdit.setText(self.path)

        # Show
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.show()

    def create_layout(self):
        # Fields
        self.study_id_lineEdit = QLineEdit()
        self.study_id_lineEdit.setPlaceholderText('Study id')
        self.subj_id_lineEdit = QLineEdit()
        self.subj_id_lineEdit.setPlaceholderText('Subject id')
        self.session_id_lineEdit = QLineEdit()
        self.session_id_lineEdit.setPlaceholderText('Session id')
        self.description_textEdit = QTextEdit()
        self.description_textEdit.setProperty('class', 'file_dialog')
        self.description_textEdit.setPlaceholderText(
            'Description of the recording')

        # File path
        self.file_path_lineEdit = QLineEdit()
        # self.file_path_lineEdit.setProperty('class', 'file_dialog')
        self.file_path_lineEdit.setReadOnly(True)
        self.browse_button = QToolButton()
        self.browse_button.setIcon(gui_utils.get_icon(
            'search.svg', theme_colors=self.theme_colors))
        # self.browse_button.setProperty('class', 'file_dialog')
        # self.browse_button.setCursor(QCursor(Qt.PointingHandCursor))
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

        layout = QFormLayout()
        layout.addRow(QLabel('Study id'), self.study_id_lineEdit)
        layout.addRow(QLabel('Subject id'), self.subj_id_lineEdit)
        layout.addRow(QLabel('Session id'), self.session_id_lineEdit)
        layout.addRow(QLabel('Description'), self.description_textEdit)
        layout.addRow(QLabel('Save path'), path_layout)
        layout.addItem(QSpacerItem(40, 20, QSizePolicy.Minimum,
                                   QSizePolicy.Expanding))
        layout.addWidget(self.buttonBox)
        return layout

    @staticmethod
    def get_default_date_format() -> str:
        return time.strftime("%d-%m-%Y_%H%M%S", time.localtime())

    def get_rec_info(self):
        study_id = self.study_id_lineEdit.text()
        subj_id = self.subj_id_lineEdit.text()
        session_id = self.session_id_lineEdit.text()
        file_description = self.description_textEdit.toPlainText()
        path = os.path.dirname(self.path)
        split_path = os.path.basename(self.path).split('.')
        rec_id = ''.join(split_path[:-2])
        app_ext = split_path[-2]
        file_ext = split_path[-1]
        # Update rec info dict
        self.rec_info['rec_id'] = rec_id
        self.rec_info['file_ext'] = file_ext
        self.rec_info['path'] = path
        self.rec_info['study_id'] = study_id
        self.rec_info['subject_id'] = subj_id
        self.rec_info['session_id'] = session_id
        self.rec_info['description'] = file_description
        return self.path, self.rec_info

    def on_browse_button_clicked(self):
        # Delete the extension
        filter = 'Binary (*.bson);; Binary (*.mat);; Text (*.json)'
        path = QFileDialog.getSaveFileName(caption='Save recording file',
                                           dir=self.path,
                                           filter=filter)[0]
        # Check that the user selected a file name
        if len(path) == 0:
            return
        # Check format errors
        split_name = os.path.basename(path).split('.')
        if len(split_name) < 3:
            dialogs.error_dialog('Incorrect file name: %s. '
                                 'The extension must be *.%s.%s' %
                                 (os.path.basename(path),
                                  self.app_ext, split_name[-1]),
                                 'Error')
            return
        if split_name[-2] != self.app_ext:
            dialogs.error_dialog('Incorrect file name: %s. '
                                 'The extension must be *.%s.%s' %
                                 (os.path.basename(path),
                                  self.app_ext, split_name[-1]),
                                 'Error')
            return
        if split_name[-1] not in ['bson', 'mat', 'json']:
            dialogs.error_dialog('Current supported formats are bson, mat and '
                                 'json', 'Error')
            return
        # Save info
        self.path = path
        self.file_path_lineEdit.setText(path)


class BasicConfigWindow(QDialog):
    """ This class provides a basic graphical configuration for an app
    """

    close_signal = Signal(object)

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

        # Set style
        self.theme_colors = theme_colors
        self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)
        self.setWindowIcon(QIcon('gui/images/medusa_task_icon.png'))
        self.setWindowTitle('Default configuration window')
        self.resize(640, 480)

        # Attributes
        self.medusa_interface = medusa_interface
        self.working_lsl_streams_info = working_lsl_streams_info
        self.original_settings = sett
        self.settings = sett
        self.changes_made = False

        # Set layout
        layout = self.create_layout()
        self.setLayout(layout)

        # Set text
        self.text_edit.setText(
            json.dumps(self.settings.to_serializable_obj(), indent=4))

        # Show application
        self.setModal(True)
        self.show()

    def create_layout(self):
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

        # % IMPORTANT % Connect signals
        self.button_reset.clicked.connect(self.btn_reset)
        self.button_save.clicked.connect(self.btn_save)
        self.button_load.clicked.connect(self.btn_load)
        self.button_done.clicked.connect(self.btn_done)
        self.text_edit.textChanged.connect(self.on_text_changed)

        return self.main_layout

    def on_text_changed(self):
        self.changes_made = True

    def btn_reset(self):
        # Set default settings
        self.settings = self.original_settings
        self.text_edit.setText(json.dumps(
            self.settings.to_serializable_obj(), indent=4))

    def btn_save(self):
        fdialog = QFileDialog()
        fname = fdialog.getSaveFileName(
            fdialog, 'Save settings', '../config/', 'JSON (*.json)')
        if fname[0]:
            self.settings = self.settings.from_serializable_obj(json.loads(
                self.text_edit.toPlainText()))
            self.settings.save(path=fname[0])

    def btn_load(self):
        """ Opens a dialog to load a configuration file. """
        fdialog = QFileDialog()
        fname = fdialog.getOpenFileName(
            fdialog, 'Load settings', '../config/', 'JSON (*.json)')
        if fname[0]:
            self.settings = self.settings.load(fname[0])
            self.text_edit.setText(json.dumps(
                self.settings.to_serializable_obj(), indent=4))

    def btn_done(self):
        """ Shows a confirmation dialog if non-saved changes has been made. """
        self.changes_made = False
        self.close()

    @staticmethod
    def close_dialog():
        """ Shows a confirmation dialog that asks the user if he/she wants to
        close the configuration window.

        Returns
        -------
        output value: boolean
            False the user do not want to close the window, and True otherwise.
        """
        res = dialogs.confirmation_dialog(
            text='Do you want to leave this window?',
            title='Row-Col Paradigm',
            informative_text='Non-saved changes will be discarded.'
        )
        return res

    def closeEvent(self, event):
        """ Overrides the closeEvent in order to show the confirmation dialog.
        """
        if self.changes_made:
            retval = self.close_dialog()
            if retval:
                self.close_signal.emit(None)
                event.accept()
            else:
                event.ignore()
        else:
            sett = self.settings.from_serializable_obj(
                json.loads(self.text_edit.toPlainText()))
            self.close_signal.emit(sett)
            event.accept()
