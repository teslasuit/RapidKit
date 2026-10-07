# SPDX-License-Identifier: MIT
"""
Pre-built tab widgets for FES Framework GUI applications.
"""

from .overview_tab import OverviewTab
from .biomechanics_tab import SensorDataTab

# Backward-compatible alias
BiomechanicsTab = SensorDataTab

__all__ = ["OverviewTab", "SensorDataTab", "BiomechanicsTab"]
