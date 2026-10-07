# SPDX-License-Identifier: MIT
"""
Elbow flexion example — reusable building blocks.

Two self-contained helpers used by ``ElbowFlexionPIDStrategy``:

* ``SimplePID`` — minimal clamped PID with anti-windup.  Deliberately tiny
  so the example does not pull in ``simple-pid`` as a dependency.
* ``FFTAutoTuner`` — state machine that ramps Kp until sustained oscillation
  is detected, then picks Kp/Ki/Kd via a Ziegler-Nichols rule with the
  oscillation period taken from the dominant FFT frequency of the angle
  trace.  Ported in spirit from the source project's ``calibrate_PID``
  routine (``FES-Elbow-flexion-control/src/.../control_system.py``).

Both classes are framework-agnostic — the strategy drives them with raw
floats and timing deltas.
"""
from __future__ import annotations

from collections import deque
from typing import Optional, Tuple

import numpy as np

from .elbow_types import (
    TUNER_STATE_ANALYZING,
    TUNER_STATE_COLLECTING,
    TUNER_STATE_DONE,
    TUNER_STATE_FAILED,
    TUNER_STATE_IDLE,
    TUNER_STATE_NAMES,
    TUNER_STATE_RAMPING,
)


class SimplePID:
    """Clamped PID controller with integral anti-windup.

    Usage::

        pid = SimplePID(kp=1.0, ki=0.1, kd=0.01, output_limits=(0, 100))
        while running:
            output = pid(error, dt)
    """

    def __init__(self, kp: float = 0.0, ki: float = 0.0, kd: float = 0.0,
                 output_limits: Tuple[float, float] = (0.0, 100.0)) -> None:
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self._out_min, self._out_max = output_limits
        self._integral = 0.0
        self._prev_measurement: Optional[float] = None

    def update_gains(self, kp: float, ki: float, kd: float) -> None:
        """Update gains live. Safe to call every cycle."""
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)

    def reset(self) -> None:
        """Clear integral and derivative history."""
        self._integral = 0.0
        self._prev_measurement = None

    def __call__(self, setpoint: float, measurement: float, dt: float) -> float:
        """Compute the controller output for the given setpoint/measurement.

        Uses **derivative on measurement** (rather than on error) so a step
        change in ``setpoint`` — e.g. the operator dragging the angle slider
        or ``mirror_mode`` snapping onto the opposite arm's angle — does not
        produce a spurious D-term spike. When ``setpoint`` is held constant
        this is identical to the textbook ``d(error)/dt`` form, since
        ``d(error)/dt = -d(measurement)/dt``.

        Anti-windup has two layers working together so the I-term cannot
        oversaturate the output:

        1. **Conditional integration** — if the raw PID sum saturates the
           output and the current error sign would push the integral
           *further* into saturation, freeze the integral. If the error
           sign is pulling the output back from the saturation bound,
           the integral is *allowed* to update (so the accumulator can
           unwind quickly rather than take as long to empty as it did to
           fill).
        2. **Integral span clamp** — the integral accumulator itself is
           hard-bounded so that ``|ki * integral|`` can never exceed the
           full output range. With a high-Ki slider setting this stops
           the I-term alone from pegging the output and dominating the
           P / D contributions.
        """
        error = setpoint - measurement
        if dt <= 0.0:
            return self._clamp(self.kp * error)

        if self._prev_measurement is None:
            derivative = 0.0
        else:
            derivative = -(measurement - self._prev_measurement) / dt
        self._prev_measurement = measurement

        candidate_integral = self._integral + error * dt
        raw = (self.kp * error
               + self.ki * candidate_integral
               + self.kd * derivative)
        clamped = self._clamp(raw)

        # Layer 1: conditional integration with unwinding exception.
        unwinding = (
            (clamped >= self._out_max and error < 0.0)
            or (clamped <= self._out_min and error > 0.0)
        )
        if clamped == raw or unwinding:
            self._integral = candidate_integral
        # else: saturated and error would wind further — freeze integral.

        # Layer 2: hard-bound the integral so its contribution is at most the
        # full output span. Guards against high-Ki slider or auto-tuner
        # results swamping P and D with an unbounded accumulator.
        if self.ki != 0.0:
            integral_span = (self._out_max - self._out_min) / abs(self.ki)
            if self._integral > integral_span:
                self._integral = integral_span
            elif self._integral < -integral_span:
                self._integral = -integral_span

        return clamped

    def _clamp(self, value: float) -> float:
        if value < self._out_min:
            return self._out_min
        if value > self._out_max:
            return self._out_max
        return value


class FFTAutoTuner:
    """State-machine auto-tuner using FFT-based period estimation.

    Lifecycle (call ``step(angle, dt)`` each control cycle):

        IDLE -> RAMPING_KP -> COLLECTING -> ANALYZING -> DONE | FAILED

    - ``start()`` transitions IDLE -> RAMPING_KP.  While RAMPING_KP the
      tuner exposes an increasing ``kp_suggested`` that the strategy
      applies to its PID, and tracks oscillation amplitude of the fed
      angle signal.
    - When oscillation amplitude exceeds ``oscillation_threshold`` for
      a short confirmation window, transitions to COLLECTING for
      ``collect_seconds``.
    - After collection, runs FFT on the angle buffer, picks the dominant
      non-DC frequency, and computes Ku/Tu → (Kp, Ki, Kd) via
      Ziegler-Nichols.  Stores result in ``self.result`` and moves to
      DONE.  Fails (FAILED) if total elapsed time exceeds ``time_limit``
      or no oscillation is detected.

    Safety: ``kp_suggested`` is capped at ``kp_cap`` (default 3.0) to
    avoid runaway stimulation.  The strategy should still require an
    explicit user press + FES-active before invoking ``start()``.
    """

    def __init__(self,
                 kp_ramp_rate: float = 0.5,        # units of Kp per second
                 kp_cap: float = 3.0,              # hard ceiling on Kp
                 oscillation_threshold: float = 4.0,  # degrees peak-to-peak
                 confirmation_seconds: float = 1.0,
                 collect_seconds: float = 6.0,
                 time_limit: float = 30.0,
                 window_seconds: float = 2.0) -> None:
        self.kp_ramp_rate = kp_ramp_rate
        self.kp_cap = kp_cap
        self.oscillation_threshold = oscillation_threshold
        self.confirmation_seconds = confirmation_seconds
        self.collect_seconds = collect_seconds
        self.time_limit = time_limit
        self.window_seconds = window_seconds

        self.state: int = TUNER_STATE_IDLE
        self.kp_suggested: float = 0.0
        self.result: Optional[Tuple[float, float, float]] = None

        self._elapsed: float = 0.0
        self._confirm_elapsed: float = 0.0
        self._collect_elapsed: float = 0.0

        # Sliding window for oscillation detection (peak-to-peak)
        self._recent_angles: deque = deque()
        self._recent_dts: deque = deque()
        # Full collection buffer for FFT
        self._collected_angles: list = []
        self._collected_dts: list = []
        # Kp value at the moment sustained oscillation was detected
        self._kp_at_oscillation: float = 0.0

    # ── Public API ───────────────────────────────────────────────

    @property
    def is_done(self) -> bool:
        return self.state in (TUNER_STATE_DONE, TUNER_STATE_FAILED)

    @property
    def status_text(self) -> str:
        return TUNER_STATE_NAMES.get(self.state, "?")

    def start(self) -> None:
        """Transition IDLE -> RAMPING_KP. No-op if not IDLE."""
        if self.state != TUNER_STATE_IDLE:
            return
        self._reset_internal()
        self.state = TUNER_STATE_RAMPING

    def reset(self) -> None:
        """Return to IDLE, clearing result."""
        self._reset_internal()
        self.state = TUNER_STATE_IDLE
        self.result = None

    def step(self, angle: float, dt: float) -> None:
        """Advance the state machine by one control cycle."""
        if self.state == TUNER_STATE_IDLE or self.state == TUNER_STATE_DONE \
                or self.state == TUNER_STATE_FAILED:
            return

        self._elapsed += dt
        if self._elapsed > self.time_limit:
            self.state = TUNER_STATE_FAILED
            return

        if self.state == TUNER_STATE_RAMPING:
            self._step_ramping(angle, dt)
        elif self.state == TUNER_STATE_COLLECTING:
            self._step_collecting(angle, dt)
        elif self.state == TUNER_STATE_ANALYZING:
            self._step_analyzing()

    # ── State handlers ────────────────────────────────────────────

    def _step_ramping(self, angle: float, dt: float) -> None:
        # Ramp Kp
        self.kp_suggested = min(
            self.kp_suggested + self.kp_ramp_rate * dt,
            self.kp_cap,
        )

        # Update sliding window of recent angles (last `window_seconds`)
        self._recent_angles.append(angle)
        self._recent_dts.append(dt)
        window_total = sum(self._recent_dts)
        while window_total > self.window_seconds and len(self._recent_dts) > 1:
            self._recent_dts.popleft()
            self._recent_angles.popleft()
            window_total = sum(self._recent_dts)

        # Peak-to-peak over the window
        if len(self._recent_angles) < 8:
            return
        pk2pk = max(self._recent_angles) - min(self._recent_angles)

        if pk2pk >= self.oscillation_threshold:
            self._confirm_elapsed += dt
            if self._confirm_elapsed >= self.confirmation_seconds:
                # Oscillation sustained — begin collection
                self._kp_at_oscillation = self.kp_suggested
                self.state = TUNER_STATE_COLLECTING
                self._collect_elapsed = 0.0
                self._collected_angles = list(self._recent_angles)
                self._collected_dts = list(self._recent_dts)
        else:
            self._confirm_elapsed = 0.0

    def _step_collecting(self, angle: float, dt: float) -> None:
        self._collect_elapsed += dt
        self._collected_angles.append(angle)
        self._collected_dts.append(dt)
        if self._collect_elapsed >= self.collect_seconds:
            self.state = TUNER_STATE_ANALYZING

    def _step_analyzing(self) -> None:
        result = self._compute_gains()
        if result is None:
            self.state = TUNER_STATE_FAILED
            return
        self.result = result
        self.state = TUNER_STATE_DONE

    # ── Internals ─────────────────────────────────────────────────

    def _compute_gains(self) -> Optional[Tuple[float, float, float]]:
        """Run FFT on collected angle buffer and compute ZN gains.

        Returns (Kp, Ki, Kd) or None on failure (not enough samples,
        no dominant frequency, etc.).
        """
        n = len(self._collected_angles)
        if n < 32:
            return None
        angles = np.asarray(self._collected_angles, dtype=float)
        dts = np.asarray(self._collected_dts, dtype=float)
        mean_dt = float(np.mean(dts))
        if mean_dt <= 0.0:
            return None
        fs = 1.0 / mean_dt  # sampling frequency (Hz)

        # Remove DC and any linear drift
        angles = angles - np.mean(angles)
        # Windowed FFT (Hann) to suppress leakage
        window = np.hanning(n)
        spectrum = np.abs(np.fft.rfft(angles * window))
        freqs = np.fft.rfftfreq(n, d=mean_dt)

        # Ignore DC bin + anything below 0.3 Hz (slow drift) and above fs/3
        valid = (freqs > 0.3) & (freqs < fs / 3.0)
        if not np.any(valid):
            return None
        idx_rel = int(np.argmax(spectrum[valid]))
        dominant_freq = float(freqs[valid][idx_rel])
        if dominant_freq <= 0.0:
            return None

        tu = 1.0 / dominant_freq
        ku = self._kp_at_oscillation
        if ku <= 0.0:
            return None
        # Classic Ziegler-Nichols (PID) coefficients
        kp = 0.6 * ku
        ki = 1.2 * ku / tu
        kd = 0.075 * ku * tu
        return (kp, ki, kd)

    def _reset_internal(self) -> None:
        self.kp_suggested = 0.0
        self.result = None
        self._elapsed = 0.0
        self._confirm_elapsed = 0.0
        self._collect_elapsed = 0.0
        self._recent_angles.clear()
        self._recent_dts.clear()
        self._collected_angles = []
        self._collected_dts = []
        self._kp_at_oscillation = 0.0
