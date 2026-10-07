# SPDX-License-Identifier: MIT
"""
Vestibular Training GUI entry point.

Wires the BalanceTab into a FesApp shell using VestibularControlMessage so
the QueueHandler carries boundary geometry and neutral-offset fields in
addition to the bare ControlMessage base fields.

Reuses the Teslasuit dark stylesheet from haptic_navigation so all three
operator consoles feel like one product family. Fonts are loaded from the
haptic_navigation assets directory as a fallback when no local copy is present.
"""
from __future__ import annotations

from pathlib import Path

from PyQt5 import QtGui

from teslasuit_rapidkit.gui.app import FesApp

from ..vestibular_training_types import VestibularControlMessage
from .balance_tab import BalanceTab


_TS_STYLESHEET = """
QMainWindow, QWidget {
    background: #181818;
    color: #BCC0C3;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 0;
    background: #181818;
}
QTabBar::tab {
    background: #181818;
    color: #7D7F82;
    padding: 8px 18px;
    border: 0;
    font-family: 'Jura', 'Segoe UI';
    letter-spacing: 1.4px;
    font-size: 11px;
}
QTabBar::tab:selected {
    color: #FFFFFF;
    border-bottom: 1.5px solid #005FFF;
}
"""

_LOCAL_FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
_FALLBACK_FONTS = (
    Path(__file__).resolve().parents[3]
    / "haptic_navigation" / "gui" / "assets" / "fonts"
)


def register_fonts() -> None:
    db = QtGui.QFontDatabase
    for source in (_LOCAL_FONTS, _FALLBACK_FONTS):
        if source.exists():
            for ttf in source.glob("Jura-*.ttf"):
                db.addApplicationFont(str(ttf))
            if any(source.glob("Jura-*.ttf")):
                return


def gui_main(control_queue, utility_queue) -> None:
    app = FesApp(
        control_queue=control_queue,
        utility_queue=utility_queue,
        control_message=VestibularControlMessage(),
        title="TeslaSuit — Vestibular Training · Operator Console",
        tabs=[("Balance", BalanceTab)],
        stylesheet=_TS_STYLESHEET,
    )
    register_fonts()
    app.run()
