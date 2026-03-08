from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QFrame, QGraphicsDropShadowEffect


class GlassFrame(QFrame):
    def __init__(self, parent=None, radius=18):
        super().__init__(parent)
        self._radius = radius
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.setStyleSheet(
            f"""
            QFrame {{
                background: rgba(255, 255, 255, 180);
                border: 1px solid rgba(255, 255, 255, 140);
                border-radius: {radius}px;
            }}
            """
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 45))
        self.setGraphicsEffect(shadow)
