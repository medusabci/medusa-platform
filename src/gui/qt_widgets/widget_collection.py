import copy, abc
import json, os
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, \
    QSizePolicy, QHeaderView, QAbstractItemView, QCheckBox, QLineEdit, \
    QComboBox, QFileDialog, QToolButton, QSpacerItem
from PySide6.QtGui import QAction, QIntValidator
from PySide6.QtCore import Qt, QSize, Signal
from gui import gui_utils as gu


class ProcessTableWidget(QWidget):

    row_created_sig = Signal(int)
    row_removed_sig = Signal()

    def __init__(self, header_labels, theme_colors=None):

        super().__init__()
        self.theme_colors = theme_colors
        # Attributes
        self.header_labels = header_labels
        self.n_cols = len(header_labels)
        # Create table
        self.table_widget = QTableWidget(self)
        self.table_widget.setColumnCount(self.n_cols)
        self.table_widget.setHorizontalHeaderLabels(header_labels)
        self.table_widget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        # Control buttons
        table_buttons_layout = QVBoxLayout()
        add_row_button = QToolButton()
        add_row_button.setIconSize(QSize(20, 20))
        add_row_button.setIcon(
            gu.get_icon("add_element.svg",
                        custom_color=self.theme_colors['THEME_GREEN']))
        add_row_button.clicked.connect(self.insert_row)
        table_buttons_layout.addWidget(add_row_button)
        remove_row_button = QToolButton()
        remove_row_button.setIconSize(QSize(20, 20))
        remove_row_button.setIcon(gu.get_icon(
            "remove.svg", custom_color=self.theme_colors['THEME_RED']))
        remove_row_button.clicked.connect(self.remove_selected_row)
        table_buttons_layout.addWidget(remove_row_button)
        spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        table_buttons_layout.addItem(spacer)
        # Layout
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.table_widget)
        main_layout.addLayout(table_buttons_layout)
        # Set layout
        self.setLayout(main_layout)

    @abc.abstractmethod
    def create_row_widgets(self, row_position, **kwargs):
        """Function to create the default widgets that will be inserted when
        adding a new row
        """
        raise NotImplementedError

    def insert_row(self, checked=None, widgets=None,  emmit_signal=True):
        # Get insertion position
        row_position = self.table_widget.currentRow()
        if row_position < 0:
            row_position = self.table_widget.rowCount()
        else:
            row_position += 1
        self.table_widget.insertRow(row_position)
        # Add widgets
        widgets = widgets if widgets is not None \
            else self.create_row_widgets(row_position=row_position)
        for i, widget in enumerate(widgets):
            self.table_widget.setCellWidget(row_position, i, widget)
        if emmit_signal:
            self.row_created_sig.emit(row_position)
        return row_position

    def remove_row(self, row_position, emmit_signal=True):
        self.table_widget.removeRow(row_position)
        if emmit_signal:
            self.row_removed_sig.emit()

    def remove_selected_row(self, update_rec_ids=False):
        row_position = self.table_widget.currentRow()
        if row_position >= 0:
            self.remove_row(row_position)

    def clear_table(self):
        self.table_widget.setRowCount(0)

    def get_data(self):
        # todo: Maybe better in the parent?
        pass

    def set_data(self, session_plan):
        # todo: Maybe better in the parent?
        pass