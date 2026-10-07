# SPDX-License-Identifier: MIT
"""Per-muscle stimulation parameter card.

Strategy-agnostic: works with any muscle name from MuscleMap.
Emits a dict of core EMS parameters on any change so the parent can
forward it to QueueHandler.control_message.
"""

from PyQt5 import QtCore, QtWidgets


class MuscleControlCard(QtWidgets.QWidget):
    """Control card for a single muscle's stimulation parameters.

    Provides the universal EMS controls (enable, frequency, amplitude,
    pulse width).  Application-specific controls (e.g. timing windows)
    should be added at the application layer.

    Emits ``parametersChanged(muscle_name, params_dict)`` on any edit.
    """

    parametersChanged = QtCore.pyqtSignal(str, dict)

    def __init__(
        self,
        muscle_name: str,
        *,
        display_name: str = "",
        default_enabled: bool = True,
        default_amplitude: int = 50,
        default_pulse_width: int = 200,
        default_frequency: float = 30.0,
        parent=None,
    ):
        super().__init__(parent)
        self.muscle_name = muscle_name

        group = QtWidgets.QGroupBox(display_name or muscle_name)
        glayout = QtWidgets.QHBoxLayout()
        glayout.setSpacing(8)
        glayout.setContentsMargins(8, 6, 8, 6)

        self._enable = QtWidgets.QCheckBox("Enabled")
        self._enable.setChecked(default_enabled)
        self._enable.stateChanged.connect(self._emit)
        glayout.addWidget(self._enable)

        glayout.addWidget(QtWidgets.QLabel("PW:"))
        self._pw = QtWidgets.QSpinBox()
        self._pw.setRange(0, 1000)
        self._pw.setValue(default_pulse_width)
        self._pw.setSuffix(" \u00b5s")
        self._pw.setMaximumWidth(90)
        self._pw.valueChanged.connect(self._emit)
        glayout.addWidget(self._pw)

        glayout.addWidget(QtWidgets.QLabel("Freq:"))
        self._freq = QtWidgets.QDoubleSpinBox()
        self._freq.setRange(0, 200)
        self._freq.setValue(default_frequency)
        self._freq.setSuffix(" Hz")
        self._freq.setMaximumWidth(90)
        self._freq.valueChanged.connect(self._emit)
        glayout.addWidget(self._freq)

        glayout.addWidget(QtWidgets.QLabel("Amp:"))
        self._amp = QtWidgets.QSpinBox()
        self._amp.setRange(0, 100)
        self._amp.setValue(default_amplitude)
        self._amp.setSuffix(" %")
        self._amp.setMaximumWidth(80)
        self._amp.valueChanged.connect(self._emit)
        glayout.addWidget(self._amp)

        group.setLayout(glayout)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(group)

    # ── Public ────────────────────────────────────────────────────

    def get_params(self) -> dict:
        """Return current parameters as a dict.

        Keys match ``_default_stim_params`` structure: ``is_active``,
        ``frequency``, ``amplitude``, ``pulse_width``.
        """
        return {
            "is_active": self._enable.isChecked(),
            "frequency": self._freq.value(),
            "amplitude": self._amp.value(),
            "pulse_width": self._pw.value(),
        }

    # ── Internals ─────────────────────────────────────────────────

    def _emit(self, *_args):
        self.parametersChanged.emit(self.muscle_name, self.get_params())
