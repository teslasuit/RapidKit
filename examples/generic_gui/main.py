# SPDX-License-Identifier: MIT
"""
Generic GUI Example — FES Framework

Demonstrates how to assemble a complete FES application with GUI using
the framework's reusable widget toolkit.  No application-specific code.

Run::

    python examples/generic_gui/main.py
    # or
    python -m examples.generic_gui.main
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path so this script works when run directly.
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from functools import partial
from multiprocessing import freeze_support

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase
from teslasuit_rapidkit.data.types import EMSParamData, shared_memory_frame
from teslasuit_rapidkit.orchestrator import launch
from teslasuit_rapidkit.gui.app import FesApp
from teslasuit_rapidkit.gui.data_adapter import DataAdapter
from teslasuit_rapidkit.gui.tabs.overview_tab import OverviewTab
from teslasuit_rapidkit.gui.tabs.biomechanics_tab import SensorDataTab
from teslasuit_rapidkit.gui.base_widget import FesWidget


# ── Configuration ─────────────────────────────────────────────────

# Use the framework's standard shared-memory dtype (biomech + step detector).
FRAME_DTYPE = shared_memory_frame

# Fields the DataAdapter should buffer (subset of FRAME_DTYPE names).
BUFFERED_FIELDS = [
    "ShoulderFlexExtR", "ShoulderFlexExtL",
    "ElbowFlexExtR",    "ElbowFlexExtL",
    "KneeFlexExtR",     "KneeFlexExtL",
    "HipFlexExtR",      "HipFlexExtL",
    "StepDetectorRight", "StepDetectorLeft",
]

# Muscles exposed on the Overview tab (must match MuscleMap / EmsData).
MUSCLES = [
    "biceps_left",              "biceps_right",
    "triceps_left",             "triceps_right",
    "quadriceps_left",          "quadriceps_right",
    "hamstring_left",           "hamstring_right",
]

# Sensor data groups for the SensorDataTab.
# Each entry: (display_title, left_field, right_field, y_unit)
SENSOR_SERIES = [
    ("Shoulder Flex/Ext", "ShoulderFlexExtL", "ShoulderFlexExtR", "deg"),
    ("Elbow Flex/Ext",    "ElbowFlexExtL",    "ElbowFlexExtR",   "deg"),
    ("Knee Flex/Ext",     "KneeFlexExtL",     "KneeFlexExtR",    "deg"),
    ("Hip Flex/Ext",      "HipFlexExtL",      "HipFlexExtR",     "deg"),
]


# ── Custom tab example (subclass FesWidget) ──────────────────────

class ConnectionTab(FesWidget):
    """Tiny custom tab that shows backend connection status.

    Demonstrates the FesWidget base class: override ``build_ui()``
    to create widgets and ``refresh()`` to update them at 30 Hz.
    """

    always_update = True  # refresh even when this tab is hidden

    def build_ui(self) -> None:
        from PyQt5 import QtWidgets, QtCore

        self._label = QtWidgets.QLabel("Waiting for backend…")
        self._label.setAlignment(QtCore.Qt.AlignCenter)
        self._label.setStyleSheet("font-size: 18px;")
        self.layout().addWidget(self._label)

    def refresh(self) -> None:
        if self.data and self.data.is_connected:
            self._label.setText("✓ Backend connected")
            self._label.setStyleSheet("font-size: 18px; color: #50fa7b;")
        else:
            self._label.setText("Waiting for backend…")
            self._label.setStyleSheet("font-size: 18px; color: #ff5555;")


# ── Dummy strategy (replace with your own) ────────────────────────

class DummyStrategy(ControlStrategyBase):
    """Minimal no-op strategy for GUI demo purposes."""

    def process(self) -> None:
        """No stimulation logic — just passes through."""
        pass


# ── GUI entry point ───────────────────────────────────────────────

def gui_main(control_queue, utility_queue):
    """GUI process entry point — called by ``orchestrator.launch()``."""

    adapter = DataAdapter(
        buffer_name="fes_shared_buffer",
        frame_dtype=FRAME_DTYPE,
        fields=BUFFERED_FIELDS,
        max_points=300,   # ~3 s at 100 Hz
        capacity=1000,
    )

    # Use partial/lambda to pass extra kwargs to tab constructors
    overview_factory = partial(OverviewTab, muscles=MUSCLES, show_activity_plot=True)
    sensor_factory = partial(SensorDataTab, series=SENSOR_SERIES)

    app = FesApp(
        control_queue=control_queue,
        utility_queue=utility_queue,
        data_adapter=adapter,
        title="FES Framework — Generic Example",
        tabs=[
            ("Overview",    overview_factory),
            ("Sensor Data", sensor_factory),
            ("Connection",  ConnectionTab),   # custom FesWidget tab
        ],
    )
    app.run()


# ── Main ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    freeze_support()
    launch(
        DummyStrategy,
        gui_runner=gui_main,
        lsl_enabled=False,
    )
