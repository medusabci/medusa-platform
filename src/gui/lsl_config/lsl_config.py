# Built-in imports
import copy
import sys, os, json, traceback, math
# External imports
from PySide6.QtUiTools import loadUiType
from PySide6 import QtGui, QtWidgets
from PySide6.QtCore import Qt
import pylsl
# Medusa imports
from gui import gui_utils as gu
from gui.qt_widgets import dialogs
from gui.qt_widgets.notifications import NotificationStack
from acquisition import lsl_utils
import exceptions
import constants
from gui.qt_widgets.channel_selection import LSLEEGChannelSelection, \
    LSLGeneralChannelSelection

# Load the .ui files
ui_main_dialog = loadUiType(
    'gui/ui_files/lsl_config_dialog.ui')[0]
ui_stream_config_dialog = loadUiType(
    'gui/ui_files/lsl_config_medusa_params_dialog_new.ui')[0]


class LSLConfigDialog(QtWidgets.QDialog, ui_main_dialog):
    """ Main dialog class of the LSL config panel
    """
    def __init__(self, lsl_config, lsl_config_file_path,
                 theme_colors=None):
        """ Class constructor

        Parameters
        ----------
        lsl_config: list of acquisition.lsl_utils.LSLStreamWrapper
            List with the current working LSL streams
        theme_colors: dict
            Dict with the theme colors
        """
        try:
            super().__init__()
            self.setupUi(self)
            self.resize(600, 400)
            # Initialize the gui application
            self.dir = os.path.dirname(__file__)
            # TODO: Fix theme
            self.theme = 'dark'
            self.theme_colors = theme_colors
            self.stl = gu.set_css_and_theme(self, self.theme_colors)
            self.setWindowIcon(QtGui.QIcon('%s/medusa_task_icon.png' %
                               constants.IMG_FOLDER))
            self.setWindowTitle('Lab streaming layer (LSL) settings')
            # Set up tables
            self.tableWidget_available_streams.horizontalHeader().\
                setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
            self.tableWidget_available_streams.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows)
            self.tableWidget_available_streams.setEditTriggers(
                QtWidgets.QTableWidget.NoEditTriggers)
            self.tableWidget_working_streams.horizontalHeader(). \
                setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
            self.tableWidget_working_streams.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows)
            self.tableWidget_working_streams.setEditTriggers(
                QtWidgets.QTableWidget.NoEditTriggers)
            # ToolButtons
            self.set_up_tool_buttons()
            # First search
            self.lsl_config = lsl_config
            self.available_streams = []
            self.init_listwidget_working_streams()
            self.lsl_search(first_search=True)
            self.lsl_config_file_path = lsl_config_file_path
            # Connect the buttons
            self.setModal(True)
            self.show()
        except Exception as e:
            self.handle_exception(e)

    def init_listwidget_working_streams(self):
        try:
            # Add items
            updated_working_streams = []
            for idx, lsl_stream_wrapper in enumerate(
                    self.lsl_config['working_streams']):
                # Check that the lsl stream is available
                try:
                    lsl_utils.get_lsl_streams(
                        force_one_stream=True,
                        name=lsl_stream_wrapper.lsl_name,
                        type=lsl_stream_wrapper.lsl_type,
                        uid=lsl_stream_wrapper.lsl_uid,
                        source_id=lsl_stream_wrapper.lsl_source_id,
                        channel_count=lsl_stream_wrapper.lsl_n_cha,
                        nominal_srate=lsl_stream_wrapper.lsl_fs,
                    )
                except exceptions.LSLStreamNotFound as e:
                    continue
                # Add lsl_stream_info
                self.insert_working_stream_in_table(lsl_stream_wrapper)
                updated_working_streams.append(lsl_stream_wrapper)
            self.lsl_config['working_streams'] = updated_working_streams
        except Exception as e:
            self.handle_exception(e)

    def set_up_tool_buttons(self):
        try:
            # Search button
            icon = gu.get_icon("refresh.svg", theme_colors=self.theme_colors)
            # icon = QtGui.QIcon("%s/icons/reload.png" % constants.IMG_FOLDER)
            self.toolButton_search.setIcon(icon)
            self.toolButton_search.clicked.connect(self.lsl_search)
            # Add button
            icon = gu.get_icon("add.svg", theme_colors=self.theme_colors)
            # icon = QtGui.QIcon("%s/icons/plus.png" % constants.IMG_FOLDER)
            self.toolButton_add.setIcon(icon)
            self.toolButton_add.clicked.connect(self.add_lsl_stream)
            # Edit button
            icon = gu.get_icon("edit.svg", theme_colors=self.theme_colors)
            # icon = QtGui.QIcon("%s/icons/edit.png" % constants.IMG_FOLDER)
            self.toolButton_edit.setIcon(icon)
            self.toolButton_edit.clicked.connect(self.edit_lsl_stream)
            # Remove button
            icon = gu.get_icon("remove.svg", theme_colors=self.theme_colors)
            # icon = QtGui.QIcon("%s/icons/minus.png" % constants.IMG_FOLDER)
            self.toolButton_remove.setIcon(icon)
            self.toolButton_remove.clicked.connect(self.remove_lsl_stream)
        except Exception as e:
            self.handle_exception(e)

    def lsl_search(self, first_search=False):
        """This function searches for available LSL streams.
        """
        try:
            # Clear listWidget
            self.tableWidget_available_streams.setRowCount(0)
            # Search streams
            streams = lsl_utils.get_lsl_streams()
            # There are streams available
            self.available_streams = []
            for s, lsl_stream in enumerate(streams):
                try:
                    lsl_stream_wrapper = lsl_utils.LSLStreamWrapper(lsl_stream)
                    lsl_stream_wrapper.set_inlet(
                        proc_clocksync=False, proc_dejitter=False,
                        proc_monotonize=False, proc_threadsafe=True)
                    self.insert_available_stream_in_table(lsl_stream_wrapper)
                    self.available_streams.append(lsl_stream_wrapper)
                except pylsl.util.TimeoutError:
                    ex = exceptions.LSLStreamTimeout(
                        "An LSL stream outlet was detected, but the stream "
                        "information could not be retrieved. Possible causes "
                        "include incorrect network configuration, a missing or "
                        "inactive stream source, or firewall restrictions. "
                        "Please check your network settings and ensure the "
                        "stream source is active.")
                    self.handle_exception(ex)
        except exceptions.LSLStreamNotFound as e:
            if not first_search:
                self.handle_exception(e)
        except Exception as e:
            self.handle_exception(e)

    def add_lsl_stream(self):
        try:
            sel_item_row = self.get_selected_available_stream()
            if sel_item_row is None:
                return
            # Show dialog
            self.edit_stream_dialog = EditStreamDialog(
                self.available_streams[sel_item_row],
                self.lsl_config['working_streams'],
                theme_colors=self.theme_colors)
            self.edit_stream_dialog.accepted.connect(
                self.on_add_stream_ok)
            self.edit_stream_dialog.rejected.connect(
                self.on_edit_stream_cancel)
            self.edit_stream_dialog.exec_()
        except Exception as e:
            self.handle_exception(e)

    def edit_lsl_stream(self):
        try:
            # Get stream item and index
            sel_item_row = self.get_selected_working_stream()
            if sel_item_row is None:
                return
            self.lsl_stream_editing_idx = sel_item_row
            # Show dialog
            self.edit_stream_dialog = EditStreamDialog(
                self.lsl_config['working_streams'][self.lsl_stream_editing_idx],
                self.lsl_config['working_streams'],
                editing=True,
                theme_colors=self.theme_colors)
            self.edit_stream_dialog.accepted.connect(
                self.on_edit_stream_ok)
            self.edit_stream_dialog.rejected.connect(
                self.on_edit_stream_cancel)
            self.edit_stream_dialog.exec_()
        except Exception as e:
            self.handle_exception(e)

    def remove_lsl_stream(self):
        """ This function takes the selected item from the list and places its
        name in the LSL stream name.
        """
        try:
            sel_item_row = self.get_selected_working_stream()
            if sel_item_row is None:
                return
            # Remove stream
            self.tableWidget_working_streams.removeRow(sel_item_row)
            self.lsl_config['working_streams'].pop(sel_item_row)
        except Exception as e:
            self.handle_exception(e)

    def get_working_streams(self):
        try:
            return self.available_streams
        except Exception as e:
            self.handle_exception(e)

    def on_add_stream_ok(self):
        try:
            lsl_stream_wrapper = self.edit_stream_dialog.get_lsl_stream_info()
            self.insert_working_stream_in_table(lsl_stream_wrapper)
            self.lsl_config['working_streams'].append(lsl_stream_wrapper)
            self.edit_stream_dialog = None
        except Exception as e:
            self.handle_exception(e)

    def on_edit_stream_ok(self):
        try:
            lsl_stream_wrapper = self.edit_stream_dialog.get_lsl_stream_info()
            self.tableWidget_working_streams.removeRow(
                self.lsl_stream_editing_idx)
            self.insert_working_stream_in_table(
                lsl_stream_wrapper, self.lsl_stream_editing_idx)
            self.lsl_config['working_streams'][self.lsl_stream_editing_idx] = \
                lsl_stream_wrapper
            self.lsl_stream_editing_idx = None
            self.edit_stream_dialog = None
        except Exception as e:
            self.handle_exception(e)

    def on_edit_stream_cancel(self):
        try:
            pass
        except Exception as e:
            self.handle_exception(e)

    def get_selected_available_stream(self):
        sel_items = self.tableWidget_available_streams.selectedItems()
        if len(sel_items) == 0:
            return None
        return sel_items[0].row()

    def get_selected_working_stream(self):
        sel_items = self.tableWidget_working_streams.selectedItems()
        if len(sel_items) == 0:
            return None
        return sel_items[0].row()

    def insert_available_stream_in_table(self, lsl_stream_wrapper, row=None):
        # Row number
        row = row if row is not None \
            else self.tableWidget_available_streams.rowCount()
        # Insert row
        self.tableWidget_available_streams.insertRow(row)
        # Add Name
        self.tableWidget_available_streams.setItem(
            row, 0, QtWidgets.QTableWidgetItem(lsl_stream_wrapper.lsl_name))
        self.tableWidget_available_streams.setItem(
            row, 1, QtWidgets.QTableWidgetItem(lsl_stream_wrapper.hostname))
        self.tableWidget_available_streams.setItem(
            row, 2, QtWidgets.QTableWidgetItem(lsl_stream_wrapper.lsl_type))
        self.tableWidget_available_streams.setItem(
            row, 3, QtWidgets.QTableWidgetItem(
                str(lsl_stream_wrapper.lsl_n_cha)))

    def insert_working_stream_in_table(self, lsl_stream_wrapper, row=None):
        # Row number
        row = row if row is not None \
            else self.tableWidget_working_streams.rowCount()
        # Insert row
        self.tableWidget_working_streams.insertRow(row)
        # Add Name
        self.tableWidget_working_streams.setItem(
            row, 0, QtWidgets.QTableWidgetItem(lsl_stream_wrapper.medusa_uid))
        self.tableWidget_working_streams.setItem(
            row, 1, QtWidgets.QTableWidgetItem(lsl_stream_wrapper.hostname))
        self.tableWidget_working_streams.setItem(
            row, 2, QtWidgets.QTableWidgetItem(lsl_stream_wrapper.medusa_type))
        self.tableWidget_working_streams.setItem(
            row, 3, QtWidgets.QTableWidgetItem(
                str(lsl_stream_wrapper.n_cha)))

    def accept(self):
        """ This function updates the lsl_streams.json file and saves it
        """
        try:
            super().accept()
            lsl_config = dict(self.lsl_config)
            with open(self.lsl_config_file_path, 'w') as f:
                lsl_config['working_streams'] = \
                    [stream.to_serializable_obj() for stream in
                     lsl_config['working_streams']]
                json.dump(lsl_config, f, indent=4)
        except Exception as e:
            self.handle_exception(e)

    def reject(self):
        """ This function cancels the configuration"""
        try:
            super().reject()
        except Exception as e:
            self.handle_exception(e)

    def handle_exception(self, ex):
        traceback.print_exc()
        dialogs.error_dialog(str(ex), ex.__class__.__name__, self.theme_colors)


class EditStreamDialog(QtWidgets.QDialog, ui_stream_config_dialog):

    def __init__(self, lsl_stream_info, working_lsl_streams, editing=False,
                 theme_colors=None):
        try:
            # Super call
            super().__init__()
            self.setupUi(self)
            # Set style
            self.theme_colors = gu.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gu.set_css_and_theme(self, self.theme_colors)
            self.setWindowIcon(QtGui.QIcon('%s/medusa_task_icon.png' %
                                           constants.IMG_FOLDER))
            self.setWindowTitle('Stream settings')
            self.resize(600, 400)
            # Params
            self.editing = editing
            self.cha_info = None
            # Create a new lsl wrapper object to avoid reference passing
            # problems with working_lsl_streams
            self.lsl_stream_info = lsl_utils.LSLStreamWrapper(
                lsl_stream_info.lsl_stream)
            self.lsl_stream_info.set_inlet(
                proc_clocksync=lsl_stream_info.lsl_proc_clocksync,
                proc_dejitter=lsl_stream_info.lsl_proc_dejitter,
                proc_monotonize=lsl_stream_info.lsl_proc_monotonize,
                proc_threadsafe=lsl_stream_info.lsl_proc_threadsafe)
            if self.lsl_stream_info.lsl_fs is None:
                self.lsl_stream_info.lsl_fs = self.lsl_stream_info.fs
            if self.editing:
                self.lsl_stream_info.update_medusa_parameters_from_lslwrapper(
                    lsl_stream_info)
                self.cha_info = self.lsl_stream_info.cha_info
            # Check errors
            if self.lsl_stream_info.fs <= 0:
                self.handle_exception(exceptions.IncorrectLSLConfig(
                    f"The sample rate of the stream "
                    f"'{self.lsl_stream_info.lsl_name}' "
                    f"is not defined. This may affect processing and "
                    f"timeouts that requires a fixed sampling rate."))
            self.working_lsl_streams = working_lsl_streams
            # Init widgets
            self.init_widgets()
        except Exception as e:
            self.handle_exception(e)

    def init_widgets(self):
        # Medusa uid edit line
        self.lineEdit_medusa_uid.textChanged.connect(
            self.on_medusa_stream_uid_changed)
        # Medusa type combobox
        for key, val in constants.MEDUSA_LSL_TYPES.items():
            self.comboBox_medusa_type.addItem(key, val)
        self.comboBox_medusa_type.currentIndexChanged.connect(
            self.on_medusa_stream_type_changed)
        # LSL parameters
        self.checkBox_lsl_clocksync.setChecked(
            self.lsl_stream_info.lsl_proc_clocksync)
        self.checkBox_lsl_monotonize.setChecked(
            self.lsl_stream_info.lsl_proc_monotonize)
        self.checkBox_lsl_dejitter.setChecked(
            self.lsl_stream_info.lsl_proc_dejitter)
        self.checkBox_lsl_threadsafe.setChecked(
            self.lsl_stream_info.lsl_proc_threadsafe)
        self.checkBox_lsl_clocksync.toggled.connect(
            self.lsl_processing_flags_changed)
        self.checkBox_lsl_monotonize.toggled.connect(
            self.lsl_processing_flags_changed)
        self.checkBox_lsl_dejitter.toggled.connect(
            self.lsl_processing_flags_changed)
        self.checkBox_lsl_threadsafe.toggled.connect(
            self.lsl_processing_flags_changed)
        self.spinBox_lsl_fs.setValue(self.lsl_stream_info.fs)
        self.pushButton_lsl_fs.clicked.connect(self.on_change_fs)
        # Initialize comboboxes
        self.update_desc_fields()
        self.update_channel_fields()
        if not self.editing:
            self.on_read_channels_info()
        else:
            self.update_channels_table()
        # Connect events
        self.comboBox_desc_channels_field.currentIndexChanged.connect(
            self.update_channel_fields)
        self.comboBox_channel_label_field.currentIndexChanged.connect(
            self.update_cha_label)
        # Channels buttons
        self.pushButton_ch_config.clicked.connect(self.on_configure_channels)
        # Table
        self.tableView_ch_summary.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.tableView_ch_summary.setMinimumHeight(100)
        self.tableView_ch_summary.setMaximumHeight(300)
        self.tableView_ch_summary.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch)
        # self.tableView_ch_summary.horizontalHeader().hide()
        self.tableView_ch_summary.verticalHeader().hide()
        # Init params
        if self.lsl_stream_info.medusa_params_initialized:
            self.lineEdit_medusa_uid.setText(self.lsl_stream_info.medusa_uid)
            gu.select_entry_combobox_with_data(
                self.comboBox_medusa_type,
                self.lsl_stream_info.medusa_type,
                force_selection=True,
                forced_selection='CustomBiosignalData')
            gu.select_entry_combobox_with_data(
                self.comboBox_desc_channels_field,
                self.lsl_stream_info.desc_channels_field)
            gu.select_entry_combobox_with_data(
                self.comboBox_channel_label_field,
                self.lsl_stream_info.channel_label_field)
            # self.set_checked_channels(
            #     self.lsl_stream_info.selected_channels_idx)
        else:
            self.lineEdit_medusa_uid.setText(self.lsl_stream_info.lsl_name)
            gu.select_entry_combobox_with_data(
                self.comboBox_medusa_type,
                self.lsl_stream_info.lsl_type,
                force_selection=True,
                forced_selection='CustomBiosignalData')

    def on_medusa_stream_uid_changed(self):
        try:
            pass
        except Exception as e:
            self.handle_exception(e)

    def on_medusa_stream_type_changed(self):
        try:
            self.update_channels_table()
            pass
        except Exception as e:
            self.handle_exception(e)

    def lsl_processing_flags_changed(self):
        clocksync = self.checkBox_lsl_clocksync.isChecked()
        monotonize = self.checkBox_lsl_monotonize.isChecked()
        dejitter = self.checkBox_lsl_dejitter.isChecked()
        threadsafe = self.checkBox_lsl_threadsafe.isChecked()
        self.lsl_stream_info.set_inlet(
            proc_clocksync=clocksync, proc_monotonize=monotonize,
            proc_dejitter=dejitter, proc_threadsafe=threadsafe)

    def update_desc_fields(self):
        """Updates the values of the combobox to select the channels description
        """
        # Get channels
        desc_fields = self.lsl_stream_info.get_description_fields()
        # Update combobox
        self.comboBox_desc_channels_field.clear()
        if len(desc_fields) > 0:
            for field in desc_fields:
                self.comboBox_desc_channels_field.addItem(field, True)
            gu.select_entry_combobox_with_text(
                self.comboBox_desc_channels_field,
                'channels', force_selection=True)
        else:
            self.comboBox_desc_channels_field.addItem('channels', False)

    def on_change_fs(self):
        # Create a QDialog
        dialog = QtWidgets.QDialog()
        dialog.stl = gu.set_css_and_theme(dialog, self.theme_colors)
        dialog.setWindowTitle("Change sampling frequency value")

        # Layout
        layout = QtWidgets.QVBoxLayout(dialog)

        # Warning label
        label = QtWidgets.QLabel("Attention! This action should be performed from the software that emits the LSL stream.")
        label.setAlignment(Qt.AlignCenter)

        # Crear un QLabel adicional para el mensaje informativo
        info_label = QtWidgets.QLabel("Select the new sampling frequency value:")
        info_label.setAlignment(Qt.AlignCenter)

        # Crear un QSpinBox
        spin_box = QtWidgets.QSpinBox()
        spin_box.setMinimum(1)
        spin_box.setMaximum(1000000000)
        spin_box.setValue(self.spinBox_lsl_fs.value())  # Valor inicial
        spin_box.setAlignment(Qt.AlignCenter)

        # Agregar los widgets al layout
        layout.addWidget(label)
        layout.addWidget(info_label)
        layout.addWidget(spin_box)

        # Crear los botones de "Aceptar" y "Cancelar"
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(button_box)

        # Conectar las señales de los botones
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        # Mostrar el diálogo
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.spinBox_lsl_fs.setValue(spin_box.value())
    def update_channel_fields(self):
        """Updates the values of the combobox to select the channel label
        """
        # Get channels
        current_desc_field = \
            self.comboBox_desc_channels_field.currentText()
        dec_cha_info = self.lsl_stream_info.get_desc_field_value(
            current_desc_field)
        # Check errors
        if not isinstance(dec_cha_info, list) or len(dec_cha_info) == 0:
            dialogs.error_dialog(
                message='Malformed channels field "%s"' % current_desc_field,
                title='Error',
                theme_colors=self.theme_colors)
            dec_cha_info = list()
            self.comboBox_channel_label_field.setVisible(False)
            self.label_channels_label_field.setVisible(False)
            for i in range(self.lsl_stream_info.lsl_n_cha):
                dec_cha_info.append({'label': str(i)})
        else:
            self.comboBox_channel_label_field.setVisible(True)

        # Update combobox
        self.comboBox_channel_label_field.clear()
        cha_fields = list(dec_cha_info[0].keys())
        for field in cha_fields:
            self.comboBox_channel_label_field.addItem(field)
        gu.select_entry_combobox_with_text(
            self.comboBox_channel_label_field, 'label')

    def on_configure_channels(self):
        if self.comboBox_medusa_type.currentData() == 'EEG':
            channel_selection = LSLEEGChannelSelection(
                self.comboBox_channel_label_field.currentText(),
            lsl_cha_info=self.cha_info)
            channel_selection.close_signal.connect(self.config_finished)
            channel_selection.exec_()

        else:
            channel_selection = LSLGeneralChannelSelection(
                self.comboBox_channel_label_field.currentText(),
                lsl_cha_info=self.cha_info)
            channel_selection.close_signal.connect(self.config_finished)
            channel_selection.exec_()

    def config_finished(self,data):
        # Update LSL cha info
        self.cha_info = data

        self.update_channels_table()


    def on_read_channels_info(self):
        current_desc_field = \
            self.comboBox_desc_channels_field.currentText()
        self.cha_info = \
            self.lsl_stream_info.get_desc_field_value(current_desc_field)
        self.update_cha_label()

    def load_custom_labels(self):
        # Save json to test
        # -------------------------------------------------------------------
        # desc_channels_field = self.comboBox_desc_channels_field.currentText()
        # channel_label_field = self.comboBox_channel_label_field.currentText()
        # # Get selected channels and update cha info
        # selected_channels_idx = self.get_checked_channels_idx()
        # sel_cha_info = [self.cha_info[i] for i in selected_channels_idx]
        # n_cha = len(selected_channels_idx)
        # l_cha = [info[channel_label_field] for info in sel_cha_info] \
        #     if channel_label_field is not None else list(range(n_cha))
        # new_l_cha = dict(zip(l_cha, [str(c) for c in range(n_cha)]))
        # with open('../config/custom_cha.json', 'w') as f:
        #     json.dump(new_l_cha, f, indent=4)
        # -------------------------------------------------------------------
        # Show file dialog
        fdialog = QtWidgets.QFileDialog()
        fname = fdialog.getOpenFileName(
            parent=self,
            caption='Custom labels file',
            dir='../config/',
            filter='Settings (*.json)')[0]
        if fname:
            with open(fname, 'r') as f:
                custom_labels = json.load(f)
        # Set labels in channels
        for i in range(self.tableWidget_channels.rowCount()):
            for j in range(self.tableWidget_channels.columnCount()):
                cell_widget = self.tableWidget_channels.cellWidget(i, j)
                if cell_widget is not None:
                    # Get widgets
                    cha_line_edit = cell_widget.findChild(QtWidgets.QLineEdit,
                                                          'cha_line_edit')
                    curr_label = cha_line_edit.text()
                    if curr_label in custom_labels:
                        new_label = custom_labels[curr_label]
                        cha_line_edit.setText(new_label)

    def select_all_channels(self):
        for i in range(self.tableWidget_channels.rowCount()):
            for j in range(self.tableWidget_channels.columnCount()):
                # Get widgets
                cell_widget = self.tableWidget_channels.cellWidget(i, j)
                if cell_widget is not None:
                    cha_checkbox = cell_widget.findChild(QtWidgets.QCheckBox,
                                                         'cha_checkbox')
                    cha_checkbox.setChecked(True)

    def deselect_all_channels(self):
        for i in range(self.tableWidget_channels.rowCount()):
            for j in range(self.tableWidget_channels.columnCount()):
                # Get widgets
                cell_widget = self.tableWidget_channels.cellWidget(i, j)
                if cell_widget is not None:
                    cha_checkbox = cell_widget.findChild(QtWidgets.QCheckBox,
                                                         'cha_checkbox')
                    cha_checkbox.setChecked(False)
    def update_cha_info_dict(self):
        ch_label = self.comboBox_channel_label_field.currentText()
        if self.cha_info != None:
            for i, ch in enumerate(self.cha_info):
                if self.comboBox_medusa_type.currentData() == 'EEG':
                    order = [ch_label, 'medusa_label', 'x_pos', 'y_pos','selected']
                    if 'x_pos' not in ch.keys():
                        ch['x_pos'] = None
                        ch['y_pos'] = None
                        ch['selected'] = False

                else:
                    order = [ch_label, 'medusa_label', 'selected']
                    if 'selected' not in ch.keys():
                        ch['selected'] = False
                    if 'x_pos' in ch.keys():
                        del ch['x_pos']
                        del ch['y_pos']


                ch_ro = {k: ch[k] for k in order if k in ch}
                ch_ro.update({k: v for k, v in ch.items() if k not in order})
                self.cha_info[i] = ch_ro

    def update_cha_label(self):
        ch_label = self.comboBox_channel_label_field.currentText()
        for i, ch in enumerate(self.cha_info):
            ch['medusa_label'] = ch[ch_label]
        self.update_channels_table()

    def update_channels_table(self):
        self.update_cha_info_dict()
        self.tableView_ch_summary.clearSpans()

        model = QtGui.QStandardItemModel()

        if isinstance(self.cha_info, list) and \
                len(self.cha_info) > 0:

            keys = list(self.cha_info[0].keys())

            model.setColumnCount(len(keys))
            for col, key in enumerate(keys):
                model.setHorizontalHeaderItem(col, QtGui.QStandardItem(key))

            for row_data in self.cha_info:
                row_items = []

                for key in keys:
                    value = row_data.get(key, "")
                    item = QtGui.QStandardItem(
                        str(value))
                    row_items.append(item)

                model.appendRow(row_items)
            self.tableView_ch_summary.setModel(model)
        else:
            self.tableView_ch_summary.clearSpans()

    def set_checked_channels(self, cha_idx):
        idx = 0
        for i in range(self.tableWidget_channels.rowCount()):
            for j in range(self.tableWidget_channels.columnCount()):
                # Get widgets
                cell_widget = self.tableWidget_channels.cellWidget(i, j)
                if cell_widget is not None:
                    cha_checkbox = cell_widget.findChild(QtWidgets.QCheckBox,
                                                         'cha_checkbox')
                    if idx in cha_idx:
                        cha_checkbox.setChecked(True)
                    else:
                        cha_checkbox.setChecked(False)
                idx += 1
        return cha_idx

    def get_checked_channels_idx(self):
        # Iterate channels
        cha_idx = []
        for idx,channel in enumerate(self.cha_info):
            if channel['selected']:
                cha_idx.append(idx)
        return cha_idx

    def get_lsl_stream_info(self):
        try:
            return self.lsl_stream_info
        except Exception as e:
            self.handle_exception(e)

    def accept(self):
        # Check the medusa uid, it has to be unique
        medusa_uid = self.lineEdit_medusa_uid.text()
        if not self.editing:
            if not lsl_utils.check_if_medusa_uid_is_available(
                    self.working_lsl_streams, medusa_uid):
                dialogs.error_dialog(
                    'Duplicated MEDUSA LSL UID. This parameter must be unique, '
                    'please change it.', 'Incorrect medusa_uid')
                return
        # Check processing flags
        if not self.lsl_stream_info.local_stream:
            if not self.lsl_stream_info.lsl_proc_clocksync:
                if not dialogs.confirmation_dialog(
                    'This LSL stream comes from another host, '
                    'and LSL clocksync proccessing flag is disabled. '
                    'For external LSL streams it is recommended to '
                    'enable this processing flag. Are you sure you want '
                    'to continue?', 'Warning!'):
                        return
        # Get lsl params
        medusa_type = self.comboBox_medusa_type.currentData()
        desc_channels_field = self.comboBox_desc_channels_field.currentText()
        channel_label_field = self.comboBox_channel_label_field.currentText()
        fs = self.spinBox_lsl_fs.value()
        # Get selected channels and update cha info
        sel_cha_idx = self.get_checked_channels_idx()
        # Set medusa params
        self.lsl_stream_info.set_medusa_parameters(
            medusa_uid=medusa_uid,
            medusa_type=medusa_type,
            desc_channels_field=desc_channels_field,
            channel_label_field=channel_label_field,
            cha_info=self.cha_info,
            selected_channels_idx=sel_cha_idx,
            fs=fs,
            lsl_fs=self.lsl_stream_info.lsl_fs)
        super().accept()

    def reject(self):
        super().reject()

    def handle_exception(self, ex):
        traceback.print_exc()
        dialogs.error_dialog(str(ex), ex.__class__.__name__, self.theme_colors)
