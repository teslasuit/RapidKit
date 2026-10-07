# SPDX-License-Identifier: MIT
"""
Haptic Navigation GUI entry point.

Wires the KeyboardNavigationTab into a FesApp shell. Passes a fresh
NavigationControlMessage so the underlying QueueHandler uses our subclass
(with the four direction fields) instead of the bare ControlMessage.

Applies the Teslasuit dark theme on top of the FesApp default stylesheet so
the tab content renders against a #181818 canvas matching the design handoff.
"""
from teslasuit_rapidkit.gui.app import FesApp

from ..haptic_navigation_types import NavigationControlMessage
from .keyboard_tab import KeyboardNavigationTab, register_fonts


# Minimal global stylesheet — colors/typography pulled from the design's
# ds/colors_and_type.css. Keeps the tab background dark and removes the
# margin around the tab pages so the operator console fills the window.
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


def gui_main(control_queue, utility_queue) -> None:
    app = FesApp(
        control_queue=control_queue,
        utility_queue=utility_queue,
        control_message=NavigationControlMessage(),
        title="TeslaSuit — Haptic Navigation · Operator Console",
        tabs=[("Navigation", KeyboardNavigationTab)],
        stylesheet=_TS_STYLESHEET,
    )
    register_fonts()
    app.run()
