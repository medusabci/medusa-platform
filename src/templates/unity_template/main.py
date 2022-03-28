# Python imports
import multiprocessing as mp
import time
# External imports
from PyQt5.QtWidgets import QApplication
# Medusa imports
import resources, constants, exceptions
from app_controller import AppController
from constants import *
from gui import gui_utils
# Medusa core imports
from medusa import components
from medusa import meeg


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

    def __init__(self, app_settings, app_extension, medusa_interface,
                 app_state, run_state, working_lsl_streams_info):
        """ Constructor method for the ``App`` class.

        Parameters
        ----------
        app_settings : Settings
        app_extension : str
        medusa_interface : components.MedusaInterface
        app_state : multiprocessing.Value
        run_state : multiprocessing.Value
        working_lsl_streams_info : list of lsl_utils.LSLStreamWrapper
        """
        try:
            # Call superclass constructor
            super().__init__(app_settings, app_extension, medusa_interface,
                             app_state, run_state, working_lsl_streams_info)
            # Set attributes
            self.app_controller = None
            # Queues to communicate with the AppGui class
            self.queue_to_controller = mp.Queue()
            self.queue_from_controller = mp.Queue()
            # Color
            theme_colors = gui_utils.get_theme_colors('dark')
            self.log_color = theme_colors['THEME_TEXT_ACCENT']
        except Exception as ex:
            self.handle_exception(ex)

    def handle_exception(self, ex):
        # Treat exception
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_unity/App/handle_exception')
        # Notify exception to gui main
        self.medusa_interface.error(ex)

    def check_lsl_config(self, working_lsl_streams_info):
        # Check LSL config (each app can have different LSL requirements)
        try:
            if len(working_lsl_streams_info) > 1:
                return False
            else:
                return True
        except Exception as ex:
            self.handle_exception(ex)

    def manager_thread_worker(self):
        """ Manager thread worker that controls the application flow.

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
            self.app_controller.stop()  # Send the stop signal to unity
            print(TAG, 'Close signal emitted to Unity.')

            # Wait until the Unity server notify us that the app is closed
            while self.app_controller.unity_state.value == UNITY_READY:
                time.sleep(0.1)
            print(TAG, 'Unity application closed!')

            # Close the main app and exit the loop
            self.stop = True
            self.close_app()

        # Worker flow
        try:
            # Wait until MEDUSA is ready
            print(TAG, "Waiting MEDUSA to be ready...")
            while self.run_state.value != constants.RUN_STATE_READY:
                time.sleep(0.1)

            # Wait until the app_controller is initialized
            while self.app_controller is None: time.sleep(0.1)

            # Set up the TCP server and wait for the Unity client
            self.send_to_log('Setting up the TCP server...')
            self.app_controller.start_server()

            # Wait until UNITY is UP and send the parameters
            while self.app_controller.unity_state.value == UNITY_DOWN:
                time.sleep(0.1)
            self.app_controller.send_parameters()

            # Wait until UNITY is ready
            while self.app_controller.unity_state.value == UNITY_UP:
                time.sleep(0.1)
            self.send_to_log('Unity is ready to start')

            # If play is pressed
            while self.run_state.value == constants.RUN_STATE_READY:
                time.sleep(0.1)
            if self.run_state.value == constants.RUN_STATE_RUNNING:
                self.app_controller.play()

            # Check for an early stop
            if self.run_state.value == constants.RUN_STATE_STOP:
                close_everything()

            # Loop
            while not self.stop:
                # TODO: should we process events here instead of direct callback?

                # Check for pause
                if self.run_state.value == constants.RUN_STATE_PAUSED:
                    self.app_controller.pause()
                    while self.run_state.value == constants.RUN_STATE_PAUSED: time.sleep(0.1)
                    # If resumed
                    if self.run_state.value == constants.RUN_STATE_RUNNING:
                        self.app_controller.resume()

                # Check for stop
                if self.run_state.value == constants.RUN_STATE_STOP:
                    close_everything()
            print(TAG, 'Terminated')
        except Exception as ex:
            self.handle_exception(ex)

    def main(self):
        """ Controls the main life cycle of the ``App`` class.

            First, changes the app state to powering on and sets up the
            ``AppController`` instance. Then, changes the app state to on. It
            waits until the TCP Server instantiated by the ``AppController`` is
            up, and afterward tells the ``AppController`` to open the Unity's
            .exe application, which is a blocking process. When the application
            is closed, this function changes the app state to poweing off and
            shows a dialog to save the file (only if we have data available).
            Finally, it changes the app state to off and dies.
        """
        try:
            # 1 - Change app state to powering on
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_POWERING_ON)
            # 2 - Set up the controller that starts the TCP server
            self.app_controller = AppController(
                callback=self,
                app_settings=self.app_settings,
                run_state=self.run_state)
            # 3 - Change app state to power on
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_ON)
            # 4 - Start the Unity app and block the execution until it is closed
            while self.app_controller.server_state.value == SERVER_DOWN:
                time.sleep(0.1)
            self.app_controller.start_application()
            # while self.app_controller: time.sleep(1)  # For debugging Unity: comment the previous line and uncomment this one
            # 5 - Change app state to powering off
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_POWERING_OFF)
            # 6 - Save recording
            if self.get_lsl_worker().data.shape[0] > 0:
                app = QApplication([])  # Initialize a QtApplication in this process, otherwise the saving dialog won't show
                self.save_recording()
            # 7 - Change app state to power off
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_OFF)
        except Exception as ex:
            self.handle_exception(ex)

    def process_event(self, event):
        """ Process any interesting event.

            These events may be called by the `manager_thread_worker` whenever
            Unity requests any kind-of processing. As we do not have any MEDUSA
            GUI, this function call be also directly called by the instance of
            ``AppController`` if necessary.

            In this case, the possible events, encoded in 'event_type' are:
                - 'request_samples': Unity requires us to send the current
                registered samples of the LSL stream.
                - 'close': Unity said it has been closed, so we need to close
                everything.
        """
        try:
            self.send_to_log('Message from Unity: %s' % str(event))
            if event["event_type"] == 'request_samples':
                # Get the current number of samples of the first LSL stream
                # and send it to Unity again
                lsl_worker = self.get_lsl_worker()
                no_samples = lsl_worker.data.shape[0]
                self.app_controller.send_command({"event_type": "samplesUpdate",
                                                  "no_samples": no_samples})
            elif event["event_type"] == 'close':
                self.close_app()
        except Exception as ex:
            self.handle_exception(ex)

    def close_app(self):
        """ Closes the ``AppController`` and working threads. """
        try:
            # Trigger the close event in the AppController. Returns True if
            # closed correctly, and False otherwise. If everything was
            # correct, stop the working threads
            if self.app_controller.close():
                self.stop_working_threads()
            self.app_controller = None
        except Exception as ex:
            self.handle_exception(ex)

    def save_recording(self):
        """Stops the run and saves the corresponding files. """
        try:
            # Show file info
            save_file_dialog = resources.SaveFileDialog(self.app_extension)
            res = save_file_dialog.exec()
            if res:
                file_info = save_file_dialog.get_file_info()
                self.on_save_rec_accepted(file_info)
            else:
                self.on_save_rec_rejected()
        except Exception as ex:
            self.handle_exception(ex)

    def on_save_rec_accepted(self, file_info):
        """ Converts the data into a ``CustomExperimentData`` class and closes
        the current application. """
        try:
            # Experiment data
            exp_data = components.CustomExperimentData(
                **self.app_settings.to_serializable_obj()
            )
            # EEG data
            lsl_worker = self.get_lsl_worker()
            channels = meeg.EEGChannelSet()
            channels.set_standard_channels(lsl_worker.receiver.l_cha)
            eeg = meeg.EEG(lsl_worker.timestamps,
                           lsl_worker.data,
                           lsl_worker.receiver.fs,
                           channels,
                           equipement=lsl_worker.receiver.name)
            # Recording
            rec = components.Recording(
                subject_id=file_info['subject_id'],
                recording_id=file_info['recording_id'],
                description=file_info['description'],
                date=time.strftime("%d-%m-%Y %H:%M", time.localtime())
            )
            rec.add_biosignal(eeg)
            rec.add_experiment_data(exp_data)
            rec.save(file_info['path'])

            # Stop app by finishing all working threads and the main process
            self.close()
        except Exception as ex:
            self.handle_exception(ex)

    def on_save_rec_rejected(self):
        """ Closes the app without saving the EEG data. """
        try:
            # Stop app by finishing all working threads and the main process
            self.close()
        except Exception as e:
            self.handle_exception(e)

    def get_lsl_worker(self):
        """ Returns the LSL worker. """
        return list(self.lsl_workers.values())[0]

    def send_to_log(self, msg):
        """ Styles a message to be sent to the main MEDUSA log. """
        self.medusa_interface.log(msg,
                                  {'color': self.log_color,
                                   'font-style': 'italic'})