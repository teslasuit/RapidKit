# SPDX-License-Identifier: MIT
"""
Muscle activity timeline — shows which muscles are active over time.

Each muscle gets a horizontal lane.  When the muscle's ``is_active``
parameter is ``True``, the lane is filled; otherwise it stays empty.
The result is a compact timeline view of stimulation on/off state.

Usage::

    from teslasuit_rapidkit.gui.components.muscle_activity_plot import MuscleActivityPlot

    plot = MuscleActivityPlot(muscles=["quadriceps_left", "quadriceps_right"])
    plot.update_data(time_array, {"quadriceps_left": active_array, ...})
"""

from typing import Dict, List, Optional

import numpy as np
import pyqtgraph as pg
from PyQt5 import QtWidgets

from ..theme import COLORS, PLOT_PALETTE


class MuscleActivityPlot(QtWidgets.QWidget):
    """Timeline plot showing per-muscle active/inactive state.

    Each muscle is rendered as a filled horizontal band (y = row index)
    when active (1) and empty when inactive (0).

    Args:
        muscles: List of muscle names (one lane per muscle).
        title: Plot title (default ``"Muscle Activity"``).
        max_height: Maximum widget height in pixels.
        parent: Parent widget.
    """

    def __init__(
        self,
        muscles: Optional[List[str]] = None,
        *,
        title: str = "Muscle Activity",
        max_height: int = 300,
        parent=None,
    ):
        super().__init__(parent)
        self._muscles: List[str] = list(muscles or [])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._gfx = pg.GraphicsLayoutWidget()
        self._gfx.setMaximumHeight(max_height)
        layout.addWidget(self._gfx)

        self._plot = self._gfx.addPlot(title=title)
        self._plot.setLabel("bottom", "Time", units="s")
        self._plot.showGrid(x=False, y=False)
        self._style_plot()

        # Y-axis: one row per muscle, labelled with display names
        y_axis = self._plot.getAxis("left")
        ticks = [(i + 0.5, self._display(m)) for i, m in enumerate(self._muscles)]
        y_axis.setTicks([ticks])
        self._plot.setYRange(0, max(len(self._muscles), 1))

        # One fill curve per muscle
        self._fills: Dict[str, pg.PlotDataItem] = {}
        for i, muscle in enumerate(self._muscles):
            colour = PLOT_PALETTE[i % len(PLOT_PALETTE)]
            item = self._plot.plot(
                pen=None,
                brush=pg.mkBrush(colour + "99"),  # ~60 % opacity
                fillLevel=float(i),
            )
            self._fills[muscle] = (item, i)

    # ── Public API ────────────────────────────────────────────────

    def update_data(
        self,
        time_array: np.ndarray,
        activity: Dict[str, Optional[np.ndarray]],
    ):
        """Push fresh activity data.

        Args:
            time_array: x-axis values (seconds).
            activity: ``{muscle_name: 0/1_array}`` for each muscle.
                      ``1`` = active, ``0`` = inactive.
        """
        if len(time_array) == 0:
            return

        for muscle, (item, row) in self._fills.items():
            arr = activity.get(muscle)
            if arr is not None and len(arr) == len(time_array):
                # Scale the binary signal into the muscle's row band
                y = np.where(arr >= 0.5, float(row + 1), float(row))
                item.setData(time_array, y)
                item.setFillLevel(float(row))

    # ── Internals ─────────────────────────────────────────────────

    @staticmethod
    def _display(name: str) -> str:
        """``'quadriceps_left'`` → ``'Quadriceps L'``."""
        for suffix, short in (("_left", " L"), ("_right", " R")):
            if name.endswith(suffix):
                return name[: -len(suffix)].replace("_", " ").title() + short
        return name.replace("_", " ").title()

    def _style_plot(self):
        vb = self._plot.getViewBox()
        if vb:
            vb.setBackgroundColor(COLORS["bg_primary"])
        tc = COLORS["text_primary"]
        for axis in ("left", "bottom"):
            self._plot.getAxis(axis).setPen(pg.mkPen(tc, width=1))
            self._plot.getAxis(axis).setTextPen(pg.mkPen(tc))
        self._plot.setTitle(color=COLORS["accent"], size="9pt")
