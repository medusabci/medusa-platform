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
