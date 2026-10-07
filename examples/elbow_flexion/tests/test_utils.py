# SPDX-License-Identifier: MIT
"""Offline tests for SimplePID, FFTAutoTuner, and ElbowFlexionPIDStrategy.

Run with ``pytest examples/elbow_flexion/tests/`` from the repo root. No
hardware required.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from examples.elbow_flexion.elbow_utils import FFTAutoTuner, SimplePID
from examples.elbow_flexion.elbow_types import (
    TUNER_STATE_DONE,
    TUNER_STATE_FAILED,
    TUNER_STATE_IDLE,
    TUNER_STATE_RAMPING,
)


# ────────────────────────────────────────────────────────────
# SimplePID
# ────────────────────────────────────────────────────────────

def test_simple_pid_p_only_clamps_to_limits():
    pid = SimplePID(kp=10.0, output_limits=(0, 100))
    # Error of +100 → kp*error = 1000 → clamped to 100
    out = pid(setpoint=100.0, measurement=0.0, dt=0.01)
    assert out == 100.0
    # Negative error → output would be -1000 → clamped to 0
    out = pid(setpoint=0.0, measurement=100.0, dt=0.01)
    assert out == 0.0


def test_simple_pid_integral_windup_prevented():
    pid = SimplePID(kp=0.0, ki=1.0, kd=0.0, output_limits=(0, 10))
    # Feed a large positive error at saturation for many steps
    for _ in range(1000):
        out = pid(setpoint=100.0, measurement=0.0, dt=0.01)
    assert out == 10.0
    # Integral should not have accumulated unboundedly — switching to
    # negative error should respond within a bounded number of steps.
    recovered = False
    for _ in range(200):
        out = pid(setpoint=0.0, measurement=10.0, dt=0.01)
        if out == 0.0:
            recovered = True
            break
    assert recovered, "Anti-windup failed: integral kept PID saturated"


def test_simple_pid_update_gains_mid_run():
    pid = SimplePID(kp=1.0, output_limits=(0, 100))
    assert pid(setpoint=10.0, measurement=0.0, dt=0.01) == 10.0
    pid.update_gains(kp=2.0, ki=0.0, kd=0.0)
    assert pid(setpoint=10.0, measurement=0.0, dt=0.01) == 20.0


def test_simple_pid_i_term_alone_cannot_oversaturate_span():
    """Integral span clamp: ``|ki * integral|`` stays within output range.

    A high Ki combined with a persistent error used to let the I-term alone
    dwarf the output range, taking seconds to unwind. The integral is now
    hard-bounded so its contribution never exceeds ``out_max - out_min``.
    """
    pid = SimplePID(kp=0.0, ki=5.0, kd=0.0, output_limits=(0, 100))
    # Hammer a large positive error for 10 seconds of simulated time.
    for _ in range(1000):
        pid(setpoint=50.0, measurement=0.0, dt=0.01)
    # Integral span cap is (100 - 0) / 5 = 20 → |ki * integral| ≤ 100.
    assert abs(pid.ki * pid._integral) <= (100.0 - 0.0) + 1e-6

    # Switching the error sign should unwind quickly (within ~2 s), not drag
    # on for however long the windup accumulated.
    recovered_in = None
    for step in range(400):
        if pid(setpoint=0.0, measurement=50.0, dt=0.01) == 0.0:
            recovered_in = step
            break
    assert recovered_in is not None and recovered_in < 250, (
        f"Unwinding took too long ({recovered_in} steps); "
        "integral span clamp not holding"
    )


def test_simple_pid_reset_clears_history():
    pid = SimplePID(kp=1.0, ki=1.0, kd=1.0, output_limits=(-1000, 1000))
    for _ in range(50):
        pid(setpoint=1.0, measurement=0.0, dt=0.01)
    # Before reset the integral has accumulated to ~0.5, giving output ~1.5.
    pre_reset = pid(setpoint=1.0, measurement=0.0, dt=0.01)
    assert pre_reset > 1.4
    pid.reset()
    # After reset the integral is cleared.  The first call integrates a single
    # step (error*dt = 0.01), so the output is P + ki*0.01 ≈ 1.01 — much
    # closer to the P-only value than to the pre-reset output.
    post_reset = pid(setpoint=1.0, measurement=0.0, dt=0.01)
    assert post_reset == pytest.approx(1.0, abs=0.05)


def test_simple_pid_no_derivative_kick_on_setpoint_step():
    """A step change in setpoint must NOT produce a D-term spike.

    Under derivative-on-error, raising the setpoint from 0 to 100 between
    two cycles would yield a derivative of (100 - 0) / dt = huge, swamping
    the P term. Derivative-on-measurement cancels this: with measurement
    constant the D contribution is zero regardless of setpoint jumps.
    """
    pid = SimplePID(kp=1.0, ki=0.0, kd=10.0, output_limits=(-1000, 1000))
    # Prime with setpoint == measurement so error = 0 and _prev_measurement
    # is populated.
    pid(setpoint=0.0, measurement=0.0, dt=0.01)
    # Step setpoint up; measurement is still 0. P contributes kp*100 = 100.
    # If derivative were on error, it would add kd * (100 - 0) / 0.01 = 1e5.
    out = pid(setpoint=100.0, measurement=0.0, dt=0.01)
    assert out == pytest.approx(100.0, abs=1e-6), (
        f"Derivative kick detected: expected ~100 (P-only), got {out}"
    )


# ────────────────────────────────────────────────────────────
# FFTAutoTuner
# ────────────────────────────────────────────────────────────

def test_tuner_starts_in_idle():
    tuner = FFTAutoTuner()
    assert tuner.state == TUNER_STATE_IDLE
    assert not tuner.is_done


def test_tuner_start_transitions_to_ramping():
    tuner = FFTAutoTuner()
    tuner.start()
    assert tuner.state == TUNER_STATE_RAMPING


def test_tuner_step_is_noop_when_idle():
    tuner = FFTAutoTuner()
    tuner.step(angle=10.0, dt=0.01)
    assert tuner.state == TUNER_STATE_IDLE
    assert tuner.kp_suggested == 0.0


def test_tuner_fails_on_time_limit_with_flat_input():
    tuner = FFTAutoTuner(time_limit=2.0, kp_ramp_rate=0.1, kp_cap=5.0)
    tuner.start()
    # Feed a constant angle — no oscillation, should time out as FAILED
    for _ in range(int(3.0 / 0.01)):
        tuner.step(angle=10.0, dt=0.01)
        if tuner.is_done:
            break
    assert tuner.state == TUNER_STATE_FAILED


def test_tuner_completes_with_synthetic_oscillation():
    """Feed a clear sinusoid → tuner should reach DONE with plausible gains.

    Uses a generous configuration to keep the test deterministic:
    * ramp Kp quickly so we leave RAMPING early;
    * oscillation threshold is well below the sinusoid amplitude;
    * confirmation window is short.
    """
    tuner = FFTAutoTuner(
        kp_ramp_rate=5.0,            # ramp fast
        kp_cap=2.0,
        oscillation_threshold=2.0,   # sinusoid amplitude 20° peak-to-peak > threshold
        confirmation_seconds=0.3,
        collect_seconds=3.0,
        time_limit=20.0,
        window_seconds=1.0,
    )
    tuner.start()
    dt = 0.01
    freq_hz = 2.0  # known dominant frequency
    amp_deg = 10.0  # zero-to-peak → 20° peak-to-peak
    t = 0.0
    for _ in range(int(20.0 / dt)):
        angle = amp_deg * math.sin(2 * math.pi * freq_hz * t)
        tuner.step(angle, dt)
        t += dt
        if tuner.is_done:
            break
    assert tuner.state == TUNER_STATE_DONE
    assert tuner.result is not None
    kp, ki, kd = tuner.result
    # Ziegler-Nichols with Tu = 1/2 Hz = 0.5s:
    # kp = 0.6 * Ku
    # ki = 1.2 * Ku / 0.5 = 2.4 * Ku
    # kd = 0.075 * Ku * 0.5 = 0.0375 * Ku
    # Just sanity-check they're in a reasonable range and positive.
    assert kp > 0
    assert ki > 0
    assert kd > 0
    # Tu should come out close to 0.5 s → ki/kp ≈ 2.4/0.6 = 4.0
    assert (ki / kp) == pytest.approx(4.0, rel=0.3), \
        f"Expected ki/kp ≈ 4.0 (Tu≈0.5s), got {ki/kp:.2f}"


# ────────────────────────────────────────────────────────────
# Strategy smoke test (no hardware)
# ────────────────────────────────────────────────────────────

def test_strategy_emits_stimulation_when_error_is_positive():
    """With setpoint > current, biceps should get a non-muted command."""
    from examples.elbow_flexion.elbow_control_strategy import ElbowFlexionPIDStrategy
    from examples.elbow_flexion.elbow_init_utils import init_ElbowControlMessage

    strategy = ElbowFlexionPIDStrategy()
    strategy.setup(muscles=None)
    strategy.params = init_ElbowControlMessage()
    strategy.params.active_arm = "left"
    strategy.params.desired_angle_deg = 90.0
    strategy.params.pid_kp = 5.0   # enough gain that PID output > 0
    strategy.params.ems_amplitude = 20
    strategy.joints.ElbowFlexExtL = 30.0   # current well below setpoint
    strategy.joints.ElbowFlexExtR = 0.0
    strategy.process()

    bl = strategy.ems_output.biceps_left
    tl = strategy.ems_output.triceps_left
    br = strategy.ems_output.biceps_right
    tr = strategy.ems_output.triceps_right

    assert not bl.IsMuted
    assert bl.PulseWidth > 0, "Biceps (agonist for flexion) should have pulse width"
    # Triceps PID receives the negated error, so when flexion is needed the
    # triceps output saturates to 0 (the antagonist relaxes).
    assert not tl.IsMuted
    assert tl.PulseWidth == 0
    # Inactive arm is muted
    assert br.IsMuted
    assert tr.IsMuted


def test_strategy_freezes_pid_and_tuner_when_fes_inactive():
    """FES kill-switch: integral must not accumulate and the auto-tuner
    must not progress while FES is inactive. Stimulation is muted by the
    framework regardless; this test pins down the strategy's internal
    state gating so the operator doesn't get a stimulation spike when
    FES is re-enabled after an idle period.
    """
    from examples.elbow_flexion.elbow_control_strategy import ElbowFlexionPIDStrategy
    from examples.elbow_flexion.elbow_init_utils import init_ElbowControlMessage
    from teslasuit_rapidkit.data.types import (
        BiomechanicalData,
        EmsData,
        StepDetectorData,
    )

    strategy = ElbowFlexionPIDStrategy()
    strategy.setup(muscles=None)

    params = init_ElbowControlMessage()
    params.active_arm = "left"
    params.desired_angle_deg = 90.0
    params.pid_kp = 5.0
    params.pid_ki = 3.0
    params.pid_kd = 0.1
    params.auto_tune_request = True          # would normally start the tuner
    params.ems_amplitude = 20

    joints = BiomechanicalData()
    joints.ElbowFlexExtL = 30.0               # large error: 90 - 30 = 60 deg

    # Drive many cycles with FES inactive — the strategy must stay quiescent.
    for _ in range(500):
        strategy.run_strategy(
            control_message=params,
            biomechanical_data=joints,
            step_detector_data=StepDetectorData(),
            ems_data=EmsData(),
            fes_active=False,
        )

    # PID accumulators must not have moved.
    assert strategy._pid_biceps._integral == 0.0
    assert strategy._pid_triceps._integral == 0.0
    assert strategy._pid_biceps._prev_measurement is None
    assert strategy._pid_triceps._prev_measurement is None
    # Tuner must not have progressed past IDLE.
    assert strategy._tuner.state == TUNER_STATE_IDLE
    # One-shot auto_tune_request must be cleared so it doesn't auto-fire
    # when FES comes back on.
    assert params.auto_tune_request is False


def test_strategy_mirror_mode_uses_opposite_arm_as_setpoint():
    from examples.elbow_flexion.elbow_control_strategy import ElbowFlexionPIDStrategy
    from examples.elbow_flexion.elbow_init_utils import init_ElbowControlMessage

    strategy = ElbowFlexionPIDStrategy()
    strategy.setup(muscles=None)
    strategy.params = init_ElbowControlMessage()
    strategy.params.active_arm = "left"
    strategy.params.desired_angle_deg = 0.0   # ignored in mirror mode
    strategy.params.mirror_mode = True
    strategy.params.pid_kp = 5.0
    strategy.params.ems_amplitude = 20

    # Right arm is raised; mirror mode should make that the target for the left.
    strategy.joints.ElbowFlexExtL = 30.0
    strategy.joints.ElbowFlexExtR = 120.0
    strategy.process()
    bl = strategy.ems_output.biceps_left
    # Error = 120 - 30 = +90 → biceps should be actively stimulated
    assert bl.PulseWidth > 0


def _strategy_for_autotune_tests():
    from examples.elbow_flexion.elbow_control_strategy import ElbowFlexionPIDStrategy
    from examples.elbow_flexion.elbow_init_utils import init_ElbowControlMessage
    s = ElbowFlexionPIDStrategy()
    s.setup(muscles=None)
    s.params = init_ElbowControlMessage()
    s.params.active_arm = "left"
    s.params.ems_amplitude = 20
    return s


def test_autotune_can_be_restarted_after_done():
    """Once a tune completes successfully, a fresh request restarts it.

    Regression: after latching a DONE result the strategy must return the
    tuner to IDLE, and a subsequent ``auto_tune_request=True`` must trigger
    a new RAMPING run.
    """
    from examples.elbow_flexion.elbow_types import (
        TUNER_STATE_DONE, TUNER_STATE_IDLE, TUNER_STATE_RAMPING,
    )
    s = _strategy_for_autotune_tests()
    s.params.auto_tune_request = True
    s.process()
    assert s._tuner.state == TUNER_STATE_RAMPING

    # Simulate a successful FFT result.
    s._tuner.state = TUNER_STATE_DONE
    s._tuner.result = (1.0, 0.5, 0.05)
    s._tuner._kp_at_oscillation = 1.67
    s.process()
    assert s._tuner.state == TUNER_STATE_IDLE
    assert s.params.pid_kp == 1.0
    assert s._tuner_result_counter == 1

    # Second request should start another tune.
    s.params.auto_tune_request = True
    s.process()
    assert s._tuner.state == TUNER_STATE_RAMPING
    assert s.params.auto_tune_request is False


def test_autotune_can_be_restarted_after_failed():
    """A FAILED tune must not lock the operator out.

    Regression: the old latch-on-success path left the tuner permanently
    in FAILED when no oscillation was detected, and the subsequent
    ``state == IDLE`` guard on the request rejected every future click.
    Now a request from FAILED resets and restarts the tuner.
    """
    from examples.elbow_flexion.elbow_types import (
        TUNER_STATE_FAILED, TUNER_STATE_RAMPING,
    )
    s = _strategy_for_autotune_tests()
    s.params.auto_tune_request = True
    s.process()
    assert s._tuner.state == TUNER_STATE_RAMPING

    # Simulate the tuner giving up (e.g. no oscillation within time_limit).
    s._tuner.state = TUNER_STATE_FAILED
    s._tuner.result = None
    s.process()
    # One cycle of FAILED is visible so the GUI can show the failure.
    assert s._tuner.state == TUNER_STATE_FAILED

    # Operator clicks auto-tune again: must start a fresh run.
    s.params.auto_tune_request = True
    s.process()
    assert s._tuner.state == TUNER_STATE_RAMPING
    assert s.params.auto_tune_request is False


def test_autotune_ignores_click_during_active_run():
    """A request while the tuner is RAMPING/COLLECTING is a no-op.

    The flag is kept latched so it isn't silently lost — only consumed
    at the moment the strategy actually starts (or restarts) a run.
    """
    from examples.elbow_flexion.elbow_types import TUNER_STATE_RAMPING
    s = _strategy_for_autotune_tests()
    s.params.auto_tune_request = True
    s.process()
    assert s._tuner.state == TUNER_STATE_RAMPING
    assert s.params.auto_tune_request is False

    # Double-click while tuning: request is preserved, tuner keeps running.
    s.params.auto_tune_request = True
    s.process()
    assert s._tuner.state == TUNER_STATE_RAMPING
    assert s.params.auto_tune_request is True
