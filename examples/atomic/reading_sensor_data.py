# SPDX-License-Identifier: MIT
"""
Reading Structured Sensor Data

Inside a ``ControlStrategyBase.process()`` the framework populates two
attributes for you:

    self.joints   : BiomechanicalData — 29 joint angles (degrees), PascalCase
                    field names mirroring the Teslasuit SDK enums
                    (``KneeFlexExtR``, ``HipFlexExtL``, …).
    self.contacts : StepDetectorData — ``left_foot_contact`` / ``right_foot_contact``
                    booleans produced by the step detector.

The lower abstraction layers (raw IMU and processed mocap for all 20 body
segments) are not passed to the strategy — they live on the engine's
``DataStreamer``:

    engine.data_streamer.raw_data        # RawData   (all 20 SensorData)
    engine.data_streamer.processed_data  # ProcessedData (all 20 MocapBoneData)

See ``rapidkit/data/types.py`` for the full list of fields in
``BiomechanicalData``, ``RawData``, and ``ProcessedData``.

How to observe success:
    - Teslasuit is connected, the subject is wearing it and moving.
    - Run ``python examples/atomic/reading_sensor_data.py``.
    - Every ~1 s the console prints left/right knee flexion, hip flexion, and
      the two foot-contact flags. The numbers should change as the subject
      moves; foot contacts should flip as they step.
    - Press Ctrl-C to stop.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase
from teslasuit_rapidkit.orchestrator import launch


class SensorPrintStrategy(ControlStrategyBase):
    """Read joint angles and foot contacts every cycle; print periodically."""

    PRINT_EVERY_N_CYCLES = 1  # ~1 s at 100 Hz

    def __init__(self) -> None:
        super().__init__()
        self._cycles = 0

    def process(self) -> None:
        self._cycles += 1

        # Every cycle, the framework has already written fresh data to:
        #   self.joints   (BiomechanicalData)
        #   self.contacts (StepDetectorData)
        # Access fields by name — no buffer parsing, no indexing.
        if self._cycles % self.PRINT_EVERY_N_CYCLES == 0:
            print(
                f"[SensorPrintStrategy] cycle={self._cycles} "
                f"KneeFlexExtL={self.joints.KneeFlexExtL:+6.1f}° "
                f"KneeFlexExtR={self.joints.KneeFlexExtR:+6.1f}° "
                f"HipFlexExtL={self.joints.HipFlexExtL:+6.1f}° "
                f"HipFlexExtR={self.joints.HipFlexExtR:+6.1f}° "
                f"left_contact={self.contacts.left_foot_contact} "
                f"right_contact={self.contacts.right_foot_contact}"
            )

        # NOTE: this strategy is read-only — it never writes to self.ems_output,
        # so no stimulation is emitted. See semantic_muscle_control.py for the
        # opposite: writing stimulation commands by muscle name.


if __name__ == "__main__":
    launch(SensorPrintStrategy)
