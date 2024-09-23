# Built-in modules
import sys, os, json

# External modules
from PySide6 import QtGui, QtWidgets, QtCore

# Medusa modules
from gui import gui_utils
from . import settings


class Config(QtWidgets.QMainWindow):

    """ This class provides graphical configuration for the app """

    close_signal = QtCore.Signal(object)

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
        QtWidgets.QMainWindow.__init__(self)
        self.settings = sett

        # Initialize the gui application
        self.theme_colors = gui_utils.get_theme_colors('dark') if \
            theme_colors is None else theme_colors
        self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)
        self.setWindowIcon(QtGui.QIcon('../gui/images/medusa_task_icon.png'))
        self.setWindowTitle('Default configuration window')
        self.changes_made = False

        # Create layout
        self.main_layout = QtWidgets.QVBoxLayout()

        # Custom interface
        self.text_edit = QtWidgets.QTextEdit()
        self.main_layout.addWidget(self.text_edit)

        # % IMPORTANT % Mandatory buttons
        self.buttons_layout = QtWidgets.QVBoxLayout()
        self.button_reset = QtWidgets.QPushButton('Reset')
        self.button_save = QtWidgets.QPushButton('Save')
        self.button_load = QtWidgets.QPushButton('Load')
        self.button_done = QtWidgets.QPushButton('Done')
        self.buttons_layout.addWidget(self.button_reset)
        self.buttons_layout.addWidget(self.button_save)
        self.buttons_layout.addWidget(self.button_load)
        self.buttons_layout.addWidget(self.button_done)
        self.main_layout.addLayout(self.buttons_layout)

        # Add central widget
        self.central_widget = QtWidgets.QWidget()
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
        self.settings = settings.Settings()
        self.text_edit.setText(json.dumps(
            self.settings.to_serializable_obj(), indent=4))

    def save(self):
        fdialog = QtWidgets.QFileDialog()
        fname = fdialog.getSaveFileName(
            fdialog, 'Save settings', '../../../config/', 'JSON (*.json)')
        if fname[0]:
            self.settings = self.settings.from_serializable_obj(json.loads(
                self.text_edit.toPlainText()))
            self.settings.save(path=fname[0])

    def load(self):
        """ Opens a dialog to load a configuration file. """
        fdialog = QtWidgets.QFileDialog()
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
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setWindowIcon(QtGui.QIcon(os.path.join(
            os.path.dirname(__file__), '../../gui/images/medusa_task_icon.png')))
        msg.setText("Do you want to leave this window?")
        msg.setInformativeText("Non-saved changes will be discarded.")
        msg.setWindowTitle("Row-Col Paradigm")
        msg.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        return msg.exec_()

    def closeEvent(self, event):
        """ Overrides the closeEvent in order to show the confirmation dialog.
        """
        if self.changes_made:
            retval = self.close_dialog()
            if retval == QtWidgets.QMessageBox.Yes:
                self.close_signal.emit(None)
                event.accept()
            else:
                event.ignore()
        else:
            sett = self.settings.from_serializable_obj(
                json.loads(self.text_edit.toPlainText()))
            self.close_signal.emit(sett)
            event.accept()
