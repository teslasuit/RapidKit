# SPDX-License-Identifier: MIT
"""
Sensor data visualisation tab — bilateral live plots with optional overlay.

Creates one LivePlot per data group, arranged in left / right columns.
Uses DataAdapter for field lookup so it works with any frame dtype that
exposes the requested keys.
"""

from typing import Dict, List, Optional, Tuple

from PyQt5 import QtWidgets

from ..components.live_plot import LivePlot


class SensorDataTab(QtWidgets.QWidget):
    """Live sensor data visualisation tab.

    Plots are arranged bilaterally (left / right columns).  Each entry
    in *series* produces one plot per side.  An optional binary overlay
    field (0/1 signal) can shade each plot's background.

    Args:
        data_adapter: DataAdapter instance (``None`` means no live data).
        queue_handler: QueueHandler (unused here, accepted for API
            consistency with other tabs).
        series: List of ``(title, left_field, right_field, unit)`` tuples
            describing the data groups to plot.  **Required** — there are
            no built-in defaults.
        overlay_field_left: Optional DataAdapter field name for a 0/1
            signal displayed as background shading on left-side plots.
        overlay_field_right: Same for right-side plots.
        overlay_label: Legend label for the overlay region
            (default ``"Active"``).
        parent: Parent widget.
    """

    always_update = False  # only refresh when visible (lazy)

    def __init__(
        self,
        *,
        data_adapter=None,
        queue_handler=None,
        series: Optional[List[Tuple[str, str, str, str]]] = None,
        overlay_field_left: Optional[str] = None,
        overlay_field_right: Optional[str] = None,
        overlay_label: str = "Active",
        parent=None,
    ):
        super().__init__(parent)
        self._data = data_adapter
        self._overlay_left = overlay_field_left
        self._overlay_right = overlay_field_right
        self._series = list(series or [])
        show_bg = overlay_field_left is not None or overlay_field_right is not None

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(4)

        cols = QtWidgets.QHBoxLayout()
        left_col = QtWidgets.QVBoxLayout()
        right_col = QtWidgets.QVBoxLayout()

        left_col.addWidget(QtWidgets.QLabel("Left"))
        right_col.addWidget(QtWidgets.QLabel("Right"))

        self._plots_left: Dict[str, LivePlot] = {}
        self._plots_right: Dict[str, LivePlot] = {}

        for title, lf, rf, unit in self._series:
            lp = LivePlot(
                title=f"{title} L", y_label=unit, series=[lf],
                show_background=show_bg, background_label=overlay_label,
            )
            left_col.addWidget(lp)
            self._plots_left[lf] = lp

            rp = LivePlot(
                title=f"{title} R", y_label=unit, series=[rf],
                show_background=show_bg, background_label=overlay_label,
            )
            right_col.addWidget(rp)
            self._plots_right[rf] = rp

        left_col.addStretch()
        right_col.addStretch()
        cols.addLayout(left_col)
        cols.addLayout(right_col)
        root.addLayout(cols)

    # ── Refresh (called at 30 Hz by FesApp when tab is visible) ──

    def refresh(self):
        if self._data is None or not self._data.has_data:
            return

        t = self._data.get_time()
        ovl_l = self._data.get(self._overlay_left) if self._overlay_left else None
        ovl_r = self._data.get(self._overlay_right) if self._overlay_right else None

        for field, plot in self._plots_left.items():
            arr = self._data.get(field)
            if arr is not None:
                plot.update_data(t, {field: arr}, overlay_data=ovl_l)

        for field, plot in self._plots_right.items():
            arr = self._data.get(field)
            if arr is not None:
                plot.update_data(t, {field: arr}, overlay_data=ovl_r)
