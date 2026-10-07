# SPDX-License-Identifier: MIT
"""Main window for the Elbow FES Flexion Control app.

Single-view dashboard.
Top bar: brand + nav + session timer + emergency stop.  A row of four
metric cards summarises live state.  The main area splits between the
kinematics visualizer (left) and a stacked angle plot / error deviation
bar / pulse-intensity chart (right).  The footer carries the core
operator controls (arm toggle, FES chip, PID sliders, amplitude, mirror,
auto-tune, calibrate).
"""
from __future__ import annotations

import time
from multiprocessing import Queue
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

try:
    import pyqtgraph as pg
    _HAS_PG = True
except ImportError:  # pragma: no cover
    _HAS_PG = False

from teslasuit_rapidkit.ipc.queue_handler import QueueHandler
from examples.elbow_flexion.elbow_init_utils import init_ElbowControlMessage
from examples.elbow_flexion.gui.data_handler import ElbowDataHandler
from examples.elbow_flexion.gui.styles import APP_STYLESHEET, Colors
from examples.elbow_flexion.gui.widgets import (
    ErrorDeviationBar,
    KinematicsVisualizer,
    MetricCard,
    PulseIntensityBars,
)


class ElbowMainWindow(QtWidgets.QMainWindow):
    """Elbow FES Flexion Control — single-view operator dashboard."""

    def __init__(self, control_queue: Optional[Queue] = None,
                 utility_queue: Optional[Queue] = None,
                 parent=None) -> None:
        super().__init__(parent)

        self.refresh_rate = 30  # Hz
        self._session_start = time.time()
        # Last auto-tune result counter we've latched into the sliders. The
        # backend bumps this when a new Ku/Tu-derived gain triplet is ready;
        # the GUI watches it in ``_refresh_tuner_status`` and snaps the
        # Kp/Ki/Kd sliders to match.
        self._last_tuner_result_counter: int = 0

        self.data_handler = ElbowDataHandler()
        self.data_handler.connect(max_attempts=3)

        self.queue_handler = QueueHandler(
            control_queue=control_queue,
            utility_queue=utility_queue,
            control_message=init_ElbowControlMessage(),
        )

        self._build_ui()
        self.setStyleSheet(APP_STYLESHEET)
        self.setWindowTitle("Elbow Flexion Control")
        self.resize(1280, 820)

        # FES chip starts unchecked (FES idle) → mirror that in the
        # controller-related widgets so the operator can't queue a
        # gain change or an auto-calibrate run before enabling FES.
        self._set_controller_controls_enabled(self.fes_chip.isChecked())

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(int(1000 / self.refresh_rate))

        QtCore.QTimer.singleShot(250, self._send_initial_state)

    # ─────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QtWidgets.QWidget()
        root.setObjectName("Dashboard")
        self.setCentralWidget(root)

        outer = QtWidgets.QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_top_bar())

        body = QtWidgets.QVBoxLayout()
        body.setContentsMargins(24, 18, 24, 14)
        body.setSpacing(14)
        outer.addLayout(body, 1)

        body.addLayout(self._build_metrics_row())
        body.addLayout(self._build_main_split(), 1)

        outer.addWidget(self._build_footer())

    # ── Top bar ──────────────────────────────────────────────────
    def _build_top_bar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)

        lay = QtWidgets.QHBoxLayout(bar)
        lay.setContentsMargins(28, 0, 28, 0)
        lay.setSpacing(30)

        brand = QtWidgets.QLabel("ELBOW FLEXION CONTROL")
        brand.setObjectName("Brand")
        lay.addWidget(brand)

        nav = QtWidgets.QHBoxLayout()
        nav.setSpacing(22)
        for name in ("Monitor", "Diagnostics", "History", "Settings"):
            lbl = QtWidgets.QLabel(name)
            lbl.setObjectName("NavActive" if name == "Monitor" else "NavInactive")
            nav.addWidget(lbl)
        lay.addLayout(nav)
        lay.addStretch(1)

        # Session chip
        chip = QtWidgets.QFrame()
        chip.setObjectName("SessionChip")
        chip_lay = QtWidgets.QHBoxLayout(chip)
        chip_lay.setContentsMargins(12, 4, 12, 4)
        chip_lay.setSpacing(8)
        chip_lay.addWidget(self._label("SESSION", "SessionLabel"))
        self._session_label = QtWidgets.QLabel("00:00:00")
        self._session_label.setObjectName("SessionText")
        chip_lay.addWidget(self._session_label)
        lay.addWidget(chip)

        self.emergency_btn = QtWidgets.QPushButton("EMERGENCY STOP")
        self.emergency_btn.setObjectName("EmergencyStop")
        self.emergency_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.emergency_btn.clicked.connect(self._on_emergency_stop)
        lay.addWidget(self.emergency_btn)
        return bar

    # ── Metrics row ──────────────────────────────────────────────
    def _build_metrics_row(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(14)
        self.card_current = MetricCard("Current Angle")
        self.card_target  = MetricCard("Target Angle", value_role="neutral",
                                       accent_bar=True)
        self.card_error   = MetricCard("Error Margin", value_role="tertiary")
        self.card_stim    = MetricCard("Stimulation Intensity")
        for c in (self.card_current, self.card_target,
                  self.card_error, self.card_stim):
            row.addWidget(c, 1)
        return row

    # ── Main split: kinematics + right-side plots ───────────────
    def _build_main_split(self) -> QtWidgets.QHBoxLayout:
        split = QtWidgets.QHBoxLayout()
        split.setSpacing(14)
        split.addWidget(self._build_kinematics_panel(), 3)
        split.addLayout(self._build_right_column(), 2)
        return split

    def _build_kinematics_panel(self) -> QtWidgets.QFrame:
        panel = QtWidgets.QFrame()
        panel.setObjectName("GlassPanelElevated")
        lay = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(6)

        header = QtWidgets.QHBoxLayout()
        dot = QtWidgets.QLabel("●")
        dot.setStyleSheet(f"color: {Colors.PRIMARY}; font-size: 10px;")
        header.addWidget(dot)
        header.addWidget(self._label("LIVE KINEMATICS VISUALIZER", "PanelHeading"))
        header.addStretch(1)
        lay.addLayout(header)

        subtitle = self._label("PT_ID: 8829-X  //  ELBOW_FLEXION", "PanelSubtle")
        lay.addWidget(subtitle)

        self.kinematics = KinematicsVisualizer()
        lay.addWidget(self.kinematics, 1)

        # Bottom legend
        legend = QtWidgets.QHBoxLayout()
        legend.setSpacing(28)
        legend.addLayout(self._legend_item("LATENCY", self._legend_value("—")))
        legend.addLayout(self._legend_item("SAMPLE RATE",
                                           self._legend_value("— Hz",
                                                              attr="_sample_rate_label")))
        legend.addStretch(1)
        lay.addLayout(legend)
        return panel

    def _legend_item(self, caption: str, value_widget: QtWidgets.QLabel):
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(self._label(caption, "MetricLabel"))
        col.addWidget(value_widget)
        return col

    def _legend_value(self, text: str, attr: Optional[str] = None) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName("LiveFeedTag")
        if attr:
            setattr(self, attr, lbl)
        return lbl

    def _build_right_column(self) -> QtWidgets.QVBoxLayout:
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(12)
        col.addWidget(self._build_angle_plot_panel(), 1)
        col.addWidget(self._build_error_panel(), 1)
        col.addWidget(self._build_pulse_panel(), 1)
        return col

    def _build_angle_plot_panel(self) -> QtWidgets.QFrame:
        panel = QtWidgets.QFrame()
        panel.setObjectName("GlassPanel")
        lay = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(self._label("ANGLE PLOT", "PanelHeading"))
        header.addStretch(1)
        header.addWidget(self._label("LIVE FEED", "LiveFeedTag"))
        lay.addLayout(header)

        if _HAS_PG:
            self.angle_plot = pg.PlotWidget()
            self.angle_plot.setBackground(None)
            self.angle_plot.getPlotItem().getViewBox().setBackgroundColor(None)
            self.angle_plot.showGrid(x=False, y=False)
            for ax in ("left", "bottom"):
                self.angle_plot.getAxis(ax).setPen(
                    pg.mkPen(QtGui.QColor(255, 255, 255, 25)))
                self.angle_plot.getAxis(ax).setTextPen(
                    pg.mkPen(QtGui.QColor(Colors.ON_SURFACE_V)))
            self.angle_plot.setMenuEnabled(False)
            self.angle_plot.setMouseEnabled(x=False, y=False)
            self.angle_curve = self.angle_plot.plot(
                pen=pg.mkPen(Colors.PRIMARY, width=2))
            # Pre-built pens for the setpoint trace. The "idle" pen is the
            # usual thin tertiary dash; the "tuning" pen is a bolder solid
            # tertiary so the target angle trace visibly changes state on
            # every graph that plots it while the auto-tuner is driving.
            self._setpoint_pen_idle = pg.mkPen(
                Colors.TERTIARY, width=1.4, style=QtCore.Qt.DashLine)
            self._setpoint_pen_tuning = pg.mkPen(
                Colors.TERTIARY, width=2.6, style=QtCore.Qt.SolidLine)
            self.setpoint_curve = self.angle_plot.plot(
                pen=self._setpoint_pen_idle)
            lay.addWidget(self.angle_plot, 1)
        else:
            self.angle_plot = None
            lay.addWidget(QtWidgets.QLabel("pyqtgraph not installed"), 1)
        return panel

    def _build_error_panel(self) -> QtWidgets.QFrame:
        panel = QtWidgets.QFrame()
        panel.setObjectName("GlassPanel")
        lay = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(10)
        header = QtWidgets.QHBoxLayout()
        header.addWidget(self._label("ERROR DEVIATION", "PanelHeading"))
        header.addStretch(1)
        for col in (Colors.ERROR, Colors.TERTIARY):
            d = QtWidgets.QLabel("●")
            d.setStyleSheet(f"color: {col}; font-size: 10px;")
            header.addWidget(d)
        lay.addLayout(header)
        self.error_bar = ErrorDeviationBar()
        lay.addWidget(self.error_bar, 0, QtCore.Qt.AlignVCenter)
        lay.addStretch(1)
        return panel

    def _build_pulse_panel(self) -> QtWidgets.QFrame:
        panel = QtWidgets.QFrame()
        panel.setObjectName("GlassPanel")
        lay = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(8)
        lay.addWidget(self._label("PULSE INTENSITY", "PanelHeading"))
        self.pulse_bars = PulseIntensityBars()
        lay.addWidget(self.pulse_bars, 1)
        return panel

    # ── Footer: arm + FES + PID + amp + mirror + buttons ───────
    def _build_footer(self) -> QtWidgets.QWidget:
        footer = QtWidgets.QFrame()
        footer.setObjectName("Footer")
        footer.setFixedHeight(82)
        lay = QtWidgets.QHBoxLayout(footer)
        lay.setContentsMargins(28, 12, 28, 12)
        lay.setSpacing(22)

        # ── Arm toggle ──
        arm_group = QtWidgets.QFrame()
        arm_group.setObjectName("ArmToggleGroup")
        arm_lay = QtWidgets.QHBoxLayout(arm_group)
        arm_lay.setContentsMargins(4, 3, 4, 3)
        arm_lay.setSpacing(2)
        self.arm_left_btn = QtWidgets.QPushButton("LEFT ARM")
        self.arm_right_btn = QtWidgets.QPushButton("RIGHT ARM")
        for b, side in ((self.arm_left_btn, "left"),
                        (self.arm_right_btn, "right")):
            b.setObjectName("ArmTab")
            b.setCheckable(True)
            b.setCursor(QtCore.Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, s=side: self._on_arm_clicked(s))
            arm_lay.addWidget(b)
        self.arm_left_btn.setChecked(True)
        lay.addWidget(arm_group)

        # FES chip (toggle)
        self.fes_chip = QtWidgets.QPushButton("● FES SYSTEM ACTIVE")
        self.fes_chip.setObjectName("FesChip")
        self.fes_chip.setCheckable(True)
        self.fes_chip.setCursor(QtCore.Qt.PointingHandCursor)
        self.fes_chip.toggled.connect(self._on_fes_toggled)
        lay.addWidget(self.fes_chip)

        # Mirror mode toggle
        self.mirror_check = QtWidgets.QCheckBox("Mirror")
        self.mirror_check.toggled.connect(self._on_mirror_toggled)
        lay.addWidget(self.mirror_check)

        lay.addStretch(1)

        # ── PID sliders ──
        self.kp_slider, self.kp_val_label = self._build_param_slider(
            lay, "P", 0, 550, 0, 0.01)
        self.ki_slider, self.ki_val_label = self._build_param_slider(
            lay, "I", 0, 1500, 0, 0.01)
        self.kd_slider, self.kd_val_label = self._build_param_slider(
            lay, "D", 0, 150, 0, 0.01)
        for s in (self.kp_slider, self.ki_slider, self.kd_slider):
            s.valueChanged.connect(self._emit_gains)

        # Amplitude (small)
        self.amp_slider, self.amp_val_label = self._build_param_slider(
            lay, "AMP", 0, 100, 100, 1.0, unit="%")
        self.amp_slider.valueChanged.connect(self._on_amplitude_changed)

        # Setpoint (small)
        self.sp_slider, self.sp_val_label = self._build_param_slider(
            lay, "SET", 0, 180, 90, 1.0, unit="°")
        self.sp_slider.valueChanged.connect(self._on_setpoint_changed)

        lay.addSpacing(8)

        self.autotune_btn = QtWidgets.QPushButton("AUTO-CALIBRATE")
        self.autotune_btn.setObjectName("PrimaryPill")
        self.autotune_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.autotune_btn.clicked.connect(self._on_autotune)
        lay.addWidget(self.autotune_btn)

        self.reset_pid_btn = QtWidgets.QPushButton("RESET PID")
        self.reset_pid_btn.setObjectName("GhostButton")
        self.reset_pid_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.reset_pid_btn.setToolTip("Zero out Kp / Ki / Kd")
        self.reset_pid_btn.clicked.connect(self._on_reset_pid)
        lay.addWidget(self.reset_pid_btn)

        self.ipose_btn = QtWidgets.QPushButton("I-POSE")
        self.ipose_btn.setObjectName("GhostButton")
        self.ipose_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.ipose_btn.clicked.connect(self._on_calibrate)
        lay.addWidget(self.ipose_btn)

        self.tuner_status = QtWidgets.QLabel("Tuner: IDLE")
        self.tuner_status.setObjectName("TunerStatus")
        lay.addWidget(self.tuner_status)

        return footer

    def _build_param_slider(self, parent_lay, key: str, lo: int, hi: int,
                            init: int, scale: float, unit: str = ""):
        wrap = QtWidgets.QVBoxLayout()
        wrap.setSpacing(2)
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        key_lbl = QtWidgets.QLabel(key)
        key_lbl.setObjectName("ParamKey")
        val_lbl = QtWidgets.QLabel(f"{init * scale:.2f}{unit}")
        val_lbl.setObjectName("ParamValue")
        val_lbl.setAlignment(QtCore.Qt.AlignRight)
        row.addWidget(key_lbl)
        row.addStretch(1)
        row.addWidget(val_lbl)
        wrap.addLayout(row)
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setRange(lo, hi)
        slider.setValue(init)
        slider.setFixedWidth(96)
        # Pin the slider height small so the track ::sub-page / ::add-page
        # pills don't have excess vertical space to paint into. Without
        # this, Qt stretches the track fill across the widget's full
        # size-hint height (~22-26px), producing the lighter rectangle
        # behind each slider that wouldn't match the footer.
        slider.setFixedHeight(14)
        # Stash the paired labels on the slider so ``setEnabled`` calls can
        # propagate the greyed-out state to them — QLabels next to a slider
        # are siblings in a layout, not children, so Qt won't cascade the
        # disabled state automatically.
        slider._key_label = key_lbl
        slider._val_label = val_lbl
        wrap.addWidget(slider)

        def _update(v: int) -> None:
            val_lbl.setText(f"{v * scale:.2f}{unit}")

        slider.valueChanged.connect(_update)
        parent_lay.addLayout(wrap)
        return slider, val_lbl

    def _label(self, text: str, object_name: str) -> QtWidgets.QLabel:
        lbl = QtWidgets.QLabel(text)
        lbl.setObjectName(object_name)
        return lbl

    # ─────────────────────────────────────────────────────────────
    # Tick — refresh data + paint dynamic content
    # ─────────────────────────────────────────────────────────────
    def _tick(self) -> None:
        self.data_handler.update()

        # Session timer
        elapsed = int(time.time() - self._session_start)
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        self._session_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

        # Metrics + visualizer
        current = self._latest(self.data_handler.get_active_angle())
        setpoint = self._effective_setpoint()
        amp = int(self.queue_handler.control_message.ems_amplitude)

        self.card_current.set_value(f"{current:.1f}°" if current is not None else "—°")
        self.card_target.set_value(
            f"{setpoint:.1f}°", "SETPOINT A" if not self.mirror_check.isChecked()
            else "MIRROR")
        err = (setpoint - current) if current is not None else 0.0
        self.card_error.set_value(f"{err:+.1f}°")
        self.card_stim.set_value(f"{amp}%", "ACTIVE PULSE"
                                 if self.fes_chip.isChecked() else "MUTED")

        # Kinematics (scale 0-180° to the visualizer's convention)
        self.kinematics.set_angles(
            current if current is not None else 0.0,
            setpoint,
        )

        # Angle plot
        if self.angle_plot is not None:
            t = self.data_handler.get_time()
            angle = self.data_handler.get_active_angle()
            sp = self.data_handler.get_setpoint()
            n = min(t.size, angle.size, sp.size)
            if n > 0:
                self.angle_curve.setData(t[-n:], angle[-n:])
                self.setpoint_curve.setData(t[-n:], sp[-n:])

        # Error deviation bar
        self.error_bar.set_error(err)

        # Pulse intensity bars — show whichever active-arm muscle is
        # dominant. Biceps drives flexion (error > 0) and triceps drives
        # extension (error < 0); at any moment only one is non-zero, so
        # max() always picks the active channel.  Showing only biceps was
        # leaving the bar at 0 while the user felt triceps stimulation.
        bp = self.data_handler.get_biceps_pw()
        tp = self.data_handler.get_triceps_pw()
        if bp.size > 0 and tp.size > 0:
            self.pulse_bars.push_sample(max(float(bp[-1]), float(tp[-1])))

        # Sample rate
        self._sample_rate_label.setText(
            f"{self.data_handler.backend_sample_rate:.0f} Hz")

        # Tuner status
        self._refresh_tuner_status()

    def _latest(self, arr) -> Optional[float]:
        if arr is None or getattr(arr, "size", 0) == 0:
            return None
        return float(arr[-1])

    def _effective_setpoint(self) -> float:
        msg = self.queue_handler.control_message
        if msg.mirror_mode:
            # Mirror: the opposite arm's current angle
            opp = (self.data_handler.elbow_R if self.data_handler.active_arm_is_left
                   else self.data_handler.elbow_L)
            return float(opp[-1]) if len(opp) else float(msg.desired_angle_deg)
        return float(msg.desired_angle_deg)

    def _refresh_tuner_status(self) -> None:
        status = self.data_handler.tuner_status_text
        kp_hint = self.data_handler.tuner_kp_suggested
        self.tuner_status.setText(f"Tuner: {status}  Kp={kp_hint:.2f}")
        running = status in ("RAMPING_KP", "COLLECTING", "ANALYZING")
        self.autotune_btn.setProperty("running", "true" if running else "false")
        self.autotune_btn.style().unpolish(self.autotune_btn)
        self.autotune_btn.style().polish(self.autotune_btn)

        # Propagate the tuning state to every widget that displays the
        # target angle. The kinematics canvas shows a tertiary-tinted
        # backdrop (matching the AUTO-CALIBRATE button's running color),
        # the Target Angle card re-roles its value label tertiary, and
        # the setpoint trace on the angle plot switches to a bolder pen
        # so the operator sees the target-angle "state" change on every
        # graph that shows it.
        self.kinematics.set_tuning(running)
        self.card_target.set_tuning(running)
        if self.angle_plot is not None:
            self.setpoint_curve.setPen(
                self._setpoint_pen_tuning if running
                else self._setpoint_pen_idle
            )

        # Snap Kp/Ki/Kd sliders to the latest auto-tune result whenever the
        # backend publishes a new one (detected via the monotonic counter).
        counter = self.data_handler.tuner_result_counter
        if counter and counter != self._last_tuner_result_counter:
            self._last_tuner_result_counter = counter
            self._apply_pid_gains_to_sliders(
                self.data_handler.tuner_result_kp,
                self.data_handler.tuner_result_ki,
                self.data_handler.tuner_result_kd,
            )

    # ─────────────────────────────────────────────────────────────
    # Slot handlers — push changes into control/utility messages
    # ─────────────────────────────────────────────────────────────
    def _on_fes_toggled(self, active: bool) -> None:
        active = bool(active)
        self.queue_handler.utility_message.FesIsActive = active
        self.fes_chip.setText("● FES SYSTEM ACTIVE" if active
                              else "○ FES SYSTEM IDLE")
        self._set_controller_controls_enabled(active)

    def _set_controller_controls_enabled(self, enabled: bool) -> None:
        """Enable/disable every PID-controller-related footer widget.

        When FES is inactive the strategy freezes the PID state (no integral
        wind-up, no tuner progress) so the matching operator controls in the
        GUI are muted to reflect that — Kp / Ki / Kd sliders, AUTO-CALIBRATE,
        and RESET PID are disabled together, and their paired P / I / D text
        labels are greyed via ``:disabled`` styling in the stylesheet.
        Setpoint and Amplitude remain adjustable because they are
        stimulation configuration rather than controller state.
        """
        for widget in (
            self.kp_slider, self.ki_slider, self.kd_slider,
            self.autotune_btn, self.reset_pid_btn,
        ):
            widget.setEnabled(enabled)
        # Propagate the disabled state to the paired P / I / D labels so
        # their text fades in sync with the slider groove / handle.
        for slider in (self.kp_slider, self.ki_slider, self.kd_slider):
            for lbl in (getattr(slider, "_key_label", None),
                        getattr(slider, "_val_label", None)):
                if lbl is not None:
                    lbl.setEnabled(enabled)

    def _on_emergency_stop(self) -> None:
        self.fes_chip.setChecked(False)

    def _on_arm_clicked(self, side: str) -> None:
        is_left = (side == "left")
        self.arm_left_btn.setChecked(is_left)
        self.arm_right_btn.setChecked(not is_left)
        self.queue_handler.control_message.active_arm = side

    def _on_setpoint_changed(self, deg: int) -> None:
        self.queue_handler.control_message.desired_angle_deg = float(deg)

    def _on_mirror_toggled(self, on: bool) -> None:
        self.queue_handler.control_message.mirror_mode = bool(on)
        self.sp_slider.setEnabled(not on)

    def _on_amplitude_changed(self, amp: int) -> None:
        self.queue_handler.control_message.ems_amplitude = int(amp)

    def _emit_gains(self, _value: int = 0) -> None:
        kp = self.kp_slider.value() * 0.01
        ki = self.ki_slider.value() * 0.01
        kd = self.kd_slider.value() * 0.01
        msg = self.queue_handler.control_message
        msg.pid_kp = kp
        msg.pid_ki = ki
        msg.pid_kd = kd

    def _apply_pid_gains_to_sliders(self, kp: float, ki: float, kd: float) -> None:
        """Snap the three PID sliders to the given gains and push them once.

        Sliders store integer ticks scaled by 0.01, so we round to the nearest
        tick and clamp to each slider's configured range. Signals are blocked
        during the write so the per-slider ``valueChanged`` handlers don't
        each emit an intermediate gain triplet; we call ``_emit_gains`` once
        at the end to propagate the final values into the control message.
        """
        for slider, gain in (
            (self.kp_slider, kp),
            (self.ki_slider, ki),
            (self.kd_slider, kd),
        ):
            tick = int(round(gain / 0.01))
            tick = max(slider.minimum(), min(slider.maximum(), tick))
            slider.blockSignals(True)
            slider.setValue(tick)
            slider.blockSignals(False)
            # Refresh the value label manually — we blocked its signal above.
            self._refresh_param_label(slider)
        self._emit_gains()

    def _refresh_param_label(self, slider: QtWidgets.QSlider) -> None:
        """Look up the value label paired with ``slider`` and update its text.

        The sliders in the footer are created by ``_build_param_slider``,
        which stores three paired labels (``kp_val_label`` etc.) as
        attributes on the window. This helper keeps the display in sync
        when we update a slider programmatically with signals blocked.
        """
        pairs = (
            (self.kp_slider, self.kp_val_label, 0.01, ""),
            (self.ki_slider, self.ki_val_label, 0.01, ""),
            (self.kd_slider, self.kd_val_label, 0.01, ""),
        )
        for s, lbl, scale, unit in pairs:
            if s is slider:
                lbl.setText(f"{s.value() * scale:.2f}{unit}")
                return

    def _on_reset_pid(self) -> None:
        """Zero out the PID gains (sliders + control message)."""
        self._apply_pid_gains_to_sliders(0.0, 0.0, 0.0)

    def _on_autotune(self) -> None:
        self.queue_handler.control_message.auto_tune_request = True
        QtCore.QTimer.singleShot(500, self._clear_autotune_flag)

    def _clear_autotune_flag(self) -> None:
        self.queue_handler.control_message.auto_tune_request = False

    def _on_calibrate(self) -> None:
        """Request a one-shot I-pose MoCap calibration.

        The utility message is replicated to the backend in full on every
        auto-send (see ``QueueHandler.send_utility_message``), so we must
        clear the flag shortly after raising it. Otherwise the next time
        the operator changes any other utility field (e.g. toggling the
        FES chip), the queued message would still carry
        ``CalibrationLoopIsActive=True`` and the backend would re-run
        calibration automatically. Mirrors the one-shot pattern used by
        ``_on_autotune`` / ``_clear_autotune_flag``.
        """
        self.queue_handler.utility_message.CalibrationLoopIsActive = True
        QtCore.QTimer.singleShot(500, self._clear_calibration_flag)

    def _clear_calibration_flag(self) -> None:
        self.queue_handler.utility_message.CalibrationLoopIsActive = False

    # ─────────────────────────────────────────────────────────────
    # Initial state + shutdown
    # ─────────────────────────────────────────────────────────────
    def _send_initial_state(self) -> None:
        self.queue_handler.utility_message.FesIsActive = self.fes_chip.isChecked()
        msg = self.queue_handler.control_message
        msg.active_arm        = "left" if self.arm_left_btn.isChecked() else "right"
        msg.desired_angle_deg = float(self.sp_slider.value())
        msg.mirror_mode       = self.mirror_check.isChecked()
        msg.pid_kp            = self.kp_slider.value() * 0.01
        msg.pid_ki            = self.ki_slider.value() * 0.01
        msg.pid_kd            = self.kd_slider.value() * 0.01
        msg.ems_amplitude     = int(self.amp_slider.value())

    def closeEvent(self, event) -> None:  # noqa: N802
        self._timer.stop()
        self.data_handler.cleanup()
        event.accept()
