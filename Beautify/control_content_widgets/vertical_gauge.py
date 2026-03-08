from PyQt5.QtCore import Qt, QRectF, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QPen, QLinearGradient, QPainterPath
from PyQt5.QtWidgets import QWidget


class VerticalGaugeWidget(QWidget):
    """Vertical bar gauge with a glass-like background and gradient fill."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._min = 0
        self._max = 100
        self._value = 0

        self.bg_top = QColor(255, 255, 255, 80)
        self.bg_bottom = QColor(255, 255, 255, 35)
        self.border = QColor(255, 255, 255, 120)

        self.track = QColor(255, 255, 255, 35)
        self.fill_top = QColor(0, 170, 255, 220)
        self.fill_bottom = QColor(0, 110, 255, 220)

        self.setMinimumSize(60, 160)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)

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

    def _get_value(self):
        return self._value

    def _set_value(self, v):
        self.setValue(v)

    valueProp = pyqtProperty(int, fget=_get_value, fset=_set_value)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        painter.fillRect(rect, Qt.transparent)

        pad = 8
        base = rect.adjusted(pad, pad, -pad, -pad)
        radius = min(base.width(), base.height()) * 0.10

        base_path = QPainterPath()
        base_path.addRoundedRect(base, radius, radius)

        bg = QLinearGradient(base.topLeft(), base.bottomLeft())
        bg.setColorAt(0.0, self.bg_top)
        bg.setColorAt(1.0, self.bg_bottom)
        painter.fillPath(base_path, bg)

        painter.setPen(QPen(self.border, 1))
        painter.drawPath(base_path)

        inner = base.adjusted(10, 12, -10, -12)
        track_radius = min(inner.width(), inner.height()) * 0.18

        track_path = QPainterPath()
        track_path.addRoundedRect(inner, track_radius, track_radius)
        painter.fillPath(track_path, self.track)

        span = max(1, self._max - self._min)
        ratio = (self._value - self._min) / span
        ratio = max(0.0, min(1.0, ratio))

        fill_height = inner.height() * ratio
        if fill_height > 0.5:
            fill_rect = QRectF(inner.left(), inner.bottom() - fill_height, inner.width(), fill_height)
            fill_path = QPainterPath()
            fill_path.addRoundedRect(fill_rect, track_radius, track_radius)

            fg = QLinearGradient(fill_rect.topLeft(), fill_rect.bottomLeft())
            fg.setColorAt(0.0, self.fill_top)
            fg.setColorAt(1.0, self.fill_bottom)
            painter.fillPath(fill_path, fg)

            highlight_y = fill_rect.top() + 2
            painter.setPen(QPen(QColor(255, 255, 255, 140), 2))
            painter.drawLine(
                int(fill_rect.left() + 6),
                int(highlight_y),
                int(fill_rect.right() - 6),
                int(highlight_y),
            )


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
