# SPDX-License-Identifier: MIT
"""
Elbow Flexion FES example — data types.

Contains example-specific dataclasses and shared memory layout.  Not part of
the teslasuit_rapidkit package.

The ControlMessage here does NOT use ``_default_stim_params`` — this example
is a joint-angle-tracking PID, not a per-muscle event scheduler, so
stimulation parameters (frequency, amplitude, etc.) are global to the active
arm rather than per-muscle.
"""
from dataclasses import dataclass, field

import numpy as np

from teslasuit_rapidkit.data.types import ControlMessage


@dataclass
class ElbowControlMessage(ControlMessage):
    """Control message for the elbow flexion PID example.

    Fields are set by the GUI and read by ``ElbowFlexionPIDStrategy.process()``.

    Attributes:
        active_arm:        "left" or "right" — which arm is currently stimulated
        desired_angle_deg: Setpoint in degrees (used when mirror_mode is False)
        mirror_mode:       If True, setpoint = opposite arm's measured angle
        pid_kp/ki/kd:      PID gains.  Either set manually via GUI sliders,
                           or populated by the FFT auto-tuner.
        ems_amplitude:     Stimulation amplitude in % (0-100). Operator-
                           controlled via the GUI slider; the framework
                           does not clamp this value, so the operator is
                           responsible for raising it safely.
        ems_period_ms:     Stimulation period in milliseconds (20 ms = 50 Hz)
        auto_tune_request: Set True by GUI to start a one-shot auto-tune cycle
    """
    active_arm: str = "left"
    desired_angle_deg: float = 90.0
    mirror_mode: bool = False
    pid_kp: float = 1.0
    pid_ki: float = 0.0
    pid_kd: float = 0.0
    ems_amplitude: int = 100
    ems_period_ms: float = 20.0
    auto_tune_request: bool = False


# Shared memory frame for GUI visualisation.  Only the fields the elbow GUI
# needs — a small subset of the full biomechanical frame.
shared_memory_frame_elbow = np.dtype([
    ('timestamp', 'f8'),
    # Arm joint angles (the four angles the strategy / GUI care about)
    ('ElbowFlexExtL', 'f8'),
    ('ElbowFlexExtR', 'f8'),
    ('ForearmProSupL', 'f8'),
    ('ForearmProSupR', 'f8'),
    # Control state echoed from the control message (so GUI can plot setpoint)
    ('desired_angle_deg', 'f8'),
    ('active_arm_is_left', 'u1'),
    ('mirror_mode', 'u1'),
    # Auto-tuner status, encoded as a small integer (see TUNER_STATE_* below)
    ('tuner_state', 'u1'),
    ('tuner_kp_suggested', 'f4'),
    # Latest auto-tune result (held across frames so the GUI can latch it into
    # its sliders). ``tuner_result_counter`` is a monotonically increasing id
    # that the GUI watches to detect a freshly-produced result.
    ('tuner_result_counter', 'u4'),
    ('tuner_result_kp', 'f4'),
    ('tuner_result_ki', 'f4'),
    ('tuner_result_kd', 'f4'),
    # EMS output for the four arm muscles this example drives
    # Each entry: [Period (ms), Amplitude (%), PulseWidth (us)]
    ('biceps_left',   '3u4'),
    ('biceps_right',  '3u4'),
    ('triceps_left',  '3u4'),
    ('triceps_right', '3u4'),
    # Diagnostics
    ('backend_sample_rate', 'f4'),
])


TUNER_STATE_IDLE      = 0
TUNER_STATE_RAMPING   = 1
TUNER_STATE_COLLECTING = 2
TUNER_STATE_ANALYZING = 3
TUNER_STATE_DONE      = 4
TUNER_STATE_FAILED    = 5

TUNER_STATE_NAMES = {
    TUNER_STATE_IDLE:       "IDLE",
    TUNER_STATE_RAMPING:    "RAMPING_KP",
    TUNER_STATE_COLLECTING: "COLLECTING",
    TUNER_STATE_ANALYZING:  "ANALYZING",
    TUNER_STATE_DONE:       "DONE",
    TUNER_STATE_FAILED:     "FAILED",
}
