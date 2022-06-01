"""Created on Tuesday February 01 2022
@author: Diego Marcos-Martínez"""
import copy

from gui.qt_widgets.notifications import NotificationStack
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtWidgets import QWidget
from gui import gui_utils
import os
import time
import threading
import matplotlib
from medusa.components import SerializableComponent
from medusa.plots.topographic_plots import plot_topography
import numpy as np
from medusa import meeg
import matplotlib.pyplot as plt
matplotlib.use('Qt5Agg')


# Load the .ui files
ui_main_file = uic.loadUiType(os.path.dirname(__file__) + "/channel_selection.ui")[0]


class ChannelSelectionWidget(QtWidgets.QDialog, ui_main_file):
    """This class allows you to control the GUI of the EEG channel selection widget."""
    close_signal = QtCore.pyqtSignal(object)

    def __init__(self, standard='10-20', ch_labels=None):
        QtWidgets.QDialog.__init__(self)
        self.setupUi(self)
        self.TAG = '[widget/EEG Channel Selection]'

        # Initialize control
        self.finished = False

        # Initialize the gui application
        theme_colors = None
        self.theme_colors = gui_utils.get_theme_colors('dark') if \
            theme_colors is None else theme_colors
        self.stl = gui_utils.set_css_and_theme(self, self.theme_colors)
        self.setWindowIcon(QtGui.QIcon('gui\images/medusa_icon.png'))
        self.setWindowTitle('MEDUSA EEG Channel Selection')
        self.used_btn.setStyleSheet('QPushButton {background-color: #76ba1b; color: #000000;}')
        self.ground_btn.setStyleSheet('QPushButton {background-color: #fff44f; color: #000000;}')
        self.reference_btn.setStyleSheet('QPushButton {background-color: #00bdfe; color: #000000;}')
        self.notifications = NotificationStack(parent=self, timer_ms=500)
        self.changes_made = False

        # Initialize the plot
        self.interactive_selection = EEGChannelSelectionPlot(standard=standard, ch_labels=ch_labels)
        self.plotLayout.addWidget(self.interactive_selection.fig.canvas)

        # Button connections
        self.used_btn.clicked.connect(self.activate_mode_used)
        self.ground_btn.clicked.connect(self.activate_mode_ground)
        self.reference_btn.clicked.connect(self.activate_mode_reference)
        self.selectall_btn.clicked.connect(self.activate_select_all)
        self.unselectall_btn.clicked.connect(self.activate_unselect_all)
        self.save_btn.clicked.connect(self.save)
        self.load_btn.clicked.connect(self.load)
        self.done_btn.clicked.connect(self.done)

        # Set Channel Labels
        self.working_threads = list()
        Th1 = threading.Thread(target=self.set_labels_as_text)
        Th1.start()
        self.working_threads.append(Th1)

        # Uncomment to debug
        self.setModal(True)
        # self.show()

    def activate_mode_used(self):
        self.interactive_selection.selection_mode = 'Used'

    def activate_mode_ground(self):
        self.interactive_selection.selection_mode = 'Ground'

    def activate_mode_reference(self):
        self.interactive_selection.selection_mode = 'Reference'

    def activate_select_all(self):
        self.interactive_selection.select_all()
        self.changes_made = True

    def activate_unselect_all(self):
        self.interactive_selection.unselect_all()
        self.changes_made = True

    def set_labels_as_text(self):
        """ Reads continuously the channels selected and prints it in Line text edit object"""
        while not self.finished:
            time.sleep(0.1)
            # Set Ground Label
            ground_idx = np.where(self.interactive_selection.channels_selected['Ground'])[0]
            if len(ground_idx) != 0:
                self.groundText.setText(self.interactive_selection.l_cha[int(ground_idx)])
                self.changes_made = True
            else:
                self.groundText.setText('')
            # Set Reference Label
            reference_idx = np.where(self.interactive_selection.channels_selected['Reference'])[0]
            if len(reference_idx) != 0:
                self.referenceText.setText(self.interactive_selection.l_cha[int(reference_idx)])
                self.changes_made = True
            else:
                self.referenceText.setText('')
            # Set Used Channels Labels
            self.usedText.setReadOnly(True)
            used_idx = np.where(self.interactive_selection.channels_selected['Used'])[0]
            if len(used_idx) != 0:
                labels = list(self.interactive_selection.channels_selected['Labels'][self.interactive_selection.
                              channels_selected['Used']])
                # labels = [self.interactive_selection.l_cha[idx] for idx in used_idx]
                self.usedText.setText(",".join(labels))
                self.changes_made = True
            else:
                self.usedText.setText("")

    # ------------------- BASIC BUTTONS --------------------------------------

    def save(self):
        """ Opens a dialog to save the configuration as a file. """
        fdialog = QtWidgets.QFileDialog()
        fname = fdialog.getSaveFileName(
            fdialog, 'Save Channel Selection', '../../channelset/', 'JSON (*.json)')
        if fname[0]:
            self.interactive_selection.save(path=fname[0])
            self.interactive_selection.get_channels_selection_from_gui()
            self.notifications.new_notification('Channels selection saved as %s' %
                                                fname[0].split('/')[-1])

    def load(self):
        """ Opens a dialog to load a configuration file. """
        fdialog = QtWidgets.QFileDialog()
        fname = fdialog.getOpenFileName(
            fdialog, 'Load Channel Selection', '../../channelset/', 'JSON (*.json)')
        if fname[0]:
            self.plotLayout.itemAt(0).widget().deleteLater()
            # self.plotLayout.removeWidget(self.interactive_selection.fig.canvas)

            loaded_channel_selection = self.interactive_selection.load(fname[0])
            self.interactive_selection = loaded_channel_selection
            self.plotLayout.addWidget(self.interactive_selection.fig.canvas)
            self.interactive_selection.fig.canvas.draw()
            self.notifications.new_notification('Loaded channels selection: %s' %
                                                fname[0].split('/')[-1])

    def done(self):
        """ Shows a confirmation dialog if non-saved changes has been made. """
        self.interactive_selection.get_channels_selection_from_gui()
        self.changes_made = False
        self.close()

    @staticmethod
    def close_dialog():
        """ Shows a confirmation dialog that asks the user if he/she wants to
        close the configuration window.

        Returns
        -------
        output value: QtWidgets.QMessageBox.No or QtWidgets.QMessageBox.Yes
            If the user do not want to close the window, and
            QtWidgets.QMessageBox.Yes otherwise.
        """
        msg = QtWidgets.QMessageBox()
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setWindowTitle("EEG Channel Selection")
        msg.setWindowIcon(QtGui.QIcon(os.path.join(
            os.path.dirname(__file__), '../../gui/images/medusa_icon.png')))
        msg.setText("Do you want to leave this window?")
        msg.setInformativeText("Non-saved changes will be discarded.")
        msg.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        return msg.exec_()

    def closeEvent(self, event):
        """ Overrides the closeEvent in order to show the confirmation dialog.
        """
        if self.changes_made:
            retval = self.close_dialog()
            if retval == QtWidgets.QMessageBox.Yes:
                self.close_signal.emit(None)
                event.accept()
            else:
                event.ignore()
        else:
            self.interactive_selection.get_channels_selection_from_gui()
            self.close_signal.emit(None)
            event.accept()



class EEGChannelSelectionPlot(SerializableComponent):
    """This class controls the interactive topographic representation.
        After selection, a dictionary with an EEGChannelSet consisting of
        the selected channels, the selected reference and the selected
        ground is returned."""
    def __init__(self, standard, ch_labels=None, channels_selected=None):
        # Parameters
        self.standard = standard
        self.ch_labels = ch_labels

        # Initialize Variables
        self.channel_set = meeg.EEGChannelSet()
        self.channel_set.set_standard_montage(l_cha=self.ch_labels, standard=self.standard, )
        self.l_cha = self.channel_set.l_cha
        self.channels_selected = channels_selected
        self.channel_location = None
        self.fig = None
        self.axes = None
        self.tolerance_radius = None
        self.selection_mode = 'Used'
        self.color = {
            "Used": '#76ba1b',
            'Ground': '#fff44f',
            'Reference': '#00bdfe'
        }
        self.final_channel_selection = {
            'Used': copy.copy(self.channel_set),
            'Ground': None,
            'Reference': None
        }
        # Plot Channel Plot
        self.set_tolerance_radius()
        self.fig, self.axes = plot_topography(self.channel_set, plot_clabels=True, plot_contour_ch=True,
                                              show=False, chcontour_radius=self.tolerance_radius,
                                              plot_skin_in_color=True,
                                              plot_channels=True)

        # Set channel coordinates
        self.set_channel_location()

        if self.channels_selected is None:
            self.set_channel_selection_dict()
        else:
            self.load_channel_selection_settings()

        # Add interactive functionality to the figure
        self.fig.canvas.mpl_connect('button_press_event', self.onclick)

        # Uncomment to debug
        # self.fig.show()

    def set_channel_location(self):
        """For an easy treat of channel coordinates"""
        self.channel_location = dict()

        self.channel_location['radius'] = [c['r'] for c in self.channel_set.channels]
        self.channel_location['theta'] = [c['theta'] for c in self.channel_set.channels]

        self.channel_location['ch_x'] = np.array(self.channel_location['radius']) * np.cos(
            self.channel_location['theta'])
        self.channel_location['ch_y'] = np.array(self.channel_location['radius']) * np.sin(
            self.channel_location['theta'])

    def set_channel_selection_dict(self):
        """Initialize the state dict"""
        self.channels_selected = dict()
        self.channels_selected['Labels'] = np.asarray(self.l_cha)
        self.channels_selected['Selected'] = np.zeros(len(self.l_cha), dtype=bool)
        self.channels_selected['Used'] = np.zeros(len(self.l_cha), dtype=bool)
        self.channels_selected['Ground'] = np.zeros(len(self.l_cha), dtype=bool)
        self.channels_selected['Reference'] = np.zeros(len(self.l_cha), dtype=bool)
        self.channels_selected['Plot line'] = np.full(len(self.l_cha), None)

    def set_tolerance_radius(self):
        """Calculates the radius of the click area of each channel."""
        dist_matrix = self.channel_set.compute_dist_matrix()
        dist_matrix.sort()
        percentage = self.set_tolerance_parameter()
        self.tolerance_radius = percentage * dist_matrix[:, 1].min()

    def set_tolerance_parameter(self):
        """ Computes the percentage of the minimum distance between channels
            depending the montage standard with a linear function"""
        global M
        if self.standard == '10-05':
            M = 345
        elif self.standard == '10-10':
            M = 71
        elif self.standard == '10-20':
            M = 21
        return len(self.l_cha) * (0.25 / (M - 2)) + 0.25 * ((M - 4) / (M - 2))

    def onclick(self, event):
        """ Handles the mouse click event"""
        xdata = event.xdata
        ydata = event.ydata
        distance = self.check_channel_clicked((xdata, ydata))
        if distance is None:
            return
        else:
            if np.sum(distance) >= 1:
                idx = int(np.where(distance)[0])
                self.select_action(idx)
            else:
                return

    def check_channel_clicked(self, coord_click):
        """ Checks if mouse was clicked inside the channel area"""
        if (coord_click[0] is None) or (coord_click[1] is None):
            return
        r = np.sqrt(coord_click[0] ** 2 + coord_click[1] ** 2) * \
            np.ones((len(self.channel_set.channels)))
        theta = np.arctan2(coord_click[1], coord_click[0]) * np.ones((len(self.channel_set.channels)))
        distance = (r ** 2 + np.power(self.channel_location['radius'], 2) -
                    2 * r * self.channel_location['radius'] *
                    np.cos(theta - self.channel_location['theta'])) < self.tolerance_radius ** 2
        return distance

    def channel_type_selected(self):
        """Avoids incompatibilities between different selection modes"""
        if self.selection_mode == 'Reference':
            idx_reference = np.where(self.channels_selected['Reference'])[0]
            if len(idx_reference) != 0:
                self.channels_selected['Selected'][int(idx_reference)] = False
                self.channels_selected['Plot line'][int(idx_reference)].remove()
                self.channels_selected['Reference'][int(idx_reference)] = False
                plt.setp(self.axes.texts[int(idx_reference)], fontweight='normal', color='w')
        elif self.selection_mode == 'Ground':
            idx_ground = np.where(self.channels_selected['Ground'])[0]
            if len(idx_ground) != 0:
                self.channels_selected['Selected'][int(idx_ground)] = False
                self.channels_selected['Plot line'][int(idx_ground)].remove()
                self.channels_selected['Ground'][int(idx_ground)] = False
                plt.setp(self.axes.texts[int(idx_ground)], fontweight='normal', color='w')

    def select_action(self, idx):
        """Changes the 'Selected' state of the channel and its representation"""

        self.channels_selected["Selected"][idx] = not self.channels_selected["Selected"][idx]

        if self.channels_selected['Selected'][idx]:
            # Check if reference or Ground are already selected
            self.channel_type_selected()
            # Draw selection marker
            self.channels_selected['Plot line'][idx] = plt.Circle(
                (self.channel_location['ch_x'][idx], self.channel_location['ch_y'][idx]),
                radius=(0.3 * self.tolerance_radius),
                facecolor=self.color[self.selection_mode],
                edgecolor='k', alpha=1, zorder=11)
            # Highlight the selected label
            plt.setp(self.axes.texts[idx], fontweight='extra bold', color=self.color[self.selection_mode])
            self.axes.add_patch(self.channels_selected['Plot line'][idx])
            self.channels_selected[self.selection_mode][idx] = True
        else:
            self.channels_selected['Plot line'][idx].remove()
            plt.setp(self.axes.texts[idx], fontweight='normal', color='w')
            self.channels_selected['Used'][idx] = False
            self.channels_selected['Ground'][idx] = False
            self.channels_selected['Reference'][idx] = False
        self.fig.canvas.draw()
        return True

    def select_all(self):
        """Removes the already selected channels and then select them all"""
        plots = list(np.where(self.channels_selected['Plot line'])[0])
        for marker_idx in plots:
            self.channels_selected['Plot line'][int(marker_idx)].remove()
        self.set_channel_selection_dict()
        self.selection_mode = 'Used'
        self.channels_selected['Selected'] = np.ones(len(self.l_cha), dtype=bool)
        self.channels_selected['Used'] = np.ones(len(self.l_cha), dtype=bool)
        for idx in range(len(self.l_cha)):
            self.channels_selected['Plot line'][idx] = plt.Circle(
                (self.channel_location['ch_x'][idx], self.channel_location['ch_y'][idx]),
                radius=(0.3 * self.tolerance_radius),
                facecolor=self.color[self.selection_mode],
                edgecolor='k', alpha=1, zorder=11)
            plt.setp(self.axes.texts[idx], fontweight='extra bold', color=self.color[self.selection_mode])
            self.axes.add_patch(self.channels_selected['Plot line'][idx])
        self.fig.canvas.draw()

    def unselect_all(self):
        plots = list(np.where(self.channels_selected['Plot line'])[0])
        for marker_idx in plots:
            self.channels_selected['Plot line'][int(marker_idx)].remove()
        plt.setp(self.axes.texts, fontweight='normal', color='w')
        self.set_channel_selection_dict()
        self.fig.canvas.draw()

    def load_channel_selection_settings(self):
        """Initialize the selection settings and make the necessary plots"""
        for key in self.channels_selected.keys():
            self.channels_selected[key] = np.asarray(self.channels_selected[key])
        self.channels_selected['Plot line'] = np.full(len(self.l_cha), None)
        used_channels_idx = np.where(self.channels_selected['Used'])[0]
        ground_channel_idx = np.where(self.channels_selected['Ground'])[0]
        reference_channel_idx = np.where(self.channels_selected['Reference'])[0]
        if len(used_channels_idx) != 0:
            for idx in used_channels_idx:
                self.channels_selected['Selected'][idx] = False
                self.select_action(idx)
        if len(ground_channel_idx) != 0:
            self.channels_selected['Selected'][int(ground_channel_idx)] = False
            self.channels_selected['Ground'][int(ground_channel_idx)] = False
            self.selection_mode = 'Ground'
            self.select_action(int(ground_channel_idx))
        if len(reference_channel_idx) != 0:
            self.channels_selected['Selected'][int(reference_channel_idx)] = False
            self.channels_selected['Reference'][int(reference_channel_idx)] = False
            self.selection_mode = 'Reference'
            self.select_action(int(reference_channel_idx))

    def get_channels_selection_from_gui(self):
        """Updates the final_channel_selection dict. It makes possible to get from widget
           the selected channels as a EEGChannelSet object"""
        self.final_channel_selection = dict()
        saved_channel_set = meeg.EEGChannelSet()
        saved_channel_set.set_standard_montage(l_cha=list(self.channels_selected['Labels']
                                                          [self.channels_selected['Used']]),
                                               standard=self.standard)
        self.final_channel_selection['Used'] = saved_channel_set
        self.final_channel_selection['Ground'] = list(
            self.channels_selected['Labels'][self.channels_selected['Ground']])
        self.final_channel_selection['Reference'] = list(
            self.channels_selected['Labels'][self.channels_selected['Reference']])

    def to_serializable_obj(self):
        channels_selected = {k: v.tolist() for k, v in self.channels_selected.items()}
        del channels_selected['Plot line']
        sett_dict = {'standard': self.standard,
                     'ch_labels': self.ch_labels,
                     'channels_selected': channels_selected}
        return sett_dict

    @classmethod
    def from_serializable_obj(cls, dict_data):
        return cls(**dict_data)


if __name__ == '__main__':
    # self.show must be uncommented
    app = QtWidgets.QApplication([])
    mw = ChannelSelectionWidget(standard='10-05')
    app.exec_()
