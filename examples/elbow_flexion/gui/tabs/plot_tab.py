# SPDX-License-Identifier: MIT
"""Plot tab — angle-vs-setpoint and PID pulse-width outputs."""
from __future__ import annotations

from PyQt5 import QtWidgets

try:
    import pyqtgraph as pg
    _HAS_PG = True
except ImportError:  # pragma: no cover
    _HAS_PG = False


class PlotTab(QtWidgets.QWidget):
    """Two stacked plots: angle tracking (top), pulse widths (bottom)."""

    def __init__(self, data_handler, parent=None) -> None:
        super().__init__(parent)
        self.data_handler = data_handler

        layout = QtWidgets.QVBoxLayout(self)

        if not _HAS_PG:
            layout.addWidget(QtWidgets.QLabel(
                "pyqtgraph is not installed — plots unavailable. "
                "pip install pyqtgraph"
            ))
            self.angle_plot = None
            self.pw_plot = None
            return

        self.angle_plot = pg.PlotWidget(title="Elbow angle (active arm)")
        self.angle_plot.setLabel('left', 'Angle (deg)')
        self.angle_plot.setLabel('bottom', 'Time (s)')
        self.angle_plot.addLegend()
        self.angle_plot.showGrid(x=True, y=True, alpha=0.3)
        self.angle_curve = self.angle_plot.plot(pen=pg.mkPen('y', width=2),
                                                name="measured")
        self.setpoint_curve = self.angle_plot.plot(pen=pg.mkPen('r', width=2,
                                                                style=3),
                                                    name="setpoint")
        layout.addWidget(self.angle_plot)

        self.pw_plot = pg.PlotWidget(title="PID output (pulse width, us)")
        self.pw_plot.setLabel('left', 'Pulse width (us)')
        self.pw_plot.setLabel('bottom', 'Time (s)')
        self.pw_plot.addLegend()
        self.pw_plot.showGrid(x=True, y=True, alpha=0.3)
        self.biceps_curve = self.pw_plot.plot(pen=pg.mkPen('c', width=2),
                                              name="biceps")
        self.triceps_curve = self.pw_plot.plot(pen=pg.mkPen('m', width=2),
                                               name="triceps")
        layout.addWidget(self.pw_plot)

    def update_plots(self) -> None:
        if not _HAS_PG:
            return
        t = self.data_handler.get_time()
        if t.size == 0:
            return
        angle = self.data_handler.get_active_angle()
        setpoint = self.data_handler.get_setpoint()
        biceps_pw = self.data_handler.get_biceps_pw()
        triceps_pw = self.data_handler.get_triceps_pw()

        # Guard: all arrays should have same length, but deques are updated
        # in lockstep so a mismatch would indicate a bug.  Trim to the min.
        n = min(t.size, angle.size, setpoint.size,
                biceps_pw.size, triceps_pw.size)
        if n == 0:
            return
        self.angle_curve.setData(t[-n:], angle[-n:])
        self.setpoint_curve.setData(t[-n:], setpoint[-n:])
        self.biceps_curve.setData(t[-n:], biceps_pw[-n:])
        self.triceps_curve.setData(t[-n:], triceps_pw[-n:])
