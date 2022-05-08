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
from gui import gui_utils
import constants, exceptions


ui_plots_panel_widget = \
    uic.loadUiType('gui/ui_files/log_panel_widget.ui')[0]


class LogPanelWidget(QWidget, ui_plots_panel_widget):

    def __init__(self, medusa_interface, theme_colors):
        super().__init__()
        self.setupUi(self)
        # Attributes
        self.medusa_interface = medusa_interface
        self.theme_colors = theme_colors
        self.log_settings = None
        self.undocked = False
        # Set up tool bar
        self.set_up_tool_bar_log()

    def handle_exception(self, ex):
        # Treat exception
        if not isinstance(ex, exceptions.MedusaException):
            ex = exceptions.MedusaException(
                ex, importance='unknown',
                scope='log',
                origin='log_panel/log_panel/handle_exception')
        # Notify exception to gui main
        self.medusa_interface.error(ex)

    def set_undocked(self, undocked):
        self.undocked = undocked
        self.reset_tool_bar_log_buttons()

    def reset_tool_bar_log_buttons(self):
        try:
            # Creates QIcons for the app tool bar
            log_save_icon = QIcon("%s/icons/save_text.png" %
                                  constants.IMG_FOLDER)
            log_config_clean = QIcon("%s/icons/rubber.png" %
                                     constants.IMG_FOLDER)
            log_config_icon = QIcon("%s/icons/gear.png" %
                                    constants.IMG_FOLDER)
            undock_button_image = "dock_enabled_icon.png" if self.undocked else \
                "undock_enabled_icon.png"
            log_undock_icon = QIcon("%s/icons/%s" % (constants.IMG_FOLDER,
                                                     undock_button_image))

            # Set icons in buttons
            self.toolButton_log_save.setIcon(log_save_icon)
            self.toolButton_log_clean.setIcon(log_config_clean)
            self.toolButton_log_config.setIcon(log_config_icon)
            self.toolButton_log_undock.setIcon(log_undock_icon)
        except Exception as e:
            self.handle_exception(e)

    def set_up_tool_bar_log(self):
        """This method creates the QAction buttons displayed in the toolbar
        """
        try:
            # Creates QIcons for the app tool bar
            self.reset_tool_bar_log_buttons()
            # Connect signals to functions
            self.toolButton_log_save.clicked.connect(self.log_save)
            self.toolButton_log_clean.clicked.connect(self.log_clean)
            self.toolButton_log_config.clicked.connect(self.log_config)
        except Exception as e:
            self.handle_exception(e)

    def log_save(self):
        try:
            """ Opens a dialog to save a configuration file. """
            # Icon images cannot be saved as binary data, only their paths
            fdialog = QFileDialog()
            path = fdialog.getSaveFileName(fdialog, 'Save log file',
                                           '../data/',
                                           'Text (*.txt);; HTML (*.html)')[0]
            if path:
                with open(path, 'w') as f:
                    if path.split('.')[-1] == 'txt':
                        f.write(self.text_log.toPlainText())
                    elif path.split('.')[-1] == 'html':
                        f.write(self.text_log.toHtml())
                    else:
                        raise ValueError('Format not supported')
        except Exception as e:
            self.handle_exception(e)

    def log_clean(self):
        try:
            self.text_log.clear()
        except Exception as e:
            self.handle_exception(e)

    def log_config(self):
        try:
            raise Exception('Not implemented')
        except Exception as e:
            self.handle_exception(e)

    def format_log_msg(self, msg, color=None, **kwargs):
        try:
            col = self.theme_colors['THEME_TEXT_LIGHT'] \
                if color is None else color
            style = 'color:%s;' % col
            for key, value in kwargs.items():
                if not isinstance(value, str):
                    raise ValueError('Type of %s must be str' % key)
                style += '%s: %s;' % (key, value)
            return '<p style="margin:0;margin-top:2;%s"> >> %s </p>' % \
                   (style, msg)
        except Exception as e:
            self.handle_exception(e)

    def print_log(self, msg, style=None):
        """ Prints in the application log.
        """
        try:
            # Default styles
            if style == 'error':
                style = {'color': self.theme_colors['THEME_RED']}
            style = {} if style is None else style
            color = style.pop('color', None)
            formatted_msg = self.format_log_msg(msg, color=color, **style)
            curr_html = self.text_log.toHtml()
            curr_html += formatted_msg
            self.text_log.setText(curr_html)
        except Exception as e:
            self.handle_exception(e)


class LogPanelWindow(QMainWindow):

    close_signal = pyqtSignal()

    def __init__(self, log_panel_widget, theme_colors,
                 width=400, height=650):
        super().__init__()
        # self.plots_panel_widget = plots_panel_widget
        self.theme_colors = theme_colors
        self.setCentralWidget(log_panel_widget)
        gui_utils.set_css_and_theme(self, self.theme_colors)
        # Resize plots window
        self.resize(width, height)
        self.show()

    def closeEvent(self, event):
        self.close_signal.emit()
        event.accept()

    def get_plots_panel_widget(self):
        return self.centralWidget()
