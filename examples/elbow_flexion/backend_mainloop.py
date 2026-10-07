# SPDX-License-Identifier: MIT
"""
Elbow Flexion FES — backend main loop.

Thin ``ClosedLoopEngine`` subclass that adds:

* ``ElbowFlexionPIDStrategy`` as the control strategy
* ``ElbowControlMessage`` as the application control message type
* A shared-memory ring buffer named ``'elbow_buffer'`` for the GUI
* A rolling 1-second sample-rate counter
* Calibration-on-request handling (I-pose) via ``on_utility_message``

The generic engine (``teslasuit_rapidkit.engine.ClosedLoopEngine``) owns the
per-cycle sensor→strategy→stimulator pipeline; this class only wires in
the example-specific pieces.
"""
from __future__ import annotations

import time

from teslasuit_rapidkit.engine import ClosedLoopEngine
from teslasuit_rapidkit.ipc.buffer import SharedRingBuffer

from .elbow_control_strategy import ElbowFlexionPIDStrategy
from .elbow_init_utils import init_ElbowControlMessage, prepare_frame
from .elbow_types import ElbowControlMessage, shared_memory_frame_elbow


class ElbowBackendMainloop(ClosedLoopEngine):
    """Backend loop for the elbow flexion example."""

    def __init__(self, control_queue, utility_queue):
        super().__init__(
            control_strategy=ElbowFlexionPIDStrategy(),
            control_queue=control_queue,
            utility_queue=utility_queue,
        )

        # The PID strategy reads ``self.joints.ElbowFlexExt*`` every cycle.
        # DataStreamer enables biomechanical-angle collection by default,
        # so this works out of the box — no explicit toggle needed here.
        # (If you ever build an app that doesn't read joint angles, call
        # ``self.data_streamer.set_biomech_collection(False)`` here to
        # save the SDK IK call's per-cycle CPU cost.)

        # Application-specific control message type
        self.control_message = init_ElbowControlMessage()
        self.lsl_streamer.configure_control_outlet(ElbowControlMessage)

        # Shared memory ring buffer for GUI visualisation.  Given its own
        # buffer name so multiple examples' shared-memory segments don't
        # collide (though examples are not meant to run concurrently —
        # the SDK's hardware handle is a singleton).
        self.buffer = SharedRingBuffer(
            dtype=shared_memory_frame_elbow, capacity=500,
            create=True, name='elbow_buffer',
        )

        # Rolling sample-rate counter
        self._sample_count: int = 0
        self._sample_rate: float = 0.0
        self._last_rate_time: float = time.time()

    # ── Hooks ─────────────────────────────────────────────────────

    def on_utility_message(self, message) -> None:
        """Handle calibration requests from the GUI (I-pose)."""
        if message.CalibrationLoopIsActive:
            result = self.calibration.calibrate()
            if result.success:
                print("[ElbowBackend] Calibration OK.")
            else:
                print(f"[ElbowBackend] Calibration failed: {result.message}")
            # Reset flag so the next GUI click can trigger another calibration
            self.utility_message.CalibrationLoopIsActive = False

    def on_cycle_complete(self) -> None:
        """Update sample-rate counter and write a GUI frame to shared memory."""
        self._sample_count += 1
        now = time.time()
        elapsed = now - self._last_rate_time
        if elapsed >= 1.0:
            self._sample_rate = self._sample_count / elapsed
            self._sample_count = 0
            self._last_rate_time = now

        strategy = self.control_strategy
        frame = prepare_frame(
            timestamp=self.data_streamer.raw_data.timestamp,
            biomechanical_data=self.data_streamer.biomechanical_data,
            ems_data=self.ems_data,
            control=self.control_message,
            tuner_state=strategy._tuner.state,
            tuner_kp_suggested=strategy._tuner.kp_suggested,
            tuner_result_counter=strategy._tuner_result_counter,
            tuner_result_kp=strategy._tuner_result_kp,
            tuner_result_ki=strategy._tuner_result_ki,
            tuner_result_kd=strategy._tuner_result_kd,
            backend_sample_rate=self._sample_rate,
        )
        self.buffer.write_frame(frame)

    # ── Legacy entry point (matches the framework's mainloop convention) ───

    def run_backend(self):
        print("starting elbow backend mainloop")
        self.run()
