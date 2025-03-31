import copy

from gui.qt_widgets.notifications import NotificationStack

from PySide6.QtUiTools import loadUiType
from PySide6.QtGui import QIcon, QStandardItemModel,QStandardItem
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import *
from gui import gui_utils
import os
import time
import json
import threading
import matplotlib
from medusa.components import SerializableComponent
from medusa.plots.head_plots import plot_head
import numpy as np
from medusa import meeg
import matplotlib.pyplot as plt
matplotlib.use('QtAgg')
from matplotlib.widgets import Slider, Button
from functools import partial


# Load the .ui files
dir_path = os.path.dirname(__file__)
ui_eeg_file = loadUiType(f"{dir_path}/channel_selection_eeg.ui")[0]
ui_general_file = loadUiType(f"{dir_path}/channel_selection_general.ui")[0]


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
        self.notifications = NotificationStack(parent=self, timer_ms=500)
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


class EEGChannelSelectionPlot(SerializableComponent):
    """This class controls the interactive topographic representation.
        After selection, a dictionary with an EEGChannelSet consisting of
        the selected channels, the selected reference and the selected
        ground is returned."""

    def __init__(self, channel_set, channels_selected=None):
        # Parameters
        self.ch_labels = channel_set.l_cha

        # Initialize Variables
        self.channel_set = channel_set
        self.l_cha = self.channel_set.l_cha
        self.unlocated_channels = []
        self.located_channel_set = meeg.EEGChannelSet()
        self.channels_selected = channels_selected
        self.channel_location = None
        self.unlocated_ch_labels = None
        self.fig_head = None
        self.axes_head = None
        self.fig_unlocated = None
        self.axes_unlocated = None
        self.tolerance_radius = None
        self.selection_mode = 'Used'
        self.color = {
            "Used": '#76ba1b',
            'Ground': '#fff44f',
            'Reference': '#00bdfe'
        }
        self.final_channel_selection = {
            'Used': copy.copy(self.channel_set),
            'Ground': None,
            'Reference': None
        }

        self.init_plots()

        if self.channels_selected is None:
            self.set_channel_selection_dict()
        else:
            self.load_channel_selection_settings()

        # Uncomment to debug
        # self.fig_head.show()

    def check_unlocated_channels(self):
        """Separates located from unlocated channels"""
        for ch in self.channel_set.channels:
            if 'r' in ch.keys() or 'x' in ch.keys():
                self.located_channel_set.add_channel(ch, reference=None)
            else:
                self.unlocated_channels.append(ch)

    def init_plots(self):
        # Plot Channel Plot
        self.check_unlocated_channels()
        self.fig_head = plt.figure()
        self.fig_head.patch.set_alpha(False)
        self.axes_head = self.fig_head.add_subplot(111)
        if self.located_channel_set.channels != None:
            self.set_tolerance_radius()
            plot_head(axes=self.axes_head,
                      channel_set=self.located_channel_set,
                      plot_channel_labels=True,
                      channel_radius_size=self.tolerance_radius,
                      head_skin_color='#E8BEAC',
                      plot_channel_points=True)
            # Set channel coordinates
            self.set_channel_location()
        else:
            self.tolerance_radius = 0.25
            self.axes_head.set_axis_off()
            self.axes_head.set_facecolor('#00000000')

        # Add interactive functionality to the figure
        self.fig_head.canvas.mpl_connect('button_press_event', self.onclick)

        # Plot unlocated channels
        self.start_row = 0
        self.slider_ax = None
        self.unlocated_coords = {'radius':[],'theta':[],
                                 'ch_x':[],'ch_y':[]}
        self.unlocated_handles = dict()
        self.fig_unlocated, self.axes_unlocated = plt.subplots(figsize=(3, 8))
        self.fig_unlocated.patch.set_alpha(False)
        self.plot_unlocated()

        # Crear el botón de desplazamiento hacia arriba
        self.button_up_ax = self.fig_unlocated.add_axes(
            [0.4, 0.05, 0.1, 0.05])
        self.button_up = Button(self.button_up_ax, '↑')
        self.button_up.on_clicked(self.scroll_up)

        # Crear el botón de desplazamiento hacia abajo
        self.button_down_ax = self.fig_unlocated.add_axes(
            [0.6, 0.05, 0.1, 0.05])
        self.button_down = Button(self.button_down_ax, '↓')
        self.button_down.on_clicked(self.scroll_down)

        # Add interactive functionality to the figure
        self.fig_unlocated.canvas.mpl_connect('button_press_event',
                                              self.onclick)
    def plot_unlocated(self):
        # Clean axes before drawing
        self.axes_unlocated.axis("off")

        # Plot channels
        self.unlocated_ch_labels = [c['label'] for c in self.unlocated_channels]
        if len(self.unlocated_channels) > 0:

            # Plot channels as circunferences
            self.unlocated_handles['ch-contours'] = list()
            self.unlocated_handles['ch-labels'] = list()
            for ch_idx, ch in enumerate(self.unlocated_ch_labels):
                patch = matplotlib.patches.Circle(
                    (0.5, -0.5-ch_idx), radius=0.25, ec="none",
                    facecolor='#ffffff', edgecolor=None, alpha=0.4, zorder=10)
                handle_circ = self.axes_unlocated.add_patch(patch)
                self.unlocated_handles['ch-contours'].append(handle_circ)
                # Plot channels points
                handle_point = self.axes_unlocated.scatter(
                    0.5, -0.5-ch_idx, linewidths=1,
                    facecolors='w', edgecolors='k', zorder=12)
                self.unlocated_handles['ch-points'] = handle_point
                # Plot channels labels
                handle_label = self.axes_unlocated.text(
                    0.75, -0.5-ch_idx-0.125, ch,
                    fontsize=10, color='w', zorder=11)
                self.unlocated_handles['ch-labels'].append(handle_label)

                # Save coordinates
                self.unlocated_coords['radius'].append(
                    np.sqrt(0.5 ** 2 + (-0.5 - ch_idx) ** 2))
                self.unlocated_coords['theta'].append(
                    np.arctan2(-0.5 - ch_idx,0.5))
                self.unlocated_coords['ch_x'].append(0.5)
                self.unlocated_coords['ch_y'].append(-0.5 - ch_idx)

            # Number of channels to display
            max_data = min([len(self.unlocated_ch_labels),5])
            self.axes_unlocated.set_aspect('equal')
            self.axes_unlocated.set_xlim(0, 1)
            self.axes_unlocated.set_ylim(- max_data, 0)

            # Actualizar visibilidad de las etiquetas según los límites
            self.update_text_visibility()

        self.axes_unlocated.set_title('Unlocated \nChannels', fontsize=11,
                                      color='w')
        self.fig_unlocated.canvas.draw_idle()

    def update_text_visibility(self):
        # Obtener los límites actuales de y
        y_min, y_max = self.axes_unlocated.get_ylim()

        # Ajustar visibilidad de cada etiqueta
        for handle_label in self.unlocated_handles['ch-labels']:
            label_y = handle_label.get_position()[1]
            # Mostrar solo si la etiqueta está dentro de los límites
            handle_label.set_visible(y_min <= label_y <= y_max)

    def scroll_up(self, event):
        # Desplazar hacia arriba si no estamos en el inicio
        if self.start_row < 0:
            self.start_row += 1
            self.update_limits()  # Redibujar con el nuevo índice

    def scroll_down(self, event):
        # Desplazar hacia abajo si no hemos llegado al final
        if self.start_row > -len(self.unlocated_channels) + 5:
            self.start_row -= 1
            self.update_limits()  # Redibujar con el nuevo índice

    def update_limits(self):
        # Cambia los límites del eje y en función de la posición de start_row
        max_data = min(len(self.unlocated_channels), 5)
        y_min = self.start_row - max_data  # Ajusta el límite inferior
        y_max = self.start_row  # Ajusta el límite superior
        self.axes_unlocated.set_ylim(y_min, y_max)
        self.update_text_visibility()
        self.fig_unlocated.canvas.draw_idle()

    def set_channel_location(self):
        """For an easy treat of channel coordinates"""
        self.channel_location = dict()
        if 'r' in self.located_channel_set.channels[0].keys():
            self.channel_location['radius'] = \
                [c['r'] for c in self.located_channel_set.channels]
            self.channel_location['theta'] = \
                [c['theta'] for c in self.located_channel_set.channels]

            self.channel_location['ch_x'] = (
                    np.array(self.channel_location['radius']) * np.cos(
                self.channel_location['theta']))
            self.channel_location['ch_y'] = (
                    np.array(self.channel_location['radius']) * np.sin(
                self.channel_location['theta']))
        else:
            self.channel_location['ch_x'] = \
                [c['x'] for c in self.located_channel_set.channels]
            self.channel_location['ch_y'] = \
                [c['y'] for c in self.located_channel_set.channels]

            self.channel_location['radius'] = (
                np.sqrt(np.power(self.channel_location['ch_x'],2) +
                        np.power(self.channel_location['ch_y'],2)))
            self.channel_location['theta'] = (
                np.arctan2(np.array(self.channel_location['ch_y']),
                           np.array(self.channel_location['ch_x'])))

    def set_channel_selection_dict(self):
        """Initialize the state dict"""
        self.channels_selected = dict()
        self.channels_selected['Labels'] = np.asarray(self.l_cha,dtype='<U32')
        self.channels_selected['Selected'] = np.zeros(len(self.l_cha), dtype=bool)
        self.channels_selected['Plot line'] = np.full(len(self.l_cha), None)

    def set_tolerance_radius(self):
        """Calculates the radius of the click area of each channel."""
        dist_matrix = self.located_channel_set.compute_dist_matrix()
        dist_matrix.sort()
        percentage = self.set_tolerance_parameter()
        if len(self.l_cha) > 1:
            self.tolerance_radius = 1.5 * percentage * dist_matrix[:, 1].min()
        else:
            self.tolerance_radius = percentage

    def set_tolerance_parameter(self):
        """ Computes the percentage of the minimum distance between channels
            depending the montage standard with a linear function"""
        M = 345
        return len(self.l_cha) * (0.25 / (M - 2)) + 0.25 * ((M - 4) / (M - 2))

    def onclick(self, event):
        """ Handles the mouse click event"""
        xdata = event.xdata
        ydata = event.ydata
        if event.inaxes == self.axes_head:
            ch_label = self.check_channel_clicked((xdata, ydata),'head')
            if ch_label != None:
                self.change_state(ch_label)
                self.select_action(ch_label,'head')
            else:
                return
        elif event.inaxes == self.axes_unlocated:
            ch_label = self.check_channel_clicked((xdata, ydata),'unlocated')
            if ch_label != None:
                self.change_state(ch_label)
                self.select_action(ch_label,'unlocated')
            else:
                return

    def change_state(self,ch_label):
        ch_idx = self.l_cha.index(ch_label)
        self.channels_selected["Selected"][ch_idx] = not \
        self.channels_selected["Selected"][ch_idx]

    def check_channel_clicked(self, coord_click, figure):
        """ Checks if mouse was clicked inside the channel area"""
        if (coord_click[0] is None) or (coord_click[1] is None):
            return None
        distance = None

        if figure == 'head':
            if self.located_channel_set.channels != None:
                r = np.sqrt(coord_click[0] ** 2 + coord_click[1] ** 2) * \
                    np.ones((len(self.located_channel_set.channels)))
                theta = (np.arctan2(coord_click[1], coord_click[0]) *
                         np.ones((len(self.located_channel_set.channels))))
                distance = (r ** 2 + np.power(self.channel_location['radius'], 2) -
                            2 * r * self.channel_location['radius'] *
                            np.cos(theta - self.channel_location[
                                'theta'])) < self.tolerance_radius ** 2
        elif figure == 'unlocated':
            r = np.sqrt(coord_click[0] ** 2 + coord_click[1] ** 2) * \
                np.ones((len(self.unlocated_channels)))
            theta = np.arctan2(coord_click[1], coord_click[0]) * np.ones(
                (len(self.unlocated_channels)))
            distance = (r ** 2 + np.power(self.unlocated_coords['radius'], 2) -
                        2 * r * self.unlocated_coords['radius'] *
                        np.cos(theta - self.unlocated_coords[
                            'theta'])) < 0.25 ** 2
        if distance is None:
            return None
        else:
            if np.sum(distance) >= 1:
                idx = int(np.where(distance)[0])
                if figure == 'head':
                    ch_label = self.located_channel_set.l_cha[idx]
                elif figure == 'unlocated':
                    ch_label = self.unlocated_ch_labels[idx]
                return ch_label

    def channel_type_selected(self):
        """Avoids incompatibilities between different selection modes"""
        if self.selection_mode == 'Reference':
            idx_reference = np.where(self.channels_selected['Reference'])[0]
            if len(idx_reference) != 0:
                self.channels_selected['Selected'][int(idx_reference)] = False
                self.channels_selected['Plot line'][int(idx_reference)].remove()
                self.channels_selected['Reference'][int(idx_reference)] = False
                plt.setp(self.axes_head.texts[int(idx_reference)], fontweight='normal', color='w')
        elif self.selection_mode == 'Ground':
            idx_ground = np.where(self.channels_selected['Ground'])[0]
            if len(idx_ground) != 0:
                self.channels_selected['Selected'][int(idx_ground)] = False
                self.channels_selected['Plot line'][int(idx_ground)].remove()
                self.channels_selected['Ground'][int(idx_ground)] = False
                plt.setp(self.axes_head.texts[int(idx_ground)], fontweight='normal', color='w')

    def select_action(self, ch_label, figure):
        """Changes the 'Selected' state of the channel and its representation"""
        global_idx = self.l_cha.index(ch_label)
        location = None
        if figure == 'head':
            plot_idx = self.located_channel_set.l_cha.index(ch_label)
            location = self.channel_location
            axis = self.axes_head
        elif figure == 'unlocated':
            plot_idx = self.unlocated_ch_labels.index(ch_label)
            location = self.unlocated_coords
            axis = self.axes_unlocated

        if self.channels_selected['Selected'][global_idx]:
            # Check if reference or Ground are already selected
            # self.channel_type_selected()
            # Draw selection marker
            self.channels_selected['Plot line'][global_idx] = plt.Circle(
                (location['ch_x'][plot_idx], location['ch_y'][plot_idx]),
                radius=(0.5 * self.tolerance_radius),
                facecolor=self.color[self.selection_mode],
                edgecolor='k', alpha=1, zorder=12)
            # Highlight the selected label
            plt.setp(axis.texts[plot_idx], fontweight='extra bold', color=self.color[self.selection_mode])
            axis.add_patch(self.channels_selected['Plot line'][global_idx])
            # self.channels_selected[self.selection_mode][global_idx] = True
        else:
            self.channels_selected['Plot line'][global_idx].remove()
            self.channels_selected['Plot line'][global_idx] = None
            plt.setp(axis.texts[plot_idx], fontweight='normal', color='w')
            # self.channels_selected['Used'][global_idx] = False
            # self.channels_selected['Ground'][global_idx] = False
            # self.channels_selected['Reference'][global_idx] = False
        self.fig_head.canvas.draw()
        self.fig_unlocated.canvas.draw()
        return True

    def select_all(self):
        """Removes the already selected channels and then select them all"""
        plots = list(np.where(self.channels_selected['Plot line'])[0])
        for marker_idx in plots:
            self.channels_selected['Plot line'][int(marker_idx)].remove()
        self.set_channel_selection_dict()
        self.selection_mode = 'Used'
        self.channels_selected['Selected'] = np.ones(len(self.l_cha), dtype=bool)
        # self.channels_selected['Used'] = np.ones(len(self.l_cha), dtype=bool)
        for ch_label in self.l_cha:
            global_idx = self.l_cha.index(ch_label)
            if ch_label in self.located_channel_set.l_cha:
                plot_idx = self.located_channel_set.l_cha.index(ch_label)
                axis = self.axes_head
                location = self.channel_location
            else:
                plot_idx = self.unlocated_ch_labels.index(ch_label)
                axis = self.axes_unlocated
                location = self.unlocated_coords
            self.channels_selected['Plot line'][global_idx] = plt.Circle(
                (location['ch_x'][plot_idx], location['ch_y'][plot_idx]),
                radius=(0.5 * self.tolerance_radius),
                facecolor=self.color[self.selection_mode],
                edgecolor='k', alpha=1, zorder=12)
            plt.setp(axis.texts[plot_idx], fontweight='extra bold', color=self.color[self.selection_mode])
            axis.add_patch(self.channels_selected['Plot line'][global_idx])
        self.fig_head.canvas.draw()
        self.fig_unlocated.canvas.draw()

    def unselect_all(self):
        plots = list(np.where(self.channels_selected['Plot line'])[0])
        for marker_idx in plots:
            self.channels_selected['Plot line'][int(marker_idx)].remove()
            self.channels_selected['Plot line'][int(marker_idx)] = None
        plt.setp(self.axes_head.texts, fontweight='normal', color='w')
        plt.setp(self.axes_unlocated.texts, fontweight='normal', color='w')
        self.set_channel_selection_dict()
        self.fig_head.canvas.draw()
        self.fig_unlocated.canvas.draw()

    def load_channel_selection_settings(self):
        """Initialize the selection settings and make the necessary plots"""
        for key in self.channels_selected.keys():
            self.channels_selected[key] = np.asarray(self.channels_selected[key])
        if len(self.channel_set.l_cha) != 0:
            for idx in range(len(self.channel_set.l_cha)):
                if self.located_channel_set.channels is None :
                    if self.channels_selected['Selected'][idx]:
                        self.select_action(
                            self.channels_selected['Labels'][idx],
                            'unlocated')
                else:
                    if self.channels_selected['Labels'][idx] in \
                            self.located_channel_set.l_cha and \
                            self.channels_selected['Selected'][idx]:
                        self.select_action(
                            self.channels_selected['Labels'][idx],
                            'head')


                if self.unlocated_ch_labels is None:
                    if self.channels_selected['Selected'][idx]:
                        self.select_action(
                            self.channels_selected['Labels'][idx],
                            'head')
                else:
                    if self.channels_selected['Labels'][
                        idx] in self.unlocated_ch_labels and \
                            self.channels_selected['Selected'][idx]:
                        self.select_action(
                            self.channels_selected['Labels'][idx],
                            'unlocated')
                #
                # if self.located_channel_set.channels is None or\
                #         self.channels_selected['Labels'][idx] in \
                #         self.unlocated_ch_labels:
                #     if self.channels_selected['Selected'][idx]:
                #         self.select_action(self.channels_selected['Labels'][idx],
                #                                'unlocated')
                # if self.unlocated_ch_labels is None or self.channels_selected['Labels'][idx] in self.located_channel_set.l_cha:
                #     if self.channels_selected['Selected'][idx]:
                #         self.select_action(self.channels_selected['Labels'][idx],
                #                            'head')

    def get_channels_selection_from_gui(self):
        """Updates the final_channel_selection dict. It makes possible to get from widget
           the selected channels as a EEGChannelSet object"""
        self.final_channel_selection = dict()
        saved_channel_set = meeg.EEGChannelSet()
        saved_channel_set.set_standard_montage(
            l_cha=list(self.channels_selected['Labels'][self.channels_selected['Selected']]),
            montage='10-05',
            allow_unlocated_channels=True)
        self.final_channel_selection['Used'] = saved_channel_set

    def to_serializable_obj(self):
        channels_selected = {k: v.tolist() for k, v in self.channels_selected.items()}
        del channels_selected['Plot line']
        sett_dict = {'montage': self.montage,
                     'ch_labels': self.ch_labels,
                     'channels_selected': channels_selected}
        return sett_dict

    @classmethod
    def from_serializable_obj(cls, dict_data):
        return cls(**dict_data)


class CustomDoubleSpinBox(QDoubleSpinBox):
    """Subclase de QDoubleSpinBox para desactivar la rueda del ratón."""

    def wheelEvent(self, event):
        # No hacer nada en la rueda del ratón
        event.ignore()
