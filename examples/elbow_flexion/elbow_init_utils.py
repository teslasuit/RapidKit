# SPDX-License-Identifier: MIT
"""
Elbow flexion example — init utilities.

Factory for ``ElbowControlMessage`` and frame packer for the
``shared_memory_frame_elbow`` NumPy dtype.
"""
from __future__ import annotations

import numpy as np

from .elbow_types import (
    ElbowControlMessage,
    TUNER_STATE_IDLE,
    shared_memory_frame_elbow,
)


def init_ElbowControlMessage(_on_change=None) -> ElbowControlMessage:
    """Create an ``ElbowControlMessage`` with safe, conservative defaults.

    PID gains start at zero so no stimulation flows until the operator
    (or auto-tuner) sets non-zero gains; amplitude defaults to 100 %
    to match the GUI slider's default position.
    """
    return ElbowControlMessage(
        active_arm="left",
        desired_angle_deg=90.0,
        mirror_mode=False,
        pid_kp=0.0,
        pid_ki=0.0,
        pid_kd=0.0,
        ems_amplitude=100,
        ems_period_ms=20000.0,
        auto_tune_request=False,
    )


_ARM_MUSCLES = ("biceps_left", "biceps_right", "triceps_left", "triceps_right")


def prepare_frame(timestamp: float, biomechanical_data, ems_data,
                  control: ElbowControlMessage,
                  tuner_state: int = TUNER_STATE_IDLE,
                  tuner_kp_suggested: float = 0.0,
                  tuner_result_counter: int = 0,
                  tuner_result_kp: float = 0.0,
                  tuner_result_ki: float = 0.0,
                  tuner_result_kd: float = 0.0,
                  backend_sample_rate: float = 0.0) -> np.ndarray:
    """Pack one frame of strategy state into ``shared_memory_frame_elbow``.

    GUI reads these frames via the shared ring buffer to update plots.
    """
    frame = np.zeros(1, dtype=shared_memory_frame_elbow)[0]
    frame['timestamp'] = timestamp

    frame['ElbowFlexExtL']  = biomechanical_data.ElbowFlexExtL
    frame['ElbowFlexExtR']  = biomechanical_data.ElbowFlexExtR
    frame['ForearmProSupL'] = biomechanical_data.ForearmProSupL
    frame['ForearmProSupR'] = biomechanical_data.ForearmProSupR

    frame['desired_angle_deg']  = float(control.desired_angle_deg)
    frame['active_arm_is_left'] = 1 if control.active_arm == "left" else 0
    frame['mirror_mode']        = 1 if control.mirror_mode else 0

    frame['tuner_state']          = int(tuner_state)
    frame['tuner_kp_suggested']   = float(tuner_kp_suggested)
    frame['tuner_result_counter'] = int(tuner_result_counter)
    frame['tuner_result_kp']      = float(tuner_result_kp)
    frame['tuner_result_ki']      = float(tuner_result_ki)
    frame['tuner_result_kd']      = float(tuner_result_kd)

    if ems_data is None:
        for name in _ARM_MUSCLES:
            frame[name] = [0.0, 0, 0]
    else:
        for name in _ARM_MUSCLES:
            muscle = getattr(ems_data, name)
            frame[name] = [muscle.Period, muscle.Amplitude, muscle.PulseWidth]

    frame['backend_sample_rate'] = float(backend_sample_rate)
    return frame
