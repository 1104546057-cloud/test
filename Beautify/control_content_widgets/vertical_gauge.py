# Beautify/control_content_widgets/vertical_gauge.py
from PyQt5.QtCore import Qt, QRectF, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QPen, QLinearGradient, QPainterPath
from PyQt5.QtWidgets import QWidget


class VerticalGaugeWidget(QWidget):
    """竖向条形仪表：玻璃底 + 槽 + 渐变填充"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._min = 0
        self._max = 100
        self._value = 0

        # 颜色（子类可覆盖）
        self.bg_top = QColor(255, 255, 255, 80)
        self.bg_bottom = QColor(255, 255, 255, 35)
        self.border = QColor(255, 255, 255, 120)

        self.track = QColor(255, 255, 255, 35)
        self.fill_top = QColor(0, 170, 255, 220)
        self.fill_bottom = QColor(0, 110, 255, 220)

        self.setMinimumSize(60, 160)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

    # ---------- API ----------
    def setRange(self, vmin: int, vmax: int):
        vmin = int(vmin)
        vmax = int(vmax)
        if vmax <= vmin:
            vmax = vmin + 1
        self._min, self._max = vmin, vmax
        self.setValue(self._value)

    def setValue(self, v: int):
        v = int(v)
        if v < self._min:
            v = self._min
        if v > self._max:
            v = self._max
        if v != self._value:
            self._value = v
            self.update()

    def value(self) -> int:
        return self._value

    # 让 Designer / 属性系统可写 value（可选）
    def _get_value(self):
        return self._value

    def _set_value(self, v):
        self.setValue(v)

    valueProp = pyqtProperty(int, fget=_get_value, fset=_set_value)

    # ---------- 绘制 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        r = QRectF(self.rect())
        p.fillRect(r, Qt.transparent)

        pad = 8
        base = r.adjusted(pad, pad, -pad, -pad)

        radius = min(base.width(), base.height()) * 0.10
        base_path = QPainterPath()
        base_path.addRoundedRect(base, radius, radius)

        bg = QLinearGradient(base.topLeft(), base.bottomLeft())
        bg.setColorAt(0.0, self.bg_top)
        bg.setColorAt(1.0, self.bg_bottom)
        p.fillPath(base_path, bg)

        p.setPen(QPen(self.border, 1))
        p.drawPath(base_path)

        inner = base.adjusted(10, 12, -10, -12)
        track_radius = min(inner.width(), inner.height()) * 0.18

        track_path = QPainterPath()
        track_path.addRoundedRect(inner, track_radius, track_radius)
        p.fillPath(track_path, self.track)

        span = max(1, self._max - self._min)
        t = (self._value - self._min) / span
        if t < 0:
            t = 0.0
        if t > 1:
            t = 1.0

        fill_h = inner.height() * t
        if fill_h > 0.5:
            fill_rect = QRectF(inner.left(), inner.bottom() - fill_h, inner.width(), fill_h)

            fill_path = QPainterPath()
            fill_path.addRoundedRect(fill_rect, track_radius, track_radius)

            fg = QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
            fg.setColorAt(0.0, self.fill_top)
            fg.setColorAt(1.0, self.fill_bottom)
            p.fillPath(fill_path, fg)

            # 顶部高光
            hi_y = fill_rect.top() + 2
            p.setPen(QPen(QColor(255, 255, 255, 140), 2))
            p.drawLine(int(fill_rect.left() + 6), int(hi_y),
                       int(fill_rect.right() - 6), int(hi_y))


class SpeedGaugeWidget(VerticalGaugeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.fill_top = QColor(0, 170, 255, 220)
        self.fill_bottom = QColor(0, 110, 255, 220)


class BatteryGaugeWidget(VerticalGaugeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 100)
        self.fill_top = QColor(70, 220, 120, 230)
        self.fill_bottom = QColor(30, 170, 90, 230)

if __name__ == "__main__":
    import sys
    import random
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel

    app = QApplication(sys.argv)

    w = QWidget()
    w.setWindowTitle("VerticalGaugeWidget Test")
    w.resize(360, 280)

    root = QHBoxLayout(w)
    root.setContentsMargins(20, 20, 20, 20)
    root.setSpacing(30)

    # 左：速度
    left = QVBoxLayout()
    left.setSpacing(8)
    speed = SpeedGaugeWidget()
    speed.setMinimumSize(90, 240)
    left.addWidget(speed, alignment=Qt.AlignHCenter)
    left.addWidget(QLabel("速度"), alignment=Qt.AlignHCenter)

    # 右：电量
    right = QVBoxLayout()
    right.setSpacing(8)
    batt = BatteryGaugeWidget()
    batt.setMinimumSize(90, 240)
    right.addWidget(batt, alignment=Qt.AlignHCenter)
    right.addWidget(QLabel("电量"), alignment=Qt.AlignHCenter)

    root.addLayout(left)
    root.addLayout(right)

    # 定时随机更新
    t = QTimer()
    t.timeout.connect(lambda: (
        speed.setValue(random.randint(0, 100)),
        batt.setValue(random.randint(0, 100)),
    ))
    t.start(200)

    w.show()
    sys.exit(app.exec_())
