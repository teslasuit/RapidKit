# SPDX-License-Identifier: MIT
"""Data handling for the elbow flexion GUI.

Reads frames from the ``'elbow_buffer'`` shared-memory ring buffer written
by ``ElbowBackendMainloop.on_cycle_complete()`` and exposes rolling deques
for the plot widgets.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Optional

import numpy as np

from teslasuit_rapidkit.ipc.buffer import SharedRingBuffer
from examples.elbow_flexion.elbow_types import (
    TUNER_STATE_IDLE,
    TUNER_STATE_NAMES,
    shared_memory_frame_elbow,
)


class ElbowDataHandler:
    """Reads elbow strategy state from shared memory and buffers it for plots."""

    BUFFER_NAME = 'elbow_buffer'
    BUFFER_CAPACITY = 500

    def __init__(self, max_points: int = 500) -> None:
        self.max_points = max_points
        self.start_time = time.time()
        self.shared_buffer: Optional[SharedRingBuffer] = None
        self.buffer_connected = False

        self.time_buffer: Deque[float] = deque(maxlen=max_points)
        self.elbow_L: Deque[float] = deque(maxlen=max_points)
        self.elbow_R: Deque[float] = deque(maxlen=max_points)
        self.setpoint: Deque[float] = deque(maxlen=max_points)
        self.biceps_pw: Deque[float] = deque(maxlen=max_points)
        self.triceps_pw: Deque[float] = deque(maxlen=max_points)

        self.active_arm_is_left: bool = True
        self.mirror_mode: bool = False
        self.tuner_state: int = TUNER_STATE_IDLE
        self.tuner_kp_suggested: float = 0.0
        # Latest PID gains produced by the backend auto-tuner. The counter is
        # bumped by the backend each time a new result is produced; the GUI
        # diffs it to decide when to snap the sliders to the tuned values.
        self.tuner_result_counter: int = 0
        self.tuner_result_kp: float = 0.0
        self.tuner_result_ki: float = 0.0
        self.tuner_result_kd: float = 0.0
        self.backend_sample_rate: float = 0.0

    # ── Connection ────────────────────────────────────────────────

    def connect(self, max_attempts: int = 3) -> bool:
        for attempt in range(max_attempts):
            try:
                self.shared_buffer = SharedRingBuffer(
                    dtype=shared_memory_frame_elbow,
                    capacity=self.BUFFER_CAPACITY,
                    name=self.BUFFER_NAME,
                    create=False,
                )
                self.buffer_connected = True
                print(f"Connected to '{self.BUFFER_NAME}'")
                return True
            except FileNotFoundError:
                time.sleep(0.2)
            except Exception as exc:
                print(f"Error connecting to buffer: {exc}")
                time.sleep(0.2)
        self.buffer_connected = False
        return False

    def try_reconnect(self) -> None:
        try:
            self.shared_buffer = SharedRingBuffer(
                dtype=shared_memory_frame_elbow,
                capacity=self.BUFFER_CAPACITY,
                name=self.BUFFER_NAME,
                create=False,
            )
            self.buffer_connected = True
            print(f"Reconnected to '{self.BUFFER_NAME}'")
        except FileNotFoundError:
            pass
        except Exception:
            pass

    # ── Per-tick update ───────────────────────────────────────────

    def update(self) -> None:
        if self.shared_buffer is None or not self.buffer_connected:
            self.try_reconnect()
            return
        try:
            frame = self.shared_buffer.read_latest_frame()
        except Exception as exc:
            print(f"Buffer read error: {exc}")
            return
        if frame is None:
            return

        t = time.time() - self.start_time
        self.time_buffer.append(t)

        self.elbow_L.append(float(frame['ElbowFlexExtL']))
        self.elbow_R.append(float(frame['ElbowFlexExtR']))
        self.setpoint.append(float(frame['desired_angle_deg']))

        self.active_arm_is_left = bool(frame['active_arm_is_left'])
        self.mirror_mode = bool(frame['mirror_mode'])
        self.tuner_state = int(frame['tuner_state'])
        self.tuner_kp_suggested = float(frame['tuner_kp_suggested'])
        self.tuner_result_counter = int(frame['tuner_result_counter'])
        self.tuner_result_kp = float(frame['tuner_result_kp'])
        self.tuner_result_ki = float(frame['tuner_result_ki'])
        self.tuner_result_kd = float(frame['tuner_result_kd'])
        self.backend_sample_rate = float(frame['backend_sample_rate'])

        # Pick active-arm EMS values
        if self.active_arm_is_left:
            biceps = frame['biceps_left']
            triceps = frame['triceps_left']
        else:
            biceps = frame['biceps_right']
            triceps = frame['triceps_right']
        # Index 2 is PulseWidth
        self.biceps_pw.append(float(biceps[2]))
        self.triceps_pw.append(float(triceps[2]))

    # ── Accessors ─────────────────────────────────────────────────

    def get_time(self) -> np.ndarray:
        return np.array(self.time_buffer)

    def get_active_angle(self) -> np.ndarray:
        return np.array(self.elbow_L if self.active_arm_is_left else self.elbow_R)

    def get_setpoint(self) -> np.ndarray:
        return np.array(self.setpoint)

    def get_biceps_pw(self) -> np.ndarray:
        return np.array(self.biceps_pw)

    def get_triceps_pw(self) -> np.ndarray:
        return np.array(self.triceps_pw)

    @property
    def tuner_status_text(self) -> str:
        return TUNER_STATE_NAMES.get(self.tuner_state, "?")

    # ── Cleanup ───────────────────────────────────────────────────

    def cleanup(self) -> None:
        if self.shared_buffer is not None:
            try:
                self.shared_buffer.cleanup_shared_memory()
            except Exception as exc:
                print(f"Cleanup error: {exc}")
        self.buffer_connected = False
