# SPDX-License-Identifier: MIT
"""
LSL Streaming — Outlets for Recording + Inlets for External Devices

What this example shows
-----------------------
1. **Outlets**:
   Constructing ``ClosedLoopEngine`` with ``lsl_enabled=True`` flips on
   ``LSLStreamer``, which publishes 7 outlets each cycle. The names below
   match ``teslasuit_rapidkit/io/lsl_streamer.py``:

       - ``TS_Biomechanics``      (29 joint angles)
       - ``TS_API_StepDetector``  (foot contacts)
       - ``TS_EMSParameters``     (stimulation output)
       - ``TS_BonePosition``      (processed mocap)
       - ``TS_RawData``           (raw IMU)
       - ``AppData_ControlMessage``
       - ``AppData_UtilityMessage``

   To record a session: start LabRecorder (or any pylsl consumer), tick the
   streams you want, hit Start, then run this script.

2. **Inlets**:
   ``ExternalInputManager`` registers up to 2 external LSL streams. Each
   cycle, the engine polls them and writes the latest samples to
   ``strategy.external_data``, keyed by stream name. The strategy reads
   them via ``self.external_data.get("<stream_name>")``.

   This example tries to register an ``ExampleForce`` stream; if no such
   stream is on the network it prints a warning and runs outlet-only.

How to observe success
----------------------
Outlets:
    - Run ``python examples/atomic/lsl_streaming.py``.
    - In another shell, list LSL streams (``python -c "import pylsl;
      print([s.name() for s in pylsl.resolve_streams(wait_time=2.0)])"``).
      You should see the 7 ``TS_*`` / ``AppData_*`` streams above.
    - Point LabRecorder at them and record a session.

Inlets:
    - Have another process publish an LSL stream named ``ExampleForce``
      (any type). This strategy will log its latest sample every 100 cycles.
    - If ``ExampleForce`` is not on the network, registration fails cleanly
      and the engine runs in outlet-only mode.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase
from teslasuit_rapidkit.orchestrator import launch

EXTERNAL_STREAM_NAME = "ExampleForce"


class LSLDemoStrategy(ControlStrategyBase):
    """No stimulation; just reports what comes in from external LSL inlets."""

    PRINT_EVERY_N_CYCLES = 100

    def __init__(self) -> None:
        super().__init__()
        self._cycles = 0

    def process(self) -> None:
        self._cycles += 1
        if self._cycles % self.PRINT_EVERY_N_CYCLES != 0:
            return

        sample = self.external_data.get(EXTERNAL_STREAM_NAME)
        if sample is None:
            print(f"[LSLDemoStrategy] cycle={self._cycles} "
                  f"{EXTERNAL_STREAM_NAME}=<no sample yet>")
        else:
            print(f"[LSLDemoStrategy] cycle={self._cycles} "
                  f"{EXTERNAL_STREAM_NAME}={sample.data} "
                  f"ts={sample.timestamp:.3f}")


if __name__ == "__main__":
    # launch() builds the ExternalInputManager in the backend subprocess
    # (pylsl objects are not picklable). If "ExampleForce" is not on the
    # network the orchestrator logs a warning and runs outlet-only.
    launch(
        LSLDemoStrategy,
        lsl_enabled=True,                                   # 7 framework outlets
        external_input_streams=[EXTERNAL_STREAM_NAME],      # inlets (timeout=5 s)
        external_input_timeout=2.0,
    )
