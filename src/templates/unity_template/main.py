# BUILT-IN MODULES
import time
import os.path
# EXTERNAL MODULES
from PySide6.QtWidgets import QApplication
# MEDUSA-KERNEL MODULES
from medusa import components
from medusa import meeg, emg, nirs, ecg
# MEDUSA MODULES
import resources, exceptions
import constants as mds_constants
from gui import gui_utils
# APP MODULES
from . import app_controller
from . import app_constants


class App(resources.AppSkeleton):
    """ Main class of the application. For detailed comments about all
        functions, see the superclass code in resources module."""
    def __init__(self, app_info, app_settings, medusa_interface,
                 app_state, run_state, working_lsl_streams_info, rec_info):
        # Call superclass constructor
        super().__init__(app_info, app_settings, medusa_interface, app_state,
                         run_state, working_lsl_streams_info, rec_info)
        # Set attributes
        self.app_controller = None
        self.app_name = app_info["name"]
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
        # This code is just for demonstration purposes, remove for app
        # development.
        if len(working_lsl_streams_info) != 1:
            raise exceptions.IncorrectLSLConfig()

    def check_settings_config(self, app_settings):
        # This code is just for demonstration purposes, remove for app
        # development. The IP address could have any value.
        if app_settings.connection_settings.ip != '127.0.0.1':
            raise exceptions.IncorrectSettingsConfig(
                f"Incorrect IP address: "
                f"{app_settings.connection_settings.ip}")

    def get_lsl_worker(self):
        """Returns the LSL worker"""
        return list(self.lsl_workers.values())[0]

    def send_to_log(self, msg):
        """ Styles a message to be sent to the main MEDUSA log."""
        self.medusa_interface.log(
            msg, {'color': self.log_color, 'font-style': 'italic'})

    def manager_thread_worker(self):
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
        self.app_controller.start_server()
        self.send_to_log(f'[{self.app_name}] TCP server listening!')
        # Wait until UNITY is UP and send the parameters
        while self.app_controller.unity_state.value == \
                app_constants.UNITY_DOWN:
            time.sleep(0.1)
        self.app_controller.send_parameters()
        # Wait until UNITY is ready
        while self.app_controller.unity_state.value == \
                app_constants.UNITY_UP:
            time.sleep(0.1)
        self.send_to_log(f'[{self.app_name}] Unity is ready to start')
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
        rec_streams_info = self.get_rec_streams_info()
        if file_path is None:
            # Display save dialog to retrieve file_info
            self.save_file_dialog = resources.SaveFileDialog(
                self.rec_info,
                rec_streams_info,
                self.app_info['extension'])
            self.save_file_dialog.accepted.connect(self.on_save_rec_accepted)
            self.save_file_dialog.rejected.connect(self.on_save_rec_rejected)
            qt_app.exec()
        else:
            # Save file automatically
            self.save_recording(file_path, rec_streams_info)
        # 9 - Change app state to power off
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_OFF)

    @exceptions.error_handler(scope='app')
    def process_event(self, event):
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
        rec_streams_info = self.save_file_dialog.get_rec_streams_info()
        self.save_recording(file_path, rec_streams_info)

    @exceptions.error_handler(scope='app')
    def on_save_rec_rejected(self):
        pass

    @exceptions.error_handler(scope='app')
    def save_recording(self, file_path, rec_streams_info):
        # Recording
        rec = components.Recording(
            subject_id=self.rec_info.pop('subject_id'),
            recording_id=self.rec_info.pop('rec_id'),
            date=time.strftime("%d-%m-%Y %H:%M", time.localtime()),
            **self.rec_info)
        # Experiment data
        exp_data = components.CustomExperimentData(
            **self.app_settings.to_serializable_obj())
        rec.add_experiment_data(exp_data, 'exp_data')
        # Streams data
        for lsl_stream in self.lsl_streams_info:
            if not rec_streams_info[lsl_stream.medusa_uid]['enabled']:
                continue
            if lsl_stream.medusa_type == 'EEG':
                lsl_worker = self.lsl_workers[lsl_stream.medusa_uid]
                times, signal = lsl_worker.get_data()
                channel_set = meeg.EEGChannelSet()
                channel_set.set_standard_montage(
                    l_cha=lsl_worker.receiver.l_cha,
                    allow_unlocated_channels=True)
                biosignal = meeg.EEG(
                    times=times,
                    signal=signal,
                    fs=lsl_worker.receiver.fs,
                    channel_set=channel_set,
                    lsl_stream_info=lsl_stream.to_serializable_obj())
            elif lsl_stream.medusa_type == 'ECG':
                lsl_worker = self.lsl_workers[lsl_stream.medusa_uid]
                times, signal = lsl_worker.get_data()
                channel_set = ecg.ECGChannelSet()
                [channel_set.add_channel(label=l) for l in
                 lsl_worker.receiver.l_cha]
                biosignal = ecg.ECG(
                    times=times,
                    signal=signal,
                    fs=lsl_worker.receiver.fs,
                    channel_set=channel_set,
                    lsl_stream_info=lsl_stream.to_serializable_obj())
            elif lsl_stream.medusa_type == 'EMG':
                lsl_worker = self.lsl_workers[lsl_stream.medusa_uid]
                times, signal = lsl_worker.get_data()
                channel_set = lsl_stream.cha_info
                biosignal = emg.EMG(
                    times=times,
                    signal=signal,
                    fs=lsl_worker.receiver.fs,
                    channel_set=channel_set,
                    lsl_stream_info=lsl_stream.to_serializable_obj())
            elif lsl_stream.medusa_type == 'NIRS':
                lsl_worker = self.lsl_workers[lsl_stream.medusa_uid]
                times, signal = lsl_worker.get_data()
                channel_set = lsl_stream.cha_info
                biosignal = nirs.NIRS(
                    times=times,
                    signal=signal,
                    fs=lsl_worker.receiver.fs,
                    channel_set=channel_set,
                    lsl_stream_info=lsl_stream.to_serializable_obj())
            elif lsl_stream.medusa_type == 'CustomBiosignalData':
                lsl_worker = self.lsl_workers[lsl_stream.medusa_uid]
                times, signal = lsl_worker.get_data()
                channel_set = lsl_stream.cha_info
                fs = lsl_worker.receiver.fs
                biosignal = components.CustomBiosignalData(
                    times=times,
                    signal=signal,
                    fs=fs,
                    channel_set=channel_set,
                    lsl_stream_info=lsl_stream.to_serializable_obj())
            else:
                raise ValueError('Unknown biosignal type %s!' %
                                 lsl_stream.medusa_type)
            # Save stream
            att_key = rec_streams_info[lsl_stream.medusa_uid]['att-name']
            rec.add_biosignal(biosignal, att_key)
        # Save recording
        rec.save(file_path)
        # Print a message
        self.medusa_interface.log('Recording saved successfully')

