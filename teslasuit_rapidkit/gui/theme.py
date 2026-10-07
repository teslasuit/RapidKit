# SPDX-License-Identifier: MIT
"""
Theme layer for FES Framework GUI applications.

Provides colour tokens, a default dark stylesheet (TeslaSuit Design System),
and a helper to apply custom themes at runtime.
"""

# ── Colour tokens ────────────────────────────────────────────────
COLORS = {
    "bg_primary":     "#181818",
    "bg_secondary":   "#212121",
    "bg_tertiary":    "#252525",
    "border":         "#323233",
    "text_primary":   "#BCC0C3",
    "text_secondary": "#7D7F82",
    "accent":         "#005FFF",
    "accent_hover":   "#084ABA",
    "accent_pressed": "#163365",
    "success":        "#00C853",
    "warning":        "#FFD600",
    "error":          "#FF1744",
    "overlay_fill":   "#4A4A4A",
}

PLOT_PALETTE = [
    "#005FFF", "#4A5FFF", "#7B68EE", "#882DFF", "#A855F7", "#C084FC",
]


# ── Default stylesheet ───────────────────────────────────────────
DEFAULT_STYLESHEET = f"""
QMainWindow {{
    background-color: {COLORS["bg_primary"]};
    color: {COLORS["text_primary"]};
}}
QWidget {{
    background-color: {COLORS["bg_primary"]};
    color: {COLORS["text_primary"]};
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 9pt;
}}
QTabWidget::pane {{
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    background-color: {COLORS["bg_primary"]};
    padding: 4px;
}}
QTabBar::tab {{
    background-color: {COLORS["bg_secondary"]};
    color: {COLORS["text_primary"]};
    border: none;
    padding: 12px 24px;
    margin-right: 4px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    min-width: 120px;
}}
QTabBar::tab:selected {{
    background-color: {COLORS["accent"]};
    color: #FFFFFF;
}}
QTabBar::tab:hover:!selected {{
    background-color: {COLORS["bg_tertiary"]};
}}
QPushButton {{
    background-color: {COLORS["accent"]};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 10px 20px;
    font-weight: 600;
    min-height: 35px;
}}
QPushButton:hover {{
    background-color: {COLORS["accent_hover"]};
}}
QPushButton:pressed {{
    background-color: {COLORS["accent_pressed"]};
}}
QPushButton:disabled {{
    background-color: {COLORS["border"]};
    color: {COLORS["text_secondary"]};
}}
QGroupBox {{
    border: 1px solid {COLORS["border"]};
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {COLORS["accent"]};
}}
QCheckBox {{
    spacing: 8px;
    color: {COLORS["text_primary"]};
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid {COLORS["border"]};
    background-color: {COLORS["bg_secondary"]};
}}
QCheckBox::indicator:checked {{
    background-color: {COLORS["accent"]};
    border-color: {COLORS["accent"]};
}}
QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {COLORS["bg_secondary"]};
    color: {COLORS["text_primary"]};
    border: 1px solid {COLORS["border"]};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 28px;
}}
QLabel {{
    color: {COLORS["text_primary"]};
}}
QScrollArea {{
    border: none;
    background-color: {COLORS["bg_primary"]};
}}
"""
