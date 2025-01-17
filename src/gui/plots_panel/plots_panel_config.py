# PYTHON MODULES
import sys, os, json, traceback
from math import floor

# EXTERNAL MODULES
from PySide6.QtUiTools import loadUiType
from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

# MEDUSA COMPONENTS
from medusa import components
from acquisition import lsl_utils
import exceptions, constants

# MEDUSA
from gui.qt_widgets import dialogs
from gui import gui_utils as gu
from gui.plots_panel import real_time_plots

# Load the .ui files
ui_plots_panel_config = loadUiType("gui/ui_files/plots_panel_config_dialog.ui")[0]
ui_plot_config_dialog = loadUiType("gui/ui_files/plot_config_dialog.ui")[0]


class DropToolButton(QToolButton):

    delete_plot_frame = Signal(dict)

    def __init__(self, parent):
        super().__init__(parent)
        self.setToolTip('Drop the plot frame here')
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        try:
            if event.mimeData().hasFormat('text/plain'):
                event.accept()
            else:
                event.ignore()
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def dropEvent(self, event):
        try:
            data = json.loads(event.mimeData().text())
            self.delete_plot_frame.emit(data)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e


class GridCell(QFrame):

    drop_signal = Signal(dict)

    def __init__(self, uid, coordinates):
        super().__init__()
        self.uid = uid
        self.coordinates = coordinates
        self.busy = False
        self.plot_frame_uid = None
        self.setMouseTracking(True)
        self.setObjectName("grid_ell_%s" % uid)
        self.setProperty("class", "grid-cell")
        self.setAcceptDrops(True)

    def set_busy(self, busy, plot_frame_uid):
        try:
            self.busy = busy
            if busy:
                self.plot_frame_uid = plot_frame_uid
            else:
                self.plot_frame_uid = None
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def mouseMoveEvent(self, event):
        try:
            pos = event.pos()
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def dragEnterEvent(self, event):
        try:
            if event.mimeData().hasFormat('text/plain'):
                event.accept()
            else:
                event.ignore()
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def dropEvent(self, event):
        try:
            position = self.mapToParent(event.pos())
            drag_data = json.loads(event.mimeData().text())
            drag_data['drop_position'] = [position.x(), position.y()]
            self.drop_signal.emit(drag_data)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e


class PlotFrame(QLabel):

    drop_signal = Signal(dict)
    double_click_signal = Signal(dict)

    def __init__(self, uid, coordinates, span, configured=False):
        super().__init__()
        self.uid = uid
        self.coordinates = coordinates
        self.span = span
        self.configured = configured
        self.setText(str(uid))
        self.setAlignment(Qt.AlignCenter)
        self.setMouseTracking(True)
        self.setObjectName("plot_frame_%s" % uid)
        self.setProperty("class", "plot-frame")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setAcceptDrops(True)
        self.drag_data = None
        self.drag_start_position = None

    def mouseDoubleClickEvent(self, event):
        try:
            if event.button() == Qt.LeftButton:
                data = {
                    'orig_plot_frame_uid': self.uid,
                }
                self.double_click_signal.emit(data)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.LeftButton:
                self.drag_start_position = event.pos()
                self.drag_data = {
                    'orig_plot_frame_uid': self.uid,
                }
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def get_grid_cells(self, cells):
        try:
            grid_cells_uids = []
            for item in cells:
                if (self.coordinates[0] <= item.coordinates[0] <=
                    self.coordinates[0] + self.span[0] - 1) and \
                        (self.coordinates[1] <= item.coordinates[1] <=
                         self.coordinates[1] + self.span[1] - 1):
                    grid_cells_uids.append(item.uid)
            return grid_cells_uids
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def mouseMoveEvent(self, event):
        try:
            # Drag event
            if event.buttons() & Qt.LeftButton:
                # Mime data
                mimedata = QMimeData()
                mimedata.setText(json.dumps(self.drag_data))
                # Frame pixmap
                pixmap = QPixmap(self.size())
                bg_color = self.palette().color(self.backgroundRole())
                bg_color.setAlpha(128)
                pixmap.fill(bg_color)
                # Drag
                drag = QDrag(self)
                drag.setMimeData(mimedata)
                drag.setPixmap(pixmap)
                drag.setHotSpot(event.pos())
                drag.exec(Qt.MoveAction)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def dragEnterEvent(self, event):
        try:
            if event.mimeData().hasFormat('text/plain'):
                event.accept()
            else:
                event.ignore()
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def dropEvent(self, event):
        try:
            position = self.mapToParent(event.pos())
            drag_data = json.loads(event.mimeData().text())
            drag_data['dest_plot_frame_uid'] = self.uid
            drag_data['drop_position'] = [position.x(), position.y()]
            self.drop_signal.emit(drag_data)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def set_configured(self, background_color):
        try:
            self.configured = True
            gu.modify_property(self, "background-color",
                                      background_color)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def set_non_configured(self, background_color):
        try:
            self.configured = False
            gu.modify_property(self, "background-color",
                                      background_color)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e


class QSizeGripPlotFrame(QSizeGrip):

    init_grip_signal = Signal(dict)
    move_grip_signal = Signal(dict)
    release_grip_signal = Signal(dict)

    def __init__(self, parent, uid, coordinates, span):
        super().__init__(parent)
        self.parent_frame = parent
        self.uid = uid
        self.coordinates = coordinates
        self.span = span
        self.setMouseTracking(True)
        self.setObjectName("grip_rect_plot_%s" % uid)
        self.setProperty("class", "grip-plot-frame")

    def mousePressEvent(self, event):
        try:
            if event.buttons() & Qt.LeftButton:
                position = self.mapToParent(event.pos())
                data = {
                    'uid': self.uid,
                    'position': [position.x(), position.y()]
                }
                self.init_grip_signal.emit(data)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def mouseReleaseEvent(self, event):
        try:
            position = self.mapToParent(event.pos())
            data = {
                'uid': self.uid,
                'position': [position.x(), position.y()]
            }
            self.release_grip_signal.emit(data)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def mouseMoveEvent(self, event):
        try:
            if event.buttons() & Qt.LeftButton:
                position = self.mapToParent(event.pos())
                data = {
                    'uid': self.uid,
                    'position': [position.x(), position.y()]
                }
                self.move_grip_signal.emit(data)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e


class QToolButtonConfigPlotFrame(QToolButton):

    plot_frame_config_button_clicked = Signal(dict)

    def __init__(self, parent, uid, coordinates, span):
        super().__init__(parent)
        self.parent_frame = parent
        self.uid = uid
        self.coordinates = coordinates
        self.span = span
        self.setObjectName("plot_frame_config_button%s" % uid)
        self.setProperty("class", "plot-frame-config-button")

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.LeftButton:
                pass
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e


class PanelConfig(components.SerializableComponent):

    def __init__(self, n_rows, n_cols):
        # Parameters
        self.n_rows = n_rows
        self.n_cols = n_cols
        # Init
        self.grid_cells = list()
        self.plot_frames = list()
        self.plots_settings = dict()
        self.free_uid = 0
        # Create grid items
        self.arrange_grid()

    def arrange_grid(self):
        try:
            # Clear grid
            self.clear()
            # Fill grid
            grid_uid = 0
            for i in range(self.n_rows):
                for j in range(self.n_cols):
                    self.create_grid_cell(grid_cell_uid=grid_uid,
                                          coordinates=[i, j])
                    grid_uid += 1
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def create_grid_cell(self, grid_cell_uid, coordinates):
        try:
            item = GridCell(grid_cell_uid, coordinates)
            self.grid_cells.append(item)
            return item
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def create_plot_frame(self, plot_frame_uid, coordinates, span,
                          plot_info=None, signal_settings=None,
                          visualization_settings=None, lsl_stream_info=None):
        try:
            # Check uid
            if self.check_uid(plot_frame_uid):
                raise ValueError('The plot uid is already taken!')
            # Create widgets f the plot frame
            plot_frame = PlotFrame(plot_frame_uid,
                                   coordinates, span)
            plot_frame_grip = QSizeGripPlotFrame(plot_frame,
                                                 plot_frame_uid,
                                                 coordinates, span)
            # Create layout
            plot_frame_layout = QHBoxLayout(plot_frame)
            plot_frame_layout.addWidget(plot_frame_grip,
                                        Qt.AlignBottom | Qt.AlignRight)
            # Append widgets to plot_frames
            self.plot_frames.append({
                'plot_frame_layout': plot_frame_layout,
                'plot_frame_item': plot_frame,
                'plot_frame_grip_item': plot_frame_grip,
            })
            # Plot settings
            self.set_plot_settings(
                uid=plot_frame_uid,
                plot_info=plot_info,
                signal_settings=signal_settings,
                visualization_settings=visualization_settings,
                lsl_stream_info=lsl_stream_info
            )
            return len(self.plot_frames) - 1
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def check_uid(self, uid):
        try:
            for item in self.plot_frames:
                if item['plot_frame_item'].uid == uid:
                    return True
            return False
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def get_free_uid(self):
        try:
            current_uids = [plt['plot_frame_item'].uid
                            for plt in self.plot_frames]
            return max(current_uids) + 1
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def set_plot_settings(self, uid, plot_info, signal_settings,
                          visualization_settings, lsl_stream_info):
        try:
            # Check errors
            if plot_info is not None and not isinstance(plot_info, dict):
                raise ValueError('Parameter plot_info must be None or dict')
            plot_uid = None if plot_info is None else plot_info['uid']
            self.plots_settings[uid] = {
                'plot_uid': plot_uid,
                'signal_settings': signal_settings,
                'visualization_settings': visualization_settings,
                'lsl_stream_info': lsl_stream_info,
            }
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def get_grid_cell_by_uid(self, grid_cell_uid):
        try:
            for index, item in enumerate(self.grid_cells):
                if item.uid == grid_cell_uid:
                    return index, item
            return None, None
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def get_plot_frame_by_uid(self, plot_frame_uid):
        try:
            for index, item in enumerate(self.plot_frames):
                if item['plot_frame_item'].uid == plot_frame_uid:
                    return index, item
            return None, None
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def delete_plot_frame(self, index):
        try:
            item = self.plot_frames.pop(index)
            self.plots_settings.pop(item['plot_frame_item'].uid)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def are_all_plots_configured(self):
        try:
            check = []
            for plot_frame in self.plot_frames:
                check.append(plot_frame['plot_frame_item'].configured)
            return all(check)
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    def to_serializable_obj(self):
        try:
            data = dict()
            data['n_rows'] = self.n_rows
            data['n_cols'] = self.n_cols
            data['plots'] = list()
            for item in self.plot_frames:
                plot_frame_item = item['plot_frame_item']
                data['plots'].append({
                    'uid': plot_frame_item.uid,
                    'coordinates': plot_frame_item.coordinates,
                    'span': plot_frame_item.span,
                    'configured': plot_frame_item.configured,
                })
            data['plots_settings'] = dict()
            for plot_key, plot_settings in self.plots_settings.items():
                data['plots_settings'][str(plot_key)] = dict()
                for key, value in plot_settings.items():
                    if key == 'lsl_stream_info':
                        value = value.to_serializable_obj()
                    data['plots_settings'][str(plot_key)][key] = value
            return data
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e

    @classmethod
    def from_serializable_obj(cls, dict_data):
        try:
            lsl_config = dict_data['lsl_config']
            n_rows = dict_data['n_rows']
            n_cols = dict_data['n_cols']
            config = cls(n_rows, n_cols)
            # Add plots
            config.plots_settings = {int(k): v for k, v
                                     in dict_data['plots_settings'].items()}
            for item in dict_data['plots']:
                uid = item['uid']
                plot_info = real_time_plots.get_plot_info(
                    config.plots_settings[uid]['plot_uid'])
                signal_settings = \
                    config.plots_settings[uid]['signal_settings']
                visualization_settings = \
                    config.plots_settings[uid]['visualization_settings']
                lsl_stream_info = config.plots_settings[uid]['lsl_stream_info']
                try:
                    # Update lsl_stream (necessary for weak LSL search)
                    if lsl_config['weak_search']:
                        lsl_stream = lsl_utils.find_lsl_stream(
                            lsl_streams=lsl_config['working_streams'],
                            force_one_stream=True,
                            medusa_uid=lsl_stream_info['medusa_uid'],
                            name=lsl_stream_info['lsl_name'],
                            type=lsl_stream_info['lsl_type'],
                            source_id=lsl_stream_info['lsl_source_id'],
                            channel_count=lsl_stream_info['lsl_n_cha'],
                            nominal_srate=lsl_stream_info['fs'])
                    else:
                        lsl_stream = lsl_utils.find_lsl_stream(
                            lsl_streams=lsl_config['working_streams'],
                            force_one_stream=True,
                            medusa_uid=lsl_stream_info['medusa_uid'],
                            uid=lsl_stream_info['lsl_uid'],
                            name=lsl_stream_info['lsl_name'],
                            type=lsl_stream_info['lsl_type'],
                            source_id=lsl_stream_info['lsl_source_id'],
                            channel_count=lsl_stream_info['lsl_n_cha'],
                            nominal_srate=lsl_stream_info['fs'])
                    # New instance to avoid pulling data from the same stream
                    # for several plots
                    lsl_stream_info = lsl_utils.LSLStreamWrapper(
                        lsl_stream.lsl_stream)
                    lsl_stream_info.update_medusa_parameters_from_lslwrapper(
                        lsl_stream)
                except exceptions.LSLStreamNotFound as e:
                    lsl_stream_info = None
                    item['configured'] = False
                except exceptions.UnspecificLSLStreamInfo as e:
                    lsl_stream_info = None
                    item['configured'] = False
                plot_idx = config.create_plot_frame(
                    item['uid'],
                    item['coordinates'],
                    item['span'],
                    plot_info=plot_info,
                    signal_settings=signal_settings,
                    visualization_settings=visualization_settings,
                    lsl_stream_info=lsl_stream_info)
                if item['configured']:
                    config.plot_frames[plot_idx]['plot_frame_item'].\
                        set_configured(dict_data['theme_colors']['THEME_GREEN'])
            return config
        except Exception as e:
            raise e

    def clear(self):
        try:
            self.grid_cells = list()
            self.plot_frames = list()
            self.plots_settings = dict()
        except Exception as e:
            print('Exception: %s' % str(e))
            raise e


class ConfigPlotFrameDialog(QDialog, ui_plot_config_dialog):

    def __init__(self, uid, signal_settings, visualization_settings,
                 lsl_streams, plots_info, selected_lsl_stream=None,
                 selected_plot_info=None, theme_colors=None):
        try:
            super().__init__()
            self.setupUi(self)
            # Set style
            self.dir = os.path.dirname(__file__)
            self.theme_colors = gu.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gu.set_css_and_theme(self, self.theme_colors)
            self.setWindowIcon(QIcon('%s/medusa_task_icon.png' %
                                     constants.IMG_FOLDER))
            self.setWindowTitle('Plot configuration')
            # Connect signals
            self.comboBox_plot_type.currentIndexChanged.connect(
                self.on_combobox_plot_type_changed)
            self.comboBox_lsl_streams.currentIndexChanged.connect(
                self.on_combobox_lsl_stream_changed)
            self.pushButton_reset.clicked.connect(self.reset)
            # Check errors
            if selected_lsl_stream is not None and \
                    not isinstance(selected_lsl_stream,
                                   lsl_utils.LSLStreamWrapper):
                raise ValueError('Parameter selected_lsl_stream '
                                 'must be None or lsl_utils.LSLStreamWrapper')
            if selected_plot_info is not None and \
                    not isinstance(selected_plot_info, dict):
                raise ValueError('Parameter selected_plot '
                                 'must be None or dict')
            if selected_lsl_stream is not None:
                if lsl_utils.check_if_medusa_uid_is_available(
                        lsl_streams, selected_lsl_stream.medusa_uid):
                    # Perhaps the name of the stream has been changed and is no
                    # longer available
                    selected_lsl_stream = None
            # Init variables
            self.uid = uid
            self.working_lsl_streams = lsl_streams
            self.plots_info = plots_info
            self.signal_settings = signal_settings
            self.visualization_settings = visualization_settings
            self.selected_lsl_stream_info = None
            self.selected_plot_info = None
            # Set combo boxes
            self.set_lsl_streams(selected_lsl_stream)
            self.set_plot_types(selected_plot_info)
            if selected_plot_info is not None:
                self.set_settings_in_text_edits(signal_settings,
                                                visualization_settings)
        except Exception as e:
            self.exception_handler(e)

    def set_lsl_streams(self, current_lsl_stream=None):
        try:
            self.comboBox_lsl_streams.clear()
            lsl_streams_uids = [s.medusa_uid for s in self.working_lsl_streams]
            for lsl_stream_info in self.working_lsl_streams:
                stream_descr = lsl_stream_info.get_easy_description()
                self.comboBox_lsl_streams.addItem(stream_descr)
                # Select lsl_stream
                if current_lsl_stream is not None:
                    current_stream_uid = current_lsl_stream.medusa_uid
                    if current_stream_uid in lsl_streams_uids:
                        idx = lsl_streams_uids.index(current_stream_uid)
                        self.comboBox_lsl_streams.setCurrentIndex(idx)
                    else:
                        self.comboBox_lsl_streams.setCurrentIndex(0)
                else:
                    self.comboBox_lsl_streams.setCurrentIndex(0)
        except Exception as e:
            self.exception_handler(e)

    def set_plot_types(self, current_plot=None):
        try:
            self.comboBox_plot_type.clear()
            plot_types = [v['uid'] for v in self.plots_info]
            for plot_type in plot_types:
                self.comboBox_plot_type.addItem(plot_type)
            # Select plot type
            if current_plot is not None:
                current_plot_type = current_plot['uid']
                if current_plot_type in plot_types:
                    idx = plot_types.index(current_plot_type)
                    self.comboBox_plot_type.setCurrentIndex(idx)
                else:
                    self.comboBox_plot_type.setCurrentIndex(0)
            else:
                self.comboBox_plot_type.setCurrentIndex(0)
        except Exception as e:
            self.exception_handler(e)

    def on_combobox_lsl_stream_changed(self):
        lsl_stream_index = self.comboBox_lsl_streams.currentIndex()
        self.selected_lsl_stream_info = self.working_lsl_streams[lsl_stream_index]

    def on_combobox_plot_type_changed(self):
        try:
            # Get selected plot type and lsl_stream
            plot_index = self.comboBox_plot_type.currentIndex()
            # Signal options
            self.selected_plot_info = self.plots_info[plot_index]
            signal_type = self.selected_lsl_stream_info.medusa_type
            plot_type = self.selected_plot_info['uid']
            plot_class = self.selected_plot_info['class']
            # Check signal and get signal and plot options
            if plot_class.check_signal(signal_type):
                # Get default settings of the new plot
                signal_settings, visualization_settings = \
                    plot_class.get_default_settings()
                self.set_settings_in_text_edits(signal_settings,
                                                visualization_settings)
            else:
                raise ValueError('Wrong signal type %s for plot type %s' %
                                 (signal_type, plot_type))

        except Exception as e:
            self.exception_handler(e)

    def set_settings_in_text_edits(self, signal_settings,
                                   visualization_settings):
        try:
            # Update settings and text areas
            self.textEdit_signal_options.setText(
                json.dumps(signal_settings, indent=4))
            self.textEdit_plot_options.setText(
                json.dumps(visualization_settings, indent=4))
        except Exception as e:
            self.exception_handler(e)

    def reset(self):
        try:
            self.set_lsl_streams()
            self.set_plot_types()
        except Exception as e:
            self.exception_handler(e)

    def accept(self):
        try:
            # Update plot instance settings
            signal_settings = json.loads(
                self.textEdit_signal_options.toPlainText())
            visualization_settings = json.loads(
                self.textEdit_plot_options.toPlainText())
            self.signal_settings = signal_settings
            self.visualization_settings = visualization_settings
            super().accept()
        except Exception as e:
            self.exception_handler(e)

    def reject(self):
        try:
            super().reject()
        except Exception as e:
            self.exception_handler(e)

    def exception_handler(self, ex):
        traceback.print_exc()
        dialogs.error_dialog(str(ex), 'Error!')


class PlotsPanelConfigDialog(QDialog, ui_plots_panel_config):
    """ This class implements the config dialog of the plots panel.
    """

    def __init__(self, lsl_config, plots_config_file_path,
                 config=None, theme_colors=None):
        try:
            super().__init__()
            self.setupUi(self)
            # Initialize the application
            self.dir = os.path.dirname(__file__)
            self.theme_colors = gu.get_theme_colors('dark') if \
                theme_colors is None else theme_colors
            self.stl = gu.set_css_and_theme(self, self.theme_colors)
            self.setWindowIcon(QIcon('%s/medusa_task_icon.png' %
                                     constants.IMG_FOLDER))
            self.setWindowTitle('Real time plots panel configuration')
            self.gridLayout_grid.setSpacing(2)
            # Init variables
            self.lsl_config = lsl_config
            self.plots_config_file_path = plots_config_file_path
            self.plots_info = real_time_plots.__plots_info__
            if config is None:
                config = PanelConfig(n_rows=8, n_cols=8)
            else:
                config['theme_colors'] = self.theme_colors
                config['lsl_config'] = self.lsl_config
                try:
                    config = PanelConfig.from_serializable_obj(config)
                except Exception as e:
                    dialogs.error_dialog(
                        'The plots panel configuration is corrupted. The '
                        'reason could be an external modification of the '
                        'configuration file or a software update. '
                        'Please, reconfigure.', 'Error')
                    config = PanelConfig(n_rows=8, n_cols=8)
            self.config = config
            self.set_panel_config()
            # Initial state
            self.default_plot_frame_span = [1, 1]
            self.spinBox_grid_rows.setValue(self.config.n_rows)
            self.spinBox_grid_cols.setValue(self.config.n_cols)
            # State variables
            self.last_frame_resize_event = dict()
            # Spin boxes
            self.spinBox_grid_rows.valueChanged.connect(self.on_rows_changed)
            self.spinBox_grid_cols.valueChanged.connect(self.on_cols_changed)
            # Add plot button
            icon = gu.get_icon("add.svg", theme_colors=self.theme_colors)
            # icon = QIcon("%s/icons/plus.png" % constants.IMG_FOLDER)
            self.toolButton_add_plot.setIcon(icon)
            self.toolButton_add_plot.clicked.connect(self.on_add_plot_clicked)
            # Delete plot button
            self.toolButton_delete_plot = DropToolButton(self)
            self.toolButton_delete_plot.setIconSize(QSize(20, 20))
            self.horizontalLayout.addWidget(self.toolButton_delete_plot)
            icon = gu.get_icon("delete_forever.svg", theme_colors=self.theme_colors)
            # icon = QIcon("%s/icons/delete.png" % constants.IMG_FOLDER)
            self.toolButton_delete_plot.setIcon(icon)
            self.toolButton_delete_plot.delete_plot_frame.connect(
                self.on_delete_plot_drop)
            # Connect the buttons
            self.button_clear.clicked.connect(self.reset_grid)
            # Config dialog
            self.config_dialog = None
            # Show
            self.show()
        except Exception as e:
            self.exception_handler(e)

    def on_rows_changed(self):
        try:
            self.config.n_rows = self.spinBox_grid_rows.value()
            self.reset_grid()
        except Exception as e:
            self.exception_handler(e)

    def on_cols_changed(self):
        try:
            self.config.n_cols = self.spinBox_grid_cols.value()
            self.reset_grid()
        except Exception as e:
            self.exception_handler(e)

    def on_add_plot_clicked(self):
        try:
            # Find place for plot
            if len(self.config.plot_frames) > 0:
                uid = self.config.get_free_uid()
            else:
                uid = 0
            span = self.default_plot_frame_span
            coordinates = self.find_place_for_plot_frame(span)
            # Add plot
            if coordinates is not None:
                # Create new plot frame
                plot_frame_index = self.config.create_plot_frame(
                    uid, coordinates, span)
                # Add plot to grid
                self.add_plot_frame(plot_frame_index)
        except Exception as e:
            self.exception_handler(e)

    def on_delete_plot_drop(self, data):
        try:
            self.delete_plot_frame(data['orig_plot_frame_uid'])
        except Exception as e:
            self.exception_handler(e)

    def set_panel_config(self):
        try:
            # Clear all
            self.clear()
            # Add grid
            for item in self.config.grid_cells:
                self.add_grid_cell(item)
            # Add plot frames
            for plot_frame_index in range(len(self.config.plot_frames)):
                self.add_plot_frame(plot_frame_index)
        except Exception as e:
            self.exception_handler(e)

    def reset_grid(self):
        try:
            # Clear all
            self.clear()
            # Reset grid cell objects in config
            self.config.arrange_grid()
            # Add grid
            for item in self.config.grid_cells:
                self.add_grid_cell(item)
        except Exception as e:
            self.exception_handler(e)

    def add_grid_cell(self, grid_cell):
        try:
            x = grid_cell.coordinates[0]
            y = grid_cell.coordinates[1]
            grid_cell.drop_signal.connect(self.drop_plot_frame)
            self.gridLayout_grid.addWidget(grid_cell, x, y, 1, 1)
        except Exception as e:
            self.exception_handler(e)

    def add_plot_frame(self, plot_frame_index):
        try:
            # Get widgets
            widgets = self.config.plot_frames[plot_frame_index]
            plot_frame = widgets['plot_frame_item']
            plot_frame_grip = widgets['plot_frame_grip_item']
            # Connect signals
            plot_frame.drop_signal.connect(self.drop_plot_frame)
            plot_frame.double_click_signal.connect(self.double_click_plot_frame)
            plot_frame_grip.init_grip_signal.connect(
                self.init_plot_frame_grip)
            plot_frame_grip.release_grip_signal.connect(
                self.release_plot_frame_grip)
            plot_frame_grip.move_grip_signal.connect(
                self.move_plot_frame_grip)
            # Add plot frame to layout
            self.gridLayout_grid.addWidget(plot_frame,
                                           plot_frame.coordinates[0],
                                           plot_frame.coordinates[1],
                                           plot_frame.span[0],
                                           plot_frame.span[1])
            self.gridLayout_grid.addWidget(plot_frame_grip,
                                           plot_frame.coordinates[0],
                                           plot_frame.coordinates[1],
                                           plot_frame.span[0],
                                           plot_frame.span[1],
                                           Qt.AlignBottom | Qt.AlignRight)
            # Update busy cells
            plot_grid_cells = plot_frame.get_grid_cells(self.config.grid_cells)
            self.update_grid_cells_state(plot_grid_cells, True, plot_frame.uid)
        except Exception as e:
            self.exception_handler(e)

    def double_click_plot_frame(self, data):
        try:

            uid = data['orig_plot_frame_uid']
            plot_settings = self.config.plots_settings[uid]
            curr_plot_info = real_time_plots.get_plot_info(
                plot_settings['plot_uid'])
            curr_signal_settings = \
                plot_settings['signal_settings']
            curr_visualization_settings = \
                plot_settings['visualization_settings']
            curr_lsl_stream_info = plot_settings['lsl_stream_info']
            self.config_dialog = ConfigPlotFrameDialog(
                uid, curr_signal_settings, curr_visualization_settings,
                self.lsl_config['working_streams'], self.plots_info,
                selected_lsl_stream=curr_lsl_stream_info,
                selected_plot_info=curr_plot_info,
                theme_colors=self.theme_colors)
            self.config_dialog.accepted.connect(self.on_config_dialog_accept)
            self.config_dialog.rejected.connect(self.on_config_dialog_reject)
            self.config_dialog.exec()

        except Exception as e:
            self.exception_handler(e)

    def on_config_dialog_accept(self):
        try:
            uid = self.config_dialog.uid
            curr_plot_info = self.config_dialog.selected_plot_info
            curr_signal_settings = \
                self.config_dialog.signal_settings
            curr_visualization_settings = \
                self.config_dialog.visualization_settings
            curr_lsl_stream_info = self.config_dialog.selected_lsl_stream_info
            self.config.set_plot_settings(
                uid=uid,
                plot_info=curr_plot_info,
                signal_settings=curr_signal_settings,
                visualization_settings=curr_visualization_settings,
                lsl_stream_info=curr_lsl_stream_info
            )
            plot_frame_idx, plot_frame = self.config.get_plot_frame_by_uid(uid)
            plot_frame_item = plot_frame['plot_frame_item']
            plot_frame_item.set_configured(self.theme_colors['THEME_GREEN'])
            self.config_dialog = None
        except Exception as e:
            self.exception_handler(e)

    def on_config_dialog_reject(self):
        try:
            self.config_dialog = None
        except Exception as e:
            self.exception_handler(e)

    def delete_plot_frame(self, plot_frame_uid):
        try:
            index, item = self.config.get_plot_frame_by_uid(plot_frame_uid)
            plot_frame_item = item['plot_frame_item']
            plot_frame_grip_item = item['plot_frame_grip_item']
            plot_grid_cells = plot_frame_item.get_grid_cells(
                self.config.grid_cells)
            self.update_grid_cells_state(plot_grid_cells, False)
            plot_frame_item.deleteLater()
            plot_frame_grip_item.deleteLater()
            self.config.delete_plot_frame(index)
        except Exception as e:
            self.exception_handler(e)

    def find_place_for_plot_frame(self, span):
        try:
            for item in self.config.grid_cells:
                coordinates, span = self.avoid_overflow_drop(item.coordinates, span)
                check_cells_uids = self.get_grid_cells_from_coord_and_span(
                    coordinates, span)
                if check_cells_uids is None:
                    continue
                available, conflicts = self.check_if_cells_are_available(
                    check_cells_uids)
                if available:
                    return coordinates
            return None
        except Exception as e:
            self.exception_handler(e)

    def get_grid_cells_from_coord_and_span(self, coordinates, span):
        try:
            grid_cells_uids = []
            for item in self.config.grid_cells:
                if (coordinates[0] <= item.coordinates[0] <=
                    coordinates[0] + span[0] - 1) and \
                        (coordinates[1] <= item.coordinates[1] <=
                         coordinates[1] + span[1] - 1) and \
                        (coordinates[0] + span[0] <= self.config.n_rows) and \
                        (coordinates[1] + span[1] <= self.config.n_cols):
                    grid_cells_uids.append(item.uid)
            return grid_cells_uids
        except Exception as e:
            self.exception_handler(e)

    def get_grid_coordinates_from_position(self, pos):
        try:
            rect = self.gridLayout_grid.geometry()
            grid_width = rect.width()
            grid_height = rect.height()
            row = floor(pos[1] / grid_height * self.config.n_rows)
            col = floor(pos[0] / grid_width * self.config.n_cols)
            grid_coord = [row, col]
            return grid_coord
        except Exception as e:
            self.exception_handler(e)

    def check_if_cells_are_available(self, grid_cells_uids):
        try:
            check_available = []
            conflicts = []
            for uid in grid_cells_uids:
                index, item = self.config.get_grid_cell_by_uid(uid)
                check_val = not item.busy if item is not None else False
                check_available.append(check_val)
                if not check_val:
                    conflicts.append(item.plot_frame_uid)
            return all(check_available), list(set(conflicts))
        except Exception as e:
            self.exception_handler(e)

    def check_number_of_cells_available(self):
        try:
            n_available = 0
            for item in self.config.grid_cells:
                if not item.busy:
                    n_available += 1
            return n_available
        except Exception as e:
            self.exception_handler(e)

    def update_grid_cells_state(self, grid_cells_uids, state,
                                plot_frame_uid=None):
        """Updates the state of the grid cells"""
        try:
            for uid in grid_cells_uids:
                index, item = self.config.get_grid_cell_by_uid(uid)
                self.config.grid_cells[index].set_busy(state, plot_frame_uid)
        except Exception as e:
            self.exception_handler(e)

    def avoid_overflow_drop(self, coordinates, span):
        try:
            if coordinates[0] + span[0] > self.config.n_rows:
                coordinates[0] -= coordinates[0] + span[0] - self.config.n_rows
            if coordinates[1] + span[1] > self.config.n_cols:
                coordinates[1] -= coordinates[1] + span[1] - self.config.n_cols
            return coordinates, span
        except Exception as e:
            self.exception_handler(e)

    def avoid_overflow_grip(self, coordinates, span):
        try:
            # Fix rows
            if coordinates[0] + span[0] > self.config.n_rows:
                span[0] = self.config.n_rows - coordinates[0]
            # Fix columns
            if coordinates[1] + span[1] > self.config.n_cols:
                span[1] = self.config.n_cols - coordinates[1]
            # Fix span
            if span[0] <= 0:
                span[0] = 1
            if span[1] <= 0:
                span[1] = 1
            return coordinates, span
        except Exception as e:
            self.exception_handler(e)

    def init_plot_frame_grip(self, data):
        try:
            pass
        except Exception as e:
            self.exception_handler(e)

    def move_plot_frame_grip(self, data):
        try:
            pass
        except Exception as e:
            self.exception_handler(e)

    def release_plot_frame_grip(self, data):
        try:
            # Get data
            uid = data['uid']
            position = data['position']
            event_coord = self.get_grid_coordinates_from_position(position)
            # Get new coordinates and span
            index, item = self.config.get_plot_frame_by_uid(uid)
            item = item['plot_frame_item']
            coordinates = item.coordinates
            span = [event_coord[0] - coordinates[0] + 1,
                        event_coord[1] - coordinates[1] + 1]
            # Check that the resize is correct
            coordinates, span = self.avoid_overflow_grip(coordinates, span)
            check_cells_uids = self.get_grid_cells_from_coord_and_span(
                coordinates, span)
            if check_cells_uids is None:
                return
            available, conflicts = self.check_if_cells_are_available(
                check_cells_uids)
            if not available:
                if not (len(conflicts) == 1 and conflicts[0] == uid):
                    return
            self.update_plot_position(uid, coordinates, span)
        except Exception as e:
            self.exception_handler(e)

    def drop_plot_frame(self, data):
        try:
            # Get event data
            uid = data['orig_plot_frame_uid']
            drop_position = data['drop_position']
            coordinates = self.get_grid_coordinates_from_position(drop_position)
            # Avoid overload
            index, item = self.config.get_plot_frame_by_uid(uid)
            span = item['plot_frame_item'].span
            coordinates, span = self.avoid_overflow_drop(coordinates, span)
            # Check if the space is available
            cells_uids = self.get_grid_cells_from_coord_and_span(
                coordinates, span)
            available, conflicts = self.check_if_cells_are_available(
                cells_uids)
            if not available:
                if not (len(conflicts) == 1 and conflicts[0] == uid):
                    return
            self.update_plot_position(uid, coordinates, span)
        except Exception as e:
            self.exception_handler(e)

    def update_plot_position(self, uid, new_coordinates, new_span):
        # Get settings
        settings = self.config.plots_settings[uid]
        # Delete plot
        plot_frame_idx, plot_frame = self.config.get_plot_frame_by_uid(uid)
        plot_frame_item = plot_frame['plot_frame_item']
        was_configured = plot_frame_item.configured
        self.delete_plot_frame(uid)
        # Create new plot frame
        plot_frame_index = self.config.create_plot_frame(
            uid, new_coordinates, new_span,
            plot_info=real_time_plots.get_plot_info(settings['plot_uid']),
            signal_settings=settings['signal_settings'],
            visualization_settings=settings['visualization_settings'],
            lsl_stream_info=settings['lsl_stream_info']
        )
        # Add plot
        self.add_plot_frame(plot_frame_index)
        if was_configured:
            plot_frame_idx, plot_frame = \
                self.config.get_plot_frame_by_uid(uid)
            plot_frame_item = plot_frame['plot_frame_item']
            plot_frame_item.set_configured(self.theme_colors['THEME_GREEN'])

    def clear(self):
        try:
            while self.gridLayout_grid.count() > 0:
                item = self.gridLayout_grid.takeAt(0)
                item.widget().deleteLater()
        except Exception as e:
            self.exception_handler(e)

    def get_config(self):
        return self.config.to_serializable_obj()

    def accept(self):
        """ This function updates the lsl_streams.xml file and saves it
        """
        try:
            if not self.config.are_all_plots_configured():
                raise ValueError('All plots must be configured!')
            self.config.save(self.plots_config_file_path)
            super().accept()
        except Exception as e:
            self.exception_handler(e)

    def reject(self):
        """ This function cancels the configuration"""
        try:
            super().reject()
        except Exception as e:
            self.exception_handler(e)

    def exception_handler(self, ex):
        traceback.print_exc()
        dialogs.error_dialog(str(ex), 'Error!')

