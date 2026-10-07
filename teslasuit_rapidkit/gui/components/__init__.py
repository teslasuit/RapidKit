# SPDX-License-Identifier: MIT
"""
Reusable PyQt5 components for FES Framework GUIs.

All components are strategy-agnostic and communicate with the backend
exclusively through DataAdapter (read) and QueueHandler (write).
"""

from .range_slider import RangeSlider
from .parameter_row import ParameterRow
from .status_indicator import StatusIndicator
from .fes_toggle import FesToggle
from .muscle_control_card import MuscleControlCard
from .live_plot import LivePlot
from .calibration_panel import CalibrationPanel
from .muscle_activity_plot import MuscleActivityPlot

__all__ = [
    "RangeSlider",
    "ParameterRow",
    "StatusIndicator",
    "FesToggle",
    "MuscleControlCard",
    "LivePlot",
    "CalibrationPanel",
    "MuscleActivityPlot",
]
