from PyQt5 import uic
from PyQt5.QtCore import Qt, QPoint, QEvent
from PyQt5.QtWidgets import QWidget, QPushButton

from UI.pages.content_page import ContentPage


class ShellWindow(QWidget):
    def __init__(self, ui_path: str = "UI/forms/Shell.ui"):
        super().__init__()
        uic.loadUi(ui_path, self)

        # 1) 无边框窗口
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, False)  # 先不搞透明，稳定优先

        # 2) 绑定按钮功能
        self.btnClose.clicked.connect(self.close)
        self.btnMin.clicked.connect(self.showMinimized)
        self.btnBack.clicked.connect(self.on_back)

        # 3) 顶栏拖动
        self._dragging = False
        self._drag_pos = QPoint()

        # 用事件过滤器接管 titleBar 的鼠标事件
        self.titleBar.installEventFilter(self)

        # 4) Mount content page into content host
        if hasattr(self, "contentHost"):
            content = ContentPage(self)
            layout = self.contentHost.layout()
            if layout:
                layout.addWidget(content)

    def on_back(self):
        print("Back clicked")  # 先占位，后面再接页面切换

    def _mouse_on_button(self, pos_in_titlebar) -> bool:
        """判断鼠标点下位置是否落在 titleBar 内的某个 QPushButton 上"""
        w = self.titleBar.childAt(pos_in_titlebar)
        while w is not None:
            if isinstance(w, QPushButton):
                return True
            w = w.parentWidget()
        return False

    def eventFilter(self, obj, event):
        if obj is self.titleBar:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                # 点在按钮上：不进入拖动
                if self._mouse_on_button(event.pos()):
                    return False

                self._dragging = True
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                return True

            if event.type() == QEvent.MouseMove and self._dragging:
                self.move(event.globalPos() - self._drag_pos)
                return True

            if event.type() == QEvent.MouseButtonRelease:
                self._dragging = False
                return True

        return super().eventFilter(obj, event)

