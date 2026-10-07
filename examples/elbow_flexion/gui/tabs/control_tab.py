# SPDX-License-Identifier: MIT
"""Control tab — setpoint, PID gains, arm selection, auto-tune."""
from __future__ import annotations

from PyQt5 import QtCore, QtWidgets


class ControlTab(QtWidgets.QWidget):
    """Operator controls: arm, setpoint, PID gains, mirror, auto-tune, FES."""

    # Signals consumed by the main window
    fesActiveChanged         = QtCore.pyqtSignal(bool)
    activeArmChanged         = QtCore.pyqtSignal(str)   # "left" | "right"
    setpointChanged          = QtCore.pyqtSignal(float)
    mirrorModeChanged        = QtCore.pyqtSignal(bool)
    pidGainsChanged          = QtCore.pyqtSignal(float, float, float)
    amplitudeChanged         = QtCore.pyqtSignal(int)
    autoTuneRequested        = QtCore.pyqtSignal()
    calibrationRequested     = QtCore.pyqtSignal()

    def __init__(self, data_handler, parent=None) -> None:
        super().__init__(parent)
        self.data_handler = data_handler

        root = QtWidgets.QHBoxLayout(self)

        # ── Left column: master switches + arm + mirror + auto-tune ─
        left = QtWidgets.QVBoxLayout()
        root.addLayout(left, 1)

        self.fes_toggle = QtWidgets.QCheckBox("Enable FES (master)")
        self.fes_toggle.toggled.connect(self.fesActiveChanged.emit)
        left.addWidget(self.fes_toggle)

        arm_box = QtWidgets.QGroupBox("Active arm")
        arm_layout = QtWidgets.QHBoxLayout(arm_box)
        self.arm_left = QtWidgets.QRadioButton("Left")
        self.arm_right = QtWidgets.QRadioButton("Right")
        self.arm_left.setChecked(True)
        self.arm_left.toggled.connect(self._on_arm_toggled)
        arm_layout.addWidget(self.arm_left)
        arm_layout.addWidget(self.arm_right)
        left.addWidget(arm_box)

        self.mirror_toggle = QtWidgets.QCheckBox("Mirror opposite arm")
        self.mirror_toggle.toggled.connect(self.mirrorModeChanged.emit)
        left.addWidget(self.mirror_toggle)

        self.calibrate_btn = QtWidgets.QPushButton("Calibrate (T-pose)")
        self.calibrate_btn.clicked.connect(self.calibrationRequested.emit)
        left.addWidget(self.calibrate_btn)

        self.autotune_btn = QtWidgets.QPushButton("Auto-tune PID")
        self.autotune_btn.clicked.connect(self.autoTuneRequested.emit)
        left.addWidget(self.autotune_btn)

        self.tuner_status = QtWidgets.QLabel("Tuner: IDLE")
        left.addWidget(self.tuner_status)

        left.addStretch(1)

        # ── Right column: sliders ─────────────────────────────────
        right = QtWidgets.QVBoxLayout()
        root.addLayout(right, 2)

        self.setpoint_slider, self.setpoint_label = self._add_slider(
            right, "Desired angle (deg)", 0, 180, 90, scale=1.0)
        self.setpoint_slider.valueChanged.connect(self._emit_setpoint)

        self.kp_slider, self.kp_label = self._add_slider(
            right, "Kp (×0.01)", 0, 550, 0, scale=0.01)
        self.ki_slider, self.ki_label = self._add_slider(
            right, "Ki (×0.01)", 0, 1500, 0, scale=0.01)
        self.kd_slider, self.kd_label = self._add_slider(
            right, "Kd (×0.01)", 0, 150, 0, scale=0.01)
        for s in (self.kp_slider, self.ki_slider, self.kd_slider):
            s.valueChanged.connect(self._emit_gains)

        self.amp_slider, self.amp_label = self._add_slider(
            right, "Amplitude (%)", 0, 100, 100, scale=1.0)
        self.amp_slider.valueChanged.connect(self._emit_amplitude)

        right.addStretch(1)

        # Status-refresh timer (reads tuner state from data_handler)
        self._status_timer = QtCore.QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(200)

    # ── Helpers ───────────────────────────────────────────────────

    def _add_slider(self, parent_layout, label, lo, hi, initial, scale):
        row_label = QtWidgets.QLabel(f"{label}: {initial * scale:.2f}")
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(initial)
        slider._scale = scale
        slider._label_template = label
        slider._row_label = row_label

        def update_label(v):
            row_label.setText(f"{label}: {v * scale:.2f}")

        slider.valueChanged.connect(update_label)
        parent_layout.addWidget(row_label)
        parent_layout.addWidget(slider)
        return slider, row_label

    def _on_arm_toggled(self, checked: bool) -> None:
        if not checked:
            return  # only react on the "now-checked" side
        self.activeArmChanged.emit("left" if self.arm_left.isChecked() else "right")

    def _emit_setpoint(self, value: int) -> None:
        self.setpointChanged.emit(float(value))

    def _emit_gains(self, _value: int) -> None:
        kp = self.kp_slider.value() * 0.01
        ki = self.ki_slider.value() * 0.01
        kd = self.kd_slider.value() * 0.01
        self.pidGainsChanged.emit(kp, ki, kd)

    def _emit_amplitude(self, value: int) -> None:
        self.amplitudeChanged.emit(int(value))

    def _refresh_status(self) -> None:
        status = self.data_handler.tuner_status_text
        kp_hint = self.data_handler.tuner_kp_suggested
        rate = self.data_handler.backend_sample_rate
        self.tuner_status.setText(
            f"Tuner: {status}   Kp_ramp={kp_hint:.2f}   Backend: {rate:.0f} Hz"
        )
        # After auto-tune finishes, the strategy writes suggested gains back
        # into the control message.  Pull those into the sliders so the
        # operator can see and adjust.
        if status == "DONE":
            # Reset slider positions to reflect the newly-suggested gains.
            # (The strategy will have written them back to self.params.)
            # No-op here: the main window wires this via control_message
            # if it wants to reflect them; keeping this tab stateless.
            pass

    # ── Public accessors for initial-state push ───────────────────

    def initial_state(self) -> dict:
        return {
            "fes_active": self.fes_toggle.isChecked(),
            "active_arm": "left" if self.arm_left.isChecked() else "right",
            "desired_angle_deg": float(self.setpoint_slider.value()),
            "mirror_mode": self.mirror_toggle.isChecked(),
            "pid_kp": self.kp_slider.value() * 0.01,
            "pid_ki": self.ki_slider.value() * 0.01,
            "pid_kd": self.kd_slider.value() * 0.01,
            "ems_amplitude": int(self.amp_slider.value()),
        }
