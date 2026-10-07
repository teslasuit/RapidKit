# SPDX-License-Identifier: MIT
"""
Haptic Proximity Radar GUI entry point.

Wires the RadarTab into a FesApp shell. Passes a fresh ProximityControlMessage
so the underlying QueueHandler uses our subclass (obj_x / obj_y /
master_intensity_pct) instead of the bare ControlMessage.

Reuses the Teslasuit dark stylesheet from the navigation example so the two
operator consoles look like one product family.
"""
from pathlib import Path

from PyQt5 import QtGui

from teslasuit_rapidkit.gui.app import FesApp

from ..proximity_radar_types import ProximityControlMessage
from .radar_tab import RadarTab


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


# Try the local fonts dir first; fall back to the navigation example so we
# don't have to duplicate the .ttf files until a designer ships dedicated
# assets for this example.
_LOCAL_FONTS = Path(__file__).resolve().parent / "assets" / "fonts"
_FALLBACK_FONTS = (
    Path(__file__).resolve().parents[2] / "haptic_navigation" / "gui" / "assets" / "fonts"
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
        control_message=ProximityControlMessage(),
        title="TeslaSuit — Haptic Proximity Radar · Operator Console",
        tabs=[("Radar", RadarTab)],
        stylesheet=_TS_STYLESHEET,
    )
    register_fonts()
    app.run()
