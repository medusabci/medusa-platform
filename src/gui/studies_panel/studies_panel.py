# PYTHON MODULES
import sys
import json
import importlib
import multiprocessing as mp
# EXTERNAL MODULES
from PyQt5 import uic
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
# MEDUSA MODULES
from gui import gui_utils as gu
import constants, exceptions


ui_plots_panel_widget = \
    uic.loadUiType('gui/ui_files/studies_panel_widget.ui')[0]


class StudiesPanelWidget(QWidget, ui_plots_panel_widget):

    def __init__(self, medusa_interface, theme_colors):
        super().__init__()
        self.setupUi(self)
        # Attributes
        self.medusa_interface = medusa_interface
        self.theme_colors = theme_colors
        self.studies_settings = None
        self.undocked = False
        # Set up tool bar
        self.set_up_tool_bar_studies()

    def handle_exception(self, ex):
        # Treat exception
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(
                ex, importance='unknown',
                scope='studies',
                origin='studies_panel/studies_panel/handle_exception')
        # Notify exception to gui main
        self.medusa_interface.error(ex)

    def set_undocked(self, undocked):
        self.undocked = undocked
        self.reset_tool_bar_studies_buttons()

    def reset_tool_bar_studies_buttons(self):
        try:
            # Set icons in buttons
            self.toolButton_studies_config.setIcon(
                gu.get_icon("settings.svg", self.theme_colors))
            self.toolButton_studies_config.setToolTip('Studies settings')
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

    def set_up_tool_bar_studies(self):
        """This method creates the QAction buttons displayed in the toolbar
        """
        try:
            # Creates QIcons for the app tool bar
            self.reset_tool_bar_studies_buttons()
            # Connect signals to functions
            self.toolButton_studies_config.clicked.connect(self.studies_config)
        except Exception as e:
            self.handle_exception(e)

    def studies_config(self):
        try:
            raise Exception('Not implemented')
        except Exception as e:
            self.handle_exception(e)


class StudiesPanelWindow(QMainWindow):

    close_signal = pyqtSignal()

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
