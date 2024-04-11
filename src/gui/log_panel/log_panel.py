# EXTERNAL MODULES
from PySide6.QtUiTools import loadUiType
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *
# MEDUSA MODULES
from gui import gui_utils as gu
import constants, exceptions


ui_plots_panel_widget = loadUiType('gui/ui_files/log_panel_widget.ui')[0]


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
            # Set icons in buttons
            self.toolButton_log_save.setIcon(
                gu.get_icon("save_as.svg", self.theme_colors))
            self.toolButton_log_save.setToolTip('Save to file')
            self.toolButton_log_clean.setIcon(
                gu.get_icon("delete_sweep.svg", self.theme_colors))
            self.toolButton_log_clean.setToolTip('Clear log')
            self.toolButton_log_config.setIcon(
                gu.get_icon("settings.svg", self.theme_colors))
            self.toolButton_log_config.setToolTip('Log settings')
            if self.undocked:
                self.toolButton_log_undock.setIcon(
                    gu.get_icon("open_in_new_down.svg", self.theme_colors))
                self.toolButton_log_undock.setToolTip(
                    'Redock in main window')
            else:
                self.toolButton_log_undock.setIcon(
                    gu.get_icon("open_in_new.svg", self.theme_colors))
                self.toolButton_log_undock.setToolTip('Undock')
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

    def format_log_msg(self, msg, **kwargs):
        try:
            # Default style
            kwargs.setdefault('color', self.theme_colors['THEME_TEXT_LIGHT'])
            kwargs.setdefault('margin', '0')
            kwargs.setdefault('margin-top', '2px')
            kwargs.setdefault('margin-top', '2px')
            kwargs.setdefault('font-size', '9pt')
            # Format css
            style = ''
            for key, value in kwargs.items():
                if not isinstance(value, str):
                    raise ValueError('Type of %s must be str' % key)
                style += '%s: %s;' % (key, value)
            return '<p style="margin:0;margin-top:2;%s"> >> %s </p>' % \
                   (style, msg)
        except Exception as e:
            self.handle_exception(e)

    def remove_last_line(self):
        cursor = self.text_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.select(QTextCursor.LineUnderCursor)
        cursor.removeSelectedText()
        cursor.deletePreviousChar()
        cursor.movePosition(QTextCursor.End)
        self.text_log.setTextCursor(cursor)

    def print_log(self, msg, style=None, mode='append'):
        """ Prints in the application log.

        Parameters
        ----------
        msg: str
            String to print int the log panel
        style: dict or str
            If it is a dict, it must contain css properties and values for
            PyQt5. If it is a string, it must be one of the predefined styles,
            which are: ['error', 'warning'].
        mode: str {'append', 'replace'}
            Mode append cretes a new message in the log panel. Mode replace
            removes the last line and place the new one. This mode is designed
            for repetitive messages.
        """
        try:
            # Default styles
            if isinstance(style, str):
                if style == 'error':
                    style = {'color': self.theme_colors['THEME_RED']}
                elif style == 'warning':
                    style = {'color': self.theme_colors['THEME_YELLOW']}
                else:
                    raise ValueError('Custom style %s not recognized' % style)
            elif isinstance(style, dict):
                pass
            elif style is None:
                style = {}
            else:
                raise ValueError('Unrecognized style type')

            # Print log
            formatted_msg = self.format_log_msg(msg, **style)
            if mode == 'append':
                self.text_log.append(formatted_msg)
            elif mode == 'replace':
                self.remove_last_line()
                self.text_log.append(formatted_msg)
            else:
                raise ValueError('Unknown log mode! Valid values are'
                                 '{append, replace}')
        except Exception as e:
            self.handle_exception(e)


class LogPanelWindow(QMainWindow):

    close_signal = Signal()

    def __init__(self, log_panel_widget, theme_colors,
                 width=400, height=650):
        super().__init__()
        # self.plots_panel_widget = plots_panel_widget
        self.theme_colors = theme_colors
        self.setCentralWidget(log_panel_widget)
        gu.set_css_and_theme(self, self.theme_colors)
        # Window title and icon
        self.setWindowIcon(QIcon('%s/medusa_task_icon.png' %
                                 constants.IMG_FOLDER))
        self.setWindowTitle('Log panel')
        # Resize plots window
        self.resize(width, height)
        self.show()

    def closeEvent(self, event):
        self.close_signal.emit()
        event.accept()

    def get_plots_panel_widget(self):
        return self.centralWidget()
