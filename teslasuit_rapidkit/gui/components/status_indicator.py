# SPDX-License-Identifier: MIT
"""Colour-coded status indicator badge."""

from PyQt5 import QtWidgets

from ..theme import COLORS


class StatusIndicator(QtWidgets.QWidget):
    """Small labelled circle that reflects a boolean or tri-state status.

    Call ``set_status("ok")``, ``set_status("warning")``, or
    ``set_status("error")`` to change colour.
    """

    _COLOR_MAP = {
        "ok":      COLORS["success"],
        "warning": COLORS["warning"],
        "error":   COLORS["error"],
        "off":     COLORS["border"],
    }

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = QtWidgets.QLabel()
        self._dot.setFixedSize(12, 12)
        layout.addWidget(self._dot)

        self._label = QtWidgets.QLabel(label)
        layout.addWidget(self._label)
        layout.addStretch()

        self.set_status("off")

    def set_status(self, status: str):
        colour = self._COLOR_MAP.get(status, self._COLOR_MAP["off"])
        self._dot.setStyleSheet(
            f"background-color: {colour}; border-radius: 6px;"
        )

    def set_label(self, text: str):
        self._label.setText(text)
