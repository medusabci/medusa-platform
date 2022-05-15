# BUILT-IN MODULES
import multiprocessing as mp
import time
# EXTERNAL MODULES
from PyQt5.QtWidgets import QApplication
# MEDUSA-KERNEL MODULES
from medusa import components
# MEDUSA MODULES
import resources, exceptions
import constants as mds_constants
# APP MODULES
from . import app_constants
from . import app_gui


class App(resources.AppSkeleton):

    def __init__(self, app_info, app_settings, medusa_interface,
                 app_state, run_state, working_lsl_streams_info):
        # Call superclass constructor
        super().__init__(app_info, app_settings, medusa_interface,
                         app_state, run_state, working_lsl_streams_info)
        # Set attributes
        self.qt_app = None
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
                self.close_app(force=True)
                ex.set_handled(True)

    def check_lsl_config(self, working_lsl_streams_info):
        # Check LSL config (each app can have different LSL requirements)
        if len(working_lsl_streams_info) > 1:
            return False
        else:
            return True

    def get_lsl_worker(self):
        """Returns the LSL worker"""
        return list(self.lsl_workers.values())[0]

    def manager_thread_worker(self):
        """If this thread raises an unhandled exception and is terminated,
        the app cannot recover from the error. Thus the importance of unhandled
        exceptions in this method is CRITICAL"""
        while not self.stop:
            # Get event. Check if the queue is empty to avoid blocking calls
            if not self.queue_from_gui.empty():
                self.process_event(self.queue_from_gui.get())
            # Check run state
            if self.run_state.value == mds_constants.RUN_STATE_STOP:
                self.close_app()

    def main(self):
        # 1 - Change app state to powering on
        self.medusa_interface.app_state_changed(
            mds_constants.APP_STATE_POWERING_ON)
        # 2 - Prepare app
        qt_app = QApplication([])
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
        # 6 - Save recording
        self.save_file_dialog = resources.SaveFileDialog(
            self.app_info['extension'])
        self.save_file_dialog.accepted.connect(self.on_save_rec_accepted)
        self.save_file_dialog.rejected.connect(self.on_save_rec_rejected)
        qt_app.exec()
        # 7 - Change app state to power off
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
        # Trigger the close event in the Qt app. Returns True if it was
        # closed correctly, and False otherwise. If everything was
        # correct, stop the working threads
        print('close_app-0')
        if self.app_gui is not None:
            if force:
                self.app_gui.is_close_forced = True
            if self.app_gui.close():
                print('close_app-1')
                self.stop_working_threads()
                print('close_app-2')
            print('close_app-3')

    @exceptions.error_handler(scope='app')
    def on_save_rec_accepted(self):
        file_info = self.save_file_dialog.get_file_info()
        # Experiment data
        exp_data = components.CustomExperimentData(
            **self.app_settings.to_serializable_obj()
        )
        # EEG data
        lsl_worker = self.get_lsl_worker()
        eeg = components.CustomBiosignal(
            timestamps=lsl_worker.timestamps,
            data=lsl_worker.data,
            fs=lsl_worker.receiver.fs,
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

    @exceptions.error_handler(scope='app')
    def on_save_rec_rejected(self):
        pass
