from PyQt5.QtCore import (QAbstractItemModel, QItemSelectionModel,
                          QModelIndex, Qt)
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5 import QtWidgets, QtCore
from medusa.components import SerializableComponent
from collections import OrderedDict
from copy import deepcopy


class SettingsItem(SerializableComponent):
    """General class to represent settings field.
        """

    def __init__(self, key, info, value_type, value):
        """Class constructor.

        Parameters
        ----------
        key: str
            Tree item key
        info: str
            Information about this item
        value_type: str ['string'|'number'|'boolean'|'dict'|'list'], optional
            Type of the data stored in attribute value. Leave to None if the
            item is going to be a tree.
        value: str, int, float, bool, dict or list, optional
            Tree item value. It must be one of the JSON types to be compatible
            with serialization. Leave to None if the item is going to be a tree.
        """
        # Init attributes
        self.item_type = 'field'
        self.key = key
        self.info = info
        self.value_type = None
        self.value = None
        self.set_data(value=value, value_type=value_type)

    def set_data(self, value, value_type=None):
        """Adds tree item to the tree. Use this function to build a custom tree.

        Parameters
        ----------
        value: str, int, float, bool, dict or list
            Tree item value. It must be one of the JSON types to be compatible
            with serialization. If list or dict, the items must be of type
            SettingsTreeItem.
        value_type: str ['string'|'number'|'boolean'|'dict'|'list']
            Type of the data stored in attribute value. If a list is provided,
            several data types are accepted for attribute value.
        """
        # Check errors
        if value_type == 'string':
            if value is not None:
                assert isinstance(value, str), \
                    'Parameter value must be of type %s' % str
        elif value_type == 'number':
            if value is not None:
                assert isinstance(value, int) or isinstance(value, float), \
                    'Parameter value must be of types %s or %s' % \
                    (int, float)
        elif value_type == 'boolean':
            if value is not None:
                assert isinstance(value, bool), \
                    'Parameter value must be of type %s' % bool
        elif value_type == 'list':
            if value is not None:
                assert isinstance(value, list), \
                    'Parameter value must be of type %s' % list
        elif value_type == 'dict':
            if value is not None:
                assert isinstance(value, dict), \
                    'Parameter value must be of type %s' % dict
        elif value_type is None:
            if self.value_type is None:
                raise ValueError('The type must be specified')
            else:
                value_type = self.value_type
        else:
            raise ValueError('Unknown value_type %s. Read the docs!' % value_type)

        self.value_type = value_type
        self.value = value

    def to_serializable_obj(self):
        return self.__dict__

    @classmethod
    def from_serializable_obj(cls, data):
        return cls(data['key'], data['info'], data['value_type'], data['value'])


class SettingsTree(SerializableComponent):
    """General class to represent settings tree.
    """
    def __init__(self, key, info):
        """Class constructor.

        Parameters
        ----------
        key: str
            Tree item key
        info: str
            Information about this item
        """
        # Init attributes
        self.item_type = 'tree'
        self.key = key
        self.info = info
        self.items = OrderedDict()

    def add_item(self, item):
        """Adds tree item to the tree. Use this function to build a custom tree.
        Take into account that if this function is used, attributes value and
        type will be set to None.

        Parameters
        ----------
        item: SettingsTree or SettingsItem
            Tree item to add
        """
        # Check errors
        if item.key in self.items:
            raise ValueError('There is already an item with key %s' % item.key)

        # Add item
        if isinstance(item, SettingsTree):
            pass
        elif isinstance(item, SettingsItem):
            pass
        else:
            raise ValueError('Parameter item must be of type %s or %s' %
                             (type(SettingsTree), type(SettingsItem)))
        self.items[item.key] = item

    def find_item(self, key):
        """Looks for an item in this Tree. To find items in subtrees, use syntax item_tree1:item_tree2:...:item_key"""
        key_split = key.split(':')
        items = self.items
        for key in key_split:
            if key not in items:
                raise KeyError()
            if isinstance(items[key], SettingsTree):
                items = items[key].items
            else:
                return items[key]

    def count_items(self):
        return len(self.items)

    def to_serializable_obj(self):
        ser_obj = deepcopy(self.__dict__)
        for k, v in ser_obj['items'].items():
            ser_obj['items'][k] = v.to_serializable_obj()
        return ser_obj

    @classmethod
    def from_serializable_obj(cls, data):
        tree = cls(data['key'], data['info'])
        for k, item in data['items'].items():
            if item['item_type'] == 'tree':
                tree.items[k] = SettingsTree.from_serializable_obj(item)
            elif item['item_type'] == 'field':
                tree.items[k] = SettingsItem.from_serializable_obj(item)
            else:
                raise ValueError('Malformed SettingsTree')
        return tree


class TreeItem:

    def __init__(self, data, parent=None):
        self.parent_item = parent
        self.item_data = data
        self.child_items = []

    def child(self, row):
        if row < 0 or row >= len(self.child_items):
            return None
        return self.child_items[row]

    def child_count(self):
        return len(self.child_items)

    def child_number(self):
        if self.parent_item is not None:
            return self.parent_item.child_items.index(self)
        return 0

    def column_count(self):
        return len(self.item_data)

    def data(self, column):
        if column < 0 or column >= len(self.item_data):
            return None
        return self.item_data[column]

    def insert_children(self, position, count, columns):
        if position < 0 or position > len(self.child_items):
            return False
        for row in range(count):
            data = [None for v in range(columns)]
            item = TreeItem(data, self)
            self.child_items.insert(position, item)
        return True

    def insert_columns(self, position, columns):
        if position < 0 or position > len(self.item_data):
            return False
        for column in range(columns):
            self.item_data.insert(position, None)
        for child in self.child_items:
            child.insert_columns(position, columns)
        return True

    def parent(self):
        return self.parent_item

    def remove_children(self, position, count):
        if position < 0 or position + count > len(self.child_items):
            return False
        for row in range(count):
            self.child_items.pop(position)
        return True

    def remove_columns(self, position, columns):
        if position < 0 or position + columns > len(self.item_data):
            return False
        for column in range(columns):
            self.item_data.pop(position)
        for child in self.child_items:
            child.remove_columns(position, columns)
        return True

    def set_data(self, column, value):
        if column < 0 or column >= len(self.item_data):
            return False
        self.item_data[column] = value
        return True


class TreeModel(QAbstractItemModel):

    def __init__(self, data, parent=None):
        super(TreeModel, self).__init__(parent)
        headers = ("Key", "Value", "Type", "Info")
        root_data = [header for header in headers]
        self.root_item = TreeItem(root_data)
        self.settings_tree = data
        self.set_settings_tree(data, self.root_item)

    def flags(self, index):
        if not index.isValid():
            return 0
        return Qt.ItemIsEditable | super(TreeModel, self).flags(index)

    def data(self, index, role):
        """Returns the data of one column only if its valid and has DisplayRole or EditRole. It is called when the
        columns are resized to contents, but I don't fully understand why.
        """
        if not index.isValid():
            return None
        if role != Qt.DisplayRole and role != Qt.EditRole:
            return None
        item = self.getItem(index)
        return item.data(index.column())

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False
        # Update TreeModel
        model_item = self.getItem(index)
        result = model_item.set_data(index.column(), value)
        if result:
            self.dataChanged.emit(index, index)
        # Update SettingsTree
        keys = list()
        parent = model_item
        while True:
            keys.append(parent.data(0))
            parent = parent.parent()
            if parent is None:
                break
        keys.reverse()
        key = ':'.join(keys[1:])
        settings_item = self.settings_tree.find_item(key)
        if settings_item.item_type == 'field':
            # If the item is a field
            if settings_item.value_type == 'list':
                # If the item is a list
                if settings_item.key == keys[-1]:
                    # If the item is the whole list
                    field_to_update = ['key', 'value', 'value_type', 'info'][index.column()]
                    settings_item.__dict__[field_to_update] = value
                else:
                    # If the item is a list item
                    settings_item.value[int(keys[-1])] = value
            elif settings_item.value_type == 'dict':
                # If the item is a dict
                if settings_item.key == keys[-1]:
                    # If the item is the whole dict
                    field_to_update = ['key', 'value', 'value_type', 'info'][index.column()]
                    settings_item.__dict__[field_to_update] = value
                else:
                    # If the item is dict entry
                    settings_item.value[keys[-1]] = value
            else:
                # If the item is a tree
                field_to_update = ['key', 'value', 'value_type', 'info'][index.column()]
                settings_item.__dict__[field_to_update] = value
        else:
            field_to_update = ['key', 'info'][index.column()]
            settings_item.__dict__[field_to_update] = value
        return result

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.root_item.data(section)

    def setHeaderData(self, section, orientation, value, role=Qt.EditRole):
        if role != Qt.EditRole or orientation != Qt.Horizontal:
            return False
        result = self.root_item.set_data(section, value)
        if result:
            self.headerDataChanged.emit(orientation, section, section)
        return result

    def getItem(self, index):
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item
        return self.root_item

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        childItem = self.getItem(index)
        parentItem = childItem.parent()
        if parentItem == self.root_item:
            return QModelIndex()
        return self.createIndex(parentItem.child_number(), 0, parentItem)

    def index(self, row, column, parent=QModelIndex()):
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()
        parent_item = self.getItem(parent)
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()

    def insertColumns(self, position, columns, parent=QModelIndex()):
        self.beginInsertColumns(parent, position, position + columns - 1)
        success = self.root_item.insert_columns(position, columns)
        self.endInsertColumns()
        return success

    def insertRows(self, position, rows, parent=QModelIndex()):
        parent_item = self.getItem(parent)
        self.beginInsertRows(parent, position, position + rows - 1)
        success = parent_item.insert_children(position, rows,
                                              self.root_item.column_count())
        self.endInsertRows()
        return success

    def removeColumns(self, position, columns, parent=QModelIndex()):
        self.beginRemoveColumns(parent, position, position + columns - 1)
        success = self.root_item.remove_columns(position, columns)
        self.endRemoveColumns()

        if self.root_item.column_count() == 0:
            self.removeRows(0, self.rowCount())

        return success

    def removeRows(self, position, rows, parent=QModelIndex()):
        parentItem = self.getItem(parent)

        self.beginRemoveRows(parent, position, position + rows - 1)
        success = parentItem.remove_children(position, rows)
        self.endRemoveRows()

        return success

    def columnCount(self, parent=QModelIndex()):
        return self.root_item.column_count()

    def rowCount(self, parent=QModelIndex()):
        parentItem = self.getItem(parent)
        return parentItem.child_count()

    def set_child_data(self, ch, ch_key, ch_info, ch_val_type, ch_value):
        ch.set_data(0, ch_key)
        ch.set_data(1, ch_value)
        ch.set_data(3, ch_info)
        ch.set_data(2, ch_val_type)

    def set_settings_tree(self, data, parent):
        for key, item in data.items.items():
            if isinstance(item, SettingsTree):
                # Append child
                parent.insert_children(parent.child_count(), 1, self.root_item.column_count())
                new_parent = parent.child(parent.child_count() - 1)
                # Set data, leaving type and value empty
                self.set_child_data(new_parent, item.key, item.info, '', '')
                # Set settings tree
                self.set_settings_tree(item, new_parent)
            elif isinstance(item, SettingsItem):
                if item.value_type == 'string' or \
                        item.value_type == 'number' or \
                        item.value_type == 'boolean':
                    # Append child
                    parent.insert_children(parent.child_count(), 1, self.root_item.column_count())
                    field = parent.child(parent.child_count() - 1)
                    # Set data
                    self.set_child_data(field, item.key, item.info, item.value_type, item.value)
                elif item.value_type == 'dict':
                    parent.insert_children(parent.child_count(), 1,
                                           self.root_item.column_count())
                    new_parent = parent.child(parent.child_count() - 1)
                    self.set_child_data(new_parent, item.key, item.info,
                                        item.value_type, item.value)
                    for child_key, child_value in item.value.items():
                        new_parent.insert_children(new_parent.child_count(), 1,
                                                   self.root_item.column_count())
                        self.set_child_data(
                            new_parent.child(new_parent.child_count() - 1),
                            child_key, '', '', child_value)
                elif item.value_type == 'list':
                    parent.insert_children(parent.child_count(), 1,
                                           self.root_item.column_count())
                    new_parent = parent.child(parent.child_count() - 1)
                    self.set_child_data(new_parent, item.key, item.info,
                                        item.value_type, item.value)
                    for child_key, child_value in enumerate(item.value):
                        new_parent.insert_children(new_parent.child_count(), 1,
                                                   self.root_item.column_count())
                        self.set_child_data(
                            new_parent.child(new_parent.child_count() - 1),
                            str(child_key), '', '', child_value)
            else:
                raise ValueError('Malformed MDSJson file')


class MainWindow(QMainWindow):

    def __init__(self, settings_tree_item):
        super().__init__()
        self.setupUi(self)
        # Create and set model
        model = TreeModel(settings_tree_item)
        self.view.setModel(model)
        for column in range(model.columnCount()):
            self.view.resizeColumnToContents(column)

        self.exitAction.triggered.connect(QApplication.instance().quit)

        self.view.selectionModel().selectionChanged.connect(self.updateActions)

        self.actionsMenu.aboutToShow.connect(self.updateActions)
        self.insertRowAction.triggered.connect(self.insertRow)
        self.insertColumnAction.triggered.connect(self.insertColumn)
        self.removeRowAction.triggered.connect(self.removeRow)
        self.removeColumnAction.triggered.connect(self.removeColumn)
        self.insertChildAction.triggered.connect(self.insertChild)
        self.printJsonAction.triggered.connect(self.print_json)

        self.updateActions()

    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(QtWidgets.QDesktopWidget().availableGeometry(self).size() * 0.5)
        self.centralwidget = QtWidgets.QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.vboxlayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.vboxlayout.setContentsMargins(0, 0, 0, 0)
        self.vboxlayout.setSpacing(0)
        self.vboxlayout.setObjectName("vboxlayout")
        self.view = QtWidgets.QTreeView(self.centralwidget)
        self.view.setAlternatingRowColors(True)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.view.setHorizontalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.view.setAnimated(False)
        self.view.setAllColumnsShowFocus(True)
        self.view.setObjectName("view")
        self.vboxlayout.addWidget(self.view)
        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 573, 31))
        self.menubar.setObjectName("menubar")
        self.fileMenu = QtWidgets.QMenu(self.menubar)
        self.fileMenu.setObjectName("fileMenu")
        self.actionsMenu = QtWidgets.QMenu(self.menubar)
        self.actionsMenu.setObjectName("actionsMenu")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.exitAction = QtWidgets.QAction(MainWindow)
        self.exitAction.setObjectName("exitAction")
        self.insertRowAction = QtWidgets.QAction(MainWindow)
        self.insertRowAction.setObjectName("insertRowAction")
        self.removeRowAction = QtWidgets.QAction(MainWindow)
        self.removeRowAction.setObjectName("removeRowAction")
        self.insertColumnAction = QtWidgets.QAction(MainWindow)
        self.insertColumnAction.setObjectName("insertColumnAction")
        self.removeColumnAction = QtWidgets.QAction(MainWindow)
        self.removeColumnAction.setObjectName("removeColumnAction")
        self.insertChildAction = QtWidgets.QAction(MainWindow)
        self.insertChildAction.setObjectName("insertChildAction")
        self.printJsonAction = QtWidgets.QAction(MainWindow)
        self.printJsonAction.setObjectName("printJsonAction")
        self.fileMenu.addAction(self.exitAction)
        self.actionsMenu.addAction(self.insertRowAction)
        self.actionsMenu.addAction(self.insertColumnAction)
        self.actionsMenu.addSeparator()
        self.actionsMenu.addAction(self.removeRowAction)
        self.actionsMenu.addAction(self.removeColumnAction)
        self.actionsMenu.addSeparator()
        self.actionsMenu.addAction(self.insertChildAction)
        self.actionsMenu.addSeparator()
        self.actionsMenu.addAction(self.printJsonAction)
        self.menubar.addAction(self.fileMenu.menuAction())
        self.menubar.addAction(self.actionsMenu.menuAction())

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "Editable Tree Model"))
        self.fileMenu.setTitle(_translate("MainWindow", "&File"))
        self.actionsMenu.setTitle(_translate("MainWindow", "&Actions"))
        self.exitAction.setText(_translate("MainWindow", "E&xit"))
        self.exitAction.setShortcut(_translate("MainWindow", "Ctrl+Q"))
        self.insertRowAction.setText(_translate("MainWindow", "Insert Row"))
        self.insertRowAction.setShortcut(_translate("MainWindow", "Ctrl+I, R"))
        self.removeRowAction.setText(_translate("MainWindow", "Remove Row"))
        self.removeRowAction.setShortcut(_translate("MainWindow", "Ctrl+R, R"))
        self.insertColumnAction.setText(_translate("MainWindow", "Insert Column"))
        self.insertColumnAction.setShortcut(_translate("MainWindow", "Ctrl+I, C"))
        self.removeColumnAction.setText(_translate("MainWindow", "Remove Column"))
        self.removeColumnAction.setShortcut(_translate("MainWindow", "Ctrl+R, C"))
        self.insertChildAction.setText(_translate("MainWindow", "Insert Child"))
        self.insertChildAction.setShortcut(_translate("MainWindow", "Ctrl+N"))
        self.printJsonAction.setText(_translate("MainWindow", "Print JSON"))

    def print_json(self):
        try:
            import json
            settings_tree = self.view.model().settings_tree
            print(json.dumps(settings_tree.to_serializable_obj(), indent=4))
        except Exception as e:
            print(e)

    def insertChild(self):
        try:
            index = self.view.selectionModel().currentIndex()
            model = self.view.model()

            if model.columnCount(index) == 0:
                if not model.insertColumn(0, index):
                    return

            if not model.insertRow(0, index):
                return

            for column in range(model.columnCount(index)):
                child = model.index(0, column, index)
                model.setData(child, '', Qt.EditRole)
                if model.headerData(column, Qt.Horizontal) is None:
                    model.setHeaderData(
                        column, Qt.Horizontal, '', Qt.EditRole)
            self.view.selectionModel().setCurrentIndex(
                model.index(0, 0, index), QItemSelectionModel.ClearAndSelect)
            self.updateActions()
        except Exception as e:
            print(e)

    def insertColumn(self):
        try:
            model = self.view.model()
            column = self.view.selectionModel().currentIndex().column()

            changed = model.insertColumn(column + 1)
            if changed:
                model.setHeaderData(column + 1, Qt.Horizontal, '', Qt.EditRole)
            self.updateActions()

            return changed
        except Exception as e:
            print(e)

    def insertRow(self):
        try:
            index = self.view.selectionModel().currentIndex()
            model = self.view.model()

            if not model.insertRow(index.row()+1, index.parent()):
                return
            self.updateActions()

            for column in range(model.columnCount(index.parent())):
                child = model.index(index.row()+1, column, index.parent())
                model.setData(child, '', Qt.EditRole)
        except Exception as e:
            print(e)

    def removeColumn(self):
        try:
            model = self.view.model()
            column = self.view.selectionModel().currentIndex().column()

            changed = model.removeColumn(column)
            if changed:
                self.updateActions()

            return changed
        except Exception as e:
            print(e)

    def removeRow(self):
        try:
            index = self.view.selectionModel().currentIndex()
            model = self.view.model()

            if model.removeRow(index.row(), index.parent()):
                self.updateActions()
        except Exception as e:
            print(e)

    def updateActions(self):
        try:
            hasSelection = not self.view.selectionModel().selection().isEmpty()
            self.removeRowAction.setEnabled(hasSelection)
            self.removeColumnAction.setEnabled(hasSelection)

            hasCurrent = self.view.selectionModel().currentIndex().isValid()
            self.insertRowAction.setEnabled(hasCurrent)
            self.insertColumnAction.setEnabled(hasCurrent)

            if hasCurrent:
                self.view.closePersistentEditor(self.view.selectionModel().currentIndex())

                row = self.view.selectionModel().currentIndex().row()
                column = self.view.selectionModel().currentIndex().column()
                if self.view.selectionModel().currentIndex().parent().isValid():
                    self.statusBar().showMessage("Position: (%d,%d)" % (row, column))
                else:
                    self.statusBar().showMessage("Position: (%d,%d) in top level" % (row, column))
        except Exception as e:
            print(e)


if __name__ == '__main__':

    import sys, json

    # =========================== SettingsTreeItem =========================== #
    # Create settings
    settings = SettingsTree('settings', 'General settings')
    # Preprocessing settings
    prep_sett = SettingsTree('prep_settings', 'Preprocessing settings')
    prep_sett.add_item(SettingsItem('fs', 'Sample rate', 'number', 256))
    prep_sett.add_item(SettingsItem('n_cha', 'Number of channels', 'number', 4))
    prep_sett.add_item(SettingsItem('l_cha', 'Labels of the channels', 'list', ['Fz', 'Cz', 'Pz', 'Oz']))
    filt_sett = SettingsTree('filt_settings', 'Filter settings')
    filt_sett.add_item(SettingsItem('apply_filt', 'Apply filter?', 'boolean', False))
    filt_sett.add_item(SettingsItem('cutoff', 'Cutoff frequencies', 'dict', {'low': 0.1, 'high': 30}))
    prep_sett.add_item(filt_sett)
    settings.add_item(prep_sett)

    settings_ser_obj = json.dumps(settings.to_serializable_obj(), indent=4)
    settings_from_ser_obj = SettingsTree.from_serializable_obj(json.loads(settings_ser_obj))

    # ================================ QT APP ================================ #
    app = QApplication(sys.argv)
    window = MainWindow(settings_from_ser_obj)
    window.show()
    sys.exit(app.exec_())
