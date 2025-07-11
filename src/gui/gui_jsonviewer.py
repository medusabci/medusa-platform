#!/usr/bin/env python3

import argparse
import collections
import json
import sys
from PySide6 import QtCore, QtWidgets
from medusa.components import TreeDict


class TextToTreeItem:
    def __init__(self):
        self.text_list = []
        self.titem_list = []

    def append(self, text_list, titem):
        for text in text_list:
            self.text_list.append(text)
            self.titem_list.append(titem)

    def find(self, find_str):
        find_str = find_str.lower()  # Convert search string to lowercase
        return [self.titem_list[i] for i, s in enumerate(self.text_list) if find_str in s.lower()]


class TreeView(QtWidgets.QWidget):
    """
    A QWidget-based class that visualizes a JSON-compatible dictionary or list using a hierarchical tree view.

    Parameters:
        jdata (dict or list): A JSON-compatible dictionary or list containing for each item: key, default value
        (optional), input format (optional), value range (optional), value options (optional) and sub-items (optional).
    """
    def __init__(self, jdata):
        super(TreeView, self).__init__()

        if isinstance(jdata, TreeDict):
            jdata = jdata.to_dict()

        self.find_box = None
        self.tree_widget = None
        self.text_to_titem = TextToTreeItem()
        self.find_str = ""
        self.found_titem_list = []
        self.found_idx = 0
        self.jdata = jdata

        # Find UI
        find_layout = self.make_find_ui()

        # Tree Widget
        self.tree_widget = QtWidgets.QTreeWidget()
        self.tree_widget.setHeaderLabels(["Key", "Value", "Info"])
        self.tree_widget.header().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

        # Populate Tree
        self.recurse_jdata(self.jdata, self.tree_widget)

        # Layout
        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.tree_widget)
        gbox = QtWidgets.QGroupBox()
        gbox.setLayout(layout)
        layout2 = QtWidgets.QVBoxLayout()
        layout2.addLayout(find_layout)
        layout2.addWidget(gbox)
        self.setLayout(layout2)

    def make_find_ui(self):
        # Text box
        self.find_box = QtWidgets.QLineEdit()
        self.find_box.returnPressed.connect(self.find_button_clicked)
        # Find Button
        find_button = QtWidgets.QPushButton("Find")
        find_button.clicked.connect(self.find_button_clicked)

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.find_box)
        layout.addWidget(find_button)

        return layout

    def find_button_clicked(self):
        find_str = self.find_box.text()
        if not find_str:
            return

        if find_str != self.find_str:
            self.find_str = find_str
            self.found_titem_list = self.text_to_titem.find(self.find_str)
            self.found_idx = 0
        else:
            item_num = len(self.found_titem_list)
            self.found_idx = (self.found_idx + 1) % item_num

        if self.found_titem_list:
            self.tree_widget.setCurrentItem(self.found_titem_list[self.found_idx])
        else:
            QtWidgets.QMessageBox.warning(self, "Search", "No matches found.")

    def recurse_jdata(self, jdata, tree_widget):
        if isinstance(jdata, dict):
            for data in jdata.values():
                self.tree_add_row(data, tree_widget)
        elif isinstance(jdata, list):
            for data in jdata:
                self.tree_add_row(data, tree_widget)

    def tree_add_row(self, data, tree_widget, delete=False):
        text_list = []

        # Obtain the necessary fields
        key = data.get("key", "")
        default_value = data.get("default_value", None)
        info = data.get("info", None)
        input_format = data.get("input_format", None)
        value_range = data.get("value_range", None)
        value_options = data.get("value_options", None)
        items = data.get("items", None)

        # Set input format
        if input_format is None:
            if isinstance(default_value, bool):
                input_format = "checkbox"
            elif isinstance(default_value, list):
                input_format = "list"
            elif isinstance(default_value, int):
                input_format = "combobox" if value_options else "spinbox"
            elif isinstance(default_value, float):
                input_format = "combobox" if value_options else "doublespinbox"
            elif isinstance(default_value, str):
                input_format = "combobox" if value_options else "lineedit"
        else:
            input_format = input_format.lower()

        text_list.append(key)

        # Add the row item
        row_item = QtWidgets.QTreeWidgetItem(tree_widget)

        if delete:
            key_widget = QtWidgets.QWidget()
            key_layout = QtWidgets.QHBoxLayout()
            key_layout.setContentsMargins(0, 0, 0, 0)
            key_label = QtWidgets.QLabel(str(key))
            remove_button = QtWidgets.QPushButton("-")
            remove_button.setFixedWidth(30)
            remove_button.clicked.connect(lambda: self.remove_list_item(row_item))
            key_layout.addWidget(key_label)
            key_layout.addWidget(remove_button)
            key_widget.setLayout(key_layout)
            self.tree_widget.setItemWidget(row_item, 0, key_widget)
        else:
            key_label = QtWidgets.QLabel(str(key))
            self.tree_widget.setItemWidget(row_item, 0, key_label)

        if info is not None:
            info_label = QtWidgets.QLabel(str(info))
            info_label.setStyleSheet("padding-left: 10px; border:none")
            scroll_area = QtWidgets.QScrollArea()
            scroll_area.setWidget(info_label)
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            scroll_area.setAlignment(QtCore.Qt.AlignTop)
            scroll_area.setStyleSheet("""
                QScrollArea {
                    border: none;  
                    padding: 0px; 
                    background: transparent;
                }
                QScrollBar:horizontal {
                    height: 5px; 
                    background: transparent;  
                    border: none; 
                }
                QScrollBar::handle:horizontal {
                    background: #a0a0a0;  
                    min-width: 20px;  
                    border-radius: 2px;
                }
            """)
            self.tree_widget.setItemWidget(row_item, 2, scroll_area)

        # Add widgets based on input_format for the 'Value' column
        if input_format == "combobox":
            assert value_options is not None, \
                'Options list must not be empty'
            default_value = str(default_value)
            value_options = [str(option) for option in value_options]
            combobox = QtWidgets.QComboBox()
            combobox.addItems(value_options)
            combobox.setCurrentIndex(value_options.index(default_value))
            self.tree_widget.setItemWidget(row_item, 1, combobox)
        elif input_format == "checkbox":
            assert isinstance(default_value, bool), \
                'For the selected input format default value must be of type %s' % bool
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(default_value)
            self.tree_widget.setItemWidget(row_item, 1, checkbox)
        elif input_format == "spinbox":
            assert isinstance(default_value, int), \
                'For the selected input format default value must be of type %s' % int
            spinbox = QtWidgets.QSpinBox()
            if value_range:
                low_lim = value_range[0] if value_range[0] is not None else -1000000000
                upper_lim = value_range[1] if value_range[1] is not None else 1000000000
                spinbox.setRange(low_lim, upper_lim)
            else:
                spinbox.setRange(-1000000000, 1000000000)
            spinbox.setValue(default_value)
            self.tree_widget.setItemWidget(row_item, 1, spinbox)
        elif input_format == "doublespinbox":
            assert isinstance(default_value, float), \
                'For the selected input format default value must be of type %s' % float
            float_spinbox = QtWidgets.QDoubleSpinBox()
            if value_range:
                low_lim = value_range[0] if value_range[0] is not None else -1000000000
                upper_lim = value_range[1] if value_range[1] is not None else 1000000000
                float_spinbox.setRange(low_lim, upper_lim)
            else:
                float_spinbox.setRange(-1000000000, 1000000000)
            float_spinbox.setValue(default_value)
            self.tree_widget.setItemWidget(row_item, 1, float_spinbox)
        elif input_format == "lineedit":
            line_edit = QtWidgets.QLineEdit()
            line_edit.setText(str(default_value))
            self.tree_widget.setItemWidget(row_item, 1, line_edit)
        elif input_format == "list":
            for idx, list_item in enumerate(default_value):
                subkey = f"{key}[{idx}]"
                subdata = {
                    "key": subkey,
                    "default_value": list_item
                }

                if isinstance(list_item, bool):
                    subdata["input_format"] = "checkbox"
                elif isinstance(list_item, int):
                    subdata["input_format"] = "spinbox"
                elif isinstance(list_item, float):
                    subdata["input_format"] = "doublespinbox"
                elif isinstance(list_item, str):
                    subdata["input_format"] = "lineedit"
                elif isinstance(list_item, list):
                    subdata["input_format"] = "list"

                self.tree_add_row(subdata, row_item, delete=True)

            # Add "Add" button at the bottom
            button_container = QtWidgets.QWidget()
            button_layout = QtWidgets.QHBoxLayout()
            add_button = QtWidgets.QPushButton("Add")
            button_layout.addWidget(add_button)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_container.setLayout(button_layout)
            button_item = QtWidgets.QTreeWidgetItem(row_item)
            self.tree_widget.setItemWidget(button_item, 0, button_container)
            add_button.clicked.connect(lambda: self.add_button_clicked(row_item, key))

        if items:
            self.recurse_jdata(items, row_item)

        if isinstance(tree_widget, QtWidgets.QTreeWidget):
            tree_widget.addTopLevelItem(row_item)
        else:
            tree_widget.addChild(row_item)

        self.text_to_titem.append(text_list, row_item)

    def add_button_clicked(self, row_item, parent_key):
        items = ["str", "int", "float", "bool", "list"]
        item_type, ok = QtWidgets.QInputDialog.getItem(self,
                                        "Choose item type",
                                        "Choose item type",
                                        items,
                                        0,
                                        False)
        if ok:
            type_defaults = {
                "str": ("", "lineedit"),
                "int": (0, "spinbox"),
                "float": (0.0, "doublespinbox"),
                "bool": (False, "checkbox"),
                "list": ([], "list")
            }

            default_value, input_format = type_defaults[item_type]
            new_key = f"{parent_key}[{row_item.childCount()-1}]"
            new_data = {
                "key": new_key,
                "default_value": default_value,
                "input_format": input_format
            }

            self.tree_add_row(new_data, row_item, delete=True)

            #Take 'Add' button to the end of the list
            row_item.takeChild(row_item.childCount()-2)
            button_container = QtWidgets.QWidget()
            button_layout = QtWidgets.QHBoxLayout()
            add_button = QtWidgets.QPushButton("Add")
            button_layout.addWidget(add_button)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_container.setLayout(button_layout)
            button_item = QtWidgets.QTreeWidgetItem(row_item)
            self.tree_widget.setItemWidget(button_item, 0, button_container)
            add_button.clicked.connect(lambda: self.add_button_clicked(row_item, parent_key))

            self.reindex_list_items(row_item, parent_key)

    def remove_list_item(self, item):
        parent_item = item.parent()
        if parent_item:
            parent_item.removeChild(item)
            self.reindex_list_items(parent_item)

    def reindex_list_items(self, parent_item, parent_key=None):
        child_count = parent_item.childCount()-1
        index = 0
        for i in range(child_count):
            child = parent_item.child(i)
            label_widget = self.tree_widget.itemWidget(child, 0)
            label = label_widget.findChild(QtWidgets.QLabel)
            if parent_key is None:
                last_bracket = label.text().rfind("[")
                parent_key = label.text()[:last_bracket]
            new_key = f"{parent_key}[{index}]"
            label.setText(new_key)
            index += 1
            self.reindex_list_items(child, new_key)



class TreeViewer(QtWidgets.QMainWindow):
    """
        A main window class that hosts the TreeView widget.

        Parameters:
            jdata (dict or list): The JSON-compatible data to be visualized in the tree view.
        """
    def __init__(self, jdata):
        super(TreeViewer, self).__init__()

        json_view = TreeView(jdata)

        self.setCentralWidget(json_view)
        self.setWindowTitle("Tree Viewer")
        self.resize(1000, 600)
        self.show()

    def keyPressEvent(self, e):
        if e.key() == QtCore.Qt.Key_Escape:
            self.close()
