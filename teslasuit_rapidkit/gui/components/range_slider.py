# SPDX-License-Identifier: MIT
"""Double-handle range slider widget for selecting value ranges."""

from PyQt5 import QtCore, QtWidgets, QtGui

from ..theme import COLORS


class RangeSlider(QtWidgets.QWidget):
    """Custom double-handle range slider.

    Emits ``rangeChanged(low, high)`` on drag.
    """

    rangeChanged = QtCore.pyqtSignal(int, int)

    def __init__(self, minimum: int = 0, maximum: int = 100, parent=None):
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = maximum
        self._low = minimum
        self._high = maximum
        self._pressed = None
        self._click_offset = 0
        self.setMinimumSize(100, 20)
        self.setMaximumSize(300, 30)

    # ── Properties ────────────────────────────────────────────────

    def minimum(self):
        return self._minimum

    def maximum(self):
        return self._maximum

    def setMinimum(self, v):
        self._minimum = v
        self._low = max(self._low, v)
        self.update()

    def setMaximum(self, v):
        self._maximum = v
        self._high = min(self._high, v)
        self.update()

    def low(self):
        return self._low

    def high(self):
        return self._high

    def setLow(self, v):
        self._low = max(self._minimum, min(v, self._high))
        self.update()

    def setHigh(self, v):
        self._high = min(self._maximum, max(v, self._low))
        self.update()

    def setRange(self, low, high):
        self._low = max(self._minimum, min(low, high))
        self._high = min(self._maximum, max(high, low))
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def range(self):
        return (self._low, self._high)

    # ── Painting ──────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect()
        margin = 10
        groove_y = rect.height() // 2 - 1
        groove_h = 3
        groove_w = rect.width() - 2 * margin

        # Groove background
        p.fillRect(QtCore.QRect(margin, groove_y, groove_w, groove_h),
                    QtGui.QColor(COLORS["border"]))

        if self._maximum <= self._minimum or groove_w <= 0:
            return

        span = self._maximum - self._minimum
        low_x = margin + (self._low - self._minimum) * groove_w // span
        high_x = margin + (self._high - self._minimum) * groove_w // span

        # Active range
        if high_x > low_x:
            p.fillRect(QtCore.QRect(low_x, groove_y, high_x - low_x, groove_h),
                        QtGui.QColor(COLORS["accent"]))

        # Handles
        hs = 10
        for hx in (low_x, high_x):
            p.setBrush(QtGui.QBrush(QtGui.QColor(COLORS["accent"])))
            p.setPen(QtGui.QPen(QtGui.QColor(COLORS["bg_primary"]), 2))
            p.drawEllipse(QtCore.QRect(hx - hs // 2, groove_y - 3, hs, hs))

    # ── Mouse interaction ─────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return
        margin = 10
        groove_w = self.rect().width() - 2 * margin
        if groove_w <= 0 or self._maximum <= self._minimum:
            return

        span = self._maximum - self._minimum
        low_x = margin + (self._low - self._minimum) * groove_w // span
        high_x = margin + (self._high - self._minimum) * groove_w // span

        if abs(event.x() - low_x) < abs(event.x() - high_x):
            self._pressed = "low"
            self._click_offset = event.x() - low_x
        else:
            self._pressed = "high"
            self._click_offset = event.x() - high_x

    def mouseMoveEvent(self, event):
        if not self._pressed:
            return
        margin = 10
        groove_w = self.rect().width() - 2 * margin
        if groove_w <= 0 or self._maximum <= self._minimum:
            return

        value = self._minimum + (event.x() - self._click_offset - margin) * (
            self._maximum - self._minimum
        ) // groove_w
        value = max(self._minimum, min(self._maximum, value))

        if self._pressed == "low":
            self.setLow(value)
        else:
            self.setHigh(value)
        self.rangeChanged.emit(self._low, self._high)

    def mouseReleaseEvent(self, event):
        self._pressed = None
