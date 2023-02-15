# from gui.qt_widgets.notifications import NotificationStack
from PyQt5 import QtWidgets, QtCore
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
import numpy as np
import time


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self):
        QtWidgets.QMainWindow.__init__(self)

        # Initialize Variables
        fig = Figure()
        fig.add_subplot(111)
        self.widget = FigureCanvasQTAgg(fig)

        self.setCentralWidget(self.widget)

        # Timer
        th = Thread()
        th.update_signal.connect(self.update_plot)
        th.start()

        self.show()

    def update_plot(self):
        self.widget.figure.axes[0].cla()
        self.widget.figure.axes[0].plot(np.arange(5),
                                        np.random.random(5))
        self.widget.draw()


class Thread(QtCore.QThread):

    update_signal = QtCore.pyqtSignal()

    def __int__(self):
        super().__init__()

    def run(self):

        while True:
            self.update_signal.emit()
            time.sleep(0.1)


if __name__ == '__main__':
    # self.show must be uncommented
    app = QtWidgets.QApplication([])
    mw = MainWindow()
    app.exec_()