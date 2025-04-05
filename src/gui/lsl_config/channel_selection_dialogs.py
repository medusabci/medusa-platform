# PYTHON MODULES
import os, time, json, threading
from functools import partial
# EXTERNAL IMPORTS
import numpy as np
from PySide6.QtUiTools import loadUiType
from PySide6.QtGui import QIcon
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import *
import matplotlib
import matplotlib.pyplot as plt
matplotlib.use('QtAgg')
# MEDUSA-KERNEL IMPORTS
from medusa import meeg
# MEDUSA IMPORTS
from gui import gui_utils
from gui.qt_widgets.eeg_channel_selection import EEGChannelSelectionPlot

# Load the .ui files
ui_eeg_file = loadUiType('gui/ui_files/lsl_config_channel_selection_eeg.ui')[0]
ui_general_file = loadUiType('gui/ui_files/lsl_config_channel_selection_general.ui')[0]


class GeneralChannelSelection(QDialog):
    """This class allows you to control the GUI of the general channel
       selection widget."""
    def __init__(self, cha_field,lsl_cha_info, ui_file):
        super().__init__()
        self.ui = ui_file()
        self.ui.setupUi(self)
        # Initialize the gui application
        theme_colors = None
        self.theme_colors = gui_utils.get_theme_colors('dark') if \
            theme_colors is None else theme_colors
        self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)
        self.setWindowIcon(QIcon('gui/images/medusa_task_icon.png'))
        self.setWindowTitle('MEDUSA Channel Selection')
        self.changes_made = False

        # Initialize variables
        self.cha_field = cha_field
        self.lsl_cha_info = lsl_cha_info
        self.lsl_cha_keys = lsl_cha_info[0].keys()
        self.ch_labels = [channel['medusa_label'] for channel in
                          self.lsl_cha_info]

        # Initialize the table
        self.table_keys = []
        self.ch_checkboxs = []

        # Button connections
        self.ui.selectall_btn.clicked.connect(self.activate_select_all)
        self.ui.unselectall_btn.clicked.connect(self.activate_unselect_all)
        self.ui.save_btn.clicked.connect(self.save)
        self.ui.load_btn.clicked.connect(self.load)
        self.ui.done_btn.clicked.connect(self.done)

    def init_table(self):
        raise NotImplementedError

    def activate_select_all(self):
        raise NotImplementedError

    def activate_unselect_all(self):
        raise NotImplementedError

    def get_ch_dict(self):
        raise NotImplementedError

    def save(self):
        """ Opens a dialog to save the configuration as a file. """
        fdialog = QFileDialog()
        fname = fdialog.getSaveFileName(
            fdialog, 'Save Channel Selection', '../../channelset/', 'JSON (*.json)')
        if fname[0]:
            with open(fname[0], 'w', encoding='utf-8') as f:
                json.dump(self.get_ch_dict(), f, indent=4)
            self.notifications.new_notification('Channels selection saved as %s' %
                                                fname[0].split('/')[-1])
    def load(self):
        raise NotImplementedError

    def done(self):
        """ Shows a confirmation dialog if non-saved changes has been made. """
        self.close()

    def closeEvent(self, event):
        """ Overrides the closeEvent in order to show the confirmation dialog.
        """
        if self.changes_made:
            retval = self.close_dialog()
            if retval == QMessageBox.Yes:
                cha_info = self.get_ch_dict()
                self.close_signal.emit(cha_info)
                event.accept()
            else:
                event.ignore()
        else:
            cha_info = self.get_ch_dict()
            self.close_signal.emit(cha_info)
            event.accept()

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
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Channel Selection")
        msg.setWindowIcon(QIcon(os.path.join(
            os.path.dirname(__file__),
            '../../gui/images/medusa_task_icon.png')))
        msg.setText("Do you want to leave this window?")
        msg.setInformativeText("Non-saved changes will be discarded.")
        msg.setStandardButtons(
            QMessageBox.Yes | QMessageBox.No)
        return msg.exec_()

    @staticmethod
    def show_warning(text):
        """ Shows a warning message with an OK button. """
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Warning")
        msg.setText("Incorrect file format uploaded in channel selection.")
        msg.setInformativeText(text)

        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()


class LSLGeneralChannelSelection(GeneralChannelSelection):
    """This class allows you to control the GUI of the general channel
       selection widget."""

    close_signal = Signal(object)
    def __init__(self, cha_field,lsl_cha_info):
        super().__init__(cha_field=cha_field,
                         lsl_cha_info=lsl_cha_info,
                         ui_file=ui_general_file)
        self.init_table()

    def init_table(self):
        self.ui.channels_table.setColumnCount(len(self.lsl_cha_keys)-1)
        self.ui.channels_table.setRowCount(len(self.lsl_cha_info))
        table_keys = ["medusa_label"]
        for key in self.lsl_cha_keys:
            if key not in table_keys and key != 'selected':
                table_keys.append(key)
        self.ui.channels_table.setHorizontalHeaderLabels(table_keys)
        header = self.ui.channels_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.ui.channels_table.verticalHeader().hide()

        for i_r, row_data in enumerate(self.lsl_cha_info):
            channel = self.lsl_cha_info[i_r]
            checkbox = QCheckBox()  # Añade el texto como etiqueta
            checkbox.setCheckable(True)  # Hacer el ítem checkable
            checkbox.setChecked(row_data['selected'])
            self.ch_checkboxs.append(checkbox)

            cha_line_edit = QLineEdit(channel['medusa_label'])
            cha_line_edit.setObjectName('cha_name')
            cell_layout = QHBoxLayout()
            cell_layout.addWidget(checkbox)
            cell_layout.addWidget(cha_line_edit)
            cell_widget = QWidget()
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_widget.setLayout(cell_layout)
            self.ui.channels_table.setCellWidget(
                i_r, 0, cell_widget)

            # Add rest of data
            for i_k, key in enumerate(table_keys):
                if i_k > 0:
                    value = row_data.get(key, "")
                    item = QLineEdit(str(value))
                    if key == self.cha_field:
                        item.setEnabled(False)
                    self.ui.channels_table.setCellWidget(i_r, i_k, item)

    def activate_select_all(self):
        for checkbox in self.ch_checkboxs:
            checkbox.setChecked(True)
        self.changes_made = True

    def activate_unselect_all(self):
        for checkbox in self.ch_checkboxs:
            checkbox.setChecked(False)
        self.changes_made = True

    def get_ch_dict(self):
        channels_dict = []
        for row in range(self.ui.channels_table.rowCount()):
            # Get LSL label
            ch_dict = {}
            # Get Medusa label
            ch_dict['medusa_label'] = self.ui.channels_table.cellWidget(row, 0).findChild(
                QLineEdit, 'cha_name').text()
            # Get Selected state
            ch_dict['selected'] = self.ui.channels_table.cellWidget(row, 0).findChild(QCheckBox).isChecked()
            # Get rest of the data
            for col in range(1,self.ui.channels_table.columnCount()):
                ch_dict[f'{self.ui.channels_table.horizontalHeaderItem(col).text()}'] = \
                self.ui.channels_table.cellWidget(row,col).text()
            channels_dict.append(ch_dict)
        return channels_dict

    def load(self):
        """ Opens a dialog to load a configuration file. """
        fdialog = QFileDialog()
        fname = fdialog.getOpenFileName(
            fdialog, 'Load Channel Selection', '../../channelset/', 'JSON (*.json)')
        if fname[0]:
            with open(fname[0], 'r', encoding='utf-8') as f:
                loaded_channel_dict = json.load(f)
            # Check if json loaded has the correct format
            necessary_keys = ['medusa_label', 'selected']
            if len(loaded_channel_dict) != 0:
                for channel in loaded_channel_dict:
                   for n_k in necessary_keys:
                       if n_k in channel.keys():
                           pass
                       else:
                           msg_error = "The json file must include for all " \
                                       "channels the following labels: " \
                                       "“medusa_label” and ‘selected’."
                           self.show_warning(msg_error)
                           return

            else:
                msg_error = "The json file is empty."
                self.show_warning(msg_error)
                return

            # Check if json loaded corresponds to the channel set in use
            for i_ch, channel in enumerate(loaded_channel_dict):
                if channel[self.cha_field] not in self.lsl_cha_info[i_ch][self.cha_field]:
                    msg_error = "The config file loaded does not correspond" \
                                " to the channel set in use."
                    self.show_warning(msg_error)
                    return

            self. lsl_cha_info = loaded_channel_dict

            self.notifications.new_notification('Loaded channels selection: %s' %
                                                fname[0].split('/')[-1])

            self.table_keys = []
            self.ch_checkboxs = []
            self.init_table()


class LSLEEGChannelSelection(GeneralChannelSelection):

    close_signal = Signal(object)

    def __init__(self,cha_field,lsl_cha_info):
        # Initialize variables
        super().__init__(cha_field=cha_field,
                         lsl_cha_info=lsl_cha_info,
                         ui_file=ui_eeg_file)

        self.channel_set = meeg.EEGChannelSet()
        self.channel_set.set_standard_montage(
            self.ch_labels, allow_unlocated_channels=True)
        self.update_ch_set(self.lsl_cha_info)

        # Initialize control
        self.finished = False

        # Initialize the plot
        self.interactive_selection = EEGChannelSelectionPlot(
            channel_set=self.channel_set,
            channels_selected=self.update_ch_info())
        self.ui.plotLayout.addWidget(self.interactive_selection.fig_head.canvas)
        self.ui.unlocatedChannelsLayout.addWidget(
            self.interactive_selection.fig_unlocated.canvas)

        # Connect channels in plot with channels in table
        self.working_threads = list()
        Th1 = threading.Thread(target=self.watch_ch_clicked)
        Th1.start()
        self.working_threads.append(Th1)

        # Uncomment to debug
        self.setModal(True)
        # self.show()

        self.init_table()
        self.ui.refresh_btn.clicked.connect(self.on_refresh)


    def activate_select_all(self):
        self.interactive_selection.select_all()
        self.changes_made = True


    def activate_unselect_all(self):
        self.interactive_selection.unselect_all()
        self.changes_made = True


    def on_checked(self, state, ch_index):
        label = self.interactive_selection.l_cha[ch_index]
        if state == 0:
            state = False
        else:
            state = True
        if self.interactive_selection.channels_selected["Selected"][
            ch_index] != state:
            if label in \
                    self.interactive_selection.located_channel_set.l_cha:
                fig = 'head'
            else:
                fig = 'unlocated'
            self.interactive_selection.change_state(label)
            self.interactive_selection.select_action(label, fig)

    def watch_ch_clicked(self):
        while not self.finished:
            time.sleep(0.1)
            for i_ch, checkbox in enumerate(self.ch_checkboxs):
                state = self.interactive_selection.channels_selected['Selected'][
                    i_ch]
                checkbox.setChecked(state)

    def update_ch_info(self):
        channels_selected = {}
        channels_selected['Labels'] = np.asarray([channel["medusa_label"] for channel in
                                       self.lsl_cha_info], dtype='<U32')
        channels_selected['Selected'] = [channel["selected"]
                                         for channel in self.lsl_cha_info]
        channels_selected['Plot line'] = np.full(len(self.ch_labels), None)
        return channels_selected

    def update_ch_set(self, cha_info):
        for i, ch in enumerate(self.channel_set.channels):
            if cha_info[i]['x_pos'] != None:
                ch['x'] = cha_info[i]['x_pos']
                ch['y'] = cha_info[i]['y_pos']

    def get_channel_labels(self):
        return [cha_dict['medusa_label'] for cha_dict in self.lsl_cha_info]

    def init_table(self):
        channel_set = self.interactive_selection.channel_set
        self.ui.channels_table.setColumnCount(len(self.lsl_cha_keys))
        self.ui.channels_table.setRowCount(len(channel_set.channels))
        table_keys = ["medusa_label","x_pos", "y_pos","manage position"]
        for key in self.lsl_cha_keys:
            if key not in table_keys and key != 'selected':
                table_keys.append(key)
        self.ui.channels_table.setHorizontalHeaderLabels(table_keys)
        header = self.ui.channels_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.ui.channels_table.verticalHeader().hide()

        for i_r, row_data in enumerate(self.lsl_cha_info):
            channel = self.interactive_selection.channel_set.channels[i_r]
            checkbox = QCheckBox() # Añade el texto como etiqueta
            checkbox.setCheckable(True)  # Hacer el ítem checkable
            checkbox.setChecked(row_data['selected'])
            checkbox.stateChanged.connect(
                lambda state, index=i_r: self.on_checked(state,index))
            self.ch_checkboxs.append(checkbox)

            cha_line_edit = QLineEdit(channel['label'])
            cha_line_edit.setObjectName('cha_name')
            cell_layout = QHBoxLayout()
            cell_layout.addWidget(checkbox)
            cell_layout.addWidget(cha_line_edit)
            cell_widget = QWidget()
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_widget.setLayout(cell_layout)
            self.ui.channels_table.setCellWidget(
                i_r, 0, cell_widget)

            x_spinbox = CustomDoubleSpinBox()
            x_spinbox.setMinimum(-3)
            x_spinbox.setMaximum(3)
            y_spinbox = CustomDoubleSpinBox()
            y_spinbox.setMinimum(-3)
            y_spinbox.setMaximum(3)
            manage_button = QPushButton()
            if 'r' in channel.keys():
                x_spinbox.setValue(channel['r']*np.cos(channel['theta']))
                y_spinbox.setValue(channel['r']*np.sin(channel['theta']))
                manage_button.setText('Make unlocated')
            elif 'x' in channel.keys():
                x_spinbox.setValue(channel['x'])
                y_spinbox.setValue(channel['y'])
                manage_button.setText('Make unlocated')
            else:
                x_spinbox.setEnabled(False)
                y_spinbox.setEnabled(False)
                manage_button.setText('Set coordinates')

            self.ui.channels_table.setCellWidget(i_r, 1, x_spinbox)
            self.ui.channels_table.setCellWidget(i_r, 2, y_spinbox)
            manage_button.clicked.connect(partial(self.on_define_coords,i_r))
            self.ui.channels_table.setCellWidget(i_r, 3, manage_button)
            # Add rest of data
            for i_k, key in enumerate(table_keys):
                if i_k > 3:
                    value = row_data.get(key, "")
                    item = QLineEdit(str(value))
                    if key == self.cha_field:
                       item.setEnabled(False)
                    self.ui.channels_table.setCellWidget(i_r,i_k, item)

    def on_refresh(self):
        self.interactive_selection.located_channel_set = meeg.EEGChannelSet()
        self.interactive_selection.unlocated_channels = []
        for i in range(len(self.ch_checkboxs)):
            # Update the name of the channel names
            label = self.ui.channels_table.cellWidget(i, 0).findChild(
                QLineEdit, 'cha_name').text()
            self.interactive_selection.channels_selected['Labels'][i] = label
            # If second column is active -> located channel
            if self.ui.channels_table.cellWidget(i,1).isEnabled():
                xpos = self.ui.channels_table.cellWidget(i,1).value()
                ypos = self.ui.channels_table.cellWidget(i,2).value()
                r = np.sqrt(xpos**2 + ypos**2)
                theta = np.arctan2(ypos,xpos)
                self.interactive_selection.channel_set.channels[i]['label'] = label
                self.interactive_selection.channel_set.channels[i]['r'] = r
                self.interactive_selection.channel_set.channels[i]['theta'] = theta
                self.interactive_selection.channel_set.channels[i]['x'] = xpos
                self.interactive_selection.channel_set.channels[i]['y'] = ypos
            # Else -> unlocated channel
            else:
                self.interactive_selection.channel_set.channels[i] = {'label':label,'reference':None}
            self.interactive_selection.channel_set.l_cha[i] = label

        self.interactive_selection.l_cha = self.interactive_selection.channel_set.l_cha

        self.clear_plots()

        self.interactive_selection.init_plots()
        self.interactive_selection.load_channel_selection_settings()
        self.ui.plotLayout.addWidget(self.interactive_selection.fig_head.canvas)
        self.ui.unlocatedChannelsLayout.addWidget(
            self.interactive_selection.fig_unlocated.canvas)

    def on_define_coords(self,i):
        # Remove existing buttons
        if self.ui.channels_table.cellWidget(i,3).text() == 'Set coordinates':
            self.ui.channels_table.cellWidget(i, 1).setEnabled(True)
            self.ui.channels_table.cellWidget(i, 2).setEnabled(True)
            self.ui.channels_table.cellWidget(i, 3).setText('Make unlocated')
        else:
            self.ui.channels_table.cellWidget(i, 1).setEnabled(False)
            self.ui.channels_table.cellWidget(i, 2).setEnabled(False)
            self.ui.channels_table.cellWidget(i, 3).setText('Set coordinates')

    def get_ch_dict(self):
        channels_dict = []
        for row in range(self.ui.channels_table.rowCount()):
            # Get LSL label
            ch_dict = {}
            # Get Medusa label
            ch_dict['medusa_label'] = self.ui.channels_table.cellWidget(row, 0).findChild(
                QLineEdit, 'cha_name').text()
            # Get Selected state
            ch_dict['selected'] = self.ui.channels_table.cellWidget(row, 0).findChild(QCheckBox).isChecked()
            # Get coordinates
            if self.ui.channels_table.cellWidget(row, 1).isEnabled():
                ch_dict['x_pos'] = self.ui.channels_table.cellWidget(row, 1).value()
                ch_dict['y_pos'] = self.ui.channels_table.cellWidget(row, 2).value()
            else:
                ch_dict['x_pos'] = None
                ch_dict['y_pos'] = None
            # Get rest of the data
            for col in range(4,self.ui.channels_table.columnCount()):
                ch_dict[f'{self.ui.channels_table.horizontalHeaderItem(col).text()}'] = \
                self.ui.channels_table.cellWidget(row,col).text()
            channels_dict.append(ch_dict)
        return channels_dict

    def clear_plots(self):
        self.interactive_selection.fig_unlocated.clf()
        self.interactive_selection.fig_head.clf()
        self.ui.plotLayout.removeWidget(self.interactive_selection.fig_head.canvas)
        self.interactive_selection.fig_head.canvas.deleteLater()
        self.interactive_selection.fig_head.canvas = None
        self.ui.unlocatedChannelsLayout.removeWidget(
            self.interactive_selection.fig_unlocated.canvas)
        self.interactive_selection.fig_unlocated.canvas.deleteLater()
        self.interactive_selection.fig_unlocated.canvas = None
        plt.close(self.interactive_selection.fig_head)
        self.interactive_selection.fig_head = None
        plt.close(self.interactive_selection.fig_unlocated)
        self.interactive_selection.fig_unlocated = None

    @staticmethod
    def show_warning(text):
        """ Shows a warning message with an OK button. """
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Warning")
        msg.setText("Incorrect file format uploaded in EEG channel selection.")
        msg.setInformativeText(text)

        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()

    # ------------------- BASIC BUTTONS --------------------------------------
    def save(self):
        """ Opens a dialog to save the configuration as a file. """
        fdialog = QFileDialog()
        fname = fdialog.getSaveFileName(
            fdialog, 'Save Channel Selection', '../../channelset/', 'JSON (*.json)')
        if fname[0]:
            with open(fname[0], 'w', encoding='utf-8') as f:
                json.dump(self.get_ch_dict(), f, indent=4)
            self.notifications.new_notification('Channels selection saved as %s' %
                                                fname[0].split('/')[-1])

    def load(self):
        """ Opens a dialog to load a configuration file. """
        fdialog = QFileDialog()
        fname = fdialog.getOpenFileName(
            fdialog, 'Load Channel Selection', '../../channelset/', 'JSON (*.json)')
        if fname[0]:
            with open(fname[0], 'r', encoding='utf-8') as f:
                loaded_channel_dict = json.load(f)
            # Check if json loaded has the correct format
            necessary_keys = ['medusa_label', 'selected', 'x_pos', 'y_pos']
            if len(loaded_channel_dict) != 0:
                for channel in loaded_channel_dict:
                   for n_k in necessary_keys:
                       if n_k in channel.keys():
                           pass
                       else:
                           msg_error = "The json file must include for all " \
                                       "channels the following labels: " \
                                       "“medusa_label”, “selected”, “x_pos” " \
                                       "and “y_pos”."
                           self.show_warning(msg_error)
                           return

            else:
                msg_error = "The json file is empty."
                self.show_warning(msg_error)
                return

            # Check if json loaded corresponds to the channel set in use
            for channel in loaded_channel_dict:
                if channel[self.cha_field] not in self.interactive_selection.channel_set.l_cha:
                    msg_error = "The config file loaded does not correspond" \
                                " to the EEG channel set in use."
                    self.show_warning(msg_error)
                    return


            channels_selected = self.interactive_selection.channels_selected
            channels_selected['Labels'] = [channel["medusa_label"] for channel in loaded_channel_dict]
            channels_selected['Selected'] = [channel["selected"]
                                             for channel in loaded_channel_dict]


            self.clear_plots()
            self.ch_labels = channels_selected['Labels']
            self.channel_set = meeg.EEGChannelSet()
            self.channel_set.set_standard_montage(self.ch_labels,
                                                  allow_unlocated_channels=True)
            self.update_ch_set(loaded_channel_dict)
            self.interactive_selection = EEGChannelSelectionPlot(
                channel_set=self.channel_set,
                channels_selected=channels_selected)
            self.ui.plotLayout.addWidget(self.interactive_selection.fig_head.canvas)
            self.interactive_selection.fig_head.canvas.draw()
            self.ui.unlocatedChannelsLayout.addWidget(
                self.interactive_selection.fig_unlocated.canvas)
            self.notifications.new_notification('Loaded channels selection: %s' %
                                                fname[0].split('/')[-1])

            self.table_keys = []
            self.ch_checkboxs = []
            self.init_table()

    def closeEvent(self, event):
        """ Overrides the closeEvent in order to show the confirmation dialog.
        """
        if self.changes_made:
            retval = self.close_dialog()
            if retval == QMessageBox.Yes:
                cha_info = self.get_ch_dict()
                self.close_signal.emit(cha_info)
                event.accept()
            else:
                event.ignore()
        else:
            cha_info = self.get_ch_dict()
            self.close_signal.emit(cha_info)
            self.ui.plotLayout.deleteLater()
            event.accept()


class CustomDoubleSpinBox(QDoubleSpinBox):
    """Subclase de QDoubleSpinBox para desactivar la rueda del ratón."""

    def wheelEvent(self, event):
        # No hacer nada en la rueda del ratón
        event.ignore()
