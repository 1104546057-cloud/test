from PyQt5 import QtWidgets
from PyQt5.QtCore import QTimer, QRectF, QSize
from PyQt5.QtGui import QColor, QPainterPath, QRegion, QTransform, QIcon
from qfluentwidgets import FluentIcon as FIF, ThemeColor
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QEvent
import random

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))
from UI.generated.content import Ui_Form


class ContentPage(QtWidgets.QWidget, Ui_Form):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        self.apply_glass_frames()
        self.apply_dpad_style()
        self.apply_dpad_icons()
        self.setup_window_controls()
        self.apply_section_labels()
        self.apply_topbar_style()
        self.apply_estop_style()
        self.setup_gauge_labels()

        self._t = QTimer(self)
        self._t.timeout.connect(self._mock_update)
        self._t.start(800)

    def apply_glass_frames(self) -> None:
        for name in ["frameVideo", "frameMap", "frameDriveInfo", "frameEStop"]:
            frame = getattr(self, name, None)
            if not frame:
                continue
            # Apply glass style directly to keep child widgets intact.
            frame.setStyleSheet(
                "QFrame {"
                "background: rgba(255, 255, 255, 180);"
                "border: 1px solid rgba(255, 255, 255, 140);"
                "border-radius: 18px;"
                "}"
            )
            shadow = QGraphicsDropShadowEffect(frame)
            shadow.setBlurRadius(30)
            shadow.setOffset(0, 10)
            shadow.setColor(QColor(0, 0, 0, 45))
            frame.setGraphicsEffect(shadow)

    def apply_dpad_style(self) -> None:
        qss = """
        QPushButton {
            border-radius: 20px;
            border: 1px solid rgba(255, 255, 255, 170);
            background-color: rgba(255, 255, 255, 120);
            padding: 0px;
        }
        QPushButton:hover {
            background-color: rgba(255, 255, 255, 160);
            border: 1px solid rgba(255, 255, 255, 220);
        }
        QPushButton:pressed {
            background-color: rgba(255, 255, 255, 190);
            padding-top: 2px;
        }
        """

        buttons = [
            self.btnUpLeft, self.btnUp, self.btnUpRight,
            self.btnStop,
            self.btnDownLeft, self.btnDown, self.btnDownRight,
        ]
        for btn in buttons:
            if not btn:
                continue
            btn.setStyleSheet(qss)
            shadow = QGraphicsDropShadowEffect(btn)
            shadow.setBlurRadius(25)
            shadow.setOffset(0, 8)
            shadow.setColor(QColor(0, 0, 0, 45))
            btn.setGraphicsEffect(shadow)

    def apply_dpad_icons(self) -> None:
        accent = ThemeColor.PRIMARY.color()

        def rotated_icon(base_icon: QIcon, size: int, angle: int) -> QIcon:
            pix = base_icon.pixmap(size, size)
            rot = pix.transformed(QTransform().rotate(angle))
            return QIcon(rot)

        icon_size = 18
        up_icon = FIF.UP.icon(accent)
        down_icon = FIF.DOWN.icon(accent)
        left_icon = FIF.LEFT_ARROW.icon(accent)
        right_icon = FIF.RIGHT_ARROW.icon(accent)

        mapping = {
            "btnUp": up_icon,
            "btnDown": down_icon,
            "btnUpLeft": rotated_icon(up_icon, icon_size, -45),
            "btnUpRight": rotated_icon(up_icon, icon_size, 45),
            "btnDownLeft": rotated_icon(down_icon, icon_size, 45),
            "btnDownRight": rotated_icon(down_icon, icon_size, -45),
            "btnStop": FIF.CLOSE.icon(accent),
        }

        for name, icon in mapping.items():
            btn = getattr(self, name, None)
            if not btn:
                continue
            btn.setText("")
            btn.setIcon(icon)
            btn.setIconSize(QSize(icon_size, icon_size))

    def apply_section_labels(self) -> None:
        label_qss = """
        QLabel {
            color: #5f6b7a;
            font-size: 12px;
            font-weight: 600;
            padding: 6px 10px;
        }
        """
        for name in ["label", "label_2", "labelDriveInfo", "labelEStop"]:
            lbl = getattr(self, name, None)
            if lbl:
                lbl.setStyleSheet(label_qss)

    def apply_estop_style(self) -> None:
        if hasattr(self, "frameEStop"):
            self.frameEStop.setStyleSheet(
                "QFrame {"
                "background: rgba(255, 235, 235, 220);"
                "border: 1px solid rgba(255, 140, 140, 140);"
                "border-radius: 16px;"
                "}"
            )
        if hasattr(self, "labelEStop"):
            self.labelEStop.setStyleSheet(
                "QLabel {"
                "color: #d14c4c;"
                "font-size: 12px;"
                "font-weight: 600;"
                "}"
            )
    def setup_window_controls(self) -> None:
        # Remove native title bar; use custom buttons instead.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(True)

        self._ensure_max_button()
        self.apply_background_style()
        self.apply_topbar_icons()

        if hasattr(self, "btnMin"):
            self.btnMin.clicked.connect(self.showMinimized)
        if hasattr(self, "btnMax"):
            self.btnMax.clicked.connect(self._toggle_maximize)
        if hasattr(self, "btnClose"):
            self.btnClose.clicked.connect(self.close)
        # Back button: close this page
        if hasattr(self, "btnBack"):
            self.btnBack.clicked.connect(self.close)

        # Allow dragging by the top bar area
        if hasattr(self, "frameTopBar"):
            self.frameTopBar.installEventFilter(self)

    def apply_topbar_icons(self) -> None:
        accent = ThemeColor.PRIMARY.color()
        if hasattr(self, "btnBack"):
            self.btnBack.setIcon(FIF.LEFT_ARROW.icon(accent))
            self.btnBack.setIconSize(QSize(18, 18))
        if hasattr(self, "btnMin"):
            self.btnMin.setIcon(FIF.MINIMIZE.icon(accent))
            self.btnMin.setIconSize(QSize(18, 18))
        if hasattr(self, "btnMax"):
            self.btnMax.setIcon(FIF.FULL_SCREEN.icon(accent))
            self.btnMax.setIconSize(QSize(18, 18))
        if hasattr(self, "btnClose"):
            self.btnClose.setIcon(FIF.CLOSE.icon(accent))
            self.btnClose.setIconSize(QSize(18, 18))

    def _ensure_max_button(self) -> None:
        if hasattr(self, "btnMax"):
            return
        top_layout = getattr(self, "topBarLayout", None)
        if top_layout is None:
            return
        btn_max = QtWidgets.QPushButton(self.frameTopBar)
        btn_max.setObjectName("btnMax")
        btn_max.setMinimumSize(QSize(36, 36))
        btn_max.setMaximumSize(QSize(36, 36))
        btn_max.setText("")
        self.btnMax = btn_max

        btn_close = getattr(self, "btnClose", None)
        if btn_close:
            idx = top_layout.indexOf(btn_close)
            if idx >= 0:
                top_layout.insertWidget(idx, btn_max)
            else:
                top_layout.addWidget(btn_max)
        else:
            top_layout.addWidget(btn_max)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def apply_background_style(self) -> None:
        qss = """
        QWidget#Form {
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 #f3f8ff,
                stop:0.5 #f6f7fb,
                stop:1 #f1f1f1
            );
            border: 1px solid rgba(0, 0, 0, 18);
            border-radius: 16px;
        }
        """
        self.setStyleSheet(self.styleSheet() + "\n" + qss)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        radius = 16
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))
        self._update_video_map_aspect()

    def _update_video_map_aspect(self) -> None:
        # Keep video/map panels at 4:3 (width:height).
        for name in ["frameVideo", "frameMap"]:
            frame = getattr(self, name, None)
            if not frame:
                continue
            w = frame.width()
            if w <= 0:
                continue
            h = int(w * 3 / 4)
            frame.setMinimumHeight(h)
            frame.setMaximumHeight(h)

    def eventFilter(self, obj, event):
        if hasattr(self, "frameTopBar") and obj is self.frameTopBar:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
                return True
            if event.type() == QEvent.MouseMove and event.buttons() & Qt.LeftButton:
                if hasattr(self, "_drag_pos"):
                    self.move(event.globalPos() - self._drag_pos)
                return True
        return super().eventFilter(obj, event)


    def apply_topbar_style(self) -> None:
        accent = ThemeColor.PRIMARY.color()
        r, g, b, _ = accent.getRgb()
        qss = """
        QPushButton {
            border-radius: 8px;
            border: 1px solid rgba(%d, %d, %d, 90);
            background-color: rgba(255, 255, 255, 180);
            padding: 0px;
        }
        QPushButton:hover {
            border: 1px solid rgba(%d, %d, %d, 160);
            background-color: rgba(%d, %d, %d, 28);
        }
        QPushButton:pressed {
            background-color: rgba(%d, %d, %d, 45);
            padding-top: 1px;
        }
        """ % (r, g, b, r, g, b, r, g, b, r, g, b)

        for btn in [getattr(self, "btnBack", None), getattr(self, "btnMin", None), getattr(self, "btnClose", None)]:
            if btn:
                btn.setStyleSheet(qss)

    def setup_gauge_labels(self) -> None:
        # Speed gauge: value label + left scale + unit
        if hasattr(self, "verticalLayout_2") and hasattr(self, "speedBarPlaceholder"):
            self.speedValueLabel = QtWidgets.QLabel(self.frameSpeedBar)
            self.speedValueLabel.setAlignment(Qt.AlignCenter)
            self.speedValueLabel.setStyleSheet("QLabel { color: #3a4a5e; font-size: 13px; font-weight: 600; }")

            self.speedUnitLabel = QtWidgets.QLabel(self.frameSpeedBar)
            self.speedUnitLabel.setAlignment(Qt.AlignCenter)
            self.speedUnitLabel.setText("cm/s")
            self.speedUnitLabel.setStyleSheet("QLabel { color: #7a8796; font-size: 11px; }")

            # Insert value above and unit below the existing bar
            self.verticalLayout_2.insertWidget(1, self.speedValueLabel)
            self.verticalLayout_2.insertWidget(3, self.speedUnitLabel)

        # Battery gauge: value label
        if hasattr(self, "verticalLayout_3") and hasattr(self, "batteryBarPlaceholder"):
            self.batteryValueLabel = QtWidgets.QLabel(self.frameBatteryBar)
            self.batteryValueLabel.setAlignment(Qt.AlignCenter)
            self.batteryValueLabel.setStyleSheet("QLabel { color: #3a4a5e; font-size: 13px; font-weight: 600; }")

            # Insert value above the existing bar
            self.verticalLayout_3.insertWidget(1, self.batteryValueLabel)

    def _mock_update(self):
        speed = random.randint(0, 200)
        battery = random.randint(0, 100)

        if hasattr(self, "speedBarPlaceholder"):
            self.speedBarPlaceholder.setValue(speed)
        if hasattr(self, "batteryBarPlaceholder"):
            self.batteryBarPlaceholder.setValue(battery)

        if hasattr(self, "speedValueLabel"):
            self.speedValueLabel.setText(f"{speed}")
        if hasattr(self, "batteryValueLabel"):
            self.batteryValueLabel.setText(f"{battery}%")
