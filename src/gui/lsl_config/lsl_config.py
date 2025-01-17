# Built-in imports
import copy
import sys, os, json, traceback, math
# External imports
from PySide6.QtUiTools import loadUiType
from PySide6 import QtGui, QtWidgets
# Medusa imports
from gui import gui_utils as gu
from gui.qt_widgets import dialogs
from gui.qt_widgets.notifications import NotificationStack
from acquisition import lsl_utils
import exceptions
import constants

# Load the .ui files
ui_main_dialog = loadUiType(
    'gui/ui_files/lsl_config_dialog.ui')[0]
ui_stream_config_dialog = loadUiType(
    'gui/ui_files/lsl_config_medusa_params_dialog.ui')[0]


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
            self.notifications = NotificationStack(parent=self)
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
                        nominal_srate=lsl_stream_wrapper.fs,
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
                lsl_stream_wrapper = lsl_utils.LSLStreamWrapper(lsl_stream)
                self.insert_available_stream_in_table(lsl_stream_wrapper)
                self.available_streams.append(lsl_stream_wrapper)
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
        dialogs.error_dialog(str(ex), 'Error', self.theme_colors)


class EditStreamDialog(QtWidgets.QDialog, ui_stream_config_dialog):

    def __init__(self, lsl_stream_info, working_lsl_streams, editing=False,
                 theme_colors=None):
        try:
            # Super call
            super().__init__()
            self.setupUi(self)
            self.notifications = NotificationStack(parent=self)
            # Set style
            self.theme_colors = gu.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gu.set_css_and_theme(self, self.theme_colors)
            self.setWindowIcon(QtGui.QIcon('%s/medusa_task_icon.png' %
                                           constants.IMG_FOLDER))
            self.setWindowTitle('Stream settings')
            self.resize(400, 400)
            # Params
            self.editing = editing
            # Create a new lsl wrapper object to avoid reference passing
            # problems with working_lsl_streams
            self.lsl_stream_info = lsl_utils.LSLStreamWrapper(
                lsl_stream_info.lsl_stream)
            if self.editing:
                self.lsl_stream_info.update_medusa_parameters_from_lslwrapper(
                    lsl_stream_info)
                self.cha_info = self.lsl_stream_info.cha_info
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
        self.comboBox_medusa_type.currentIndexChanged.connect(
            self.on_medusa_stream_type_changed)
        for key, val in constants.MEDUSA_LSL_TYPES.items():
            self.comboBox_medusa_type.addItem(key, val)
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
        self.pushButton_read_channels_info.clicked.connect(
            self.on_read_channels_info)
        # Table
        self.tableWidget_channels.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.tableWidget_channels.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch)
        self.tableWidget_channels.horizontalHeader().hide()
        self.tableWidget_channels.verticalHeader().hide()
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
            self.set_checked_channels(
                self.lsl_stream_info.selected_channels_idx)
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
            pass
        except Exception as e:
            self.handle_exception(e)

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
            self.label_channels_label_field.setVisible(True)
        # Update combobox
        self.comboBox_channel_label_field.clear()
        cha_fields = list(dec_cha_info[0].keys())
        for field in cha_fields:
            self.comboBox_channel_label_field.addItem(field)
        gu.select_entry_combobox_with_text(
            self.comboBox_channel_label_field, 'label')

    def on_read_channels_info(self):
        current_desc_field = \
            self.comboBox_desc_channels_field.currentText()
        self.cha_info = \
            self.lsl_stream_info.get_desc_field_value(current_desc_field)
        self.update_channels_table()

    def update_channels_table(self):
        self.tableWidget_channels.clear()
        curr_label_field = self.comboBox_channel_label_field.currentText()
        max_n_cols = 4  # Max number of columns of the table
        if isinstance(self.cha_info, list) and \
            len(self.cha_info) > 0 and \
            curr_label_field in self.cha_info[0]:
            row_idx = 0
            col_idx = 0
            for cha in self.cha_info:
                # Insert column and row if necessary
                if self.tableWidget_channels.rowCount() < row_idx + 1:
                    self.tableWidget_channels.insertRow(
                        self.tableWidget_channels.rowCount())
                if self.tableWidget_channels.columnCount() < col_idx + 1:
                    self.tableWidget_channels.insertColumn(
                        self.tableWidget_channels.columnCount())
                # Set widget
                cha_checkbox = QtWidgets.QCheckBox()
                cha_checkbox.setChecked(True)
                cha_checkbox.setObjectName('cha_checkbox')
                cha_line_edit = QtWidgets.QLineEdit(cha[curr_label_field])
                cha_line_edit.setObjectName('cha_line_edit')
                cell_layout = QtWidgets.QHBoxLayout()
                cell_layout.addWidget(cha_checkbox)
                cell_layout.addWidget(cha_line_edit)
                cell_widget = QtWidgets.QWidget()
                cell_layout.setContentsMargins(0, 0, 0, 0)
                cell_widget.setLayout(cell_layout)
                self.tableWidget_channels.setCellWidget(
                    row_idx, col_idx, cell_widget)
                col_idx += 1
                if col_idx > max_n_cols - 1:
                    col_idx = 0
                    row_idx += 1
        else:
            self.tableWidget_channels.clear()

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
        # Get channel field
        channel_label_field = self.comboBox_channel_label_field.currentText()
        # Iterate table widgets
        cha_idx = []
        idx = 0
        for i in range(self.tableWidget_channels.rowCount()):
            for j in range(self.tableWidget_channels.columnCount()):
                cell_widget = self.tableWidget_channels.cellWidget(i, j)
                if cell_widget is not None:
                    # Get widgets
                    cha_checkbox = cell_widget.findChild(QtWidgets.QCheckBox,
                                                         'cha_checkbox')
                    cha_line_edit = cell_widget.findChild(QtWidgets.QLineEdit,
                                                          'cha_line_edit')
                    if cha_checkbox.isChecked():
                        cha_idx.append(idx)
                    # Update channel label
                    self.cha_info[idx][channel_label_field] = \
                        cha_line_edit.text()
                    idx += 1
        return cha_idx

    def get_lsl_stream_info(self):
        try:
            return self.lsl_stream_info
        except Exception as e:
            self.handle_exception(e)

    def accept(self):
        # Get lsl params
        medusa_uid = self.lineEdit_medusa_uid.text()
        medusa_type = self.comboBox_medusa_type.currentData()
        desc_channels_field = self.comboBox_desc_channels_field.currentText()
        channel_label_field = self.comboBox_channel_label_field.currentText()
        # Get selected channels and update cha info
        sel_cha_idx = self.get_checked_channels_idx()
        # Set medusa params
        self.lsl_stream_info.set_medusa_parameters(
            medusa_uid=medusa_uid,
            medusa_type=medusa_type,
            desc_channels_field=desc_channels_field,
            channel_label_field=channel_label_field,
            cha_info=self.cha_info,
            selected_channels_idx=sel_cha_idx)
        # Check the medusa uid, it has to be unique
        if not self.editing:
            if not lsl_utils.check_if_medusa_uid_is_available(
                    self.working_lsl_streams, medusa_uid):
                dialogs.error_dialog(
                    'Duplicated MEDUSA LSL UID. This parameter must be unique, '
                    'please change it.', 'Incorrect medusa_uid')
                return
        super().accept()

    def reject(self):
        super().reject()

    def handle_exception(self, ex):
        traceback.print_exc()
        dialogs.error_dialog(str(ex), 'Error', self.theme_colors)
