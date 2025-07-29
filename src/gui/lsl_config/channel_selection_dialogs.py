# PYTHON MODULES
import os, time, json, threading
from functools import partial
# EXTERNAL IMPORTS
import numpy as np
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
from gui.qt_widgets.dialogs import *


class GeneralChannelSelection(MedusaDialog):
    """This class allows you to control the GUI of the general channel
       selection widget."""
    def __init__(self, cha_field, lsl_cha_info):
        super().__init__('MEDUSA Channel Selection',
                         theme_colors=None,
                         width=640, heigh=360,
                         pos_x=None, pos_y=None)
        # Size constraints
        self.setMinimumSize(320, 180)
        # Initialize variables
        self.changes_made = False
        self.cha_field = cha_field
        self.lsl_cha_info = lsl_cha_info
        self.lsl_cha_keys = lsl_cha_info[0].keys()
        self.ch_labels = [channel['medusa_label'] for channel in
                          self.lsl_cha_info]
        self.table_keys = []
        self.ch_checkboxs = []

    def create_layout(self):
        """Creates the layout of the dialog. Reimplement this method to create
        the custom layout.
        """
        label = QLabel('Empty layout')
        layout = QVBoxLayout()
        layout.addWidget(label)
        return layout

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
            fdialog,
            caption='Save channel selection',
            dir='../../channelset/',
            filter='JSON (*.json)')
        if fname[0]:
            with open(fname[0], 'w', encoding='utf-8') as f:
                json.dump(self.get_ch_dict(), f, indent=4)

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

    def show_warning(self, text):
        warning_dialog(message=text, title="Warning",
                       theme_colors=self.theme_colors)


class LSLGeneralChannelSelection(GeneralChannelSelection):
    """This class allows you to control the GUI of the general channel
       selection widget."""
    close_signal = Signal(object)
    def __init__(self, cha_field,lsl_cha_info):
        super().__init__(cha_field=cha_field,
                         lsl_cha_info=lsl_cha_info)

        # Init table
        self.init_table()

        # Prevent resizing too small
        self.setMinimumSize(800, 300)

    def create_layout(self):
        # === Main vertical layout ===
        layout = QVBoxLayout(self)
        # layout.setSizeConstraint(QVBoxLayout.SetNoConstraint)

        # === Horizontal split ===
        horizontal_layout = QHBoxLayout()
        layout.addLayout(horizontal_layout)

        # === Left: QTableWidget ===
        self.channels_table = ChannelSelectionTable()
        horizontal_layout.addWidget(self.channels_table)

        # === Right: Button column ===
        button_column = QVBoxLayout()
        horizontal_layout.addLayout(button_column)

        buttons = [
            ("selectall_btn", "Select all", 'select_all'),
            ("unselectall_btn", "Unselect all", 'unselect_all'),
            ("load_btn", "Load", 'load'),
            ("save_btn", "Save", 'save'),
            ("done_btn", "Done", 'close'),
        ]

        for obj_name, label, func in buttons:
            btn = QPushButton(label)
            btn.setObjectName(obj_name)
            btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            btn.clicked.connect(getattr(self, func))
            setattr(self, obj_name, btn)
            button_column.addWidget(btn)

        # Add vertical spacer at the bottom
        button_column.addItem(
            QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        return layout

    def select_all(self):
        for checkbox in self.ch_checkboxs:
            checkbox.setChecked(True)
        self.changes_made = True

    def unselect_all(self):
        for checkbox in self.ch_checkboxs:
            checkbox.setChecked(False)
        self.changes_made = True

    def init_table(self):
        self.channels_table.setColumnCount(len(self.lsl_cha_keys))
        self.channels_table.setRowCount(len(self.lsl_cha_info))
        # Set column headers
        table_keys = ["", "medusa_label"]
        for key in self.lsl_cha_keys:
            if key not in table_keys and key != 'selected':
                table_keys.append(key)
        self.channels_table.setHorizontalHeaderLabels(table_keys)

        # Checkbox column
        header = self.channels_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.channels_table.setColumnWidth(0, 25)

        for i_r, row_data in enumerate(self.lsl_cha_info):
            channel = self.lsl_cha_info[i_r]
            # Checkbox
            checkbox = QCheckBox()
            checkbox.setCheckable(True)
            checkbox.setChecked(row_data['selected'])
            self.ch_checkboxs.append(checkbox)
            self.channels_table.setCellWidget(i_r, 0, checkbox)
            # Line edit
            cha_line_edit = QLineEdit(channel['medusa_label'])
            cha_line_edit.setObjectName('cha_name')
            self.channels_table.setCellWidget(
                i_r, 1, cha_line_edit)
            # Add rest of data
            for i_k, key in enumerate(table_keys):
                if i_k > 1:
                    value = row_data.get(key, "")
                    item = QLineEdit(str(value))
                    if key == self.cha_field:
                        item.setEnabled(False)
                    self.channels_table.setCellWidget(i_r, i_k, item)

    def get_ch_dict(self):
        channels_dict = []
        for row in range(self.channels_table.rowCount()):
            # Init channel dict
            ch_dict = {}

            # Get checkbox
            checkbox_widget = self.channels_table.cellWidget(row, 0)
            if checkbox_widget is not None:
                ch_dict['selected'] = checkbox_widget.isChecked()
            else:
                raise ValueError

            # Get line edit for medusa_label
            label_widget = self.channels_table.cellWidget(row, 1)
            if label_widget is not None:
                ch_dict['medusa_label'] = label_widget.text()
            else:
                raise ValueError

            # Get remaining fields
            for col in range(2, self.channels_table.columnCount()):
                widget = self.channels_table.cellWidget(row, col)
                if widget is not None:
                    ch_dict[self.channels_table.horizontalHeaderItem(
                        col).text()] = widget.text()
                else:
                    ch_dict[self.channels_table.horizontalHeaderItem(
                        col).text()] = ""
            channels_dict.append(ch_dict)

        return channels_dict

    def load(self):
        """ Opens a dialog to load a configuration file. """
        fdialog = QFileDialog()
        fname = fdialog.getOpenFileName(
            fdialog,
            caption='Load Channel Selection',
            dir='../../channelset/',
            filter='JSON (*.json)')
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

            self.lsl_cha_info = loaded_channel_dict
            self.table_keys = []
            self.ch_checkboxs = []
            self.init_table()


class LSLEEGChannelSelection(GeneralChannelSelection):

    close_signal = Signal(object)

    def __init__(self,cha_field,lsl_cha_info):

        # Call super
        super().__init__(cha_field=cha_field,
                         lsl_cha_info=lsl_cha_info)

        # Initialize interactive selection
        self.channel_set = meeg.EEGChannelSet()
        self.channel_set.set_standard_montage(
            self.ch_labels, allow_unlocated_channels=True)
        self.update_ch_set(self.lsl_cha_info)
        self.interactive_selection = EEGChannelSelectionPlot(
            channel_set=self.channel_set,
            channels_selected=self.update_ch_info())

        # Topographic plot and unlocated channels
        canvas_head = self.interactive_selection.fig_head.canvas
        canvas_head.setMinimumSize(200, 200)
        canvas_head.setSizePolicy(QSizePolicy.Expanding,
                                  QSizePolicy.Expanding)
        self.plot_layout.addWidget(canvas_head)

        canvas_unlocated = self.interactive_selection.fig_unlocated.canvas
        canvas_unlocated.setMinimumSize(100, 200)
        canvas_unlocated.setSizePolicy(QSizePolicy.Expanding,
                                       QSizePolicy.Expanding)
        self.unlocated_layout.addWidget(canvas_unlocated)

        # Connect channels in plot with channels in table
        self.finished = False
        self.working_threads = list()
        Th1 = threading.Thread(target=self.watch_ch_clicked)
        Th1.start()
        self.working_threads.append(Th1)
        self.init_table()

        # Prevent resizing too small
        self.setMinimumSize(800, 600)

        # Uncomment to debug
        self.setModal(True)

    def create_layout(self):

        # Main layout
        layout = QGridLayout()

        # === Set stretch factors to allocate width ===
        layout.setColumnStretch(0, 3)  # Plot/table
        layout.setColumnStretch(1, 1)  # Button panel
        layout.setRowStretch(0, 2)  # Plots
        layout.setRowStretch(1, 3)  # Table + buttons

        # === Top left: plot_layout ===
        self.plot_layout = QVBoxLayout()
        layout.addLayout(self.plot_layout, 0, 0)

        # === Top right: unlocated_layout ===
        self.unlocated_layout = QVBoxLayout()
        layout.addLayout(self.unlocated_layout, 0, 1)

        # === Bottom row: Table + Buttons (horizontal) ===
        bottom_row_layout = QHBoxLayout()
        layout.addLayout(bottom_row_layout, 1, 0, 1, 2)

        self.channels_table = ChannelSelectionTable()
        self.channels_table.setMinimumSize(400, 200)
        self.channels_table.setSizePolicy(QSizePolicy.Expanding,
                                          QSizePolicy.Expanding)
        bottom_row_layout.addWidget(self.channels_table, stretch=1)

        # === Buttons ===
        button_column = QVBoxLayout()
        bottom_row_layout.addLayout(button_column)

        buttons = [
            ("refresh_btn", "Refresh", 'refresh'),
            ("selectall_btn", "Select all", 'select_all'),
            ("unselectall_btn", "Unselect all", 'unselect_all'),
            ("load_btn", "Load", 'load'),
            ("save_btn", "Save", 'save'),
            ("done_btn", "Done", 'close'),
        ]

        for obj_name, label, func in buttons:
            btn = QPushButton(label)
            btn.setObjectName(obj_name)
            btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            btn.clicked.connect(getattr(self, func))
            setattr(self, obj_name, btn)
            button_column.addWidget(btn)

        # Push buttons to top
        button_column.addItem(
            QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        return layout

    def select_all(self):
        self.interactive_selection.select_all()
        self.changes_made = True

    def unselect_all(self):
        self.interactive_selection.unselect_all()
        self.changes_made = True

    def refresh(self):
        self.interactive_selection.located_channel_set = meeg.EEGChannelSet()
        self.interactive_selection.unlocated_channels = []
        for i in range(len(self.ch_checkboxs)):
            # Update the name of the channel names
            label = self.channels_table.cellWidget(i, 1).text()
            self.interactive_selection.channels_selected['Labels'][i] = label
            # If second column is active -> located channel
            if self.channels_table.cellWidget(i,2).isEnabled():
                xpos = self.channels_table.cellWidget(i,2).value()
                ypos = self.channels_table.cellWidget(i,3).value()
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
        self.plot_layout.addWidget(self.interactive_selection.fig_head.canvas)
        self.unlocated_layout.addWidget(
            self.interactive_selection.fig_unlocated.canvas)

    def on_checked(self, state, ch_index):
        label = self.interactive_selection.l_cha[ch_index]
        if state == 0:
            state = False
        else:
            state = True
        if self.interactive_selection.channels_selected["Selected"][
            ch_index] != state:
            if label in self.interactive_selection.located_channel_set.l_cha:
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
        self.channels_table.setColumnCount(len(self.lsl_cha_keys))
        self.channels_table.setRowCount(len(channel_set.channels))
        # Set column headers
        table_keys = ["", "medusa_label", "x_pos", "y_pos", "manage position"]
        for key in self.lsl_cha_keys:
            if key not in table_keys and key != 'selected':
                table_keys.append(key)
        self.channels_table.setHorizontalHeaderLabels(table_keys)

        # Checkbox column
        header = self.channels_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.channels_table.setColumnWidth(0, 25)

        for i_r, row_data in enumerate(self.lsl_cha_info):
            channel = channel_set.channels[i_r]
            # Checkbox
            checkbox = QCheckBox()
            checkbox.setCheckable(True)
            checkbox.setChecked(row_data['selected'])
            checkbox.stateChanged.connect(
                lambda state, index=i_r: self.on_checked(state, index))
            self.ch_checkboxs.append(checkbox)
            self.channels_table.setCellWidget(i_r, 0, checkbox)

            # Line edit
            cha_line_edit = QLineEdit(channel['label'])
            cha_line_edit.setObjectName('cha_name')
            self.channels_table.setCellWidget(
                i_r, 1, cha_line_edit)

            # Position
            x_spinbox = CustomDoubleSpinBox()
            x_spinbox.setMinimum(-3)
            x_spinbox.setMaximum(3)
            y_spinbox = CustomDoubleSpinBox()
            y_spinbox.setMinimum(-3)
            y_spinbox.setMaximum(3)
            manage_button = QPushButton()
            if 'r' in channel.keys():
                x_spinbox.setValue(channel['r'] * np.cos(channel['theta']))
                y_spinbox.setValue(channel['r'] * np.sin(channel['theta']))
                manage_button.setText('Make unlocated')
            elif 'x' in channel.keys():
                x_spinbox.setValue(channel['x'])
                y_spinbox.setValue(channel['y'])
                manage_button.setText('Make unlocated')
            else:
                x_spinbox.setEnabled(False)
                y_spinbox.setEnabled(False)
                manage_button.setText('Set coordinates')

            self.channels_table.setCellWidget(i_r, 2, x_spinbox)
            self.channels_table.setCellWidget(i_r, 3, y_spinbox)
            manage_button.clicked.connect(partial(self.on_define_coords, i_r))
            self.channels_table.setCellWidget(i_r, 4, manage_button)

            # Add rest of data
            for i_k, key in enumerate(table_keys):
                if i_k > 4:
                    value = row_data.get(key, "")
                    item = QLineEdit(str(value))
                    if key == self.cha_field:
                        item.setEnabled(False)
                    self.channels_table.setCellWidget(i_r, i_k, item)

    def on_define_coords(self,i):
        # Remove existing buttons
        if self.channels_table.cellWidget(i,4).text() == 'Set coordinates':
            self.channels_table.cellWidget(i, 2).setEnabled(True)
            self.channels_table.cellWidget(i, 3).setEnabled(True)
            self.channels_table.cellWidget(i, 4).setText('Make unlocated')
        else:
            self.channels_table.cellWidget(i, 2).setEnabled(False)
            self.channels_table.cellWidget(i, 3).setEnabled(False)
            self.channels_table.cellWidget(i, 4).setText('Set coordinates')

    def get_ch_dict(self):
        channels_dict = []
        for row in range(self.channels_table.rowCount()):
            # Init channel dict
            ch_dict = {}
            # Get checkbox
            checkbox_widget = self.channels_table.cellWidget(row, 0)
            if checkbox_widget is not None:
                ch_dict['selected'] = checkbox_widget.isChecked()
            else:
                raise ValueError
            # Get line edit for medusa_label
            label_widget = self.channels_table.cellWidget(row, 1)
            if label_widget is not None:
                ch_dict['medusa_label'] = label_widget.text()
            else:
                raise ValueError
            # Get coordinates
            if self.channels_table.cellWidget(row, 2).isEnabled():
                ch_dict['x_pos'] = (
                    self.channels_table.cellWidget(row, 2).value())
                ch_dict['y_pos'] = (
                    self.channels_table.cellWidget(row, 3).value())
            else:
                ch_dict['x_pos'] = None
                ch_dict['y_pos'] = None

            # Get rest of the data
            for col in range(4, self.channels_table.columnCount()):
                key = f'{self.channels_table.horizontalHeaderItem(col).text()}'
                ch_dict[key] = self.channels_table.cellWidget(row, col).text()
            channels_dict.append(ch_dict)

        return channels_dict

    def clear_plots(self):
        self.interactive_selection.fig_unlocated.clf()
        self.interactive_selection.fig_head.clf()
        self.plot_layout.removeWidget(self.interactive_selection.fig_head.canvas)
        self.interactive_selection.fig_head.canvas.deleteLater()
        self.interactive_selection.fig_head.canvas = None
        self.unlocated_layout.removeWidget(
            self.interactive_selection.fig_unlocated.canvas)
        self.interactive_selection.fig_unlocated.canvas.deleteLater()
        self.interactive_selection.fig_unlocated.canvas = None
        plt.close(self.interactive_selection.fig_head)
        self.interactive_selection.fig_head = None
        plt.close(self.interactive_selection.fig_unlocated)
        self.interactive_selection.fig_unlocated = None

    def load(self):
        """ Opens a dialog to load a configuration file. """
        fdialog = QFileDialog()
        fname = fdialog.getOpenFileName(
            fdialog,
            caption='Load Channel Selection',
            dir='../../channelset/',
            filter='JSON (*.json)')

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
            # Get selected channels
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
            self.plot_layout.addWidget(self.interactive_selection.fig_head.canvas)
            self.interactive_selection.fig_head.canvas.draw()
            self.unlocated_layout.addWidget(
                self.interactive_selection.fig_unlocated.canvas)
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
            self.plot_layout.deleteLater()
            event.accept()


class ChannelSelectionTable(QTableWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("channels_table")
        # Configure size policy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(400, 200)
        # Configure scroll bars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Configure horizontal header
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setMinimumSectionSize(0)
        header.setDefaultSectionSize(50)
        # Configure horizontal header
        # self.verticalHeader().hide()



class CustomDoubleSpinBox(QDoubleSpinBox):
    """Subclase de QDoubleSpinBox para desactivar la rueda del ratón."""

    def wheelEvent(self, event):
        # No hacer nada en la rueda del ratón
        event.ignore()
