from gui.main_window import GuiMainClass
from PyQt5.QtWidgets import QApplication
import sys, json, os


if __name__ == '__main__':
    # Load session
    # session_file_path = 'session.json'
    # if os.path.isfile(session_file_path):
    #     # Load session
    #     s = session.Session.load(session_file_path)
    # else:
    #     # First time
    #     pass
    # Init QT application
    application = QApplication(sys.argv)
    main_window = GuiMainClass()
    sys.exit(application.exec_())
