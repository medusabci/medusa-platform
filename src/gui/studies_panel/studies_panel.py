# PYTHON MODULES
import json
import os
import glob
import shutil

# EXTERNAL MODULES
from PySide6.QtUiTools import loadUiType
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
# MEDUSA MODULES
from gui import gui_utils as gu
from gui.qt_widgets import dialogs
import constants, exceptions


ui_plots_panel_widget = loadUiType('gui/ui_files/studies_panel_widget.ui')[0]


class StudiesPanelWidget(QWidget, ui_plots_panel_widget):

    selection_signal = Signal()
    start_session_signal = Signal(list)

    def __init__(self, medusa_interface, studies_config_file_path,
                 theme_colors):
        super().__init__()
        self.setupUi(self)
        # Attributes
        self.medusa_interface = medusa_interface
        self.theme_colors = theme_colors
        self.undocked = False
        self.selected_item_tree = None
        self.selected_item_type = None
        # Set up tool bar
        self.set_up_tool_bar_studies()
        # Tree view context menu
        self.treeView_studies.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treeView_studies.customContextMenuRequested.connect(
            self.on_custom_context_menu_requested)
        # Splitter
        self.splitter.setSizes(
            [int(0.3 * self.width()), int(0.7 * self.width())])
        # Initial configuration
        self.studies_panel_config = dict()
        self.studies_config_file_path = studies_config_file_path
        if os.path.isfile(self.studies_config_file_path):
            try:
                with open(self.studies_config_file_path, 'r') as f:
                    self.studies_panel_config = json.load(f)
                self.update_studies_panel()
            except json.decoder.JSONDecodeError as e:
                msg = '[ERROR] Corrupted file 5s. The studies config could ' \
                      'not be loaded' % self.studies_config_file_path
                self.medusa_interface.log(msg)

    def handle_exception(self, ex):
        # # Treat exception
        # if not isinstance(ex, exceptions.MedusaException):
        #     ex = exceptions.MedusaException(
        #         ex, importance='unknown',
        #         scope='studies',
        #         origin='studies_panel/studies_panel/handle_exception')
        # # Notify exception to gui main
        self.medusa_interface.error(ex)
        dialogs.error_dialog(str(ex), 'Error')

    @exceptions.error_handler(scope='studies')
    def set_undocked(self, undocked):
        self.undocked = undocked
        self.reset_tool_bar_studies_buttons()

    @exceptions.error_handler(scope='studies')
    def reset_tool_bar_studies_buttons(self):
        try:
            # Set icons in buttons
            self.toolButton_studies_refresh.setIcon(
                gu.get_icon("refresh.svg", self.theme_colors))
            # self.toolButton_studies_config.setToolTip('Refresh')
            # self.toolButton_studies_config.setIcon(
            #     gu.get_icon("settings.svg", self.theme_colors))
            # self.toolButton_studies_config.setToolTip('Studies settings')
            self.lineEdit_studies_path.setDisabled(True)
            self.toolButton_studies_set_path.setIcon(
                gu.get_icon("folder.svg", self.theme_colors))
            self.toolButton_studies_set_path.setToolTip('Set root path')
            if self.undocked:
                self.toolButton_studies_undock.setIcon(
                    gu.get_icon("open_in_new_down.svg", self.theme_colors))
                self.toolButton_studies_undock.setToolTip(
                    'Redock in main window')
            else:
                self.toolButton_studies_undock.setIcon(
                    gu.get_icon("open_in_new.svg", self.theme_colors))
                self.toolButton_studies_undock.setToolTip('Undock')
        except Exception as e:
            self.handle_exception(e)

    @exceptions.error_handler(scope='studies')
    def set_up_tool_bar_studies(self):
        """This method creates the QAction buttons displayed in the toolbar
        """
        try:
            # Creates QIcons for the app tool bar
            self.reset_tool_bar_studies_buttons()
            # Connect signals to functions
            self.toolButton_studies_refresh.clicked.connect(
                self.update_studies_panel)
            # self.toolButton_studies_config.clicked.connect(
            #     self.open_studies_config_dialog)
            self.toolButton_studies_set_path.clicked.connect(
                self.set_root_path)
        except Exception as e:
            self.handle_exception(e)

    @exceptions.error_handler(scope='studies')
    def save_studies_config(self):
        with open(self.studies_config_file_path, 'w') as f:
            json.dump(self.studies_panel_config, f, indent=4)

    @exceptions.error_handler(scope='studies')
    def set_root_path(self, checked=None):
        # Get app file
        directory = "../data"
        if not os.path.exists(directory):
            os.makedirs(directory)
        studies_root_path = QFileDialog.getExistingDirectory(
            caption="Root path", dir=directory)
        self.studies_panel_config['root_path'] = studies_root_path
        self.update_studies_panel()
        self.save_studies_config()

    @exceptions.error_handler(scope='studies')
    def open_studies_config_dialog(self, checked=None):
        raise NotImplementedError()

    @exceptions.error_handler(scope='studies')
    def update_studies_panel(self, checked=None):
        # Clean variables
        self.selected_item_type = None
        self.selected_item_tree = None
        # Initialize the tree model
        self.tree_model = QStandardItemModel()
        self.treeView_studies.setModel(self.tree_model)
        self.treeView_studies.setHeaderHidden(True)
        self.selection_model = self.treeView_studies.selectionModel()
        self.selection_model.selectionChanged.connect(self.on_item_selected)
        self.clear_tab_widget()
        # Set root path
        if 'root_path' not in self.studies_panel_config or \
                not os.path.isdir(self.studies_panel_config['root_path']):
            self.studies_panel_config['root_path'] = ''
            self.studies_panel_config.pop('root_path')
            self.lineEdit_studies_path.setText('')
        else:
            # Set root path
            self.lineEdit_studies_path.setText(
                self.studies_panel_config['root_path'])
            # Create tree
            root_item = RootItem(os.path.basename(
                self.studies_panel_config['root_path']), self.theme_colors)
            studies = glob.glob(
                '%s/*/' % self.studies_panel_config['root_path'])
            # Append studies
            for study in studies:
                subjects = glob.glob('%s/*/' % study)
                study_item = StudyItem(os.path.basename(study[0:-1]),
                                       self.theme_colors)
                # Append subjects
                for subject in subjects:
                    sessions = glob.glob('%s/*/' % subject)
                    subject_item = SubjectItem(
                        os.path.basename(subject[0:-1]), self.theme_colors)
                    for session in sessions:
                        session_item = SessionItem(
                            os.path.basename(session[0:-1]), self.theme_colors)
                        subject_item.appendRow(session_item)
                    study_item.appendRow(subject_item)
                root_item.appendRow(study_item)
            # Append root item to the model and expand tree
            self.tree_model.appendRow(root_item)
            self.treeView_studies.setExpanded(root_item.index(), True)

    @exceptions.error_handler(scope='studies')
    def on_custom_context_menu_requested(self, pos):
        # Create context menu
        menu = QMenu(self)
        create_action = QAction('Create', self)
        create_action.triggered.connect(self.on_create_element)
        menu.addAction(create_action)
        edit_action = QAction('Edit', self)
        edit_action.triggered.connect(self.on_edit_element)
        menu.addAction(edit_action)
        delete_action = QAction('Delete', self)
        delete_action.triggered.connect(self.on_delete_element)
        menu.addAction(delete_action)
        menu.popup(self.treeView_studies.viewport().mapToGlobal(pos))

    @exceptions.error_handler(scope='studies')
    def on_create_element(self, checked=None):
        # Check errors
        if 'root_path' not in self.studies_panel_config:
            raise ValueError('Please, set the root path first')
        if self.selected_item_tree is None:
            raise ValueError('Select the root element!')
        # The element to create is one logical level below the current
        # selection
        if len(self.selected_item_tree) == 0:
            element_to_create = 'project'
        elif len(self.selected_item_tree) == 1:
            element_to_create = 'subject'
        elif len(self.selected_item_tree) == 2:
            element_to_create = 'session'
        else:
            element_to_create = None
        dialog = CreateElementDialog(element_to_create,
                                     self.selected_item_tree,
                                     self.studies_panel_config['root_path'])
        dialog.exec_()
        self.update_studies_panel()

    @exceptions.error_handler(scope='studies')
    def on_edit_element(self, checked=None):
        dialog = CreateElementDialog(self.selected_item_type,
                                     self.selected_item_tree,
                                     self.studies_panel_config['root_path'],
                                     edit=True)
        dialog.exec_()
        self.update_studies_panel()

    @exceptions.error_handler(scope='studies')
    def on_delete_element(self, checked=None):
        element_path = self.get_element_dir(
            self.studies_panel_config['root_path'],
            self.selected_item_tree)
        title = 'This %s is not empty!' % self.selected_item_type \
            if self.selected_item_type != 'root' else \
            'The root folder is not empty!'
        if len(glob.glob('%s/*' % element_path)):
            res = dialogs.confirmation_dialog(
                text='All contents will be eliminated. Do you want to proceed?',
                title=title)
            if not res:
                return
        shutil.rmtree(element_path)
        self.update_studies_panel()

    @exceptions.error_handler(scope='studies')
    def on_item_selected(self, selected_item, deselected_item):
        selected_item_indexes = selected_item.indexes()
        selected_item_index = selected_item_indexes[0]
        # Clean tab widget
        self.clear_tab_widget()
        # Set selected item tree
        item_path = '%s' % self.studies_panel_config['root_path']
        self.selected_item_tree = []
        while selected_item_index.isValid():
            # Append to item tree
            item_name = selected_item_index.data()
            item_data = None
            self.selected_item_tree.append(
                {
                    'item_name': item_name,
                    'item_data': item_data,
                 }
            )
            # Update parent
            selected_item_index = selected_item_index.parent()
        # Reverse and pop root item
        self.selected_item_tree.reverse()
        self.selected_item_tree.pop(0)
        # Set selected item type
        if len(self.selected_item_tree) == 0:
            self.selected_item_type = 'root'
        elif len(self.selected_item_tree) == 1:
            self.selected_item_type = 'project'
        elif len(self.selected_item_tree) == 2:
            self.selected_item_type = 'subject'
        elif len(self.selected_item_tree) == 3:
            self.selected_item_type = 'session'
        else:
            self.selected_item_type = None
        # Add pages to info tab widget
        tab_idx = 0
        for item in self.selected_item_tree:
            # Get data
            item_name = item['item_name']
            # Set data info
            item_path += '/%s' % item_name
            if os.path.isfile('%s/data' % item_path):
                with open('%s/data' % item_path, 'r') as f:
                    item['item_data'] = f.read()
            item_data = item['item_data']
            # Add tab widget
            tab_layout = QHBoxLayout()
            data_widget = QTextBrowser()
            tab_layout.addWidget(data_widget)
            if item_data is not None:
                data_widget.setText(item_data)
            tab_widget = QWidget()
            tab_widget.setProperty("class", "studies-tab-widget")
            tab_widget.setLayout(tab_layout)
            tab_idx = self.tabWidget_studies.addTab(tab_widget, item_name)
            if tab_idx > 0:
                self.tabWidget_studies.setTabIcon(
                    tab_idx, gu.get_icon("arrow_forward.svg",
                                         self.theme_colors))
        self.tabWidget_studies.setCurrentIndex(tab_idx)
        self.selection_signal.emit()

    @exceptions.error_handler(scope='studies')
    def clear_tab_widget(self):
        # Clean tab widget
        while self.tabWidget_studies.count() > 0:
            self.tabWidget_studies.removeTab(0)

    @exceptions.error_handler(scope='studies')
    def get_element_dir(self, root_path, selected_item_tree) -> str:
        for item in selected_item_tree:
            root_path += '/%s' % item['item_name']
        return root_path


class RootItem(QStandardItem):
    def __init__(self, name, theme_colors):
        super().__init__()
        self.theme_colors = theme_colors
        self.setForeground(QColor(self.theme_colors['THEME_TEXT_LIGHT']))
        self.setText(name)
        self.setEditable(False)


class StudyItem(QStandardItem):
    def __init__(self, name, theme_colors):
        super().__init__()
        self.theme_colors = theme_colors
        self.setForeground(QColor(self.theme_colors['THEME_TEXT_LIGHT']))
        self.setText(name)
        self.setEditable(False)
        self.setIcon(gu.get_icon("science.svg", self.theme_colors))


class SubjectItem(QStandardItem):
    def __init__(self, name, theme_colors):
        super().__init__()
        self.theme_colors = theme_colors
        self.setForeground(QColor(self.theme_colors['THEME_TEXT_LIGHT']))
        self.setText(name)
        self.setEditable(False)
        self.setIcon(gu.get_icon("person.svg", self.theme_colors))


class SessionItem(QStandardItem):
    def __init__(self, name, theme_colors):
        super().__init__()
        self.theme_colors = theme_colors
        self.setForeground(QColor(self.theme_colors['THEME_TEXT_LIGHT']))
        self.setText(name)
        self.setEditable(False)
        self.setIcon(gu.get_icon("calendar_clock.svg", self.theme_colors))


class CreateElementDialog(dialogs.MedusaDialog):

    def __init__(self, selected_item_type, selected_item_tree, root_path,
                 edit=False):
        # Check errors
        if selected_item_type is None or selected_item_tree is None:
            raise ValueError('Select the root element!')
        # Parameters
        self.selected_item_type = selected_item_type
        self.selected_item_tree = selected_item_tree
        self.element_dir = self.get_element_dir(root_path, selected_item_tree)
        self.edit = edit
        self.lineEdit_name = None
        self.textEdit_data = None
        action = 'Create' if not edit else 'Edit'
        super().__init__('%s %s' % (action, selected_item_type))

    def get_element_dir(self, root_path, selected_item_tree) -> str:
        for item in selected_item_tree:
            root_path += '/%s' % item['item_name']
        return root_path

    def create_layout(self):
        # Main layout
        main_layout = QVBoxLayout()
        # Name lineEdit
        form_layout = QFormLayout()
        self.lineEdit_name = QLineEdit()
        form_layout.addRow(QLabel('Name'), self.lineEdit_name)
        # Data textEdit
        self.textEdit_data = QTextEdit()
        form_layout.addRow(QLabel('Data'), self.textEdit_data)
        main_layout.addLayout(form_layout)
        # If edit set data in widgets
        if self.edit:
            # Name
            self.lineEdit_name.setDisabled(True)
            self.lineEdit_name.setText(self.selected_item_tree[-1]['item_name'])
            # Data
            if self.selected_item_tree[-1]['item_data'] is not None:
                self.textEdit_data.setText(
                    self.selected_item_tree[-1]['item_data'])
        # Buttons
        buttons_layout = QHBoxLayout()
        accept_button = QPushButton('Accept')
        accept_button.clicked.connect(self.on_accept)
        cancel_button = QPushButton('Cancel')
        cancel_button.clicked.connect(self.on_reject)
        buttons_layout.addItem(
            QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Expanding))
        buttons_layout.addWidget(accept_button)
        buttons_layout.addWidget(cancel_button)
        main_layout.addLayout(buttons_layout)
        return main_layout

    def on_accept(self) -> None:
        try:
            if self.edit:
                element_path = self.element_dir
            else:
                element_path = '%s/%s' % (self.element_dir,
                                          self.lineEdit_name.text())
                if not os.path.isdir(element_path):
                    os.mkdir(element_path)
            data_str = self.textEdit_data.toPlainText()
            if len(data_str) > 0:
                try:
                    data = json.loads(data_str)
                    with open('%s/data' % element_path, 'w') as f:
                        json.dump(data, f, indent=4)
                except json.decoder.JSONDecodeError as e:
                    with open('%s/data' % element_path, 'w') as f:
                        f.write(data_str)
            # Call accept to close the dialog
            self.accept()
        except json.decoder.JSONDecodeError as e:
            dialogs.error_dialog('Error in the JSON code: %s' % str(e),
                                 'Error!')
        except Exception as e:
            dialogs.error_dialog('Error: %s' % str(e),
                                 'Error!')

    def on_reject(self) -> None:
        # Call reject to close the dialog
        self.reject()


class StudiesPanelWindow(QMainWindow):

    close_signal = Signal()

    def __init__(self, studies_panel_widget, theme_colors,
                 width=400, height=650):
        super().__init__()
        # self.plots_panel_widget = plots_panel_widget
        self.theme_colors = theme_colors
        self.setCentralWidget(studies_panel_widget)
        gu.set_css_and_theme(self, self.theme_colors)
        # Window title and icon
        self.setWindowIcon(QIcon('%s/medusa_task_icon.png' %
                                 constants.IMG_FOLDER))
        self.setWindowTitle('Studies management panel')
        # Resize plots window
        self.resize(width, height)
        self.show()

    def closeEvent(self, event):
        self.close_signal.emit()
        event.accept()

    def get_plots_panel_widget(self):
        return self.centralWidget()


