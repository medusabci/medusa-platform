from gui.main_window import GuiMainClass
from PySide6.QtWidgets import QApplication
import sys


if __name__ == '__main__':
    # Init QT application
    application = QApplication(sys.argv)
    main_window = GuiMainClass()
    sys.exit(application.exec())

