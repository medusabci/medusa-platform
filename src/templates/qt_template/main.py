# Python imports
import multiprocessing as mp
import time
# External imports
from PyQt5.QtWidgets import QApplication
# Medusa imports
import resources, constants, exceptions
from app_gui import AppGui
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
        # Treat exception
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/App/handle_exception')
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
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/App/check_lsl_config')
            self.handle_exception(ex)

    def get_lsl_worker(self):
        """Returns the LSL worker"""
        try:
            return list(self.lsl_workers.values())[0]
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/App/get_lsl_worker')
            self.handle_exception(ex)

    def manager_thread_worker(self):
        try:
            while not self.stop:
                # Get event. Check if the queue is empty to avoid blocking calls
                if not self.queue_from_gui.empty():
                    self.process_event(self.queue_from_gui.get())
                # Check run state
                if self.run_state.value == constants.RUN_STATE_STOP:
                    self.close_app()
            print('[Manager] Terminated')
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/App/manager_thread_worker')
            self.handle_exception(ex)

    def main(self):
        try:
            # 1 - Change app state to powering on
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_POWERING_ON)
            # 2 - Prepare app
            qt_app = QApplication([])
            self.app_gui = AppGui(self.app_settings, self.run_state,
                                  self.queue_to_gui, self.queue_from_gui)
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_ON)
            qt_app.exec()
            # 3 - Change app state to powering off
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_POWERING_OFF)
            # 4 - Save recording
            self.save_file_dialog = resources.SaveFileDialog(self.app_extension)
            self.save_file_dialog.accepted.connect(self.on_save_rec_accepted)
            self.save_file_dialog.rejected.connect(self.on_save_rec_rejected)
            qt_app.exec()
            # 5 - Change app state to power off
            self.medusa_interface.app_state_changed(
                constants.APP_STATE_OFF)
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/App/main')
            self.handle_exception(ex)

    def process_event(self, event):
        try:
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
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/App/process_event')
            self.handle_exception(ex)

    def close_app(self):
        try:
            # Trigger the close event in the Qt app. Returns True if it was
            # closed correctly, and False otherwise. If everything was
            # correct, stop the working threads
            if self.app_gui.close():
                self.stop_working_threads()
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/App/close_app')
            self.handle_exception(ex)

    def on_save_rec_accepted(self, file_info):
        try:
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
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/App/on_save_rec_accepted')
            self.handle_exception(ex)

    def on_save_rec_rejected(self):
        try:
            pass
        except Exception as ex:
            ex = exceptions.MedusaException(
                ex, importance=exceptions.EXCEPTION_UNKNOWN,
                scope='app',
                origin='dev_app_qt/App/on_save_rec_rejected')
            self.handle_exception(ex)
