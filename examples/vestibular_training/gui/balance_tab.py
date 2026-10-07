# SPDX-License-Identifier: MIT
"""
Vestibular Training Operator Console — PyQt5 implementation.

Layout (top → bottom):
    1. Status strip   (36 px — BACKEND / SUIT / TICK / ACTIVE / MASTER / clock)
    2. Main stage     (left: sway canvas;  right: inspector panels)
    3. Safety bar     (56 px — STOP ALL + keyboard cheat-sheet)

The sway canvas reads PelvisTilt and PelvisList from the ring-buffer snapshot
(self.data) to show the patient's live postural sway relative to the stability
ellipse. No dragging or click interaction — the patient's body drives the dot.

The inspector holds:
    Panel A  Master intensity slider
    Panel B  Stability boundary sliders (sagittal / frontal)
    Panel C  Calibration button (records neutral stance)
    Panel D  Zone monitor table (amp_mult / pw_mult / FIRING state per zone)

Keyboard shortcuts:
    Esc         STOP ALL
    C           Calibrate (record current PelvisTilt / PelvisList as neutral)
    , / .       Decrease / increase master intensity by 5 %
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from PyQt5 import QtCore, QtGui, QtWidgets

from teslasuit_rapidkit.gui.base_widget import FesWidget


# ── Teslasuit color tokens ─────────────────────────────────────────────────────
TS_BG_1     = "#181818"
TS_BG_2     = "#212121"
TS_BG_3     = "#252525"
TS_BG_4     = "#2D2D2D"
TS_FG_1     = "#FFFFFF"
TS_FG_2     = "#BCC0C3"
TS_FG_3     = "#7D7F82"
TS_ACCENT   = "#005FFF"
TS_CHART    = "#882DFF"
TS_OK       = "#00E124"
TS_WARN     = "#F49301"
TS_ERR      = "#F40101"
TS_ERR_DEEP = "#7A0000"

# ── Zone metadata (mirrors strategy._ZONES) ───────────────────────────────────
@dataclass(frozen=True)
class _ZoneSpec:
    name:     str
    label:    str
    region:   str
    bone:     str
    channels: str
    theta:    float   # cardinal angle, atan2 frame (rad)


_ZONES: tuple[_ZoneSpec, ...] = (
    _ZoneSpec("belly",          "FORWARD",  "Abdomen",     "8",  "ch 0–7",  math.pi / 2),
    _ZoneSpec("right_shoulder", "RIGHT",    "R. Shoulder", "14", "ch 0–2",  0.0),
    _ZoneSpec("back",           "BACKWARD", "Back",        "11", "ch 0–7", -math.pi / 2),
    _ZoneSpec("left_shoulder",  "LEFT",     "L. Shoulder", "12", "ch 0–2",  math.pi),
)

# Must match strategy constants.
_WEIGHT_EPS:   float = 0.02
_PW_MULT_MIN:  float = 0.5
_PW_MULT_MAX:  float = 1.0
_BASE_AMP_PCT: float = 60.0
_BASE_PW_US:   float = 200.0
_MAX_EXCESS:   float = 1.0

# Approaching threshold: sway at 80 % of boundary triggers WARN coloring.
_WARN_FRACTION: float = 0.8


def _qfont(family: str = "Segoe UI", size: int = 13,
           weight: int = QtGui.QFont.Normal,
           letter_spacing: float = 0.0) -> QtGui.QFont:
    f = QtGui.QFont(family, size, weight)
    if letter_spacing:
        f.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, letter_spacing)
    return f


def _slider_qss() -> str:
    return (
        f"QSlider::groove:horizontal {{ background: {TS_BG_3}; height: 4px; border-radius: 2px; }}"
        f"QSlider::sub-page:horizontal {{ background: {TS_ACCENT}; border-radius: 2px; }}"
        f"QSlider::handle:horizontal {{ background: {TS_ACCENT}; width: 14px; height: 14px; "
        f"  margin: -6px 0; border-radius: 7px; }}"
    )


# ── Sway state helper ─────────────────────────────────────────────────────────

def _wrap_180(deg: float) -> float:
    """Wrap an angle in degrees into [-180, 180]."""
    return ((deg + 180.0) % 360.0) - 180.0


def _classify(r: float) -> str:
    """'inside' | 'approaching' | 'outside' | 'critical'."""
    if r >= 2.0:
        return "critical"
    if r >= 1.0:
        return "outside"
    if r >= _WARN_FRACTION:
        return "approaching"
    return "inside"


# ── Sway canvas ───────────────────────────────────────────────────────────────

class _SwayCanvas(QtWidgets.QFrame):
    """Read-only disc showing live postural sway against the stability ellipse.

    Driven by update_sway() called from the tab's 30 Hz refresh tick.
    All drawing is done in paintEvent; no user interaction.
    """

    SWAY_DOT_R:  int = 10
    WEARER_R:    int = 14

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(420, 420)
        self.setStyleSheet(f"background: {TS_BG_2}; border-radius: 8px;")

        # Normalised sway (x = frontal/bnd_frt, y = sagittal/bnd_sag).
        self._x: float = 0.0
        self._y: float = 0.0

        # Raw degrees (for corner readouts).
        self._sag_deg: float = 0.0
        self._frt_deg: float = 0.0

        # Per-zone weights computed from sway direction.
        self.last_weights: dict[str, float] = {z.name: 0.0 for z in _ZONES}
        self.last_prox: float = 0.0   # excess beyond boundary (0 inside, >0 outside)

        # Pulsing state for the sway dot when outside boundary.
        self._pulse_phase: int = 0
        self._pulse_timer = QtCore.QTimer(self)
        self._pulse_timer.timeout.connect(self._on_pulse)
        self._pulse_timer.start(250)  # 2 Hz (250 ms half-period)

    def _on_pulse(self) -> None:
        self._pulse_phase ^= 1
        self.update()

    def update_sway(self, x: float, y: float,
                    sag_deg: float, frt_deg: float) -> None:
        """Called each refresh tick with normalised sway coordinates."""
        self._x = x
        self._y = y
        self._sag_deg = sag_deg
        self._frt_deg = frt_deg
        r = math.hypot(x, y)
        self.last_prox = max(0.0, r - 1.0)
        self._recompute_weights(x, y, r)
        self.update()

    def _recompute_weights(self, x: float, y: float, r: float) -> None:
        if r <= 1.0:
            for z in _ZONES:
                self.last_weights[z.name] = 0.0
            return
        theta = math.atan2(y, x)
        for z in _ZONES:
            cos_term = math.cos(theta - z.theta)
            w = max(0.0, cos_term) ** 2
            self.last_weights[z.name] = w if w >= _WEIGHT_EPS else 0.0

    # ── geometry ──────────────────────────────────────────────────────────────

    def _disc_geom(self) -> tuple[QtCore.QPointF, float]:
        rect = self.rect()
        side = min(rect.width(), rect.height()) - 32
        return QtCore.QPointF(rect.center()), side / 2.0

    def _to_widget(self, x: float, y: float) -> QtCore.QPointF:
        center, radius = self._disc_geom()
        return QtCore.QPointF(center.x() + x * radius,
                              center.y() - y * radius)  # +y = up

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        center, radius = self._disc_geom()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        r = math.hypot(self._x, self._y)
        state = _classify(r)

        # ── Zone heatmap wedges ──
        for z in _ZONES:
            w = self.last_weights.get(z.name, 0.0)
            excess = min(self.last_prox, _MAX_EXCESS)
            alpha = int(min(0.7, w * excess) * 255)
            if alpha <= 0:
                continue
            color = QtGui.QColor(0, 95, 255, alpha)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(color)
            start_deg = math.degrees(z.theta) - 45
            painter.drawPie(
                QtCore.QRectF(center.x() - radius, center.y() - radius,
                              radius * 2, radius * 2),
                int(start_deg * 16),
                int(90 * 16),
            )

        # ── Concentric ellipses (at 0.5, 1.0, 1.5, 2.0 × boundary) ──
        boundary_color = {
            "inside":     TS_BG_4,
            "approaching": TS_WARN,
            "outside":    TS_ERR,
            "critical":   TS_ERR,
        }[state]

        for frac, solid, width in (
            (0.5,  False, 1.0),
            (1.0,  True,  2.0),
            (1.5,  False, 1.0),
            (2.0,  False, 1.0),
        ):
            color = boundary_color if frac == 1.0 else TS_BG_4 if frac < 2.0 else TS_BG_3
            pen = QtGui.QPen(QtGui.QColor(color), width)
            pen.setStyle(QtCore.Qt.SolidLine if solid else QtCore.Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawEllipse(center, radius * frac, radius * frac)

        # ── Cardinal tick marks + labels ──
        painter.setFont(_qfont("Jura", 10, QtGui.QFont.DemiBold, letter_spacing=1.4))
        for z in _ZONES:
            tx = center.x() + math.cos(z.theta) * radius
            ty = center.y() - math.sin(z.theta) * radius
            painter.setPen(QtGui.QPen(QtGui.QColor(TS_FG_3), 1.0))
            painter.drawLine(
                QtCore.QPointF(tx, ty),
                QtCore.QPointF(tx + math.cos(z.theta) * 8,
                               ty - math.sin(z.theta) * 8),
            )
            lx = center.x() + math.cos(z.theta) * (radius + 28)
            ly = center.y() - math.sin(z.theta) * (radius + 28)
            text = f"{z.label}  ·  bone {z.bone}"
            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(text)
            painter.setPen(QtGui.QColor(TS_FG_2))
            painter.drawText(QtCore.QPointF(lx - tw / 2, ly + 4), text)

        # ── Wearer marker (center crosshair ring) ──
        painter.setPen(QtGui.QPen(QtGui.QColor(TS_FG_1), 2.0))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawEllipse(center, self.WEARER_R, self.WEARER_R)
        painter.setPen(QtGui.QPen(QtGui.QColor(TS_FG_3), 1.0))
        painter.drawLine(center.x() - 5, center.y(), center.x() + 5, center.y())
        painter.drawLine(center.x(), center.y() - 5, center.x(), center.y() + 5)

        # ── Leash (wearer → sway dot) when outside boundary ──
        sway_pt = self._to_widget(self._x, self._y)
        if r > 1.0:
            leash_pen = QtGui.QPen(QtGui.QColor(0, 95, 255, 180), 1.0, QtCore.Qt.DashLine)
            painter.setPen(leash_pen)
            painter.drawLine(center, sway_pt)

        # ── Sway dot ──
        dot_color_map = {
            "inside":     QtGui.QColor(TS_FG_1),
            "approaching": QtGui.QColor(TS_WARN),
            "outside":    QtGui.QColor(TS_ERR),
            "critical":   QtGui.QColor(TS_ERR),
        }
        dot_color = dot_color_map[state]

        if state in ("outside", "critical") and self._pulse_phase:
            glow_alpha = 140
        elif state == "approaching":
            glow_alpha = 80
        else:
            glow_alpha = 0

        if glow_alpha > 0:
            glow_q = QtGui.QColor(dot_color)
            glow_q.setAlpha(glow_alpha)
            glow = QtGui.QRadialGradient(sway_pt, self.SWAY_DOT_R + 16)
            glow.setColorAt(0.0, glow_q)
            glow.setColorAt(1.0, QtGui.QColor(0, 0, 0, 0))
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(sway_pt, self.SWAY_DOT_R + 16, self.SWAY_DOT_R + 16)

        stroke = QtGui.QColor(TS_BG_4) if state == "inside" else dot_color
        painter.setPen(QtGui.QPen(stroke, 1.5))
        painter.setBrush(dot_color)
        painter.drawEllipse(sway_pt, self.SWAY_DOT_R, self.SWAY_DOT_R)

        # ── Critical: full-canvas inner border flash ──
        if state == "critical" and self._pulse_phase:
            flash_pen = QtGui.QPen(QtGui.QColor(TS_ERR), 6.0)
            painter.setPen(flash_pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRect(self.rect().adjusted(3, 3, -3, -3))

        # ── Corner readouts ──
        theta_deg = math.degrees(math.atan2(self._y, self._x)) if r > 0 else 0.0
        armed = ", ".join(
            z.label.lower() for z in _ZONES
            if self.last_weights.get(z.name, 0.0) > 0.0
        ) or "—"
        state_color = {
            "inside":     TS_OK,
            "approaching": TS_WARN,
            "outside":    TS_ERR,
            "critical":   TS_ERR,
        }[state]
        painter.setFont(_qfont("Jura", 10, QtGui.QFont.Light, letter_spacing=1.2))
        painter.setPen(QtGui.QColor(TS_FG_3))
        painter.drawText(QtCore.QPointF(14, 20), f"sag  {self._sag_deg:+.1f}°")
        painter.drawText(QtCore.QPointF(self.width() - 120, 20),
                         f"frt  {self._frt_deg:+.1f}°")
        painter.drawText(QtCore.QPointF(14, self.height() - 12),
                         f"r    {r:.2f}")
        painter.setPen(QtGui.QColor(state_color))
        state_text = f"state  {state.upper()}"
        sw = painter.fontMetrics().horizontalAdvance(state_text)
        painter.drawText(QtCore.QPointF(self.width() - sw - 14,
                                        self.height() - 12), state_text)

        painter.end()


# ── Status strip ──────────────────────────────────────────────────────────────

class _StatusStrip(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"background: {TS_BG_2};")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(28)

        self._cells: dict[str, QtWidgets.QLabel] = {}
        for key, label in (
            ("backend", "BACKEND"),
            ("suit",    "SUIT"),
            ("tick",    "TICK"),
            ("active",  "ACTIVE"),
            ("master",  "MASTER"),
        ):
            cell = QtWidgets.QWidget()
            cl = QtWidgets.QHBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(8)
            tag = QtWidgets.QLabel(label)
            tag.setFont(_qfont("Jura", 11, QtGui.QFont.DemiBold, letter_spacing=1.4))
            tag.setStyleSheet(f"color: {TS_FG_3};")
            val = QtWidgets.QLabel("—")
            val.setFont(_qfont("Jura", 12, QtGui.QFont.DemiBold, letter_spacing=1.2))
            val.setStyleSheet(f"color: {TS_FG_1};")
            cl.addWidget(tag)
            cl.addWidget(val)
            layout.addWidget(cell)
            self._cells[key] = val
        layout.addStretch(1)
        self._clock = QtWidgets.QLabel("--:--:--")
        self._clock.setFont(_qfont("Jura", 12, QtGui.QFont.DemiBold, letter_spacing=1.2))
        self._clock.setStyleSheet(f"color: {TS_FG_2};")
        layout.addWidget(self._clock)
        timer = QtCore.QTimer(self)
        timer.timeout.connect(lambda: self._clock.setText(time.strftime("%H:%M:%S")))
        timer.start(1000)
        self._clock.setText(time.strftime("%H:%M:%S"))

    def update_state(self, *, tick: int, active: int,
                     master_pct: int, connected: bool) -> None:
        self._cells["backend"].setText("OK")
        self._cells["backend"].setStyleSheet(f"color: {TS_OK};")
        self._cells["suit"].setText("CONNECTED" if connected else "OFFLINE")
        self._cells["suit"].setStyleSheet(
            f"color: {TS_OK if connected else TS_FG_3};"
        )
        self._cells["tick"].setText(f"{tick:04d}")
        self._cells["active"].setText(f"{active}/4")
        color = TS_FG_3 if active == 0 else TS_ACCENT if active <= 2 else TS_WARN
        self._cells["active"].setStyleSheet(f"color: {color};")
        self._cells["master"].setText(f"{master_pct}%")


# ── Stage header (eyebrow + state pill) ───────────────────────────────────────

class _StageHeader(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setStyleSheet(
            f"background: rgba(0,0,0,0.2); border-bottom: 1px solid #1f1f1f;"
        )
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(18, 0, 14, 0)
        h.setSpacing(10)

        eyebrow = QtWidgets.QLabel("POSTURAL SWAY · STABILITY BOUNDARY VIEW")
        eyebrow.setStyleSheet(
            f"background: transparent; color: {TS_FG_3}; "
            f"font-family: 'Jura', 'Segoe UI'; font-size: 10px; "
            f"font-weight: 500; letter-spacing: 1.8px;"
        )
        h.addWidget(eyebrow)
        h.addStretch(1)

        self._pill = QtWidgets.QLabel("● INSIDE")
        self._pill.setObjectName("statePill")
        h.addWidget(self._pill)
        self._set_pill("inside")

    def _set_pill(self, state: str) -> None:
        text_map  = {"inside": "● INSIDE", "approaching": "● APPROACHING",
                     "outside": "● OUTSIDE", "critical": "● CRITICAL"}
        color_map = {"inside": TS_OK, "approaching": TS_WARN,
                     "outside": TS_ERR, "critical": TS_ERR}
        color = color_map.get(state, TS_FG_3)
        self._pill.setText(text_map.get(state, "● IDLE"))
        self._pill.setStyleSheet(f"""
            QLabel#statePill {{
                background: rgba(0,0,0,0.0);
                border: 1px solid {color};
                border-radius: 11px;
                padding: 3px 10px;
                color: {color};
                font-family: 'Jura', 'Segoe UI';
                font-size: 10px;
                font-weight: 600;
                letter-spacing: 1.4px;
            }}
        """)

    def update_state(self, state: str) -> None:
        self._set_pill(state)


# ── Stage (header + canvas + focus veil) ──────────────────────────────────────

class _FocusVeil(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._phase = 1
        self._apply(0.04)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(QtCore.Qt.AlignCenter)
        self._label = QtWidgets.QLabel("WINDOW UNFOCUSED  ·  CUES RELEASED")
        self._label.setAlignment(QtCore.Qt.AlignCenter)
        self._label.setStyleSheet(f"""
            QLabel {{
                background: {TS_ERR_DEEP};
                border: 1px solid {TS_ERR};
                color: {TS_FG_1};
                font-family: 'Jura', 'Segoe UI';
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 2.2px;
                padding: 10px 18px;
                border-radius: 3px;
            }}
        """)
        glow = QtWidgets.QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(28)
        glow.setOffset(0, 0)
        glow.setColor(QtGui.QColor(244, 1, 1, 180))
        self._label.setGraphicsEffect(glow)
        layout.addWidget(self._label, 0, QtCore.Qt.AlignCenter)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self.hide()

    def _apply(self, alpha: float) -> None:
        self.setStyleSheet(
            f"QFrame {{ border: 2px solid rgba(244,1,1,0.6); "
            f"background: rgba(244,1,1,{alpha:.3f}); }}"
        )

    def _pulse(self) -> None:
        self._phase ^= 1
        self._apply(0.12 if self._phase else 0.04)

    def show_veil(self) -> None:
        self._phase = 1
        self._apply(0.08)
        self.raise_()
        self.show()
        self._timer.start(700)

    def hide_veil(self) -> None:
        self._timer.stop()
        self.hide()


class _Stage(QtWidgets.QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QFrame {{ background: #141414; }}")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = _StageHeader()
        v.addWidget(self.header)
        self.canvas = _SwayCanvas()
        v.addWidget(self.canvas, 1)
        self.veil = _FocusVeil(self)

    def resizeEvent(self, event) -> None:
        self.veil.setGeometry(self.rect())
        super().resizeEvent(event)

    def show_veil(self) -> None:
        self.veil.setGeometry(self.rect())
        self.veil.show_veil()

    def hide_veil(self) -> None:
        self.veil.hide_veil()


# ── Inspector panels ──────────────────────────────────────────────────────────

class _Panel(QtWidgets.QFrame):
    def __init__(self, title: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {TS_BG_2}; border-top: 1px solid {TS_BG_4};"
        )
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(8)
        if title:
            eyebrow = QtWidgets.QLabel(title)
            eyebrow.setFont(_qfont("Jura", 11, QtGui.QFont.DemiBold, letter_spacing=1.4))
            eyebrow.setStyleSheet(f"color: {TS_FG_3};")
            self._layout.addWidget(eyebrow)

    def addRow(self, widget: QtWidgets.QWidget) -> None:
        self._layout.addWidget(widget)


class _IntensityPanel(_Panel):
    intensity_changed = QtCore.pyqtSignal(int)

    def __init__(self, parent=None) -> None:
        super().__init__("MASTER INTENSITY", parent)
        self._value_lbl = QtWidgets.QLabel("60 %")
        self._value_lbl.setFont(_qfont("Jura", 28, QtGui.QFont.DemiBold))
        self._value_lbl.setStyleSheet(f"color: {TS_FG_1};")
        self.addRow(self._value_lbl)

        self._slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(60)
        self._slider.setStyleSheet(_slider_qss())
        self._slider.valueChanged.connect(self._on_change)
        self.addRow(self._slider)

        self._peaks = QtWidgets.QLabel("PEAK AMP  0%        PEAK PW  200 µs")
        self._peaks.setFont(_qfont("Jura", 11, QtGui.QFont.Light, letter_spacing=1.4))
        self._peaks.setStyleSheet(f"color: {TS_FG_3};")
        self.addRow(self._peaks)

    def _on_change(self, v: int) -> None:
        self._value_lbl.setText(f"{v} %")
        self.intensity_changed.emit(v)

    def set_peaks(self, amp: float, pw: float) -> None:
        self._peaks.setText(
            f"PEAK AMP  {int(amp * 100)}%        "
            f"PEAK PW  {int(pw * _BASE_PW_US)} µs"
        )

    def value(self) -> int:
        return self._slider.value()

    def set_value(self, v: int) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(v)
        self._value_lbl.setText(f"{v} %")
        self._slider.blockSignals(False)


class _BoundaryPanel(_Panel):
    boundary_changed = QtCore.pyqtSignal(float, float)  # (sagittal, frontal)

    def __init__(self, parent=None) -> None:
        super().__init__("STABILITY BOUNDARY", parent)

        for attr, label, default in (
            ("_sag", "SAGITTAL (fwd/bwd)", 80),   # ×0.1 = 8.0°
            ("_frt", "FRONTAL  (L/R)",     60),    # ×0.1 = 6.0°
        ):
            row = QtWidgets.QWidget()
            rl = QtWidgets.QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(10)
            lbl = QtWidgets.QLabel(label)
            lbl.setStyleSheet(f"color: {TS_FG_3};")
            lbl.setFont(_qfont("Jura", 11, QtGui.QFont.Light, letter_spacing=1.2))
            val_lbl = QtWidgets.QLabel(f"{default / 10:.1f}°")
            val_lbl.setFont(_qfont("Jura", 12, QtGui.QFont.DemiBold))
            val_lbl.setStyleSheet(f"color: {TS_FG_1};")
            val_lbl.setMinimumWidth(38)
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(10, 200)   # 1.0 – 20.0 degrees (×0.1)
            slider.setValue(default)
            slider.setStyleSheet(_slider_qss())
            rl.addWidget(lbl)
            rl.addWidget(slider, 1)
            rl.addWidget(val_lbl)
            setattr(self, attr + "_slider", slider)
            setattr(self, attr + "_lbl",    val_lbl)
            slider.valueChanged.connect(self._on_change)
            self.addRow(row)

        hint = QtWidgets.QLabel("Adjust to match patient's natural sway envelope.")
        hint.setFont(_qfont("Jura", 11, QtGui.QFont.Light))
        hint.setStyleSheet(f"color: {TS_FG_3};")
        self.addRow(hint)

    def _on_change(self, _: int) -> None:
        sag = self._sag_slider.value() / 10.0
        frt = self._frt_slider.value() / 10.0
        self._sag_lbl.setText(f"{sag:.1f}°")
        self._frt_lbl.setText(f"{frt:.1f}°")
        self.boundary_changed.emit(sag, frt)

    def sagittal(self) -> float:
        return self._sag_slider.value() / 10.0

    def frontal(self) -> float:
        return self._frt_slider.value() / 10.0


class _CalibrationPanel(_Panel):
    calibrate_requested = QtCore.pyqtSignal()

    _STATE_IDLE       = 0
    _STATE_RECORDING  = 1
    _STATE_DONE       = 2

    def __init__(self, parent=None) -> None:
        super().__init__("NEUTRAL CALIBRATION", parent)
        self._state = self._STATE_IDLE

        self._btn = QtWidgets.QPushButton("CALIBRATE")
        self._btn.setFixedHeight(36)
        self._btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._btn.setFont(_qfont("Jura", 12, QtGui.QFont.DemiBold, letter_spacing=1.4))
        self._btn.clicked.connect(self._on_clicked)
        self._set_btn_style(self._STATE_IDLE)
        self.addRow(self._btn)

        self._neutral_lbl = QtWidgets.QLabel("NEUTRAL  sag +0.0°  frt +0.0°")
        self._neutral_lbl.setFont(_qfont("Jura", 10, QtGui.QFont.Light, letter_spacing=1.2))
        self._neutral_lbl.setStyleSheet(f"color: {TS_FG_3};")
        self.addRow(self._neutral_lbl)

        hint = QtWidgets.QLabel("Ask patient to stand quietly for 3 s, then press.")
        hint.setFont(_qfont("Jura", 11, QtGui.QFont.Light))
        hint.setStyleSheet(f"color: {TS_FG_3};")
        self.addRow(hint)

        self._done_timer = QtCore.QTimer(self)
        self._done_timer.setSingleShot(True)
        self._done_timer.timeout.connect(self._on_done_expired)

    def _set_btn_style(self, state: int) -> None:
        bg, border, text = {
            self._STATE_IDLE:      (TS_BG_3,    TS_ACCENT, TS_FG_1),
            self._STATE_RECORDING: (TS_WARN,    TS_WARN,   TS_BG_1),
            self._STATE_DONE:      (TS_BG_3,    TS_OK,     TS_OK),
        }[state]
        label = {
            self._STATE_IDLE:      "CALIBRATE",
            self._STATE_RECORDING: "RECORDING…",
            self._STATE_DONE:      "DONE",
        }[state]
        self._btn.setText(label)
        self._btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 18px;
                color: {text};
                font-family: 'Jura', 'Segoe UI';
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 1.4px;
                padding: 0 16px;
            }}
        """)

    def _on_clicked(self) -> None:
        if self._state == self._STATE_IDLE:
            self._state = self._STATE_RECORDING
            self._set_btn_style(self._STATE_RECORDING)
            self._btn.setEnabled(False)
            self.calibrate_requested.emit()
            QtCore.QTimer.singleShot(3000, self._finish_recording)

    def _finish_recording(self) -> None:
        self._state = self._STATE_DONE
        self._set_btn_style(self._STATE_DONE)
        self._done_timer.start(2000)

    def _on_done_expired(self) -> None:
        self._state = self._STATE_IDLE
        self._set_btn_style(self._STATE_IDLE)
        self._btn.setEnabled(True)

    def update_neutral(self, sag: float, frt: float) -> None:
        self._neutral_lbl.setText(f"NEUTRAL  sag {sag:+.1f}°  frt {frt:+.1f}°")


class _ZoneMonitor(QtWidgets.QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {TS_BG_2};")
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        for col, label in enumerate(("ZONE", "BONE", "AMP", "PW", "STATE")):
            lbl = QtWidgets.QLabel(label)
            lbl.setFont(_qfont("Jura", 10, QtGui.QFont.DemiBold, letter_spacing=1.4))
            lbl.setStyleSheet(f"color: {TS_FG_3};")
            grid.addWidget(lbl, 0, col)

        self._rows: dict[str, dict[str, QtWidgets.QLabel]] = {}
        for row_idx, z in enumerate(_ZONES, start=1):
            name_lbl = QtWidgets.QLabel(z.region)
            name_lbl.setFont(_qfont("Segoe UI", 12, QtGui.QFont.Medium))
            name_lbl.setStyleSheet(f"color: {TS_FG_1};")
            bone_lbl = QtWidgets.QLabel(f"{z.bone}  {z.channels}")
            bone_lbl.setFont(_qfont("Jura", 11, QtGui.QFont.Light))
            bone_lbl.setStyleSheet(f"color: {TS_FG_3};")
            amp_lbl = QtWidgets.QLabel("0.00")
            pw_lbl  = QtWidgets.QLabel("0.50")
            for lbl in (amp_lbl, pw_lbl):
                lbl.setFont(_qfont("Jura", 12, QtGui.QFont.DemiBold))
                lbl.setStyleSheet(f"color: {TS_FG_2};")
            state_lbl = QtWidgets.QLabel("muted")
            state_lbl.setFont(_qfont("Jura", 10, QtGui.QFont.DemiBold, letter_spacing=1.4))
            state_lbl.setStyleSheet(
                f"color: {TS_FG_3}; padding: 2px 8px; "
                f"background: {TS_BG_3}; border-radius: 6px;"
            )
            grid.addWidget(name_lbl,  row_idx, 0)
            grid.addWidget(bone_lbl,  row_idx, 1)
            grid.addWidget(amp_lbl,   row_idx, 2)
            grid.addWidget(pw_lbl,    row_idx, 3)
            grid.addWidget(state_lbl, row_idx, 4)
            self._rows[z.name] = {"amp": amp_lbl, "pw": pw_lbl, "state": state_lbl}

    def update_zone(self, name: str, amp_mult: float, pw_mult: float,
                    firing: bool) -> None:
        row = self._rows.get(name)
        if row is None:
            return
        row["amp"].setText(f"{amp_mult:.2f}")
        row["pw"].setText(f"{pw_mult:.2f}")
        if firing:
            row["state"].setText("FIRING")
            row["state"].setStyleSheet(
                f"color: {TS_OK}; padding: 2px 8px; "
                f"background: rgba(0,225,36,30); border-radius: 6px;"
            )
        else:
            row["state"].setText("muted")
            row["state"].setStyleSheet(
                f"color: {TS_FG_3}; padding: 2px 8px; "
                f"background: {TS_BG_3}; border-radius: 6px;"
            )


# ── Safety bar ────────────────────────────────────────────────────────────────

class _SafetyBar(QtWidgets.QFrame):
    stop_pressed = QtCore.pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(f"background: {TS_BG_2}; border-top: 1px solid {TS_BG_4};")
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(16)

        stop = QtWidgets.QPushButton("STOP ALL")
        stop.setFixedSize(240, 40)
        stop.setCursor(QtCore.Qt.PointingHandCursor)
        stop.setFont(_qfont("Jura", 14, QtGui.QFont.DemiBold, letter_spacing=1.4))
        stop.setStyleSheet(
            f"QPushButton {{ background: {TS_ERR}; color: {TS_FG_1}; "
            f"  border: none; border-radius: 20px; }}"
            f"QPushButton:pressed {{ background: {TS_ERR_DEEP}; }}"
        )
        stop.clicked.connect(self.stop_pressed)
        h.addWidget(stop)

        cheats = QtWidgets.QLabel(
            "C calibrate  ·  , / . intensity  ·  ESC stop all"
        )
        cheats.setFont(_qfont("Jura", 11, QtGui.QFont.Light, letter_spacing=1.4))
        cheats.setStyleSheet(f"color: {TS_FG_3};")
        h.addStretch(1)
        h.addWidget(cheats)


# ── BalanceTab — top-level FesWidget ─────────────────────────────────────────

class BalanceTab(FesWidget):
    """Main operator console for vestibular training.

    Reads PelvisTilt / PelvisList from the ring-buffer snapshot (self.data)
    each 30 Hz tick, computes normalised sway, drives the canvas and zone
    monitor, and mirrors parameters back through the control message.
    """

    always_update = True

    def build_ui(self) -> None:
        outer = self.layout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Status strip
        self._status = _StatusStrip(self)
        outer.addWidget(self._status)

        # Main stage
        stage_container = QtWidgets.QWidget(self)
        stage_layout = QtWidgets.QHBoxLayout(stage_container)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(0)
        outer.addWidget(stage_container, stretch=1)

        self._stage = _Stage(stage_container)
        stage_layout.addWidget(self._stage, stretch=65)

        # Right inspector
        inspector = QtWidgets.QWidget(stage_container)
        inspector.setStyleSheet(f"background: {TS_BG_2}; border-left: 1px solid {TS_BG_4};")
        insp_layout = QtWidgets.QVBoxLayout(inspector)
        insp_layout.setContentsMargins(0, 0, 0, 0)
        insp_layout.setSpacing(0)
        stage_layout.addWidget(inspector, stretch=35)

        self._intensity = _IntensityPanel(inspector)
        self._intensity.intensity_changed.connect(self._on_intensity_changed)
        insp_layout.addWidget(self._intensity)

        self._boundary = _BoundaryPanel(inspector)
        self._boundary.boundary_changed.connect(self._on_boundary_changed)
        insp_layout.addWidget(self._boundary)

        self._calibration = _CalibrationPanel(inspector)
        self._calibration.calibrate_requested.connect(self._on_calibrate)
        insp_layout.addWidget(self._calibration)

        monitor_panel = _Panel("ZONE MONITOR", inspector)
        self._monitor = _ZoneMonitor(monitor_panel)
        monitor_panel.addRow(self._monitor)
        insp_layout.addWidget(monitor_panel)
        insp_layout.addStretch(1)

        # Safety bar
        self._safety = _SafetyBar(self)
        self._safety.stop_pressed.connect(self._stop_all)
        outer.addWidget(self._safety)

        self._tick = 0

        # Focus tracking for STOP ALL on window deactivate
        QtCore.QTimer.singleShot(0, self._install_window_filter)

        # Push initial parameters to backend
        self._sync_boundary_to_message()

    # ── Window focus tracking ──────────────────────────────────────────────────

    def _install_window_filter(self) -> None:
        win = self.window()
        if win is not None and win is not self:
            win.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.window():
            if event.type() == QtCore.QEvent.WindowDeactivate:
                self._stop_all()
                self._stage.show_veil()
            elif event.type() == QtCore.QEvent.WindowActivate:
                self._stage.hide_veil()
        return super().eventFilter(obj, event)

    # ── Keyboard shortcuts ─────────────────────────────────────────────────────

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key == QtCore.Qt.Key_Escape:
            self._stop_all()
        elif key == QtCore.Qt.Key_C:
            self._calibration._on_clicked()
        elif key == QtCore.Qt.Key_Comma:
            self._intensity.set_value(max(0, self._intensity.value() - 5))
            self._on_intensity_changed(self._intensity.value())
        elif key == QtCore.Qt.Key_Period:
            self._intensity.set_value(min(100, self._intensity.value() + 5))
            self._on_intensity_changed(self._intensity.value())
        else:
            super().keyPressEvent(event)

    # ── Control message plumbing ───────────────────────────────────────────────

    def _on_intensity_changed(self, value: int) -> None:
        if self.qh is not None:
            self.qh.control_message.master_intensity_pct = int(value)

    def _on_boundary_changed(self, sag: float, frt: float) -> None:
        if self.qh is not None:
            self.qh.control_message.boundary_sagittal_deg = sag
            self.qh.control_message.boundary_frontal_deg  = frt

    def _sync_boundary_to_message(self) -> None:
        if self.qh is not None:
            self.qh.control_message.boundary_sagittal_deg = self._boundary.sagittal()
            self.qh.control_message.boundary_frontal_deg  = self._boundary.frontal()
            self.qh.control_message.master_intensity_pct  = self._intensity.value()

    def _on_calibrate(self) -> None:
        """Record the current sensor readings as neutral stance."""
        if self.qh is None:
            return
        msg = self.qh.control_message
        sag = float(getattr(msg, "pelvis_tilt_deg", 0.0))
        frt = float(getattr(msg, "pelvis_list_deg", 0.0))
        self.qh.control_message.neutral_sagittal_deg = sag
        self.qh.control_message.neutral_frontal_deg  = frt
        self._calibration.update_neutral(sag, frt)
        print(f"[VestibularTraining] Calibrated neutral — sag={sag:+.2f}° frt={frt:+.2f}°")

    def _stop_all(self) -> None:
        # No directional cues to release (strategy mutes itself when inside boundary);
        # simply ensure the master intensity message reaches the backend.
        print("[VestibularTraining] STOP ALL")

    # ── 30 Hz refresh tick ─────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._tick += 1

        # Drain inbound queue to the latest backend telemetry message.
        if self.qh is not None:
            latest = None
            while True:
                msg = self.qh.get_control_message()
                if msg is None:
                    break
                latest = msg
            if latest is not None:
                latest._on_change = self.qh.send_control_message

        msg = self.qh.control_message if self.qh else None

        # Read raw pelvis angles written by the strategy each cycle.
        sag_raw = float(getattr(msg, "pelvis_tilt_deg", 0.0)) if msg else 0.0
        frt_raw = float(getattr(msg, "pelvis_list_deg", 0.0)) if msg else 0.0

        # Apply neutral offset.  Wrap the difference to [-180, 180] so that
        # calibrating near the ±180° quaternion wrap boundary still produces
        # a small signed lean instead of ~±358°.
        neutral_sag = float(getattr(msg, "neutral_sagittal_deg", 0.0)) if msg else 0.0
        neutral_frt = float(getattr(msg, "neutral_frontal_deg",  0.0)) if msg else 0.0
        sag = _wrap_180(sag_raw - neutral_sag)
        frt = _wrap_180(frt_raw - neutral_frt)

        # Boundary values from the inspector (not from the message — GUI is authoritative).
        bnd_sag = max(0.1, self._boundary.sagittal())
        bnd_frt = max(0.1, self._boundary.frontal())

        # Normalised sway for the canvas.
        x = frt / bnd_frt
        y = sag / bnd_sag
        r = math.hypot(x, y)
        state = _classify(r)

        # Update canvas.
        self._stage.canvas.update_sway(x, y, sag, frt)
        self._stage.header.update_state(state)

        # Compute zone weights (mirrors strategy logic).
        excess = min(max(0.0, r - 1.0), _MAX_EXCESS)
        master_mult = (self._intensity.value() / _BASE_AMP_PCT) if msg else 1.0

        peak_amp = 0.0
        peak_pw  = _PW_MULT_MIN
        active   = 0
        if r > 1.0:
            theta = math.atan2(y, x)
            for z in _ZONES:
                cos_term = math.cos(theta - z.theta)
                w = max(0.0, cos_term) ** 2
                firing = w >= _WEIGHT_EPS
                amp_mult = master_mult * excess * w if firing else 0.0
                pw_mult  = (_PW_MULT_MIN + (_PW_MULT_MAX - _PW_MULT_MIN) * excess
                            if firing else _PW_MULT_MIN)
                self._monitor.update_zone(z.name, amp_mult, pw_mult, firing)
                if firing:
                    active += 1
                    peak_amp = max(peak_amp, amp_mult)
                    peak_pw  = max(peak_pw,  pw_mult)
        else:
            for z in _ZONES:
                self._monitor.update_zone(z.name, 0.0, _PW_MULT_MIN, False)

        self._intensity.set_peaks(peak_amp, peak_pw)
        self._status.update_state(
            tick=self._tick,
            active=active,
            master_pct=self._intensity.value(),
            connected=bool(getattr(msg, "suit_present", False)),
        )
