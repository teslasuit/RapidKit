# SPDX-License-Identifier: MIT
"""
Haptic Navigation Operator Console — PyQt5 port of the Teslasuit-styled design.

What's in here:
- Top status strip (backend / suit / tick / active count / intensity / clock).
- Stage header with eyebrow, diagonal-mode badge, and idle/firing pill.
- Hero compass: concentric rings, cardinal ticks, body silhouette in the middle
  with per-direction zone overlays, and four direction indicators sitting on
  the perimeter.
- Right inspector with the global intensity slider, diagonal-mode summary,
  and a bone-mapping table.
- Bottom safety bar: STOP ALL button (Esc) + cheat sheet.
- Window-blur releases all cues; Esc fires STOP ALL.

The visual style mirrors the Claude-Design handoff under
``examples/haptic_navigation/gui/assets/`` (body silhouette PNGs and Jura fonts).
"""
from __future__ import annotations

from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

from teslasuit_rapidkit.gui.base_widget import FesWidget


# ── Asset paths ─────────────────────────────────────────────────
_ASSETS = Path(__file__).resolve().parent / "assets"
_BODY_DIR = _ASSETS / "body"
_FONT_DIR = _ASSETS / "fonts"


# ── Direction metadata ─────────────────────────────────────────
DIRS = ("forward", "right", "backward", "left")  # N E S W

DIR_META = {
    "forward":  {"label": "FORWARD",  "arrow": "↑", "key": "↑",
                 "bone": "8",  "channels": "ch 0–7", "region": "Abdomen"},
    "right":    {"label": "RIGHT",    "arrow": "→", "key": "→",
                 "bone": "14", "channels": "ch 0–2", "region": "R. Shoulder"},
    "backward": {"label": "BACKWARD", "arrow": "↓", "key": "↓",
                 "bone": "11", "channels": "ch 0–7", "region": "Back"},
    "left":     {"label": "LEFT",     "arrow": "←", "key": "←",
                 "bone": "12", "channels": "ch 0–2", "region": "L. Shoulder"},
}

_KEY_TO_FIELD = {
    QtCore.Qt.Key_Up:    "forward",
    QtCore.Qt.Key_Down:  "backward",
    QtCore.Qt.Key_Left:  "left",
    QtCore.Qt.Key_Right: "right",
}

_ZONE_FILES = {
    "forward":  "zone-front.png",
    "right":    "zone-right.png",
    "backward": "zone-back.png",
    "left":     "zone-left.png",
}


# ── Teslasuit color tokens (mirror ds/colors_and_type.css) ─────
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

# Diagonal multiplier: must match _DIAGONAL_PW_MULT in the strategy.
_DIAGONAL_PW_MULT = 0.7


# ── Font registration (called once from the FesApp shell) ──────
def register_fonts() -> None:
    """Register bundled Jura fonts so the QSS strings can name them."""
    db = QtGui.QFontDatabase
    for ttf in _FONT_DIR.glob("Jura-*.ttf"):
        db.addApplicationFont(str(ttf))


# ── Small helpers ──────────────────────────────────────────────
def _qfont(family: str = "Segoe UI", size: int = 13, weight: int = QtGui.QFont.Normal,
           letter_spacing: float = 0.0) -> QtGui.QFont:
    f = QtGui.QFont(family, size, weight)
    if letter_spacing:
        f.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, letter_spacing)
    return f


# ── Compass ring (round border drawn via QPainter) ─────────────
class _Ring(QtWidgets.QWidget):
    """A single concentric circle border. Draws via QPainter so we get an
    actual ring rather than a rounded-rectangle border."""

    def __init__(self, parent: QtWidgets.QWidget, color: str, dashed: bool = False):
        super().__init__(parent)
        self._pen = QtGui.QPen(QtGui.QColor(color))
        self._pen.setWidthF(1.0)
        if dashed:
            self._pen.setStyle(QtCore.Qt.DashLine)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(self._pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawEllipse(rect)


# ── Body silhouette stack ──────────────────────────────────────
class _BodySilhouette(QtWidgets.QFrame):
    """Idle silhouette + 4 stacked zone overlays. All images share the same
    drawing rect (object-fit: contain on the parent's aspect-ratio box)."""

    ASPECT_W, ASPECT_H = 549, 587

    def __init__(self, parent):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        self._base = self._load(_BODY_DIR / "idle.png")
        self._zones = {
            name: self._load(_BODY_DIR / fname, hidden=True)
            for name, fname in _ZONE_FILES.items()
        }

    def _load(self, path: Path, hidden: bool = False) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(self)
        # Hold the original full-resolution pixmap on the label; the
        # resizeEvent below scales from this source every time so we never
        # progressively degrade by re-scaling an already-scaled pixmap.
        original = QtGui.QPixmap(str(path))
        label._original_pixmap = original  # type: ignore[attr-defined]
        label.setPixmap(original)
        label.setAlignment(QtCore.Qt.AlignCenter)
        label.setScaledContents(False)
        label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        label.setStyleSheet("background: transparent;")
        if hidden:
            label.hide()
        return label

    def set_active(self, field: str, on: bool) -> None:
        if field in self._zones:
            self._zones[field].setVisible(on)

    def resizeEvent(self, event):
        rect = self.rect()
        for label in (self._base, *self._zones.values()):
            label.setGeometry(rect)
            original = getattr(label, "_original_pixmap", None)
            if original is not None and not original.isNull():
                label.setPixmap(original.scaled(
                    rect.size(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                ))
        super().resizeEvent(event)


# ── Direction indicator (round glyph + keycap + label + readout) ──
class _DirIndicator(QtWidgets.QFrame):
    GLYPH_SIZE = 72

    def __init__(self, parent, direction: str, position: str):
        """position: 'n' | 's' | 'w' | 'e' — controls layout orientation."""
        super().__init__(parent)
        self._dir = direction
        self._position = position
        self._firing = False
        self._diag = False
        meta = DIR_META[direction]

        # Glyph (the round arrow circle)
        self._glyph = QtWidgets.QLabel(meta["arrow"])
        self._glyph.setAlignment(QtCore.Qt.AlignCenter)
        self._glyph.setFixedSize(self.GLYPH_SIZE, self.GLYPH_SIZE)
        self._glyph.setObjectName("dirGlyph")

        # Glow effect on the glyph (toggled when firing)
        self._glow = QtWidgets.QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(0)
        self._glow.setOffset(0, 0)
        self._glow.setColor(QtGui.QColor(0, 95, 255, 180))
        self._glyph.setGraphicsEffect(self._glow)

        # Keycap
        self._keycap = QtWidgets.QLabel(meta["key"])
        self._keycap.setAlignment(QtCore.Qt.AlignCenter)
        self._keycap.setFixedSize(28, 24)
        self._keycap.setObjectName("dirKeycap")

        # Label
        self._label = QtWidgets.QLabel(meta["label"])
        self._label.setAlignment(QtCore.Qt.AlignCenter)
        self._label.setObjectName("dirLabel")

        # Readout (effective intensity / multiplier).
        # Lock its size — the text grows from "—" to e.g. "60%  ×0.70" on press,
        # and without a fixed bounding box the parent QVBoxLayout would re-flow,
        # making the glyph appear to wobble (worst in diagonal mode).
        self._readout = QtWidgets.QLabel("—")
        self._readout.setAlignment(QtCore.Qt.AlignCenter)
        self._readout.setFixedSize(82, 14)
        self._readout.setObjectName("dirReadout")

        self._build_layout(position)
        self._refresh_styles()

    def _build_layout(self, position: str) -> None:
        # Stack of {keycap / label / readout} positioned away from compass center.
        text_stack = QtWidgets.QVBoxLayout()
        text_stack.setSpacing(2)
        text_stack.setContentsMargins(0, 0, 0, 0)
        align = (QtCore.Qt.AlignHCenter if position in ("n", "s")
                 else QtCore.Qt.AlignRight if position == "w"
                 else QtCore.Qt.AlignLeft)
        text_stack.addWidget(self._keycap, 0, align)
        text_stack.addWidget(self._label, 0, align)
        text_stack.addWidget(self._readout, 0, align)

        if position == "n":
            outer = QtWidgets.QVBoxLayout(self)
            outer.setSpacing(6)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addLayout(text_stack)
            outer.addWidget(self._glyph, 0, QtCore.Qt.AlignHCenter)
        elif position == "s":
            outer = QtWidgets.QVBoxLayout(self)
            outer.setSpacing(6)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(self._glyph, 0, QtCore.Qt.AlignHCenter)
            outer.addLayout(text_stack)
        elif position == "w":
            outer = QtWidgets.QHBoxLayout(self)
            outer.setSpacing(10)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addLayout(text_stack)
            outer.addWidget(self._glyph)
        else:  # e
            outer = QtWidgets.QHBoxLayout(self)
            outer.setSpacing(10)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.addWidget(self._glyph)
            outer.addLayout(text_stack)

    def set_state(self, firing: bool, diag: bool, intensity_pct: int,
                  multiplier: float) -> None:
        self._firing = firing
        self._diag = diag and firing
        if firing:
            eff = round(intensity_pct * multiplier)
            self._readout.setText(
                f"{eff}%  ×{multiplier:.2f}" if diag else f"{eff}%"
            )
        else:
            self._readout.setText("—")
        self._refresh_styles()

    def _refresh_styles(self) -> None:
        if self._firing:
            glyph_bg = TS_ACCENT
            glyph_color = TS_FG_1
            glyph_border = TS_ACCENT
            self._glow.setBlurRadius(28)
            if self._diag:
                self._glow.setColor(QtGui.QColor(136, 45, 255, 200))
            else:
                self._glow.setColor(QtGui.QColor(0, 95, 255, 200))
        else:
            glyph_bg = TS_BG_2
            glyph_color = TS_FG_3
            glyph_border = TS_BG_4
            self._glow.setBlurRadius(0)

        # Glyph font-size is held constant at 28px so the arrow doesn't
        # nudge against the circle edge when the indicator is firing.
        self._glyph.setStyleSheet(f"""
            QLabel#dirGlyph {{
                background: {glyph_bg};
                color: {glyph_color};
                border: 1.5px solid {glyph_border};
                border-radius: {self.GLYPH_SIZE // 2}px;
                font-size: 28px;
                font-weight: 500;
            }}
        """)

        keycap_active = self._firing
        keycap_bg = "rgba(0,95,255,0.18)" if keycap_active else TS_BG_1
        keycap_color = TS_FG_1 if keycap_active else TS_FG_3
        keycap_border = TS_ACCENT if keycap_active else TS_BG_4
        self._keycap.setStyleSheet(f"""
            QLabel#dirKeycap {{
                background: {keycap_bg};
                border: 1px solid {keycap_border};
                border-bottom: 2px solid {keycap_border};
                border-radius: 4px;
                color: {keycap_color};
                font-family: 'Jura', 'Segoe UI';
                font-size: 11px;
                font-weight: 500;
            }}
        """)

        label_color = TS_ACCENT if self._firing else TS_FG_3
        self._label.setStyleSheet(f"""
            QLabel#dirLabel {{
                background: transparent;
                color: {label_color};
                font-family: 'Jura', 'Segoe UI';
                font-size: 10px;
                font-weight: 500;
                letter-spacing: 1.8px;
            }}
        """)
        readout_color = TS_FG_1 if self._firing else TS_FG_3
        self._readout.setStyleSheet(f"""
            QLabel#dirReadout {{
                background: transparent;
                color: {readout_color};
                font-family: 'Jura', 'Segoe UI';
                font-size: 10px;
                font-weight: 500;
                letter-spacing: 1.0px;
            }}
        """)


# ── Compass: rings + ticks + silhouette + 4 indicators ─────────
class _Compass(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 420)
        self.setStyleSheet("background: transparent;")

        self._rings = [
            _Ring(self, "#232323"),
            _Ring(self, "#1d1d1d"),
            _Ring(self, "#1a1a1a"),
            _Ring(self, "#232323", dashed=True),
        ]

        self._ticks = {}
        for code, text in (("n", "N · 000°"), ("e", "E · 090°"),
                           ("s", "S · 180°"), ("w", "W · 270°")):
            label = QtWidgets.QLabel(text, self)
            label.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    color: {TS_FG_3};
                    font-family: 'Jura', 'Segoe UI';
                    font-size: 9px;
                    font-weight: 500;
                    letter-spacing: 1.6px;
                }}
            """)
            label.adjustSize()
            label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            self._ticks[code] = label

        self._silhouette = _BodySilhouette(self)

        self._indicators = {
            "forward":  _DirIndicator(self, "forward",  "n"),
            "right":    _DirIndicator(self, "right",    "e"),
            "backward": _DirIndicator(self, "backward", "s"),
            "left":     _DirIndicator(self, "left",     "w"),
        }

        # Center multiplier readout (visible when ≥2 active)
        self._mult_label = QtWidgets.QLabel("", self)
        self._mult_label.setAlignment(QtCore.Qt.AlignCenter)
        self._mult_label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._mult_label.hide()

    # ── Layout: every child positioned on the inscribed square ─
    def resizeEvent(self, event):
        w, h = self.width(), self.height()
        side = min(w, h)
        x0 = (w - side) // 2
        y0 = (h - side) // 2

        for ring, inset in zip(self._rings, (0.0, 0.08, 0.18, 0.28)):
            d = side - 2 * int(side * inset)
            cx = x0 + side // 2
            cy = y0 + side // 2
            ring.setGeometry(cx - d // 2, cy - d // 2, d, d)

        for code, label in self._ticks.items():
            label.adjustSize()
            tw, th = label.width(), label.height()
            cx = x0 + side // 2
            cy = y0 + side // 2
            if code == "n":
                label.move(cx - tw // 2, y0 - th - 2)
            elif code == "s":
                label.move(cx - tw // 2, y0 + side + 4)
            elif code == "w":
                label.move(x0 - tw - 6, cy - th // 2)
            else:  # e
                label.move(x0 + side + 6, cy - th // 2)

        # Silhouette: center, ~36% of compass width, aspect 549:587
        s_w = int(side * 0.36)
        s_h = int(s_w * _BodySilhouette.ASPECT_H / _BodySilhouette.ASPECT_W)
        self._silhouette.setGeometry(
            x0 + side // 2 - s_w // 2,
            y0 + side // 2 - s_h // 2,
            s_w, s_h,
        )

        for name, ind in self._indicators.items():
            ind.adjustSize()
            iw, ih = ind.sizeHint().width(), ind.sizeHint().height()
            ind.resize(iw, ih)
            cx = x0 + side // 2
            cy = y0 + side // 2
            if name == "forward":
                ind.move(cx - iw // 2, y0)
            elif name == "backward":
                ind.move(cx - iw // 2, y0 + side - ih)
            elif name == "left":
                ind.move(x0, cy - ih // 2)
            else:  # right
                ind.move(x0 + side - iw, cy - ih // 2)

        # Center multiplier readout sits below the silhouette
        self._mult_label.adjustSize()
        mw, mh = self._mult_label.width(), self._mult_label.height()
        self._mult_label.move(
            x0 + side // 2 - mw // 2,
            y0 + side // 2 + s_h // 2 + 4,
        )
        super().resizeEvent(event)

    # ── External API: drive visuals from active set + intensity ─
    def update_state(self, active: set, intensity_pct: int) -> None:
        diag = len(active) >= 2
        multiplier = _DIAGONAL_PW_MULT if diag else 1.0
        for name, ind in self._indicators.items():
            firing = name in active
            ind.set_state(firing, diag, intensity_pct, multiplier)
            self._silhouette.set_active(name, firing)
        if diag:
            self._mult_label.setText(
                f"PULSE-WIDTH MULTIPLIER  ×{multiplier:.2f}"
            )
            self._mult_label.setStyleSheet(f"""
                QLabel {{
                    background: transparent;
                    color: {TS_CHART};
                    font-family: 'Jura', 'Segoe UI';
                    font-size: 11px;
                    font-weight: 500;
                    letter-spacing: 1.4px;
                }}
            """)
            self._mult_label.adjustSize()
            self._mult_label.show()
        else:
            self._mult_label.hide()


# ── Status strip ───────────────────────────────────────────────
class _StatusStrip(QtWidgets.QFrame):
    """Top strip: backend / suit / tick / active / intensity / clock."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusStrip")
        self.setFixedHeight(28)
        self.setStyleSheet(f"""
            QFrame#statusStrip {{
                background: #0e0e0e;
                border-bottom: 1px solid {TS_BG_4};
            }}
            QLabel {{
                background: transparent;
                font-family: 'Jura', 'Segoe UI';
                font-size: 10px;
                letter-spacing: 1.4px;
            }}
        """)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(14, 0, 14, 0)
        h.setSpacing(12)

        self._dot = QtWidgets.QLabel("●")
        self._dot.setStyleSheet(f"color: {TS_OK}; font-size: 8px;")
        h.addWidget(self._dot)
        self._backend_lbl, self._backend_val = self._segment(h, "BACKEND", "Connected", val_color=TS_OK)
        self._sep(h)
        _, self._suit_val = self._segment(h, "SUIT", "TS-S-0427")
        self._sep(h)
        _, self._tick_val = self._segment(h, "TICK", "100 Hz")
        self._sep(h)
        _, self._active_val = self._segment(h, "ACTIVE", "0/4")
        self._sep(h)
        _, self._intensity_val = self._segment(h, "INTENSITY", "60%")
        h.addStretch(1)
        self._clock = QtWidgets.QLabel("--:--:--")
        self._clock.setStyleSheet(f"color: {TS_FG_2}; font-weight: 600; letter-spacing: 1.6px;")
        h.addWidget(self._clock)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick_clock)
        self._timer.start(1000)
        self._tick_clock()

    def _segment(self, parent_layout, label_text: str, value_text: str,
                 val_color: str = TS_FG_2) -> tuple[QtWidgets.QLabel, QtWidgets.QLabel]:
        label = QtWidgets.QLabel(label_text)
        label.setStyleSheet(f"color: {TS_FG_3};")
        parent_layout.addWidget(label)
        value = QtWidgets.QLabel(value_text)
        value.setStyleSheet(f"color: {val_color}; font-weight: 600;")
        parent_layout.addWidget(value)
        return label, value

    def _sep(self, parent_layout) -> None:
        s = QtWidgets.QFrame()
        s.setFixedSize(1, 14)
        s.setStyleSheet(f"background: {TS_BG_4};")
        parent_layout.addWidget(s)

    def _tick_clock(self) -> None:
        self._clock.setText(QtCore.QTime.currentTime().toString("HH:mm:ss"))

    def update_state(self, active_count: int, intensity_pct: int) -> None:
        self._active_val.setText(f"{active_count}/4")
        active_color = TS_ACCENT if active_count > 0 else TS_FG_2
        self._active_val.setStyleSheet(f"color: {active_color}; font-weight: 600;")
        self._intensity_val.setText(f"{int(intensity_pct)}%")


# ── Stage header (eyebrow + diagonal badge + live pill) ────────
class _StageHeader(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stageHeader")
        self.setFixedHeight(38)
        self.setStyleSheet(f"""
            QFrame#stageHeader {{
                background: rgba(0, 0, 0, 0.2);
                border-bottom: 1px solid #1f1f1f;
            }}
        """)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(18, 0, 14, 0)
        h.setSpacing(10)

        eyebrow = QtWidgets.QLabel("DIRECTION CUES · COMPASS VIEW")
        eyebrow.setStyleSheet(f"""
            background: transparent;
            color: {TS_FG_3};
            font-family: 'Jura', 'Segoe UI';
            font-size: 10px;
            font-weight: 500;
            letter-spacing: 1.8px;
        """)
        h.addWidget(eyebrow)
        h.addStretch(1)

        self._diag_badge = QtWidgets.QLabel(f"DIAGONAL  ×{_DIAGONAL_PW_MULT:.2f}")
        self._diag_badge.setObjectName("diagBadge")
        h.addWidget(self._diag_badge)

        self._live_pill = QtWidgets.QLabel("● IDLE")
        self._live_pill.setObjectName("livePill")
        h.addWidget(self._live_pill)

        self._refresh(False)

    def _refresh(self, diag: bool, firing: bool = False) -> None:
        if diag:
            self._diag_badge.setStyleSheet(f"""
                QLabel#diagBadge {{
                    background: rgba(136, 45, 255, 0.14);
                    border: 1px solid rgba(136, 45, 255, 0.4);
                    border-radius: 11px;
                    padding: 3px 10px;
                    color: {TS_CHART};
                    font-family: 'Jura', 'Segoe UI';
                    font-size: 10px;
                    font-weight: 600;
                    letter-spacing: 1.4px;
                }}
            """)
        else:
            self._diag_badge.setStyleSheet(f"""
                QLabel#diagBadge {{
                    background: transparent;
                    border: 1px solid {TS_BG_4};
                    border-radius: 11px;
                    padding: 3px 10px;
                    color: {TS_FG_3};
                    font-family: 'Jura', 'Segoe UI';
                    font-size: 10px;
                    font-weight: 600;
                    letter-spacing: 1.4px;
                }}
            """)
        if firing:
            self._live_pill.setText("● FIRING")
            self._live_pill.setStyleSheet(f"""
                QLabel#livePill {{
                    background: rgba(0, 95, 255, 0.08);
                    border: 1px solid rgba(0, 95, 255, 0.5);
                    border-radius: 11px;
                    padding: 3px 10px;
                    color: {TS_ACCENT};
                    font-family: 'Jura', 'Segoe UI';
                    font-size: 10px;
                    font-weight: 600;
                    letter-spacing: 1.4px;
                }}
            """)
        else:
            self._live_pill.setText("● IDLE")
            self._live_pill.setStyleSheet(f"""
                QLabel#livePill {{
                    background: rgba(255, 255, 255, 0.04);
                    border: 1px solid {TS_BG_4};
                    border-radius: 11px;
                    padding: 3px 10px;
                    color: {TS_FG_2};
                    font-family: 'Jura', 'Segoe UI';
                    font-size: 10px;
                    font-weight: 600;
                    letter-spacing: 1.4px;
                }}
            """)

    def update_state(self, active_count: int) -> None:
        self._refresh(diag=active_count >= 2, firing=active_count > 0)


# ── Inspector (right side panel) ───────────────────────────────
class _Inspector(QtWidgets.QFrame):
    intensity_changed = QtCore.pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(320)
        self.setObjectName("inspector")
        self.setStyleSheet(f"""
            QFrame#inspector {{
                background: {TS_BG_2};
                border-left: 1px solid {TS_BG_4};
            }}
            QFrame#group {{
                background: transparent;
                border-bottom: 1px solid {TS_BG_4};
            }}
            QLabel.h3 {{
                background: transparent;
                color: {TS_FG_1};
                font-family: 'Jura', 'Segoe UI';
                font-size: 11px;
                font-weight: 600;
                letter-spacing: 1.8px;
            }}
            QLabel.subtle {{
                background: transparent;
                color: {TS_FG_3};
                font-family: 'Jura', 'Segoe UI';
                font-size: 10px;
                letter-spacing: 1.2px;
            }}
            QSlider::groove:horizontal {{
                background: {TS_BG_4};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {TS_ACCENT};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {TS_FG_1};
                border: 1.5px solid {TS_ACCENT};
                width: 14px;
                margin: -6px 0;
                border-radius: 8px;
            }}
        """)
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ── Global intensity group ──
        g1 = self._group()
        g1_layout = g1.layout()
        h1 = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("GLOBAL INTENSITY")
        title.setProperty("class", "h3")
        title.setStyleSheet("")  # force re-eval of dynamic property class
        title.setObjectName("h3title")
        title.setStyleSheet(f"color: {TS_FG_1}; font-family: 'Jura'; font-size: 11px; font-weight: 600; letter-spacing: 1.8px; background: transparent;")
        rng = QtWidgets.QLabel("0–100 %")
        rng.setStyleSheet(f"color: {TS_FG_3}; font-family: 'Jura'; font-size: 10px; letter-spacing: 1.0px; background: transparent;")
        h1.addWidget(title)
        h1.addStretch(1)
        h1.addWidget(rng)
        g1_layout.addLayout(h1)

        intensity_row = QtWidgets.QHBoxLayout()
        intensity_row.setSpacing(14)
        self._big_num = QtWidgets.QLabel("60")
        self._big_num.setStyleSheet(f"""
            color: {TS_FG_1};
            background: transparent;
            font-family: 'Jura', 'Segoe UI';
            font-size: 40px;
            font-weight: 300;
            letter-spacing: 1.6px;
        """)
        self._big_num.setMinimumWidth(80)
        intensity_row.addWidget(self._big_num)
        self._slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(60)
        self._slider.setFocusPolicy(QtCore.Qt.NoFocus)
        self._slider.valueChanged.connect(self._on_slider)
        intensity_row.addWidget(self._slider, 1)
        g1_layout.addLayout(intensity_row)
        v.addWidget(g1)

        # ── Diagonal mode group ──
        g2 = self._group()
        g2l = g2.layout()
        title2 = QtWidgets.QLabel("DIAGONAL MODE")
        title2.setStyleSheet(f"color: {TS_FG_1}; font-family: 'Jura'; font-size: 11px; font-weight: 600; letter-spacing: 1.8px; background: transparent;")
        g2l.addWidget(title2)
        for left_text, right_text in (
            ("Trigger when",  "≥ 2 active"),
            ("Single direction", "×1.00"),
            ("Diagonal pulse-width",  f"×{_DIAGONAL_PW_MULT:.2f}"),
        ):
            row = QtWidgets.QHBoxLayout()
            l = QtWidgets.QLabel(left_text)
            l.setStyleSheet(f"color: {TS_FG_3}; font-family: 'Segoe UI'; font-size: 11px; background: transparent;")
            r = QtWidgets.QLabel(right_text)
            r.setStyleSheet(f"color: {TS_FG_1}; font-family: 'Jura'; font-size: 11px; background: transparent;")
            r.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            row.addWidget(l)
            row.addStretch(1)
            row.addWidget(r)
            g2l.addLayout(row)
        self._status_row = QtWidgets.QLabel("STATUS  ·  IDLE")
        self._status_row.setStyleSheet(
            f"color: {TS_FG_3}; font-family: 'Jura'; font-size: 10px; "
            f"font-weight: 600; letter-spacing: 1.6px; background: transparent;"
        )
        g2l.addWidget(self._status_row)
        v.addWidget(g2)

        # ── Bone mapping group ──
        g3 = self._group(border_bottom=False)
        g3l = g3.layout()
        title3 = QtWidgets.QLabel("BONE MAPPING")
        title3.setStyleSheet(f"color: {TS_FG_1}; font-family: 'Jura'; font-size: 11px; font-weight: 600; letter-spacing: 1.8px; background: transparent;")
        g3l.addWidget(title3)
        self._bone_rows = {}
        for d in DIRS:
            meta = DIR_META[d]
            row = QtWidgets.QFrame()
            row.setObjectName("boneRow")
            rl = QtWidgets.QHBoxLayout(row)
            rl.setContentsMargins(6, 4, 6, 4)
            rl.setSpacing(8)
            arrow = QtWidgets.QLabel(meta["arrow"])
            arrow.setFixedWidth(20)
            arrow.setStyleSheet(f"color: {TS_FG_3}; font-family: 'Jura'; font-size: 14px; background: transparent;")
            name = QtWidgets.QLabel(meta["region"])
            name.setStyleSheet(f"color: {TS_FG_2}; font-family: 'Segoe UI'; font-size: 11px; background: transparent;")
            spec = QtWidgets.QLabel(f"bone {meta['bone']} · {meta['channels']}")
            spec.setStyleSheet(f"color: {TS_FG_3}; font-family: 'Jura'; font-size: 10px; background: transparent;")
            spec.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            rl.addWidget(arrow)
            rl.addWidget(name)
            rl.addStretch(1)
            rl.addWidget(spec)
            g3l.addWidget(row)
            self._bone_rows[d] = (row, arrow, name, spec)
        g3l.addStretch(1)
        v.addWidget(g3, 1)

    def _group(self, border_bottom: bool = True) -> QtWidgets.QFrame:
        g = QtWidgets.QFrame()
        g.setObjectName("group")
        g.setStyleSheet(
            f"QFrame#group {{ background: transparent; "
            f"{'border-bottom: 1px solid ' + TS_BG_4 + ';' if border_bottom else ''} }}"
        )
        v = QtWidgets.QVBoxLayout(g)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)
        return g

    def _on_slider(self, value: int) -> None:
        self._big_num.setText(str(int(value)))
        self.intensity_changed.emit(int(value))

    def update_state(self, active: set) -> None:
        diag = len(active) >= 2
        if diag:
            self._status_row.setText("STATUS  ·  ENGAGED")
            self._status_row.setStyleSheet(
                f"color: {TS_CHART}; font-family: 'Jura'; font-size: 10px; "
                f"font-weight: 600; letter-spacing: 1.6px; background: transparent;"
            )
        else:
            self._status_row.setText("STATUS  ·  IDLE")
            self._status_row.setStyleSheet(
                f"color: {TS_FG_3}; font-family: 'Jura'; font-size: 10px; "
                f"font-weight: 600; letter-spacing: 1.6px; background: transparent;"
            )
        for d, (row, arrow, name, spec) in self._bone_rows.items():
            on = d in active
            row.setStyleSheet(
                f"QFrame#boneRow {{ background: rgba(0, 95, 255, 0.10); "
                f"border-radius: 3px; }}"
                if on else
                "QFrame#boneRow { background: transparent; }"
            )
            arrow.setStyleSheet(
                f"color: {TS_ACCENT if on else TS_FG_3}; "
                f"font-family: 'Jura'; font-size: 14px; "
                f"font-weight: {'700' if on else '400'}; background: transparent;"
            )
            name.setStyleSheet(
                f"color: {TS_FG_1 if on else TS_FG_2}; "
                f"font-family: 'Segoe UI'; font-size: 11px; background: transparent;"
            )

    def value(self) -> int:
        return int(self._slider.value())


# ── Focus veil (shown when the window is deactivated) ─────────
class _FocusVeil(QtWidgets.QFrame):
    """Red-tinted overlay that pulses across the stage when the window
    loses activation. Mirrors the design's ``.focus-veil`` element so the
    operator can see at a glance that no cues are firing — and that the
    window is no longer receiving input."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._alpha_phase = 1
        self._apply_tint(0.04)

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
        # Drop a soft red glow around the label for the mission-control look.
        glow = QtWidgets.QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(28)
        glow.setOffset(0, 0)
        glow.setColor(QtGui.QColor(244, 1, 1, 180))
        self._label.setGraphicsEffect(glow)
        layout.addWidget(self._label, 0, QtCore.Qt.AlignCenter)

        self._pulse_timer = QtCore.QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse)

        self.hide()

    def _apply_tint(self, alpha: float) -> None:
        self.setStyleSheet(
            "QFrame {"
            f"  border: 2px solid rgba(244, 1, 1, 0.6);"
            f"  background: rgba(244, 1, 1, {alpha:.3f});"
            "}"
        )

    def _pulse(self) -> None:
        # Toggle between the design's two CSS keyframe alphas every 700 ms
        # (one full 1.4 s cycle) so the veil reads as live, not stuck.
        self._alpha_phase ^= 1
        self._apply_tint(0.12 if self._alpha_phase else 0.04)

    def show_veil(self) -> None:
        self._alpha_phase = 1
        self._apply_tint(0.08)
        self.raise_()
        self.show()
        self._pulse_timer.start(700)

    def hide_veil(self) -> None:
        self._pulse_timer.stop()
        self.hide()


# ── Stage frame: header + compass + focus veil ────────────────
class _Stage(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: #141414; }")
        v = QtWidgets.QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.header = _StageHeader()
        v.addWidget(self.header)
        self.compass = _Compass()
        v.addWidget(self.compass, 1)
        # Veil is a child of the stage but NOT in the layout — we move it
        # by hand in resizeEvent so it always covers the full stage area.
        self.veil = _FocusVeil(self)

    def resizeEvent(self, event):
        self.veil.setGeometry(self.rect())
        super().resizeEvent(event)

    def show_veil(self) -> None:
        self.veil.setGeometry(self.rect())
        self.veil.show_veil()

    def hide_veil(self) -> None:
        self.veil.hide_veil()


# ── STOP ALL safety bar ────────────────────────────────────────
class _SafetyBar(QtWidgets.QFrame):
    stop_all_pressed = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("safetyBar")
        self.setStyleSheet(f"""
            QFrame#safetyBar {{
                background: #0a0a0a;
                border-top: 1px solid {TS_BG_4};
            }}
        """)
        h = QtWidgets.QHBoxLayout(self)
        h.setContentsMargins(14, 10, 14, 10)
        h.setSpacing(16)

        self._stop_btn = QtWidgets.QPushButton("  ■  STOP ALL  ESC  ")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self._stop_btn.setMinimumHeight(44)
        self._stop_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        self._stop_btn.setStyleSheet(f"""
            QPushButton#stopBtn {{
                background: {TS_ERR_DEEP};
                border: 1.5px solid {TS_ERR};
                border-radius: 4px;
                color: {TS_FG_1};
                font-family: 'Jura', 'Segoe UI';
                font-size: 14px;
                font-weight: 600;
                letter-spacing: 2.5px;
                padding: 0 22px;
            }}
            QPushButton#stopBtn:hover {{
                background: #9E0909;
            }}
            QPushButton#stopBtn:pressed {{
                background: {TS_ERR};
            }}
        """)
        self._stop_btn.clicked.connect(self.stop_all_pressed.emit)
        h.addWidget(self._stop_btn)

        # Cheat sheet
        cheat_layout = QtWidgets.QHBoxLayout()
        cheat_layout.setSpacing(14)
        for d in DIRS:
            cheat_layout.addWidget(self._cheat_item(DIR_META[d]["key"], DIR_META[d]["label"].title()))
        sep = QtWidgets.QFrame()
        sep.setFixedSize(1, 18)
        sep.setStyleSheet(f"background: {TS_BG_4};")
        cheat_layout.addWidget(sep)
        cheat_layout.addWidget(self._cheat_item("Esc", "Stop All"))
        cheat_layout.addWidget(self._cheat_item("Hold", "Continuous"))
        cheat_layout.addWidget(self._cheat_item("Multi", "Diagonal"))
        cheat_layout.addStretch(1)

        cheat_widget = QtWidgets.QWidget()
        cheat_widget.setLayout(cheat_layout)
        h.addWidget(cheat_widget, 1)

    def _cheat_item(self, key_text: str, label_text: str) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        wl = QtWidgets.QHBoxLayout(w)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(8)
        key = QtWidgets.QLabel(key_text)
        key.setStyleSheet(f"""
            QLabel {{
                background: {TS_BG_1};
                border: 1px solid {TS_BG_4};
                border-bottom: 2px solid {TS_BG_4};
                border-radius: 3px;
                color: {TS_FG_2};
                font-family: 'Jura', 'Segoe UI';
                font-size: 10px;
                font-weight: 500;
                padding: 2px 6px;
            }}
        """)
        lbl = QtWidgets.QLabel(label_text)
        lbl.setStyleSheet(f"""
            QLabel {{
                background: transparent;
                color: {TS_FG_3};
                font-family: 'Segoe UI';
                font-size: 11px;
            }}
        """)
        wl.addWidget(key)
        wl.addWidget(lbl)
        return w


# ── Main tab ───────────────────────────────────────────────────
class KeyboardNavigationTab(FesWidget):
    """Operator console: compass + body silhouette + STOP ALL.

    The control message holds four direction booleans + intensity_pct.
    Each true edge is mirrored into the live indicator immediately, plus
    written to the message (which auto-sends to the backend via the
    QueueHandler's _on_change callback).
    """

    always_update = True

    def build_ui(self) -> None:
        register_fonts()
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        layout = self.layout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._status = _StatusStrip()
        layout.addWidget(self._status)

        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self._stage = _Stage()
        self._header = self._stage.header
        self._compass = self._stage.compass
        body.addWidget(self._stage, 1)

        self._inspector = _Inspector()
        self._inspector.intensity_changed.connect(self._on_intensity)
        body.addWidget(self._inspector)

        body_widget = QtWidgets.QWidget()
        body_widget.setLayout(body)
        layout.addWidget(body_widget, 1)

        self._safety = _SafetyBar()
        self._safety.stop_all_pressed.connect(self._stop_all)
        layout.addWidget(self._safety)

        # Defer top-level window event-filter install: at build_ui time the
        # tab hasn't been re-parented under the FesApp window yet, so
        # self.window() would return self. Run on the next Qt tick.
        QtCore.QTimer.singleShot(0, self._install_window_filter)

        # Initial paint
        self._refresh_visuals()

    # ── Window-activation tracking ──
    def _install_window_filter(self) -> None:
        win = self.window()
        if win is not None and win is not self:
            win.installEventFilter(self)

    def eventFilter(self, obj, event):
        # Only react to the *top-level window's* deactivate/activate; tab or
        # child-widget focus changes (e.g. clicking the slider) are explicitly
        # ignored so they don't accidentally STOP ALL.
        if obj is self.window():
            etype = event.type()
            if etype == QtCore.QEvent.WindowDeactivate:
                self._on_window_deactivate()
            elif etype == QtCore.QEvent.WindowActivate:
                self._on_window_activate()
        return super().eventFilter(obj, event)

    def _on_window_deactivate(self) -> None:
        self._release_all(reason="window deactivated")
        self._stage.show_veil()

    def _on_window_activate(self) -> None:
        self._stage.hide_veil()

    # ── External API: message <-> visual sync ──
    def _active_set(self) -> set:
        msg = self.qh.control_message
        return {d for d in DIRS if bool(getattr(msg, d, False))}

    def _refresh_visuals(self) -> None:
        active = self._active_set()
        intensity = int(getattr(self.qh.control_message, "intensity_pct", 60))
        self._status.update_state(len(active), intensity)
        self._header.update_state(len(active))
        self._compass.update_state(active, intensity)
        self._inspector.update_state(active)

    # ── Intensity slider ──
    def _on_intensity(self, value: int) -> None:
        self.qh.control_message.intensity_pct = int(value)
        self._refresh_visuals()

    # ── Key handling ──
    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_Escape:
            self._stop_all()
            return
        if event.isAutoRepeat():
            return
        field = _KEY_TO_FIELD.get(event.key())
        if field is None:
            super().keyPressEvent(event)
            return
        setattr(self.qh.control_message, field, True)
        self._refresh_visuals()

    def keyReleaseEvent(self, event):
        if event.isAutoRepeat():
            return
        field = _KEY_TO_FIELD.get(event.key())
        if field is None:
            super().keyReleaseEvent(event)
            return
        setattr(self.qh.control_message, field, False)
        self._refresh_visuals()

    # ── STOP ALL ──
    def _stop_all(self) -> None:
        self._release_all(reason="STOP ALL")
        self._flash_stop()

    def _release_all(self, reason: str = "") -> None:
        msg = self.qh.control_message
        any_was_on = any(bool(getattr(msg, d, False)) for d in DIRS)
        for d in DIRS:
            if bool(getattr(msg, d, False)):
                setattr(msg, d, False)
        if any_was_on and reason:
            print(f"[HapticNav] {reason} — all cues released")
        self._refresh_visuals()

    def _flash_stop(self) -> None:
        # Quick red flash on the STOP button to acknowledge the action.
        btn = self._safety._stop_btn
        original = btn.styleSheet()
        btn.setStyleSheet(original + f"\nQPushButton#stopBtn {{ background: {TS_ERR}; }}")
        QtCore.QTimer.singleShot(400, lambda: btn.setStyleSheet(original))

    # ── 30 Hz tick from FesApp ──
    def refresh(self) -> None:
        # Slider may have been updated externally; mirror it.
        msg = self.qh.control_message
        intensity = int(getattr(msg, "intensity_pct", 60))
        if int(self._inspector.value()) != intensity:
            self._inspector._slider.blockSignals(True)
            self._inspector._slider.setValue(intensity)
            self._inspector._big_num.setText(str(intensity))
            self._inspector._slider.blockSignals(False)
        self._refresh_visuals()
