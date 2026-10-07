# SPDX-License-Identifier: MIT
"""Real-time scrolling plot widget backed by pyqtgraph."""

from typing import Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets

from ..theme import COLORS, PLOT_PALETTE


class LivePlot(QtWidgets.QWidget):
    """Self-contained live-scrolling plot for one or more data series.

    Usage::

        plot = LivePlot(title="Joint Angles", y_label="deg",
                        series=["KneeFlexExtR", "HipFlexExtR"])
        plot.update_data(time_array, {"KneeFlexExtR": knee_data,
                                      "HipFlexExtR": hip_data})

    An optional binary overlay (0/1 signal) can be enabled with
    ``show_background=True`` to shade regions of the plot.
    """

    def __init__(
        self,
        title: str = "",
        y_label: str = "",
        series: Optional[List[str]] = None,
        *,
        show_background: bool = False,
        background_label: str = "Active",
        max_height: int = 250,
        parent=None,
    ):
        super().__init__(parent)
        self._series_keys: List[str] = list(series or [])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._gfx = pg.GraphicsLayoutWidget()
        self._gfx.setMaximumHeight(max_height)
        layout.addWidget(self._gfx)

        self._plot = self._gfx.addPlot(title=title)
        if y_label:
            self._plot.setLabel("left", y_label)
        self._plot.setLabel("bottom", "Time", units="s")
        self._plot.showGrid(x=False, y=False, alpha=0.3)
        self._style_plot()

        # Optional binary overlay fill
        self._overlay_curve: Optional[pg.PlotDataItem] = None
        if show_background:
            self._overlay_curve = self._plot.plot(
                pen=None,
                brush=pg.mkBrush(COLORS["overlay_fill"], alpha=60),
                name=background_label,
                fillLevel=0,
            )

        # Data curves
        self._curves: Dict[str, pg.PlotDataItem] = {}
        for i, key in enumerate(self._series_keys):
            color = PLOT_PALETTE[i % len(PLOT_PALETTE)]
            self._curves[key] = self._plot.plot(
                pen=pg.mkPen(color, width=2), name=key
            )

        self._y_range: Optional[tuple] = None

    # ── Public API ────────────────────────────────────────────────

    def update_data(
        self,
        time_array: np.ndarray,
        series_data: Dict[str, Optional[np.ndarray]],
        overlay_data: Optional[np.ndarray] = None,
    ):
        """Push fresh data into the plot.

        Args:
            time_array: x-axis values (seconds)
            series_data: ``{series_key: y_values}``
            overlay_data: Optional 0/1 array for binary background shading.
        """
        if len(time_array) == 0:
            return

        # Compute auto y-range
        y_min = y_max = None
        for key, curve in self._curves.items():
            arr = series_data.get(key)
            if arr is not None and len(arr) == len(time_array):
                curve.setData(time_array, arr)
                lo, hi = float(np.min(arr)), float(np.max(arr))
                y_min = lo if y_min is None else min(y_min, lo)
                y_max = hi if y_max is None else max(y_max, hi)

        if y_min is not None and y_max is not None:
            pad = max((y_max - y_min) * 0.1, 5)
            new_range = (y_min - pad, y_max + pad)
            if self._y_range is None or self._range_changed(new_range):
                self._plot.setYRange(*new_range)
                self._y_range = new_range

        # Binary overlay background
        if (
            self._overlay_curve is not None
            and overlay_data is not None
            and self._y_range is not None
            and len(overlay_data) == len(time_array)
        ):
            mask = overlay_data.astype(float)
            lo, hi = self._y_range
            self._overlay_curve.setData(
                time_array, np.where(mask >= 0.5, hi, lo)
            )
            self._overlay_curve.setFillLevel(lo)

    # ── Internals ─────────────────────────────────────────────────

    def _range_changed(self, new_range: tuple) -> bool:
        if self._y_range is None:
            return True
        old_span = self._y_range[1] - self._y_range[0]
        new_span = new_range[1] - new_range[0]
        return (
            abs(new_span - old_span) / max(abs(old_span), 1) > 0.05
            or new_range[0] < self._y_range[0]
            or new_range[1] > self._y_range[1]
        )

    def _style_plot(self):
        vb = self._plot.getViewBox()
        if vb:
            vb.setBackgroundColor(COLORS["bg_primary"])
        tc = COLORS["text_primary"]
        for axis in ("left", "bottom"):
            self._plot.getAxis(axis).setPen(pg.mkPen(tc, width=1))
            self._plot.getAxis(axis).setTextPen(pg.mkPen(tc))
        self._plot.setTitle(color=COLORS["accent"], size="9pt")
