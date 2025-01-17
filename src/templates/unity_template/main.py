# BUILT-IN MODULES
import time
import os.path
# EXTERNAL MODULES
from PySide6.QtWidgets import QApplication
# MEDUSA-KERNEL MODULES
from medusa import components
from medusa import meeg
# MEDUSA MODULES
import resources, exceptions
import constants as mds_constants
from gui import gui_utils
# APP MODULES
from . import app_controller
from . import app_constants


class App(resources.AppSkeleton):
    """ Class that runs in a separate process to set up the app.

        This class will run in a separate process to represent the MEDUSA server
        side of the application. Its aim is to control the life cycle of the
        developed application, as well as to communicate with the main GUI of
        MEDUSA to print logs. The main() function is going to control life cycle
        by setting up the ``AppController`` (server for communicating with Unity
        clients): initializing the TCP server, opening up the Unity's .exe, and
        communicating with it. As here we do not have a GUI, the Manager thread
        via `manager_thread_worker()` will use the ``AppController`` to send and
        receive messages to and from Unity. This thread will be also devoted to
        process EEG signals, as it has access to all LSL workers.

        In this example, this App will start an Unity application that shows us
        the amount of EEG samples recorded by the LSL. The first thing the
        Unity app will do whenever is ready will be to wait for parameters.
        MEDUSA will send them immediately, according to the `settings.py` file.
        After an acknowledgment from Unity, the application starts by pressing
        the START button. Unity will request us an update with a rate according
        to the parameter `updates_per_min`. Whenever we receive a request,
        MEDUSA is going to answer it by sending the current number of recorded
        samples. Unity will listen for that and update its GUI.

        Attributes
        ----------
        app_controller : AppController
            Controller that helps us to communicate with Unity.
        queue_to_controller : queue.Queue
            Queue used to send messages to ``AppController``.
        queue_from_controller : queue.Queue
            Queue used to receive messages from ``AppController``.
    """

    def __init__(self, app_info, app_settings, medusa_interface,
                 app_state, run_state, working_lsl_streams_info, rec_info):
        # Call superclass constructor
        super().__init__(app_info, app_settings, medusa_interface, app_state,
                         run_state, working_lsl_streams_info, rec_info)
        # Set attributes
        self.app_controller = None
        # Colors
        theme_colors = gui_utils.get_theme_colors('dark')
        self.log_color = theme_colors['THEME_TEXT_ACCENT']

    def handle_exception(self, ex):
        if not isinstance(ex, exceptions.MedusaException):
            raise ValueError('Unhandled exception')
        if isinstance(ex, exceptions.MedusaException):
            # Take actions
            if ex.importance == 'critical':
                if self.app_controller.unity_state != \
                        app_constants.UNITY_DOWN:
                    self.app_controller.send_command(
                        {"event_type": "exception"})
                self.app_controller.close()
                ex.set_handled(True)

    def check_lsl_config(self, working_lsl_streams_info):
        if len(working_lsl_streams_info) != 1:
            raise exceptions.IncorrectLSLConfig()

    def check_settings_config(self, app_settings):
        """Check settings config.
        By default, this function check if unity path exits."""

        if not os.path.exists(app_settings.connection_settings.path_to_exe):
            raise exceptions.IncorrectSettingsConfig(
                f"Incorrect path of Unity file: "
                f"{app_settings.connection_settings.path_to_exe}")

    def get_lsl_worker(self):
        """Returns the LSL worker"""
        return list(self.lsl_workers.values())[0]

    def send_to_log(self, msg):
        """ Styles a message to be sent to the main MEDUSA log. """
        self.medusa_interface.log(
            msg, {'color': self.log_color, 'font-style': 'italic'})

    def manager_thread_worker(self):
        """Manager thread worker that controls the application flow.

        To set up correctly the communication between MEDUSA and Unity, it
        is required to initialize things correctly. First, it waits MEDUSA
        to be ready by checking `run_state`. Then, it waits until the main()
        function instantiates the ``AppController``, and afterward initiates
        the server by calling `app_controller.start_server()`. In parallel,
        the main() function is opening up the Unity's application, so this
        thread waits until it is up. When it is up, then it sends the
        required parameters to Unity via the ``AppController`` and waits
        until Unity confirms us that everything is ready. When user presses
        the START button, it sends a `play` command to Unity via the
        ``AppController``. The rest of the code is intended to listen for
        pause and stop events to notify Unity about them.
        """
        TAG = '[apps/dev_app_unity/App/manager_thread_worker]'
        # Function to close everything
        def close_everything():
            # Notify Unity that it must stop
            self.app_controller.stop()
            print(TAG, 'Close signal emitted to Unity.')
            # Wait until the Unity server notify us that the app is closed
            while self.app_controller.unity_state.value != \
                    app_constants.UNITY_FINISHED:
                pass
            print(TAG, 'Unity application closed!')
            # Exit the loop
            self.stop = True
        # Wait until MEDUSA is ready
        print(TAG, "Waiting MEDUSA to be ready...")
        while self.run_state.value != mds_constants.RUN_STATE_READY:
            time.sleep(0.1)
        # Wait until the app_controller is initialized
        while self.app_controller is None:
            time.sleep(0.1)
        # Set up the TCP server and wait for the Unity client
        self.send_to_log('Setting up the TCP server...')
        self.app_controller.start_server()
        # Wait until UNITY is UP and send the parameters
        while self.app_controller.unity_state.value == \
                app_constants.UNITY_DOWN:
            time.sleep(0.1)
        self.app_controller.send_parameters()
        # Wait until UNITY is ready
        while self.app_controller.unity_state.value == \
                app_constants.UNITY_UP:
            time.sleep(0.1)
        self.send_to_log('Unity is ready to start')
        # Change app state to power on
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_ON)
        # If play is pressed
        while self.run_state.value == mds_constants.RUN_STATE_READY:
            time.sleep(0.1)
        if self.run_state.value == mds_constants.RUN_STATE_RUNNING:
            self.app_controller.play()
        # Check for an early stop
        if self.run_state.value == mds_constants.RUN_STATE_STOP:
            close_everything()
        # Loop
        while not self.stop:
            # Check for pause
            if self.run_state.value == mds_constants.RUN_STATE_PAUSED:
                self.app_controller.pause()
                while self.run_state.value == mds_constants.RUN_STATE_PAUSED:
                    time.sleep(0.1)
                # If resumed
                if self.run_state.value == mds_constants.RUN_STATE_RUNNING:
                    self.app_controller.resume()
            # Check for stop
            if self.run_state.value == mds_constants.RUN_STATE_STOP:
                close_everything()
        print(TAG, 'Terminated')

    def main(self):
        """Controls the main life cycle of the ``App`` class.

        First, changes the app state to powering on and sets up the
        ``AppController`` instance. Then, changes the app state to on. It
        waits until the TCP Server instantiated by the ``AppController`` is
        up, and afterward tells the ``AppController`` to open the Unity's
        .exe application, which is a blocking process. When the application
        is closed, this function changes the app state to poweing off and
        shows a dialog to save the file (only if we have data available).
        Finally, it changes the app state to off and dies.
        """

        # 1 - Change app state to powering on
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_POWERING_ON)
        # 2 - Set up the controller that starts the TCP server
        self.app_controller = app_controller.AppController(
            callback=self,
            app_settings=self.app_settings,
            run_state=self.run_state)
        # 3 - Wait until server is UP, start the unity app and block the
        # execution until it is closed
        while self.app_controller.server_state.value == \
                app_constants.SERVER_DOWN:
            time.sleep(0.1)
        # 4 - Start application (blocking method)
        self.app_controller.start_application()
        # 5 - Close
        if self.app_controller.server_state.value != app_constants.SERVER_DOWN:
            self.app_controller.close()
        while self.app_controller.server_state.value == app_constants.SERVER_UP:
            time.sleep(0.1)
        # 6 - Change app state to powering off
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_POWERING_OFF)
        # 7 - Stop working threads
        self.stop_working_threads()
        # 8 - Save recording
        qt_app = QApplication()
        file_path = self.get_file_path_from_rec_info()
        if file_path is None:
            # Display save dialog to retrieve file_info
            self.save_file_dialog = resources.SaveFileDialog(
                self.rec_info,
                self.app_info['extension'])
            self.save_file_dialog.accepted.connect(self.on_save_rec_accepted)
            self.save_file_dialog.rejected.connect(self.on_save_rec_rejected)
            qt_app.exec()
        else:
            # Save file automatically
            self.save_recording(file_path)
        # 9 - Change app state to power off
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_OFF)

    @exceptions.error_handler(scope='app')
    def process_event(self, event):
        """Process any interesting event.

        These events may be called by the `manager_thread_worker` whenever
        Unity requests any kind-of processing. As we do not have any MEDUSA
        GUI, this function can be also directly called by the instance of
        ``AppController`` if necessary.

        In this case, the possible events, encoded in 'event_type' are:
            - 'request_samples': Unity requires us to send the current
            registered samples of the LSL stream.
            - 'close': Unity said it has been closed, so we need to close
            everything.
        """
        # self.send_to_log('Message from Unity: %s' % str(event))
        if event["event_type"] == 'request_samples':
            # Get the current number of samples of the first LSL stream
            # and send it to Unity again
            lsl_worker = self.get_lsl_worker()
            no_samples = lsl_worker.data.shape[0]
            self.app_controller.send_command({"event_type": "samplesUpdate",
                                              "no_samples": no_samples})

    @exceptions.error_handler(scope='app')
    def on_save_rec_accepted(self):
        file_path, self.rec_info = self.save_file_dialog.get_rec_info()
        self.save_recording(file_path)

    @exceptions.error_handler(scope='app')
    def on_save_rec_rejected(self):
        pass

    @exceptions.error_handler(scope='app')
    def save_recording(self, file_path):
        # Experiment data
        exp_data = components.CustomExperimentData(
            **self.app_settings.to_serializable_obj()
        )
        # Signal
        lsl_worker = self.get_lsl_worker()
        signal = components.CustomBiosignal(
            timestamps=lsl_worker.timestamps,
            data=lsl_worker.data,
            fs=lsl_worker.receiver.fs,
            equipement=lsl_worker.receiver.name)
        # Recording
        rec = components.Recording(
            subject_id=self.rec_info.pop('subject_id'),
            recording_id=self.rec_info.pop('rec_id'),
            date=time.strftime("%d-%m-%Y %H:%M", time.localtime()),
            **self.rec_info)
        rec.add_biosignal(signal)
        rec.add_experiment_data(exp_data)
        rec.save(file_path)
        # Print a message
        self.medusa_interface.log('Recording saved successfully')
