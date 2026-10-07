# SPDX-License-Identifier: MIT
"""Self-contained FES active/inactive toggle button.

Drop-in widget — pass a ``QueueHandler`` and it handles the IPC
automatically.  No boilerplate required in the parent widget.

Usage::

    from rapidkit.gui.components.fes_toggle import FesToggle

    # Inside any QWidget / FesWidget.build_ui():
    toggle = FesToggle(queue_handler=self.qh)
    self.layout().addWidget(toggle)
    # That's it — clicking sends FesIsActive to the backend.

    # Wire after construction (e.g. when qh arrives later):
    toggle.set_queue_handler(queue_handler)

    # Connect to extra logic if needed:
    toggle.toggled.connect(lambda active: print("FES:", active))
"""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets

from ..theme import COLORS


class FesToggle(QtWidgets.QWidget):
    """Self-contained FES enable/disable toggle.

    When a ``QueueHandler`` is attached (via constructor or
    ``set_queue_handler()``), clicking the button automatically sends
    ``utility_message.FesIsActive`` to the backend process.

    The ``toggled(bool)`` signal is always emitted for any additional
    handling (logging, enabling other widgets, etc.).

    Args:
        queue_handler: ``QueueHandler`` instance.  May be ``None`` and
            wired later with ``set_queue_handler()``.
        parent: Parent widget.
    """

    #: Emitted on every toggle with the new FES-active state.
    toggled = QtCore.pyqtSignal(bool)

    def __init__(self, *, queue_handler=None, parent=None):
        super().__init__(parent)
        self._qh = queue_handler

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._btn = QtWidgets.QPushButton("FES OFF")
        self._btn.setCheckable(True)
        self._btn.setMinimumWidth(90)
        self._btn.setStyleSheet(self._style(active=False))
        self._btn.toggled.connect(self._on_toggle)
        layout.addWidget(self._btn)
        layout.addStretch()

    # ── Public API ────────────────────────────────────────────────

    def set_queue_handler(self, qh) -> None:
        """Wire (or replace) the QueueHandler after construction."""
        self._qh = qh

    @property
    def is_active(self) -> bool:
        """Current FES-active state."""
        return self._btn.isChecked()

    def set_active(self, active: bool) -> None:
        """Programmatically set the toggle state (does NOT re-emit toggled)."""
        self._btn.blockSignals(True)
        self._btn.setChecked(active)
        self._btn.setText("FES ON" if active else "FES OFF")
        self._btn.setStyleSheet(self._style(active))
        self._btn.blockSignals(False)

    # ── Internals ─────────────────────────────────────────────────

    def _on_toggle(self, checked: bool) -> None:
        self._btn.setText("FES ON" if checked else "FES OFF")
        self._btn.setStyleSheet(self._style(checked))
        if self._qh is not None:
            self._qh.utility_message.FesIsActive = checked
        self.toggled.emit(checked)

    @staticmethod
    def _style(active: bool) -> str:
        if active:
            return (
                "QPushButton { background-color: #50fa7b; color: #0d1117;"
                " font-weight: bold; border-radius: 4px; padding: 4px 10px; }"
                " QPushButton:hover { background-color: #69ff8c; }"
            )
        return (
            "QPushButton { background-color: #44475a; color: #f8f8f2;"
            " font-weight: bold; border-radius: 4px; padding: 4px 10px; }"
            " QPushButton:hover { background-color: #6272a4; }"
        )
