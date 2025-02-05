# BUILT-IN MODULES
import multiprocessing as mp
import time
# EXTERNAL MODULES
from PySide6.QtWidgets import QApplication
# MEDUSA-KERNEL MODULES
from medusa import components
# MEDUSA MODULES
import resources, exceptions
import constants as mds_constants
from medusa import meeg, emg, nirs, ecg
# APP MODULES
from . import app_constants
from . import app_gui


class App(resources.AppSkeleton):
    """ Main class of the application. For detailed comments about all
        functions, see the superclass code in resources module."""
    def __init__(self, app_info, app_settings, medusa_interface,
                 app_state, run_state, working_lsl_streams_info, rec_info):
        # Call superclass constructor
        super().__init__(app_info, app_settings, medusa_interface, app_state,
                         run_state, working_lsl_streams_info, rec_info)
        # Set attributes
        self.app_gui = None
        # Queues to communicate with the AppGui class
        self.queue_to_gui = mp.Queue()
        self.queue_from_gui = mp.Queue()

    def handle_exception(self, ex):
        if not isinstance(ex, exceptions.MedusaException):
            raise ValueError('Unhandled exception')
        if isinstance(ex, exceptions.MedusaException):
            # Take actions
            if ex.importance == 'critical':
                self.app_gui.force_close = True
                self.app_gui.working_thread.close_app()
                ex.set_handled(True)

    def check_lsl_config(self, working_lsl_streams_info):
        # This code is just for demonstration purposes, remove for app
        # development.
        if len(working_lsl_streams_info) != 1:
            raise exceptions.IncorrectLSLConfig()

    def check_settings_config(self, app_settings):
        pass

    def get_lsl_worker(self):
        """Returns the LSL worker"""
        return list(self.lsl_workers.values())[0]

    def manager_thread_worker(self):
        while not self.stop:
            # Get event. Check if the queue is empty to avoid blocking calls
            if not self.queue_from_gui.empty():
                self.process_event(self.queue_from_gui.get())

    def main(self):
        # 1 - Change app state to powering on
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_POWERING_ON)
        # 2 - Prepare app
        qt_app = QApplication()
        self.app_gui = app_gui.AppGui(self.app_settings, self.run_state,
                                      self.queue_to_gui, self.queue_from_gui)
        # 3 - Change app state to power on
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_ON)
        # 4 - Start app (blocking method)
        qt_app.exec()
        # 5 - Change app state to powering off
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_POWERING_OFF)
        # 6 - Stop working threads
        self.stop_working_threads()
        # 7 - Save recording
        file_path = self.get_file_path_from_rec_info()
        rec_streams_info = self.get_rec_streams_info()
        if file_path is None:
            # Display save dialog to retrieve file_info
            self.save_file_dialog = resources.SaveFileDialog(
                rec_info=self.rec_info,
                rec_streams_info=rec_streams_info,
                app_ext=self.app_info['extension'],
                allowed_formats=self.allowed_formats)
            self.save_file_dialog.accepted.connect(self.on_save_rec_accepted)
            self.save_file_dialog.rejected.connect(self.on_save_rec_rejected)
            qt_app.exec()
        else:
            # Save file automatically
            self.save_recording(file_path, rec_streams_info)
        # 8 - Change app state to power off
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_OFF)

    def process_event(self, event):
        if event['event_type'] == 'update_request':
            # Get the number of samples of the first LSL Stream
            lsl_worker = self.get_lsl_worker()
            self.queue_to_gui.put({
                'event_type': 'update_response',
                'data': lsl_worker.data.shape[0]
            })
        elif event['event_type'] == 'error':
            print('event_type')
            raise event['exception']
        else:
            raise ValueError('Unknown event: %s' % str(event))

    def close_app(self, force=False):
        pass

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
