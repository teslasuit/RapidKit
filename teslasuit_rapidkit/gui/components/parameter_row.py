# SPDX-License-Identifier: MIT
"""Compact labeled numeric parameter control (spinbox or double-spinbox)."""

from PyQt5 import QtCore, QtWidgets


class ParameterRow(QtWidgets.QWidget):
    """Single-row labeled numeric parameter with change signal.

    Emits ``valueChanged(name, value)`` when the user edits the spinbox.
    """

    valueChanged = QtCore.pyqtSignal(str, float)

    def __init__(
        self,
        name: str,
        label: str = "",
        *,
        minimum: float = 0,
        maximum: float = 100,
        default: float = 0,
        suffix: str = "",
        decimals: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.param_name = name

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl = QtWidgets.QLabel(label or name)
        lbl.setFixedWidth(120)
        layout.addWidget(lbl)

        if decimals > 0:
            self._spin = QtWidgets.QDoubleSpinBox()
            self._spin.setDecimals(decimals)
        else:
            self._spin = QtWidgets.QSpinBox()

        self._spin.setMinimum(int(minimum) if decimals == 0 else minimum)
        self._spin.setMaximum(int(maximum) if decimals == 0 else maximum)
        self._spin.setValue(int(default) if decimals == 0 else default)
        if suffix:
            self._spin.setSuffix(suffix)
        self._spin.setMaximumWidth(120)
        self._spin.valueChanged.connect(self._on_changed)
        layout.addWidget(self._spin)
        layout.addStretch()

    def value(self) -> float:
        return float(self._spin.value())

    def setValue(self, v):
        self._spin.setValue(v)

    def _on_changed(self, v):
        self.valueChanged.emit(self.param_name, float(v))
