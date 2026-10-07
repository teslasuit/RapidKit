# SPDX-License-Identifier: MIT
"""Glassmorphism stylesheet + palette for the Elbow FES Flexion Control GUI.

Dark, atmospheric palette with semi-transparent surfaces and ice-blue
accents.
Qt does not support CSS ``backdrop-filter`` blur, so the "frozen glass"
look is approximated with rgba fills + thin luminous borders.
"""
from __future__ import annotations


class Colors:
    BG            = "#0a0e1a"
    SURFACE       = "#0f1524"
    SURFACE_HIGH  = "#141c2e"
    SURFACE_DIM   = "#0a0f1c"
    ON_SURFACE    = "#e0e8f0"
    ON_SURFACE_V  = "#a0b4c4"
    MUTED         = "#6a7a8c"
    OUTLINE       = "#2a3a48"
    PRIMARY       = "#7dd3fc"
    PRIMARY_DIM   = "#4ba9d6"
    TERTIARY      = "#c8a0f0"
    ERROR         = "#ff6b6b"


APP_STYLESHEET = f"""
* {{
    font-family: "Inter", "Segoe UI", "Helvetica Neue", sans-serif;
    color: {Colors.ON_SURFACE};
}}
QMainWindow, QWidget#Dashboard {{
    background-color: {Colors.BG};
}}

/* ── Top bar & footer ──────────────────────────────────────── */
QFrame#TopBar {{
    background-color: rgba(10, 14, 26, 200);
    border-bottom: 1px solid rgba(125, 211, 252, 35);
}}
QFrame#Footer {{
    background-color: rgba(10, 14, 26, 220);
    border-top: 1px solid rgba(125, 211, 252, 35);
}}

/* ── Glass panels ──────────────────────────────────────────── */
QFrame#GlassPanel {{
    background-color: rgba(15, 21, 36, 180);
    border: 1px solid rgba(125, 211, 252, 30);
    border-radius: 10px;
}}
QFrame#GlassPanel[accent="true"] {{
    border-left: 2px solid rgba(125, 211, 252, 110);
}}
QFrame#GlassPanel[tuning="true"] {{
    border: 1px solid rgba(200, 160, 240, 180);
    background-color: rgba(40, 28, 62, 200);
}}
QFrame#GlassPanelElevated {{
    background-color: rgba(20, 28, 46, 210);
    border: 1px solid rgba(125, 211, 252, 45);
    border-radius: 14px;
}}

/* ── Brand + nav ───────────────────────────────────────────── */
QLabel#Brand {{
    color: {Colors.PRIMARY};
    font-size: 18px;
    font-weight: 600;
}}
QLabel#NavActive {{
    color: {Colors.PRIMARY};
    font-weight: 600;
    border-bottom: 2px solid {Colors.PRIMARY};
    padding-bottom: 2px;
}}
QLabel#NavInactive {{
    color: {Colors.MUTED};
    font-weight: 500;
    padding-bottom: 2px;
}}

/* ── Metric cards ──────────────────────────────────────────── */
QLabel#MetricLabel {{
    color: {Colors.ON_SURFACE_V};
    font-size: 10px;
    font-weight: 700;
}}
QLabel#MetricValue {{
    color: {Colors.PRIMARY};
    font-size: 32px;
    font-weight: 300;
}}
QLabel#MetricValueNeutral {{
    color: {Colors.ON_SURFACE};
    font-size: 32px;
    font-weight: 300;
}}
QLabel#MetricValueTertiary {{
    color: {Colors.TERTIARY};
    font-size: 32px;
    font-weight: 300;
}}
QLabel#MetricSuffix {{
    color: {Colors.ON_SURFACE_V};
    font-size: 11px;
}}

/* ── Session badge ─────────────────────────────────────────── */
QFrame#SessionChip {{
    background-color: rgba(15, 21, 36, 200);
    border: 1px solid rgba(125, 211, 252, 60);
    border-radius: 12px;
}}
QLabel#SessionLabel {{
    color: {Colors.MUTED};
    font-size: 9px;
    font-weight: 700;
}}
QLabel#SessionText {{
    color: {Colors.PRIMARY};
    font-family: "Consolas", "Menlo", monospace;
    font-weight: 500;
    font-size: 12px;
}}

/* ── Emergency / ghost / pill buttons ──────────────────────── */
QPushButton#EmergencyStop {{
    background-color: rgba(255, 107, 107, 30);
    border: 1px solid rgba(255, 107, 107, 140);
    color: {Colors.ERROR};
    font-weight: 700;
    font-size: 11px;
    padding: 8px 16px;
    border-radius: 6px;
}}
QPushButton#EmergencyStop:hover {{
    background-color: rgba(255, 107, 107, 60);
}}
QPushButton#EmergencyStop:pressed {{
    background-color: rgba(255, 107, 107, 100);
}}
QPushButton#PrimaryPill {{
    background-color: rgba(125, 211, 252, 25);
    border: 1px solid rgba(125, 211, 252, 110);
    color: {Colors.PRIMARY};
    font-weight: 700;
    font-size: 10px;
    padding: 9px 22px;
    border-radius: 14px;
}}
QPushButton#PrimaryPill:hover {{
    background-color: rgba(125, 211, 252, 55);
}}
QPushButton#PrimaryPill:pressed {{
    background-color: rgba(125, 211, 252, 90);
}}
QPushButton#PrimaryPill[running="true"] {{
    background-color: rgba(200, 160, 240, 70);
    border-color: rgba(200, 160, 240, 180);
    color: {Colors.TERTIARY};
}}
QPushButton#PrimaryPill:disabled {{
    background-color: rgba(10, 15, 28, 140);
    border: 1px solid rgba(80, 95, 115, 60);
    color: {Colors.MUTED};
}}
QPushButton#GhostButton {{
    background-color: transparent;
    border: 1px solid rgba(125, 211, 252, 45);
    color: {Colors.ON_SURFACE_V};
    padding: 7px 14px;
    border-radius: 6px;
    font-size: 11px;
}}
QPushButton#GhostButton:hover {{
    border-color: rgba(125, 211, 252, 140);
    color: {Colors.PRIMARY};
}}
QPushButton#GhostButton:disabled {{
    background-color: rgba(10, 15, 28, 120);
    border: 1px solid rgba(80, 95, 115, 45);
    color: {Colors.MUTED};
}}

/* ── Arm toggle ────────────────────────────────────────────── */
QFrame#ArmToggleGroup {{
    background-color: rgba(10, 15, 28, 255);
    border: 1px solid rgba(125, 211, 252, 25);
    border-radius: 8px;
    padding: 2px;
}}
QPushButton#ArmTab {{
    background-color: transparent;
    border: none;
    color: {Colors.MUTED};
    padding: 6px 18px;
    font-size: 11px;
    font-weight: 600;
    border-radius: 6px;
}}
QPushButton#ArmTab:checked {{
    background-color: rgba(125, 211, 252, 50);
    color: {Colors.PRIMARY};
}}
QPushButton#ArmTab:hover:!checked {{
    color: {Colors.ON_SURFACE};
}}

/* ── FES active chip ───────────────────────────────────────── */
QPushButton#FesChip {{
    background-color: transparent;
    border: 1px solid rgba(125, 211, 252, 60);
    color: {Colors.MUTED};
    padding: 6px 14px;
    border-radius: 6px;
    font-weight: 600;
    font-size: 10px;
}}
QPushButton#FesChip:checked {{
    background-color: rgba(125, 211, 252, 35);
    border-color: rgba(125, 211, 252, 160);
    color: {Colors.PRIMARY};
}}

/* ── Checkboxes ────────────────────────────────────────────── */
QCheckBox {{
    color: {Colors.ON_SURFACE_V};
    spacing: 6px;
    font-size: 11px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {Colors.OUTLINE};
    border-radius: 3px;
    background-color: rgba(15, 21, 36, 255);
}}
QCheckBox::indicator:checked {{
    background-color: {Colors.PRIMARY};
    border: 1px solid {Colors.PRIMARY};
}}

/* ── Sliders ───────────────────────────────────────────────── */
/* Keep the slider widget itself transparent so only the groove, handle,
 * and sub-page paint. Without this, styling QSlider sub-controls makes
 * Qt draw the full widget rect with its default palette background
 * (a shade lighter than the footer). The ``background`` shorthand is
 * sometimes ignored by Qt's stylesheet engine on QSlider, so we use
 * the specific ``background-color`` property and also zero out border
 * / padding to be sure no widget-level fill leaks through.
 */
QSlider, QSlider:disabled {{
    background-color: transparent;
    border: none;
    padding: 0px;
}}
/* Keep the ::groove sub-control transparent because Qt's stylesheet engine
 * refuses to honour a sub-3px height on it — whatever colour we put here
 * gets stretched across the full slider rect, which is the lighter strip
 * we used to see behind the sliders. Instead we paint the actual track
 * using ::sub-page and ::add-page, which Qt sizes correctly. */
QSlider::groove:horizontal {{
    background: transparent;
    border: none;
    height: 3px;
}}
QSlider::handle:horizontal {{
    background-color: {Colors.PRIMARY};
    border: none;
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
}}
QSlider::sub-page:horizontal {{
    background-color: rgba(125, 211, 252, 140);
    border-radius: 2px;
}}
QSlider::add-page:horizontal {{
    background-color: {Colors.SURFACE_HIGH};
    border-radius: 2px;
}}
QSlider:disabled::handle:horizontal {{
    background-color: {Colors.OUTLINE};
}}
QSlider:disabled::sub-page:horizontal {{
    background-color: rgba(60, 75, 95, 90);
}}
QSlider:disabled::add-page:horizontal {{
    background-color: rgba(20, 28, 42, 200);
}}

/* ── PID / Amp labels ──────────────────────────────────────── */
QLabel#ParamKey {{
    color: {Colors.ON_SURFACE_V};
    font-size: 10px;
    font-weight: 700;
}}
QLabel#ParamKey:disabled {{
    color: {Colors.MUTED};
}}
QLabel#ParamValue {{
    color: {Colors.PRIMARY};
    font-family: "Consolas", "Menlo", monospace;
    font-size: 10px;
}}
QLabel#ParamValue:disabled {{
    color: {Colors.MUTED};
}}

/* ── Misc ──────────────────────────────────────────────────── */
QLabel#PanelHeading {{
    color: {Colors.ON_SURFACE_V};
    font-size: 11px;
    font-weight: 700;
}}
QLabel#PanelSubtle {{
    color: {Colors.ON_SURFACE_V};
    font-family: "Consolas", "Menlo", monospace;
    font-size: 10px;
}}
QLabel#LiveFeedTag {{
    color: {Colors.PRIMARY};
    font-family: "Consolas", "Menlo", monospace;
    font-size: 10px;
}}
QLabel#TunerStatus {{
    color: {Colors.ON_SURFACE_V};
    font-size: 10px;
}}
QLabel#VersionText {{
    color: {Colors.MUTED};
    font-size: 10px;
    font-weight: 500;
}}
"""
