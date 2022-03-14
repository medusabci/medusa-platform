from PyQt5.QtCore import (QAbstractItemModel, QItemSelectionModel,
                          QModelIndex, Qt)
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5 import QtWidgets, QtCore
from medusa.components import SettingsTreeItem


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
        self.orig_settings_tree = data
        self.set_settings_tree(data, self.root_item)

    def flags(self, index):
        if not index.isValid():
            return 0
        return Qt.ItemIsEditable | super(TreeModel, self).flags(index)

    def data(self, index, role):
        if not index.isValid():
            return None
        if role != Qt.DisplayRole and role != Qt.EditRole:
            return None
        item = self.getItem(index)
        return item.data(index.column())

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole:
            return False
        item = self.getItem(index)
        result = item.set_data(index.column(), value)
        if result:
            self.dataChanged.emit(index, index)
        return result

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.root_item.data(section)
        return None

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
        ch.set_data(3, ch_info)
        ch.set_data(2, ch_val_type)
        ch.set_data(1, ch_value)

    def set_settings_tree(self, data, parent):
        for item in data.items:
            if item.value_type == 'string' or \
                    item.value_type == 'number' or \
                    item.value_type == 'boolean':
                parent.insert_children(parent.child_count(), 1,
                                       self.root_item.column_count())
                self.set_child_data(
                    parent.child(parent.child_count() - 1),
                    item.key, item.info, item.value_type, item.value)
            elif item.value_type == 'dict':
                parent.insert_children(parent.child_count(), 1,
                                       self.root_item.column_count())
                new_parent = parent.child(parent.child_count() - 1)
                self.set_child_data(new_parent, item.key, item.info,
                                    item.value_type, item.value)
                for child_key, child_item in item.value.items():
                    new_parent.insert_children(new_parent.child_count(), 1,
                                               self.root_item.column_count())
                    self.set_child_data(
                        new_parent.child(new_parent.child_count() - 1),
                        child_key, child_item.info,
                        child_item.value_type, child_item.value)
            elif item.value_type == 'list':
                parent.insert_children(parent.child_count(), 1,
                                       self.root_item.column_count())
                new_parent = parent.child(parent.child_count() - 1)
                self.set_child_data(new_parent, item.key, item.info,
                                    item.value_type, item.value)
                for child_key, child_item in enumerate(item.value):
                    new_parent.insert_children(new_parent.child_count(), 1,
                                               self.root_item.column_count())
                    self.set_child_data(
                        new_parent.child(new_parent.child_count() - 1),
                        child_key, child_item.info,
                        child_item.value_type, child_item.value)
            elif item.is_tree():
                parent.insert_children(parent.child_count(), 1,
                                       self.root_item.column_count())
                new_parent = parent.child(parent.child_count() - 1)
                self.set_child_data(new_parent, item.key, item.info,
                                    item.value_type, item.value)
                self.set_settings_tree(item, new_parent)
            else:
                raise ValueError('Malformed MDSJson file')

    def add_item_data(self, data, item):
        item_key = item.data(0)
        item_value = item.data(1)
        item_type = item.data(2)
        item_info = item.data(3)
        if item_type == 'string' or \
                item_type == 'number' or \
                item_type == 'boolean':
            data.add_item(
                SettingsTreeItem(item_key, item_info, item_type, item_value))
        elif item_type == 'dict':
            item_value = dict()
            for i in range(item.child_count()):
                child_item = item.child(i)
                item_value[child_item.data(0)] = SettingsTreeItem(
                    child_item.data(0), child_item.data(3),
                    child_item.data(2), child_item.data(1))
            data.add_item(
                SettingsTreeItem(item_key, item_info, item_type, item_value))
        elif item_type == 'list':
            item_value = list()
            for i in range(item.child_count()):
                child_item = item.child(i)
                item_value.append(
                    SettingsTreeItem(i, child_item.data(3), child_item.data(
                        2), child_item.data(1)))
            data.add_item(
                SettingsTreeItem(item_key, item_info, item_type, item_value))
        elif item_type is None:
            child_data = SettingsTreeItem(item_key, item_info,
                                          item_type, item_value)
            for i in range(item.child_count()):
                child_data = self.add_item_data(child_data, item.child(i))
        else:
            raise ValueError('Malformed MDSJson file')
        return data

    def to_settings_tree(self):
        data = self.orig_settings_tree
        for i in range(self.root_item.child_count()):
            data = self.add_item_data(data, self.root_item.child(i))
        return data


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
        MainWindow.resize(573, 468)
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
            data = self.view.model().to_settings_tree()
            ser_data = data.to_serializable_obj()
            data2 = SettingsTreeItem.from_serializable_obj(ser_data)
            # Print JSON
            import json
            print(json.dumps(ser_data, indent=4))
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
                model.setData(child, "[No data]", Qt.EditRole)
                if model.headerData(column, Qt.Horizontal) is None:
                    model.setHeaderData(
                        column, Qt.Horizontal, "[No header]", Qt.EditRole)
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
                model.setHeaderData(column + 1, Qt.Horizontal, "[No header]",
                        Qt.EditRole)

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
                model.setData(child, "[No data]", Qt.EditRole)
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
    import sys

    # =========================== SettingsTreeItem =========================== #
    # Create settings
    settings = SettingsTreeItem('settings', 'General settings')
    # Preprocessing settings
    prep_sett = SettingsTreeItem('prep_settings', 'Preprocessing settings')
    prep_sett.add_item(SettingsTreeItem('fs', 'Sample rate', 'number', 256))
    prep_sett.add_item(SettingsTreeItem('n_cha', 'Channels', 'number', 256))
    settings.add_item(prep_sett)
    # Plot settings
    plot_sett = SettingsTreeItem('plot_settings', 'Plot settings')
    line_sett = SettingsTreeItem('line_settings', 'Line settings')
    line_sett.add_item(SettingsTreeItem('line_width', 'Plot line width',
                                        'number', 1))
    line_sett.add_item(SettingsTreeItem('line_color', 'Plot line color',
                                        'string', '#00000'))
    plot_sett.add_item(line_sett)
    plot_sett.add_item(SettingsTreeItem(
        'plot_types', 'Plot types', 'list',
        [SettingsTreeItem(None, None, 'string', 'EEGPlot'),
         SettingsTreeItem(None, None, 'string', 'PSDPlot')]))
    settings.add_item(plot_sett)

    # ================================ QT APP ================================ #
    app = QApplication(sys.argv)
    window = MainWindow(settings)
    window.show()
    sys.exit(app.exec_())
