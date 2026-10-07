# SPDX-License-Identifier: MIT
"""
Haptic Proximity Radar Operator Console — PyQt5 implementation.

Layout (top → bottom):
    1. Status strip            (Jura eyebrow row: BACKEND / SUIT / TICK / ACTIVE / MASTER / clock)
    2. Main stage              (left: interactive radar canvas;
                                right: inspector panels — master intensity,
                                auto-orbit, zone monitor, channel-direction key)
    3. Safety bar              (STOP ALL + keyboard cheat-sheet)

Interaction model on the radar:
    - Click anywhere inside the disc to teleport the target puck (instant).
    - Drag the puck with the left mouse button.
    - Arrow keys nudge the puck by 2 % of R (Shift + arrow = 10 %).
    - Space toggles auto-orbit (puck circles at current radius).
    - 0 recenters (instant mute).
    - Esc / window blur fires STOP ALL.

The widget publishes ProximityControlMessage.obj_x, obj_y, master_intensity_pct
on every state change; the underlying QueueHandler auto-sends on attribute
writes via the _on_change callback registered in __init__.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from PyQt5 import QtCore, QtGui, QtWidgets

from teslasuit_rapidkit.gui.base_widget import FesWidget


# ── Teslasuit color tokens (mirror navigation example) ─────────
TS_BG_1   = "#181818"
TS_BG_2   = "#212121"
TS_BG_3   = "#252525"
TS_BG_4   = "#2D2D2D"
TS_FG_1   = "#FFFFFF"
TS_FG_2   = "#BCC0C3"
TS_FG_3   = "#7D7F82"
TS_ACCENT = "#005FFF"
TS_CHART  = "#882DFF"
TS_OK     = "#00E124"
TS_WARN   = "#F49301"
TS_ERR    = "#F40101"
TS_ERR_DEEP = "#7A0000"


# ── Zone metadata (mirrors strategy._ZONES; kept here to avoid coupling
# the GUI process to the strategy module import path). ─────────
@dataclass(frozen=True)
class _ZoneSpec:
    name: str          # internal key (matches control message terminology)
    label: str         # display label (cardinal direction)
    region: str        # body region label
    bone: str          # bone id (as string for display)
    channels: str      # channel range string
    theta: float       # cardinal angle, radians, atan2 frame


_ZONES: tuple[_ZoneSpec, ...] = (
    _ZoneSpec("belly",          "FORWARD",  "Abdomen",       "8",  "ch 0–7",  math.pi / 2),
    _ZoneSpec("right_shoulder", "RIGHT",    "R. Shoulder",   "14", "ch 0–2",  0.0),
    _ZoneSpec("back",           "BACKWARD", "Back",          "11", "ch 0–7", -math.pi / 2),
    _ZoneSpec("left_shoulder",  "LEFT",     "L. Shoulder",   "12", "ch 0–2",  math.pi),
)

# Must match strategy constants.
_PROX_SILENCE: float = 0.05
_WEIGHT_EPS:   float = 0.02
_PW_MULT_MIN:  float = 0.5
_PW_MULT_MAX:  float = 1.0
_BASE_AMP_PCT: float = 60.0
_BASE_PW_US:   float = 200.0


def _qfont(family: str = "Segoe UI", size: int = 13,
           weight: int = QtGui.QFont.Normal,
           letter_spacing: float = 0.0) -> QtGui.QFont:
    f = QtGui.QFont(family, size, weight)
    if letter_spacing:
        f.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, letter_spacing)
    return f


# ────────────────────────────────────────────────────────────────
# Radar canvas — the hero widget
# ────────────────────────────────────────────────────────────────
class _RadarCanvas(QtWidgets.QFrame):
    """Square interactive disc. Publishes (x, y) in [-1, 1]² to the tab.

    Coordinate convention: +x right (east), +y forward (north). The puck is
    snapped to the unit-disc boundary; anything outside is clipped along the
    wearer→puck vector.
    """

    PUCK_R = 18
    WEARER_R = 14

    target_changed = QtCore.pyqtSignal(float, float)  # (x, y) normalized

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setMinimumSize(420, 420)
        self.setStyleSheet(
            f"background: {TS_BG_2}; border-radius: 8px;"
        )

        # Normalized target position; (0,0) = wearer.
        self._x: float = 0.0
        self._y: float = 0.0
        self._dragging: bool = False
        self._hover: bool = False
        # Last broadcast weights per zone (for overlay & inspector parity).
        self.last_weights: dict[str, float] = {z.name: 0.0 for z in _ZONES}
        self.last_prox: float = 0.0

    # ── geometry helpers ───────────────────────────────────────
    def _disc_geom(self) -> tuple[QtCore.QPointF, float]:
        rect = self.rect()
        side = min(rect.width(), rect.height()) - 24  # 12 px padding
        center = QtCore.QPointF(rect.center())
        return center, side / 2.0

    def _to_widget(self, x: float, y: float) -> QtCore.QPointF:
        center, radius = self._disc_geom()
        # +y is forward → up on screen → negative pixel y.
        return QtCore.QPointF(center.x() + x * radius,
                              center.y() - y * radius)

    def _to_normalized(self, pt: QtCore.QPointF) -> tuple[float, float]:
        center, radius = self._disc_geom()
        if radius <= 0:
            return 0.0, 0.0
        x = (pt.x() - center.x()) / radius
        y = -(pt.y() - center.y()) / radius
        r = math.hypot(x, y)
        if r > 1.0:
            x /= r
            y /= r
        return x, y

    # ── public API ─────────────────────────────────────────────
    def position(self) -> tuple[float, float]:
        return self._x, self._y

    def set_position(self, x: float, y: float, *, emit: bool = True) -> None:
        r = math.hypot(x, y)
        if r > 1.0:
            x /= r
            y /= r
        if (x, y) == (self._x, self._y):
            return
        self._x, self._y = x, y
        self.last_prox = max(0.0, 1.0 - math.hypot(x, y))
        self._recompute_weights()
        self.update()
        if emit:
            self.target_changed.emit(self._x, self._y)

    def nudge(self, dx: float, dy: float) -> None:
        self.set_position(self._x + dx, self._y + dy)

    def recenter(self) -> None:
        self.set_position(0.0, 0.0)

    # ── input ──────────────────────────────────────────────────
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.LeftButton:
            return super().mousePressEvent(event)
        x, y = self._to_normalized(event.pos())
        # If the click landed on the puck, just begin dragging; otherwise
        # teleport the puck to the click location (still inside disc).
        puck_pt = self._to_widget(self._x, self._y)
        if (puck_pt - event.pos()).manhattanLength() <= self.PUCK_R + 4:
            self._dragging = True
        else:
            self._dragging = True
            self.set_position(x, y)
        self.setCursor(QtCore.Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._dragging:
            x, y = self._to_normalized(event.pos())
            self.set_position(x, y)
        else:
            puck_pt = self._to_widget(self._x, self._y)
            over = (puck_pt - event.pos()).manhattanLength() <= self.PUCK_R + 2
            if over != self._hover:
                self._hover = over
                self.setCursor(QtCore.Qt.OpenHandCursor if over else QtCore.Qt.ArrowCursor)
                self.update()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(QtCore.Qt.OpenHandCursor if self._hover else QtCore.Qt.ArrowCursor)
            self.update()

    # ── computation ────────────────────────────────────────────
    def _recompute_weights(self) -> None:
        x, y = self._x, self._y
        r = math.hypot(x, y)
        prox = max(0.0, 1.0 - r)
        self.last_prox = prox
        if r == 0.0 or prox <= _PROX_SILENCE:
            for z in _ZONES:
                self.last_weights[z.name] = 0.0
            return
        theta = math.atan2(y, x)
        for z in _ZONES:
            cos_term = math.cos(theta - z.theta)
            w = max(0.0, cos_term) ** 2
            self.last_weights[z.name] = w if w >= _WEIGHT_EPS else 0.0

    # ── painting ───────────────────────────────────────────────
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        center, radius = self._disc_geom()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        # Sector heatmap — four pie wedges aligned to cardinals.
        for z in _ZONES:
            w = self.last_weights.get(z.name, 0.0)
            if w <= 0.0:
                continue
            alpha = int(min(0.7, w * self.last_prox) * 255)
            color = QtGui.QColor(0, 95, 255, alpha)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(color)
            # Qt angle units: 1/16 degree, 0 at east (+x), CCW positive.
            # Our z.theta is also CCW from east, so direct mapping works.
            start_deg = math.degrees(z.theta) - 45
            painter.drawPie(
                QtCore.QRectF(center.x() - radius, center.y() - radius,
                              radius * 2, radius * 2),
                int(start_deg * 16),
                int(90 * 16),
            )

        # Concentric rings.
        pen = QtGui.QPen(QtGui.QColor(TS_BG_4))
        for i, frac in enumerate((0.25, 0.5, 0.75, 1.0)):
            pen.setWidthF(1.5 if frac == 1.0 else 1.0)
            pen.setStyle(QtCore.Qt.SolidLine if frac == 1.0 else QtCore.Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            r_px = radius * frac
            painter.drawEllipse(center, r_px, r_px)

        # Cardinal tick marks + labels.
        painter.setPen(QtGui.QPen(QtGui.QColor(TS_FG_3), 1.0))
        font = _qfont("Jura", 10, QtGui.QFont.DemiBold, letter_spacing=1.4)
        painter.setFont(font)
        for z in _ZONES:
            tx = center.x() + math.cos(z.theta) * radius
            ty = center.y() - math.sin(z.theta) * radius
            painter.drawLine(
                QtCore.QPointF(tx, ty),
                QtCore.QPointF(tx + math.cos(z.theta) * 8,
                               ty - math.sin(z.theta) * 8),
            )
            # Label outside the tick, offset along the radial direction.
            lx = center.x() + math.cos(z.theta) * (radius + 26)
            ly = center.y() - math.sin(z.theta) * (radius + 26)
            text = f"{z.label}  ·  bone {z.bone}"
            metrics = painter.fontMetrics()
            tw = metrics.horizontalAdvance(text)
            painter.setPen(QtGui.QColor(TS_FG_2))
            painter.drawText(QtCore.QPointF(lx - tw / 2, ly + 4), text)
            painter.setPen(QtGui.QPen(QtGui.QColor(TS_FG_3), 1.0))

        # Wearer marker (centered crosshair ring).
        wearer_pen = QtGui.QPen(QtGui.QColor(TS_FG_1), 2.0)
        painter.setPen(wearer_pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawEllipse(center, self.WEARER_R, self.WEARER_R)
        painter.setPen(QtGui.QPen(QtGui.QColor(TS_FG_3), 1.0))
        painter.drawLine(center.x() - 4, center.y(), center.x() + 4, center.y())
        painter.drawLine(center.x(), center.y() - 4, center.x(), center.y() + 4)

        # Leash from wearer → puck while dragging.
        puck_pt = self._to_widget(self._x, self._y)
        if self._dragging:
            leash = QtGui.QPen(QtGui.QColor(0, 95, 255, 200), 1.0, QtCore.Qt.DashLine)
            painter.setPen(leash)
            painter.drawLine(center, puck_pt)

        # Puck — glow when dragging or near.
        if self._dragging or self.last_prox > 0.6:
            glow = QtGui.QRadialGradient(puck_pt, self.PUCK_R + 14)
            glow.setColorAt(0.0, QtGui.QColor(0, 95, 255, 160))
            glow.setColorAt(1.0, QtGui.QColor(0, 95, 255, 0))
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(puck_pt, self.PUCK_R + 14, self.PUCK_R + 14)
        stroke = QtGui.QColor(TS_ACCENT) if (self._hover or self._dragging) else QtGui.QColor(TS_BG_4)
        painter.setPen(QtGui.QPen(stroke, 1.5))
        painter.setBrush(QtGui.QColor(TS_FG_1))
        painter.drawEllipse(puck_pt, self.PUCK_R, self.PUCK_R)

        # Corner readouts.
        painter.setPen(QtGui.QColor(TS_FG_3))
        painter.setFont(_qfont("Jura", 10, QtGui.QFont.Light, letter_spacing=1.2))
        r = math.hypot(self._x, self._y)
        theta = math.degrees(math.atan2(self._y, self._x)) if r > 0 else 0.0
        armed = ", ".join(
            f"{z.label.lower()}" for z in _ZONES
            if self.last_weights.get(z.name, 0.0) > 0.0
        ) or "—"
        painter.drawText(QtCore.QPointF(14, 20), f"r     {r:.2f}")
        painter.drawText(QtCore.QPointF(self.width() - 110, 20),
                         f"θ    {theta:+6.1f}°")
        painter.drawText(QtCore.QPointF(14, self.height() - 12),
                         f"prox  {self.last_prox:.2f}")
        painter.drawText(QtCore.QPointF(self.width() - 260, self.height() - 12),
                         f"armed  {armed}")

        painter.end()


# ────────────────────────────────────────────────────────────────
# Inspector panels
# ────────────────────────────────────────────────────────────────
class _Panel(QtWidgets.QFrame):
    def __init__(self, title: str, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {TS_BG_2}; border-top: 1px solid {TS_BG_4};"
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        self._layout = layout
        if title:
            eyebrow = QtWidgets.QLabel(title)
            eyebrow.setFont(_qfont("Jura", 11, QtGui.QFont.DemiBold,
                                   letter_spacing=1.4))
            eyebrow.setStyleSheet(f"color: {TS_FG_3};")
            layout.addWidget(eyebrow)

    def addRow(self, widget: QtWidgets.QWidget) -> None:
        self._layout.addWidget(widget)


class _ZoneMonitor(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {TS_BG_2};")
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        header = ("ZONE", "BONE", "AMP", "PW", "STATE")
        for col, label in enumerate(header):
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
            bone_lbl.setStyleSheet(f"color: {TS_FG_3};")
            bone_lbl.setFont(_qfont("Jura", 11, QtGui.QFont.Light))
            amp_lbl = QtWidgets.QLabel("0.00")
            pw_lbl = QtWidgets.QLabel("0.50")
            for lbl in (amp_lbl, pw_lbl):
                lbl.setFont(_qfont("Jura", 12, QtGui.QFont.DemiBold))
                lbl.setStyleSheet(f"color: {TS_FG_2};")
            state_lbl = QtWidgets.QLabel("muted")
            state_lbl.setFont(_qfont("Jura", 10, QtGui.QFont.DemiBold, letter_spacing=1.4))
            state_lbl.setStyleSheet(
                f"color: {TS_FG_3}; padding: 2px 8px; background: {TS_BG_3}; border-radius: 6px;"
            )
            grid.addWidget(name_lbl, row_idx, 0)
            grid.addWidget(bone_lbl, row_idx, 1)
            grid.addWidget(amp_lbl, row_idx, 2)
            grid.addWidget(pw_lbl, row_idx, 3)
            grid.addWidget(state_lbl, row_idx, 4)
            self._rows[z.name] = {
                "amp": amp_lbl, "pw": pw_lbl, "state": state_lbl,
            }

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


# ────────────────────────────────────────────────────────────────
# RadarTab — top-level container
# ────────────────────────────────────────────────────────────────
class RadarTab(FesWidget):
    always_update = True  # keep status strip & monitor fresh even if hidden

    AUTO_ORBIT_DEFAULT_DPS = 30.0

    def build_ui(self) -> None:
        outer = self.layout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Status strip ──
        self._status = _StatusStrip(self)
        outer.addWidget(self._status)

        # ── Main stage ──
        stage = QtWidgets.QWidget(self)
        stage_layout = QtWidgets.QHBoxLayout(stage)
        stage_layout.setContentsMargins(16, 12, 16, 12)
        stage_layout.setSpacing(16)
        outer.addWidget(stage, stretch=1)

        # Radar canvas
        self.canvas = _RadarCanvas(stage)
        self.canvas.target_changed.connect(self._on_target_changed)
        stage_layout.addWidget(self.canvas, stretch=65)

        # Right inspector column
        inspector = QtWidgets.QWidget(stage)
        insp_layout = QtWidgets.QVBoxLayout(inspector)
        insp_layout.setContentsMargins(0, 0, 0, 0)
        insp_layout.setSpacing(0)
        stage_layout.addWidget(inspector, stretch=35)

        # Master intensity panel
        master_panel = _Panel("MASTER INTENSITY", inspector)
        self._master_value = QtWidgets.QLabel("60 %")
        self._master_value.setFont(_qfont("Jura", 28, QtGui.QFont.DemiBold))
        self._master_value.setStyleSheet(f"color: {TS_FG_1};")
        master_panel.addRow(self._master_value)
        self._master_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._master_slider.setRange(0, 100)
        self._master_slider.setValue(60)
        self._master_slider.setStyleSheet(self._slider_qss())
        self._master_slider.valueChanged.connect(self._on_master_changed)
        master_panel.addRow(self._master_slider)
        self._peaks = QtWidgets.QLabel("PEAK AMP  0%        PEAK PW  100 µs")
        self._peaks.setFont(_qfont("Jura", 11, QtGui.QFont.Light, letter_spacing=1.4))
        self._peaks.setStyleSheet(f"color: {TS_FG_3};")
        master_panel.addRow(self._peaks)
        insp_layout.addWidget(master_panel)

        # Auto-orbit panel
        orbit_panel = _Panel("AUTO-ORBIT", inspector)
        self._orbit_toggle = QtWidgets.QCheckBox("auto-orbit")
        self._orbit_toggle.setStyleSheet(f"color: {TS_FG_2};")
        self._orbit_toggle.toggled.connect(self._on_orbit_toggled)
        orbit_panel.addRow(self._orbit_toggle)
        speed_row = QtWidgets.QWidget()
        sr_layout = QtWidgets.QHBoxLayout(speed_row)
        sr_layout.setContentsMargins(0, 0, 0, 0)
        sr_label = QtWidgets.QLabel("angular speed")
        sr_label.setStyleSheet(f"color: {TS_FG_3};")
        sr_layout.addWidget(sr_label)
        self._orbit_speed = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._orbit_speed.setRange(5, 180)
        self._orbit_speed.setValue(int(self.AUTO_ORBIT_DEFAULT_DPS))
        self._orbit_speed.setStyleSheet(self._slider_qss())
        sr_layout.addWidget(self._orbit_speed, stretch=1)
        self._orbit_speed_value = QtWidgets.QLabel(f"{int(self.AUTO_ORBIT_DEFAULT_DPS)} °/s")
        self._orbit_speed_value.setStyleSheet(f"color: {TS_FG_2};")
        self._orbit_speed.valueChanged.connect(
            lambda v: self._orbit_speed_value.setText(f"{v} °/s")
        )
        sr_layout.addWidget(self._orbit_speed_value)
        orbit_panel.addRow(speed_row)
        hint = QtWidgets.QLabel("Space toggles. Useful for calibration sweeps.")
        hint.setStyleSheet(f"color: {TS_FG_3};")
        hint.setFont(_qfont("Jura", 11, QtGui.QFont.Light))
        orbit_panel.addRow(hint)
        insp_layout.addWidget(orbit_panel)

        # Zone monitor panel
        monitor_panel = _Panel("ZONE MONITOR", inspector)
        self._monitor = _ZoneMonitor(monitor_panel)
        monitor_panel.addRow(self._monitor)
        insp_layout.addWidget(monitor_panel)
        insp_layout.addStretch(1)

        # ── Safety bar ──
        self._safety = _SafetyBar(self)
        self._safety.stop_pressed.connect(self._stop_all)
        outer.addWidget(self._safety)

        # ── State ──
        self._auto_orbit_t0 = time.monotonic()
        self._auto_orbit_angle = 0.0
        self._tick = 0

        # Push the initial control state once so the backend agrees with us.
        self._on_target_changed(0.0, 0.0)
        self._on_master_changed(60)

    # ── styling helpers ────────────────────────────────────────
    @staticmethod
    def _slider_qss() -> str:
        return (
            f"QSlider::groove:horizontal {{ background: {TS_BG_3}; height: 4px; border-radius: 2px; }}"
            f"QSlider::sub-page:horizontal {{ background: {TS_ACCENT}; border-radius: 2px; }}"
            f"QSlider::handle:horizontal {{ background: {TS_ACCENT}; width: 14px; height: 14px; "
            f"  margin: -6px 0; border-radius: 7px; }}"
        )

    # ── input plumbing ─────────────────────────────────────────
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if key == QtCore.Qt.Key_Escape:
            self._stop_all()
            return
        if key == QtCore.Qt.Key_0:
            self.canvas.recenter()
            return
        if key == QtCore.Qt.Key_Space:
            self._orbit_toggle.toggle()
            return
        step = 0.10 if (event.modifiers() & QtCore.Qt.ShiftModifier) else 0.02
        if key == QtCore.Qt.Key_Up:
            self.canvas.nudge(0.0, +step)
        elif key == QtCore.Qt.Key_Down:
            self.canvas.nudge(0.0, -step)
        elif key == QtCore.Qt.Key_Left:
            self.canvas.nudge(-step, 0.0)
        elif key == QtCore.Qt.Key_Right:
            self.canvas.nudge(+step, 0.0)
        elif key == QtCore.Qt.Key_Comma:
            self._master_slider.setValue(self._master_slider.value() - 5)
        elif key == QtCore.Qt.Key_Period:
            self._master_slider.setValue(self._master_slider.value() + 5)
        else:
            super().keyPressEvent(event)

    # Window blur → STOP ALL (mirrors haptic_navigation behavior).
    def changeEvent(self, event: QtCore.QEvent) -> None:
        if event.type() == QtCore.QEvent.ActivationChange:
            top = self.window()
            if top is not None and not top.isActiveWindow():
                self._stop_all()
        super().changeEvent(event)

    # ── target / master plumbing ───────────────────────────────
    def _on_target_changed(self, x: float, y: float) -> None:
        if self.qh is None:
            return
        # Two assignments → two queue messages, but auto-coalescing in the
        # backend is fine; pairing them keeps the protocol trivial.
        self.qh.control_message.obj_x = float(x)
        self.qh.control_message.obj_y = float(y)

    def _on_master_changed(self, value: int) -> None:
        self._master_value.setText(f"{int(value)} %")
        if self.qh is not None:
            self.qh.control_message.master_intensity_pct = int(value)

    def _on_orbit_toggled(self, enabled: bool) -> None:
        self._auto_orbit_t0 = time.monotonic()
        x, y = self.canvas.position()
        self._auto_orbit_angle = math.atan2(y, x) if (x or y) else 0.0
        if enabled and math.hypot(x, y) < 0.1:
            # Kick the puck out a bit so the orbit is visible.
            self.canvas.set_position(0.5, 0.0)

    def _stop_all(self) -> None:
        self._orbit_toggle.setChecked(False)
        self.canvas.recenter()

    # ── 30 Hz refresh tick ─────────────────────────────────────
    def refresh(self) -> None:
        self._tick += 1

        # Auto-orbit advance.
        if self._orbit_toggle.isChecked():
            dt = 1.0 / 30.0  # FesApp refresh cadence
            self._auto_orbit_angle += math.radians(self._orbit_speed.value()) * dt
            r = max(0.1, math.hypot(*self.canvas.position()))
            self.canvas.set_position(
                r * math.cos(self._auto_orbit_angle),
                r * math.sin(self._auto_orbit_angle),
            )

        # Update zone monitor & peak readouts.
        master = self._master_slider.value() / _BASE_AMP_PCT
        prox = self.canvas.last_prox
        peak_amp = 0.0
        peak_pw = _PW_MULT_MIN
        active = 0
        for z in _ZONES:
            w = self.canvas.last_weights.get(z.name, 0.0)
            firing = w > 0.0 and prox > _PROX_SILENCE
            amp_mult = master * prox * w if firing else 0.0
            pw_mult = (_PW_MULT_MIN + (_PW_MULT_MAX - _PW_MULT_MIN) * prox
                       if firing else _PW_MULT_MIN)
            self._monitor.update_zone(z.name, amp_mult, pw_mult, firing)
            if firing:
                active += 1
                peak_amp = max(peak_amp, amp_mult)
                peak_pw = max(peak_pw, pw_mult)
        self._peaks.setText(
            f"PEAK AMP  {int(peak_amp * 100)}%        "
            f"PEAK PW  {int(peak_pw * _BASE_PW_US)} µs"
        )
        self._status.update_state(
            tick=self._tick,
            active=active,
            master_pct=self._master_slider.value(),
            connected=(self.data is not None and getattr(self.data, "is_connected", False)),
        )


# ────────────────────────────────────────────────────────────────
# Status strip + safety bar
# ────────────────────────────────────────────────────────────────
class _StatusStrip(QtWidgets.QFrame):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet(f"background: {TS_BG_2};")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(28)

        self._cells: dict[str, QtWidgets.QLabel] = {}
        for key, label in (
            ("backend", "BACKEND"),
            ("suit", "SUIT"),
            ("tick", "TICK"),
            ("active", "ACTIVE"),
            ("master", "MASTER"),
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

        self._clock_timer = QtCore.QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)
        self._tick_clock()

    def _tick_clock(self) -> None:
        self._clock.setText(time.strftime("%H:%M:%S"))

    def update_state(self, *, tick: int, active: int, master_pct: int,
                     connected: bool) -> None:
        self._cells["backend"].setText("OK")
        self._cells["backend"].setStyleSheet(f"color: {TS_OK};")
        self._cells["suit"].setText("CONNECTED" if connected else "OFFLINE")
        self._cells["suit"].setStyleSheet(
            f"color: {TS_OK if connected else TS_FG_3};"
        )
        self._cells["tick"].setText(f"{tick:04d}")
        self._cells["active"].setText(f"{active}/4")
        if active == 0:
            color = TS_FG_3
        elif active <= 2:
            color = TS_ACCENT
        else:
            color = TS_WARN
        self._cells["active"].setStyleSheet(f"color: {color};")
        self._cells["master"].setText(f"{master_pct}%")


class _SafetyBar(QtWidgets.QFrame):
    stop_pressed = QtCore.pyqtSignal()

    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.setStyleSheet(f"background: {TS_BG_2}; border-top: 1px solid {TS_BG_4};")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)

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
        layout.addWidget(stop)

        cheats = QtWidgets.QLabel(
            "DRAG  ·  ARROWS nudge  ·  SHIFT+ARROW jump  ·  "
            "SPACE orbit  ·  0 center  ·  ESC stop"
        )
        cheats.setFont(_qfont("Jura", 11, QtGui.QFont.Light, letter_spacing=1.4))
        cheats.setStyleSheet(f"color: {TS_FG_3};")
        layout.addStretch(1)
        layout.addWidget(cheats)
