from PyQt5 import QtGui, QtWidgets, uic, QtCore
import pylsl
import sys
import os

# Load the .ui files
ui_main_file = uic.loadUiType(os.path.dirname(__file__) + "/gui_settings.ui")[0]


class SettingsConfig(QtWidgets.QDialog, ui_main_file):
    # TODO: Color browsing (see Config windows of RCP for examples)
    # TODO: Switch cases for plot and plot pre-processing tabs
    # TODO: Bad input detection
    # TODO: Link with real file
    # TODO: Communicate with the core of MEDUSA
    def __init__(self):
        """ Class that represents the Configuration GUI for the general settings. """
        QtWidgets.QDialog.__init__(self)
        self.setupUi(self)

        # Initialize the gui application
        dir = os.path.dirname(__file__)
        #self.stl = gui_utils.set_css_and_theme(self, os.path.join(dir, '../gui_stylesheet.css'), 'dark')
        self.setWindowIcon(QtGui.QIcon(os.path.join(dir, '../images/medusa_task_icon.png')))
        self.setWindowTitle('Settings')

        # Set the current parameters
        # TODO

        # Connect the buttons
        self.button_cancel.clicked.connect(self.on_cancel)
        self.button_done.clicked.connect(self.on_done)
        self.button_run_lsl_search.clicked.connect(self.lsl_search)
        self.button_run_lsl_select.clicked.connect(self.lsl_select)

        # Update the StackedWidget
        self.list_selection_lsl_stream.currentIndexChanged.connect(self.update_lsl_stacked_widget)
        self.update_lsl_stacked_widget()

        self.show()

    def update_lsl_stacked_widget(self):
        """ This function updates the stacked widget that has to be seen whenever the user changes the LSL
        stream mode."""
        idx = self.list_selection_lsl_stream.currentIndex()
        self.stackedwidget_run_lsl.setCurrentIndex(idx)

    def on_cancel(self):
        """ This function cancels the configuration"""
        self.done()

    def on_done(self):
        """ This function saves the settings into the configuration file. """
        # TODO: Communication with the file!
        pass

    def lsl_search(self):
        """ This function searches for available LSL streams. """
        self.label_run_lsl_status.setText("Searching...")
        streams = pylsl.resolve_stream()
        if len(streams) == 0:
            self.warning_dialog("LSL search", "LSL streams could not be found.")
        else:
            # Get the names
            streams_names = list()
            for stream in streams:
                streams_names.append(stream.lsl_name())
            self.list_run_lsl_streams.addItems(streams_names)
        self.label_run_lsl_status.setText("Ready.")

    def lsl_select(self):
        """ This function takes the selected item from the list and places its name in the LSL stream name. """
        selected = self.list_run_lsl_streams.selectedItems()
        if len(selected) > 1:
            print("More than one selected! How?")
        for s in selected:
            self.edit_run_lsl_streamname.setText(s.text())

    @staticmethod
    def warning_dialog(title, message):
        """ This function shows a warning dialog. """
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setWindowIcon(QtGui.QIcon(
            os.path.join(os.path.dirname(__file__),
                         '../images/medusa_task_icon.png')))
        msg.setText(message)
        msg.setWindowTitle(title)
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
        return msg.exec_()


if __name__ == '__main__':
    """ Example of use of the SettingsConfig() class. """
    app = QtWidgets.QApplication(sys.argv)
    application = SettingsConfig()
    sys.exit(app.exec_())
