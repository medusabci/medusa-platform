# from gui.qt_widgets.notifications import NotificationStack
from PyQt5 import QtGui, QtWidgets, uic, QtCore
from PyQt5.QtWidgets import QWidget
# from gui import gui_utils
import os
import time
import threading
import matplotlib
from medusa.plots.topographic_plots import plot_topography, plot_head
import numpy as np
from medusa import meeg
import matplotlib.pyplot as plt
matplotlib.use('Qt5Agg')


class TopoplotOnline(QtWidgets.QMainWindow):

    def __init__(self,standard, ch_labels=None):
        QtWidgets.QMainWindow.__init__(self)
        # self.setupUi(self)

        # Initialize Variables
        self.standard = standard
        self.ch_labels = ch_labels
        self.channel_set = meeg.EEGChannelSet()
        self.channel_set.set_standard_montage(l_cha=self.ch_labels,
                                              standard=self.standard, )
        self.l_cha = self.channel_set.l_cha
        layout = self.layout()
        self.fig, self.axes = plot_head(self.channel_set,show=False)
        layout.addWidget(self.fig.canvas)

        T = threading.Thread(target=self.update_head)
        T.start()
        self.show()

    def update_head(self):
        while True:
            # time.sleep(1)
            handles = plot_topography(
                self.channel_set,
                np.random.random(len(self.ch_labels)),
                fig=self.fig,
                axes=None,
                show=False,
                show_colorbar=False,
                interp_points=350)
            self.fig.axes[0].remove()
            self.fig.canvas.draw()

if __name__ == '__main__':
    # self.show must be uncommented
    app = QtWidgets.QApplication([])
    mw = TopoplotOnline(standard='10-05',ch_labels=['F3','FZ','F4',
                                                    'C3','CZ','C4','P3','PZ','P4'])
    app.exec_()