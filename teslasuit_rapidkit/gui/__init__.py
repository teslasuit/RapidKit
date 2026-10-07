# SPDX-License-Identifier: MIT
"""
Reusable GUI toolkit for FES Framework applications.

Provides composable PyQt5 widgets, a data adapter for shared-memory polling,
and a generic app shell with a 30 Hz update loop. All widgets communicate
with the backend exclusively through multiprocessing queues and
SharedRingBuffer — no direct backend process access.

Typical usage::

    from rapidkit.gui.app import FesApp
    from rapidkit.gui.tabs.overview_tab import OverviewTab
    from rapidkit.gui.tabs.biomechanics_tab import BiomechanicsTab

    def gui_main(control_queue, utility_queue):
        app = FesApp(
            control_queue=control_queue,
            utility_queue=utility_queue,
            title="My FES Application",
            tabs=[
                ("Overview", OverviewTab),
                ("Biomechanics", BiomechanicsTab),
            ],
        )
        app.run()
"""

from .data_adapter import DataAdapter
from .app import FesApp
from .base_widget import FesWidget
from .components import FesToggle, CalibrationPanel

__all__ = ["DataAdapter", "FesApp", "FesWidget", "FesToggle", "CalibrationPanel"]
