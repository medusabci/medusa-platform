# Python imports
import multiprocessing as mp
import time
# External imports
from PyQt5.QtWidgets import QApplication
# Medusa imports
import resources, constants, exceptions
# App imports
import app_gui
# Medusa core imports
from medusa import components
from medusa import meeg


class App(resources.AppSkeleton):

    def __init__(self, app_settings, app_extension, medusa_interface,
                 app_state, run_state, working_lsl_streams_info):
        # Call superclass constructor
        super().__init__(app_settings, app_extension, medusa_interface,
                         app_state, run_state, working_lsl_streams_info)
        # Set attributes
        self.qt_app = None
        self.app_gui = None
        # Queues to communicate with the AppGui class
        self.queue_to_gui = mp.Queue()
        self.queue_from_gui = mp.Queue()

    def handle_exception(self, ex):
        # Check errors
        if not isinstance(ex, exceptions.MedusaException):
            raise ValueError('Exception is not an instance of '
                             'exceptions.MedusaException. It has not been '
                             'handled correctly!')
        # Take action
        if ex.importance == exceptions.EXCEPTION_CRITICAL:
            self.close_app()

    @exceptions.error_handler()
    def check_lsl_config(self, working_lsl_streams_info):
        # Check LSL config (each app can have different LSL requirements)
        if len(working_lsl_streams_info) > 1:
            return False
        else:
            return True

    @exceptions.error_handler()
    def get_lsl_worker(self):
        """Returns the LSL worker"""
        return list(self.lsl_workers.values())[0]

    @exceptions.error_handler()
    def manager_thread_worker(self):
        while not self.stop:
            # Get event. Check if the queue is empty to avoid blocking calls
            if not self.queue_from_gui.empty():
                self.process_event(self.queue_from_gui.get())
            # Check run state
            if self.run_state.value == constants.RUN_STATE_STOP:
                self.close_app()

    @exceptions.error_handler()
    def main(self):
        # 1 - Change app state to powering on
        self.medusa_interface.app_state_changed(
            constants.APP_STATE_POWERING_ON)
        # 2 - Prepare app
        qt_app = QApplication([])
        self.app_gui = app_gui.AppGui(self.app_settings, self.run_state,
                                      self.queue_to_gui, self.queue_from_gui)
        # 3 - Change app state to power on
        self.medusa_interface.app_state_changed(
            constants.APP_STATE_ON)
        # 4 - Start app (blocking method)
        qt_app.exec()
        # 5 - Change app state to powering off
        self.medusa_interface.app_state_changed(
            constants.APP_STATE_POWERING_OFF)
        # 6 - Save recording
        self.save_file_dialog = resources.SaveFileDialog(
            self.app_info['extension'])
        self.save_file_dialog.accepted.connect(self.on_save_rec_accepted)
        self.save_file_dialog.rejected.connect(self.on_save_rec_rejected)
        qt_app.exec()
        # 7 - Change app state to power off
        self.medusa_interface.app_state_changed(
            constants.APP_STATE_OFF)

    @exceptions.error_handler()
    def process_event(self, event):
        if event['event_type'] == 'update_request':
            # Get the number of samples of the first LSL Stream
            lsl_worker = self.get_lsl_worker()
            self.queue_to_gui.put({
                'event_type': 'update_response',
                'data': lsl_worker.data.shape[0]
            })
        elif event['event_type'] == 'error':
            raise event['exception']
        else:
            raise Exception('Unknown event: %s' % str(event))

    @exceptions.error_handler()
    def close_app(self):
        # Trigger the close event in the Qt app. Returns True if it was
        # closed correctly, and False otherwise. If everything was
        # correct, stop the working threads
        if self.app_gui.close():
            self.stop_working_threads()

    @exceptions.error_handler()
    def on_save_rec_accepted(self, file_info):
        # Get file info
        file_info = self.save_file_dialog.get_file_info()
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
        # Print a message
        self.medusa_interface.log('Recording saved successfully')

    @exceptions.error_handler()
    def on_save_rec_rejected(self):
        pass
