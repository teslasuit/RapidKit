# SPDX-License-Identifier: MIT
"""Calibration trigger panel.

Drop-in widget — pass a ``QueueHandler`` and it handles the IPC
automatically.  No boilerplate required in the parent widget.

Usage::

    from rapidkit.gui.components.calibration_panel import CalibrationPanel

    # Inside any QWidget / FesWidget.build_ui():
    panel = CalibrationPanel(queue_handler=self.qh)
    self.layout().addWidget(panel)
    # Clicking sends CalibrationLoopIsActive=True to the backend.

    # Mark calibrated / not calibrated from a utility message callback:
    panel.set_calibrated(True)

    # Connect extra logic if needed (always emitted regardless of queue_handler):
    panel.calibrationRequested.connect(my_slot)
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

from .status_indicator import StatusIndicator


class CalibrationPanel(QtWidgets.QWidget):
    """Self-contained calibration button and status indicator.

    When a ``QueueHandler`` is attached, clicking the button
    automatically sends ``utility_message.CalibrationLoopIsActive = True``
    to the backend process.

    The ``calibrationRequested`` signal is always emitted for any
    additional handling.

    Args:
        queue_handler: ``QueueHandler`` instance.  May be ``None`` and
            wired later with ``set_queue_handler()``.
        parent: Parent widget.
    """

    #: Emitted every time the calibrate button is pressed.
    calibrationRequested = QtCore.pyqtSignal()

    def __init__(self, *, queue_handler=None, parent=None):
        super().__init__(parent)
        self._qh = queue_handler

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._btn = QtWidgets.QPushButton("Calibrate MoCap")
        self._btn.clicked.connect(self._on_click)
        layout.addWidget(self._btn)

        self._status = StatusIndicator(label="Not calibrated")
        layout.addWidget(self._status)
        layout.addStretch()

    # ── Public API ────────────────────────────────────────────────

    def set_queue_handler(self, qh) -> None:
        """Wire (or replace) the QueueHandler after construction."""
        self._qh = qh

    def set_calibrated(self, ok: bool) -> None:
        """Update the status indicator (True = green, False = grey)."""
        if ok:
            self._status.set_status("ok")
            self._status.set_label("Calibrated")
        else:
            self._status.set_status("off")
            self._status.set_label("Not calibrated")

    # ── Internals ─────────────────────────────────────────────────

    def _on_click(self) -> None:
        if self._qh is not None:
            self._qh.utility_message.CalibrationLoopIsActive = True
        self.calibrationRequested.emit()
