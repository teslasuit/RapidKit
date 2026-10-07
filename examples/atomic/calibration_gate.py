# SPDX-License-Identifier: MIT
"""
Calibration Gate

This example demonstrates the intended headless calibration flow from
``rapidkit/calibration.py``::

    1. Create a ClosedLoopEngine (which auto-builds a CalibrationAPI).
    2. Put the subject in I-pose.
    3. Call ``engine.calibration.calibrate()`` (blocking SDK call).
    4. Gate on result.success — abort if calibration failed.
    5. Only then call ``engine.run()``.

The strategy itself is a belt-and-braces second line of defence: inside
``process()`` it checks a ``calibrated`` flag and refuses to emit EMS if
the engine starts running without calibration for any reason.

How to observe success
----------------------
    - Teslasuit connected; the subject is standing in I-pose before you
      hit Enter at the prompt.
    - Run ``python examples/atomic/calibration_gate.py``.
    - Console prints the CalibrationResult.
    - If calibration fails the script exits with a non-zero status and
      the engine is never started.
    - Otherwise the engine runs; press Ctrl-C to stop.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase
from teslasuit_rapidkit.data.types import EMSParamData
from teslasuit_rapidkit.engine import ClosedLoopEngine


class CalibrationGatedStrategy(ControlStrategyBase):
    """Refuses to emit EMS until ``calibrated`` is set True."""

    PRINT_EVERY_N_CYCLES = 100

    def __init__(self) -> None:
        super().__init__()
        self.calibrated: bool = False
        self._cycles = 0

    def process(self) -> None:
        self._cycles += 1

        if not self.calibrated:
            # Second line of defence: keep ems_output muted.
            self.ems_output.quadriceps_left = EMSParamData(
                IsMuted=True, PulseWidth=0, Amplitude=0, Period=0.0
            )
            if self._cycles % self.PRINT_EVERY_N_CYCLES == 0:
                print("[CalibrationGatedStrategy] not calibrated — muted")
            return

        # Post-calibration stimulation logic would go here. We keep it empty
        # to make the example focused on the gate itself.
        if self._cycles % self.PRINT_EVERY_N_CYCLES == 0:
            print(f"[CalibrationGatedStrategy] running (cycle={self._cycles})")


def run_calibrated_engine() -> int:
    strategy = CalibrationGatedStrategy()
    engine = ClosedLoopEngine(control_strategy=strategy)

    input("[calibration_gate] Put the subject in I-pose, then press Enter... ")

    result = engine.calibration.calibrate()
    print(f"[calibration_gate] {result.message} (ts={result.timestamp:.0f})")
    if not result.success:
        print("[calibration_gate] Calibration failed — aborting.")
        return 1

    strategy.calibrated = True
    print("[calibration_gate] Calibration OK. Starting engine (Ctrl-C to stop).")
    engine.run()
    return 0


if __name__ == "__main__":
    sys.exit(run_calibrated_engine())
