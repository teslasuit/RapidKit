# SPDX-License-Identifier: MIT
"""
Elbow Flexion PID Strategy — comprehensive joint-angle-tracking example.

What this demonstrates
----------------------
* Reading biomechanical joint angles (``self.joints.ElbowFlexExtL/R``) as
  continuous per-cycle feedback, in contrast to strategies driven by
  discrete events (e.g. foot contact).
* Agonist/antagonist stimulation: biceps drives flexion, triceps drives
  extension, both via the same signed error.
* Single-active-arm pattern with an opposite-arm mirroring mode.
* A self-contained PID controller and FFT-based auto-tuner (see
  ``elbow_utils.py``), showing how a strategy can carry substantial
  internal state across cycles.

Source
------
Ported from a standalone research prototype that used raw quaternions and
three separate QTimers; here the framework provides pre-processed joint
angles (``BiomechanicalData``) and the single engine cycle absorbs the work
previously split across view/PID/haptic timers.
"""
from __future__ import annotations

import time
from typing import Optional

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase
from teslasuit_rapidkit.data.types import (
    BiomechanicalData,
    ControlMessage,
    EmsData,
    EMSParamData,
    StepDetectorData,
)

from .elbow_types import (
    TUNER_STATE_COLLECTING,
    TUNER_STATE_DONE,
    TUNER_STATE_FAILED,
    TUNER_STATE_IDLE,
    TUNER_STATE_RAMPING,
)
from .elbow_utils import FFTAutoTuner, SimplePID


class ElbowFlexionPIDStrategy(ControlStrategyBase):
    """Closed-loop PID on elbow flexion angle, driving biceps + triceps."""

    # Per-muscle pulse-width cap (us).  Tuned conservatively for upper-body
    # stimulation; the PID output is clamped to [0, PW_CAP_US].
    PW_CAP_US: int = 300

    # Pulse-width quantization step (µs). The PID output is a float that
    # changes by ±1 µs nearly every cycle; without quantization the stimulator
    # detects ``params_changed`` on every cycle and makes 5 SDK calls per
    # active muscle (~1000 SDK calls/s at 100 Hz), competing with the MoCap
    # data stream and dropping the engine sample rate.  Rounding to the
    # nearest 5 µs reduces rebuilds by ~5× with no perceptible effect on
    # stimulation smoothness (5 µs out of 300 µs is 1.7 %).
    PW_QUANT_US: int = 5

    # Nominal control-loop period (s) fed to the PID. The engine cycle is
    # paced by the SDK's blocking data-ready call (~100 Hz); using a fixed
    # nominal here decouples the I-term (error * dt) and D-term (Δm / dt)
    # from real measurement jitter, which otherwise swings the float output
    # by several µs every cycle and turns the integer pulse-width into a
    # noisy sawtooth. The auto-tuner still gets the *measured* dt for its
    # elapsed-time bookkeeping.
    NOMINAL_DT_S: float = 0.01

    # If the actual cycle period exceeds this multiple of NOMINAL_DT_S we
    # treat it as a stall — a long gap without measurements would otherwise
    # let the integrator wind up on stale error and spike when the loop
    # catches up.
    STALL_DT_MULTIPLIER: float = 3.0


    def __init__(self) -> None:
        super().__init__()
        self._pid_biceps = SimplePID(output_limits=(0.0, float(self.PW_CAP_US)))
        self._pid_triceps = SimplePID(output_limits=(0.0, float(self.PW_CAP_US)))
        self._tuner = FFTAutoTuner()
        self._last_cycle_time: Optional[float] = None
        # Latest gains produced by the FFT auto-tuner, held across cycles so the
        # GUI can latch them into the Kp/Ki/Kd sliders after a successful run.
        # The counter is monotonic; the GUI diffs it to detect a new result.
        self._tuner_result_counter: int = 0
        self._tuner_result_kp: float = 0.0
        self._tuner_result_ki: float = 0.0
        self._tuner_result_kd: float = 0.0
        # Captured in ``run_strategy`` so ``process`` can gate controller state
        # on the global FES kill switch — integrals and derivative history are
        # quiesced while FES is inactive to prevent wind-up during the idle
        # period and a stimulation spike when the operator re-enables FES.
        self._fes_active: bool = True

    def setup(self, muscles=None, suit=None, config=None) -> None:
        super().setup(muscles=muscles, suit=suit, config=config)
        self._pid_biceps.reset()
        self._pid_triceps.reset()
        self._tuner.reset()

    def run_strategy(self,
                     control_message: ControlMessage,
                     biomechanical_data: BiomechanicalData,
                     step_detector_data: StepDetectorData,
                     ems_data: EmsData,
                     fes_active: bool = True,
                     processed_data=None) -> None:
        """Capture the global FES flag, then run the standard cycle.

        The base class applies ``fes_active`` only to the final stimulation
        mute. For closed-loop PID we also need it inside ``process`` so the
        integral accumulator and tuner state don't drift while the muscles
        are muted.
        """
        self._fes_active = bool(fes_active)
        super().run_strategy(
            control_message=control_message,
            biomechanical_data=biomechanical_data,
            step_detector_data=step_detector_data,
            ems_data=ems_data,
            fes_active=fes_active,
            processed_data=processed_data,
        )

    def process(self) -> None:
        # Guard: params may be the base ControlMessage on the very first cycle
        # before the GUI has sent anything.  Nothing to do in that case.
        if self.params is None or not hasattr(self.params, "active_arm"):
            return

        # FES kill switch: with stimulation muted, there's no plant response
        # for the controller to track. Freezing here prevents three failure
        # modes:
        #   * integral wind-up on whatever residual error the passive arm
        #     happens to carry (would cause a huge pulse-width spike when
        #     the operator flips FES back on);
        #   * stale derivative kicks from a jump in ``current`` after FES is
        #     re-enabled;
        #   * the auto-tuner silently progressing through its state machine
        #     while it isn't actually driving the muscle.
        # Also clear the one-shot ``auto_tune_request`` flag so any click
        # that landed during the FES-off window doesn't auto-start the
        # tuner the instant FES comes back on.
        if not self._fes_active:
            self._pid_biceps.reset()
            self._pid_triceps.reset()
            self._tuner.reset()
            self._last_cycle_time = None
            if getattr(self.params, "auto_tune_request", False):
                self.params.auto_tune_request = False
            return

        # ── Timing ────────────────────────────────────────────────
        # Measure the actual cycle period for tuner bookkeeping and stall
        # detection.  The PID itself uses NOMINAL_DT_S (not measured dt)
        # so that dt jitter (±10–20 % at 100 Hz) does not swing the I-term
        # and D-term each cycle, which would turn the quantised pulse-width
        # into a noisy sawtooth and trigger a stimulator rebuild every cycle.
        now = time.perf_counter()
        if self._last_cycle_time is None:
            measured_dt = 0.0
        else:
            measured_dt = now - self._last_cycle_time
        self._last_cycle_time = now

        # Stall guard: a gap longer than 3× nominal (e.g. SDK reconnect,
        # process scheduling hiccup) would let the integrator wind up on
        # stale error and produce a stimulation spike when the loop catches
        # up.  Reset both PIDs to quiesce state, matching v2 behaviour.
        if measured_dt > self.NOMINAL_DT_S * self.STALL_DT_MULTIPLIER:
            self._pid_biceps.reset()
            self._pid_triceps.reset()
            self._last_cycle_time = None

        # ── 1. Active arm → read angles + pick muscle field names ─
        if self.params.active_arm == "right":
            current  = self.joints.ElbowFlexExtR
            opposite = self.joints.ElbowFlexExtL
            biceps_field, triceps_field = "biceps_right", "triceps_right"
            inactive_biceps, inactive_triceps = "biceps_left", "triceps_left"
        else:
            current  = self.joints.ElbowFlexExtL
            opposite = self.joints.ElbowFlexExtR
            biceps_field, triceps_field = "biceps_left", "triceps_left"
            inactive_biceps, inactive_triceps = "biceps_right", "triceps_right"

        # ── 2. Setpoint: mirror the opposite arm or follow the slider ─
        if self.params.mirror_mode:
            setpoint = opposite
        else:
            setpoint = float(self.params.desired_angle_deg)

        # ── 3. Auto-tune state machine ────────────────────────────
        # Latch a completed cycle first. On DONE we push the tuned gains into
        # params and bump the monotonic counter so the GUI can snap its
        # sliders; then we park the tuner back in IDLE. FAILED is left in
        # place for this cycle so the GUI can observe the failure via the
        # shared-memory state field — the next request clears it below.
        if self._tuner.state == TUNER_STATE_DONE and self._tuner.result is not None:
            kp_tuned, ki_tuned, kd_tuned = self._tuner.result
            self.params.pid_kp = float(kp_tuned)
            self.params.pid_ki = float(ki_tuned)
            self.params.pid_kd = float(kd_tuned)
            self._tuner_result_kp = float(kp_tuned)
            self._tuner_result_ki = float(ki_tuned)
            self._tuner_result_kd = float(kd_tuned)
            self._tuner_result_counter += 1
            self._tuner.reset()

        # A fresh auto-tune request starts (or *retries*) a run. We accept it
        # from IDLE or from the terminal FAILED state — otherwise a tune that
        # timed out without finding oscillation would leave the tuner stuck
        # and the operator unable to retry. ``reset()`` is a no-op when
        # already IDLE; for FAILED it returns the tuner to a startable state.
        # We clear the one-shot flag as soon as we act on it so the tuner
        # doesn't auto-restart the instant it resets to IDLE with the GUI
        # click still latched in the message.
        if self.params.auto_tune_request and self._tuner.state in (
            TUNER_STATE_IDLE,
            TUNER_STATE_FAILED,
        ):
            self._tuner.reset()
            self._tuner.start()
            self.params.auto_tune_request = False

        self._tuner.step(current, measured_dt)

        # ── 4. Refresh PID gains from params every cycle ──────────
        kp = float(self.params.pid_kp)
        ki = float(self.params.pid_ki)
        kd = float(self.params.pid_kd)
        # While the auto-tuner is active, override the operator Kp with the
        # tuner's current suggestion. This must cover both RAMPING (where
        # kp_suggested is climbing to induce oscillation) AND COLLECTING
        # (where kp_suggested is held at ``_kp_at_oscillation`` so the plant
        # keeps oscillating long enough for the FFT window to lock onto the
        # dominant period). Ki and Kd are forced to zero: Ziegler-Nichols
        # Ku identification is defined for a proportional-only loop, so any
        # nonzero I or D term left over from a previous tune would distort
        # the oscillation period the FFT locks onto and yield garbage gains.
        if self._tuner.state in (TUNER_STATE_RAMPING, TUNER_STATE_COLLECTING):
            kp = self._tuner.kp_suggested
            ki = 0.0
            kd = 0.0
        self._pid_biceps.update_gains(kp, ki, kd)
        self._pid_triceps.update_gains(kp, ki, kd)

        # ── 5. PID law ────────────────────────────────────────────
        # Framework convention: ElbowFlexExt* grows with flexion (0° = straight
        # arm, ~135° = fully bent).  Biceps (flexor) fires when we need MORE
        # flexion — i.e. when setpoint > current → positive error.  Triceps
        # (extensor) fires when we need less flexion → we feed the negated
        # setpoint/measurement pair, which gives the triceps PID a positive
        # error exactly when extension is needed.  PID outputs are clamped
        # to [0, PW_CAP_US] so the "wrong side" saturates to zero
        # automatically. Both PIDs compute the derivative on their own
        # measurement signal, so a slider tug on ``setpoint`` doesn't kick
        # the D-term.
        biceps_pw  = self._pid_biceps( setpoint,  current, self.NOMINAL_DT_S)
        triceps_pw = self._pid_triceps(-setpoint, -current, self.NOMINAL_DT_S)

        # ── 6. Emit stimulation on active arm; mute inactive arm ───
        amp    = int(self.params.ems_amplitude)
        period = float(self.params.ems_period_ms)
        # Quantize PW to PW_QUANT_US steps before emitting. The raw PID float
        # changes by ±1 µs every cycle; without this the stimulator rebuilds
        # its playable on every cycle (5 SDK calls × 2 muscles = 10 calls/cycle
        # at 100 Hz), competing with MoCap BLE bandwidth and dropping sample
        # rate.  5 µs resolution is imperceptible to the subject.
        q = self.PW_QUANT_US
        biceps_pw_emit  = int(round(biceps_pw  / q)) * q
        triceps_pw_emit = int(round(triceps_pw / q)) * q
        setattr(self.ems_output, biceps_field, EMSParamData(
            IsMuted=False, PulseWidth=biceps_pw_emit,
            Period=period, Amplitude=amp,
        ))
        setattr(self.ems_output, triceps_field, EMSParamData(
            IsMuted=False, PulseWidth=triceps_pw_emit,
            Period=period, Amplitude=amp,
        ))
        setattr(self.ems_output, inactive_biceps,  EMSParamData(IsMuted=True))
        setattr(self.ems_output, inactive_triceps, EMSParamData(IsMuted=True))
