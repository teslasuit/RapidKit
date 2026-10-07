# SPDX-License-Identifier: MIT
"""Custom-painted widgets for the Elbow FES Flexion Control dashboard.

Kept lightweight — each widget paints its own content with QPainter and
exposes a small ``set_*`` API that the main window calls once per tick.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Deque

from PyQt5 import QtCore, QtGui, QtWidgets

from .styles import Colors


# ─────────────────────────────────────────────────────────────────
# Kinematics visualizer — pivot + current/target forearm rays
# ─────────────────────────────────────────────────────────────────
class KinematicsVisualizer(QtWidgets.QWidget):
    """2D representation of the active-arm elbow joint.

    Draws a fixed vertical upper arm (shoulder on top, elbow pivot below)
    and a forearm rotated by the current flexion angle. A dashed "ghost"
    forearm marks the target.  Convention: 0° = fully extended (forearm
    hanging straight down, continuing the upper arm), 90° = forearm
    horizontal (pointing forward/right), 180° = fully flexed (forearm
    pointing straight up, back toward the shoulder).
    """

    # Tuning-state colors — matched to QPushButton#PrimaryPill[running="true"]
    # in styles.py so the canvas background reads as the "auto-calibrating"
    # state at a glance.
    _TUNING_BG_FILL   = QtGui.QColor(200, 160, 240, 55)
    _TUNING_BG_BORDER = QtGui.QColor(200, 160, 240, 180)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 260)
        self._current_deg: float = 0.0
        self._target_deg: float = 0.0
        self._tuning: bool = False

    def set_angles(self, current_deg: float, target_deg: float) -> None:
        if (current_deg != self._current_deg or
                target_deg != self._target_deg):
            self._current_deg = float(current_deg)
            self._target_deg = float(target_deg)
            self.update()

    def set_tuning(self, active: bool) -> None:
        """Toggle the auto-calibrating visual state.

        When active, the canvas paints a tertiary-tinted background
        (matching the AUTO-CALIBRATE button's running color) and draws
        the target forearm in tertiary to make the target-angle cue
        pop while the tuner is driving the system.
        """
        active = bool(active)
        if active != self._tuning:
            self._tuning = active
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # Tuning backdrop — rounded rect filling the widget so the whole
        # kinematics panel reads as "calibrating" at a glance.
        if self._tuning:
            bg_rect = QtCore.QRectF(1, 1, w - 2, h - 2)
            p.setPen(QtGui.QPen(self._TUNING_BG_BORDER, 1.2))
            p.setBrush(self._TUNING_BG_FILL)
            p.drawRoundedRect(bg_rect, 10, 10)

        # Pivot sits in the upper third so the forearm at 0° (hanging
        # straight down) has room to draw without clipping the widget.
        pivot = QtCore.QPointF(w * 0.5, h * 0.32)
        upper_len = min(w, h) * 0.28
        fore_len  = min(w, h) * 0.36

        # Upper arm — vertical, shoulder directly above the pivot.
        shoulder = QtCore.QPointF(pivot.x(), pivot.y() - upper_len)
        p.setPen(QtGui.QPen(QtGui.QColor(Colors.OUTLINE), 3))
        p.drawLine(shoulder, pivot)

        # Target (ghost) forearm — dashed. Swap to the tertiary color and a
        # slightly thicker stroke during auto-calibration so the operator
        # immediately notices that the target marker is the "live" reference.
        target_end = self._forearm_end(pivot, fore_len, self._target_deg)
        if self._tuning:
            target_color = Colors.TERTIARY
            target_width = 2.2
        else:
            target_color = Colors.MUTED
            target_width = 1.5
        pen = QtGui.QPen(QtGui.QColor(target_color), target_width,
                         QtCore.Qt.DashLine)
        p.setPen(pen)
        p.drawLine(pivot, target_end)
        self._draw_end_marker(p, target_end, target_color,
                              filled=False, dashed=True)

        # Current forearm — solid ice-blue
        cur_end = self._forearm_end(pivot, fore_len, self._current_deg)
        pen = QtGui.QPen(QtGui.QColor(Colors.PRIMARY), 2.2)
        p.setPen(pen)
        p.drawLine(pivot, cur_end)
        self._draw_end_marker(p, cur_end, Colors.PRIMARY, filled=False, dashed=False)

        # Glow around the current-angle line (simple outer pen at low alpha)
        glow = QtGui.QColor(Colors.PRIMARY)
        glow.setAlpha(60)
        p.setPen(QtGui.QPen(glow, 6))
        p.drawLine(pivot, cur_end)

        # Pivot dot
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(Colors.PRIMARY))
        p.drawEllipse(pivot, 6, 6)
        p.setBrush(QtGui.QColor(Colors.BG))
        p.drawEllipse(pivot, 2.5, 2.5)

        # Delta angle overlay card (top-right of the visualizer)
        delta = self._target_deg - self._current_deg
        self._draw_delta_card(p, w - 18, 20, delta)

    # ── helpers ──────────────────────────────────────────────
    def _forearm_end(self, pivot: QtCore.QPointF, length: float,
                     angle_deg: float) -> QtCore.QPointF:
        # 0°   → forearm hangs straight down (continuation of the vertical
        #        upper arm, i.e. fully extended elbow).
        # 90°  → forearm horizontal, pointing forward/right.
        # 180° → forearm straight up (fully flexed, back toward shoulder).
        # Screen-y grows downward, so "down" is +y.
        theta = math.radians(angle_deg)
        return QtCore.QPointF(
            pivot.x() + length * math.sin(theta),
            pivot.y() + length * math.cos(theta),
        )

    def _draw_end_marker(self, p: QtGui.QPainter, pt: QtCore.QPointF,
                         color: str, *, filled: bool, dashed: bool) -> None:
        size = 8
        rect = QtCore.QRectF(pt.x() - size / 2, pt.y() - size / 2, size, size)
        pen = QtGui.QPen(QtGui.QColor(color), 1.3)
        if dashed:
            pen.setStyle(QtCore.Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush if not filled else QtGui.QColor(color))
        p.drawRect(rect)

    def _draw_delta_card(self, p: QtGui.QPainter, right_x: float, top_y: float,
                         delta_deg: float) -> None:
        card_w, card_h = 120, 52
        x = right_x - card_w
        rect = QtCore.QRectF(x, top_y, card_w, card_h)
        p.setPen(QtGui.QPen(QtGui.QColor(125, 211, 252, 80), 1))
        p.setBrush(QtGui.QColor(15, 21, 36, 180))
        p.drawRoundedRect(rect, 8, 8)

        f_small = QtGui.QFont()
        f_small.setPointSize(7)
        f_small.setBold(True)
        p.setFont(f_small)
        p.setPen(QtGui.QColor(Colors.ON_SURFACE_V))
        p.drawText(QtCore.QRectF(x + 10, top_y + 6, card_w - 20, 14),
                   QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   "DELTA ANGLE")

        f_big = QtGui.QFont("Consolas")
        f_big.setPointSize(16)
        p.setFont(f_big)
        p.setPen(QtGui.QColor(Colors.PRIMARY))
        p.drawText(QtCore.QRectF(x + 10, top_y + 22, card_w - 20, 26),
                   QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   f"{delta_deg:+.1f}°")


# ─────────────────────────────────────────────────────────────────
# Error deviation — centered bar with a lavender indicator
# ─────────────────────────────────────────────────────────────────
class ErrorDeviationBar(QtWidgets.QWidget):
    """Horizontal bar: centered zero, colored indicator for the error."""

    # Tick cadence (degrees). Majors get labels + a long tick, minors get
    # a short tick only. Must divide evenly into ``_max``.
    _MAJOR_STEP = 10.0
    _MINOR_STEP = 5.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # Taller than the original 40px to make room for the numeric tick
        # labels sitting under the track.
        self.setFixedHeight(56)
        self._error: float = 0.0
        self._max: float = 30.0  # clamp error display to ±max degrees

    def set_error(self, deg: float) -> None:
        self._error = float(deg)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        w, h = self.width(), self.height()

        # Reserve a strip at the bottom for tick labels; place the track
        # above it so the indicator dot, ticks, and numbers stack cleanly.
        label_strip_h = 14
        track_h = 12
        track_top = (h - label_strip_h) * 0.5 - track_h * 0.5
        track = QtCore.QRectF(0, track_top, w, track_h)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 20), 1))
        p.setBrush(QtGui.QColor(10, 15, 28, 160))
        p.drawRoundedRect(track, track.height() / 2, track.height() / 2)

        cx = w / 2

        # Tolerance zone (±3°) — subtle ice-blue fill, painted before the
        # axis so tick lines sit on top.
        tol = 3.0
        tol_left  = cx - (tol / self._max) * (w / 2)
        tol_right = cx + (tol / self._max) * (w / 2)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(QtGui.QColor(125, 211, 252, 30))
        p.drawRoundedRect(QtCore.QRectF(tol_left, track.top() + 2,
                                        tol_right - tol_left,
                                        track.height() - 4), 4, 4)

        # Axis + ticks + labels
        tick_baseline = track.bottom()
        major_tick_len = 6
        minor_tick_len = 3
        major_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 110), 1)
        minor_pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 55), 1)
        zero_pen  = QtGui.QPen(QtGui.QColor(255, 255, 255, 160), 1)
        label_pen = QtGui.QPen(QtGui.QColor(Colors.ON_SURFACE_V))

        font = p.font()
        font.setPointSizeF(7.5)
        p.setFont(font)
        fm = QtGui.QFontMetricsF(font)

        def _deg_to_x(deg: float) -> float:
            return cx + (deg / self._max) * (w / 2)

        # Walk minor cadence so we hit both majors and minors, then branch.
        n_steps = int(round(self._max / self._MINOR_STEP))
        for i in range(-n_steps, n_steps + 1):
            deg = i * self._MINOR_STEP
            x = _deg_to_x(deg)
            is_major = abs(deg % self._MAJOR_STEP) < 1e-6
            is_zero  = abs(deg) < 1e-6
            if is_zero:
                p.setPen(zero_pen)
                p.drawLine(QtCore.QPointF(x, track.top() - 3),
                           QtCore.QPointF(x, tick_baseline + major_tick_len))
            elif is_major:
                p.setPen(major_pen)
                p.drawLine(QtCore.QPointF(x, tick_baseline),
                           QtCore.QPointF(x, tick_baseline + major_tick_len))
            else:
                p.setPen(minor_pen)
                p.drawLine(QtCore.QPointF(x, tick_baseline),
                           QtCore.QPointF(x, tick_baseline + minor_tick_len))

            if is_major:
                # Sign-aware label: "0°", "+10°", "-20°".
                if is_zero:
                    text = "0°"
                else:
                    text = f"{int(deg):+d}°"
                text_w = fm.horizontalAdvance(text)
                # Clamp label x so edge labels don't clip the widget.
                label_x = max(1.0, min(w - text_w - 1.0, x - text_w / 2))
                label_y = tick_baseline + major_tick_len + fm.ascent() + 1
                p.setPen(label_pen)
                p.drawText(QtCore.QPointF(label_x, label_y), text)

        # Indicator dot (painted last so it sits on top of ticks)
        clamped = max(-self._max, min(self._max, self._error))
        pos_x = cx + (clamped / self._max) * (w / 2 - 10)
        dot_cy = track.center().y()
        dot_r = 7
        glow = QtGui.QColor(Colors.TERTIARY)
        glow.setAlpha(120)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QtCore.QPointF(pos_x, dot_cy), dot_r + 3, dot_r + 3)
        p.setBrush(QtGui.QColor(Colors.TERTIARY))
        p.drawEllipse(QtCore.QPointF(pos_x, dot_cy), dot_r, dot_r)


# ─────────────────────────────────────────────────────────────────
# Pulse intensity — rolling vertical bar chart of active-arm PW
# ─────────────────────────────────────────────────────────────────
class PulseIntensityBars(QtWidgets.QWidget):
    """Seven-bar rolling histogram of recent pulse-width samples."""

    N_BARS = 7

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(90)
        self._values: Deque[float] = deque([0.0] * self.N_BARS,
                                           maxlen=self.N_BARS)
        self._max_pw: float = 300.0  # matches strategy's PW_CAP_US

    def push_sample(self, pulse_width_us: float) -> None:
        self._values.append(float(pulse_width_us))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        n = len(self._values)
        if n == 0:
            return
        gap = 4
        bar_w = (w - gap * (n - 1)) / n
        for i, v in enumerate(self._values):
            frac = max(0.0, min(1.0, v / self._max_pw))
            bar_h = max(2.0, frac * (h - 4))
            x = i * (bar_w + gap)
            y = h - bar_h
            # Alternating alpha gives the mockup's "beaty" look
            alpha = 60 + int(180 * frac)
            color = QtGui.QColor(125, 211, 252, alpha)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QtCore.QRectF(x, y, bar_w, bar_h), 3, 3)


# ─────────────────────────────────────────────────────────────────
# Metric card — label on top, big value below, optional suffix
# ─────────────────────────────────────────────────────────────────
class MetricCard(QtWidgets.QFrame):
    def __init__(self, label: str, *, value_role: str = "primary",
                 accent_bar: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GlassPanel")
        if accent_bar:
            self.setProperty("accent", "true")
        self.setMinimumHeight(78)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        self._label = QtWidgets.QLabel(label.upper())
        self._label.setObjectName("MetricLabel")
        lay.addWidget(self._label)

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        self._value = QtWidgets.QLabel("—")
        # Remember the "normal" object name so ``set_tuning(False)`` can
        # restore the original color role after an auto-calibrate pass.
        if value_role == "tertiary":
            self._base_value_style = "MetricValueTertiary"
        elif value_role == "neutral":
            self._base_value_style = "MetricValueNeutral"
        else:
            self._base_value_style = "MetricValue"
        self._value.setObjectName(self._base_value_style)
        row.addWidget(self._value)
        self._suffix = QtWidgets.QLabel("")
        self._suffix.setObjectName("MetricSuffix")
        row.addWidget(self._suffix, 1)
        lay.addLayout(row)

        self._tuning: bool = False

    def set_value(self, value_text: str, suffix_text: str = "") -> None:
        self._value.setText(value_text)
        self._suffix.setText(suffix_text)

    def set_tuning(self, active: bool) -> None:
        """Toggle the auto-calibrating highlight for this card.

        While active, the big value label is retargeted at the tertiary
        style so the target-angle readout visibly changes state during
        an auto-calibration run, matching the kinematics visualizer
        backdrop. Flipping back restores the original role.
        """
        active = bool(active)
        if active == self._tuning:
            return
        self._tuning = active
        self._value.setObjectName(
            "MetricValueTertiary" if active else self._base_value_style
        )
        self.setProperty("tuning", "true" if active else "false")
        # Qt's style engine only picks up dynamic property / object-name
        # changes after a repolish.
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
        self.style().unpolish(self)
        self.style().polish(self)
