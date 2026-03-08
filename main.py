# main.py
import sys
from PyQt5.QtCore import QCoreApplication, Qt
from PyQt5.QtWidgets import QApplication
from app.login import LoginPage
from app.MainInterface import MainInterface

def main() -> int:
    # Required for QtWebEngine widgets (set before QApplication is created)
    QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    login = LoginPage()
    main_win = MainInterface()

    def open_main():
        login.close()
        main_win.show()

    login.login_success.connect(open_main)
    login.show()
    return app.exec_()

if __name__ == "__main__":
    raise SystemExit(main())
