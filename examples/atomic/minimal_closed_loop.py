# SPDX-License-Identifier: MIT
"""
Minimal Closed-Loop Template

This is the canonical "hello world" for the FES framework. Every other atomic
example in this folder starts from the same shape:

    1. Subclass ``ControlStrategyBase``
    2. Implement ``process()`` — called once per control cycle
    3. Hand the class off to ``rapidkit.orchestrator.launch()``

The framework auto-creates ``SuitHandler``, ``DataStreamer``, ``Stimulator``,
``LSLStreamer`` and the IPC queues. You only write strategy code.

How to observe success:
    - Teslasuit is connected and powered on.
    - Run ``python examples/atomic/minimal_closed_loop.py``.
    - Console prints ``[Orchestrator] Running headless (Ctrl-C to stop)`` and
      then a "cycle N" line every 100 cycles (~1 s at 100 Hz).
    - Press Ctrl-C. The engine shuts down cleanly.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable when this file is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase
from teslasuit_rapidkit.orchestrator import launch


class MinimalStrategy(ControlStrategyBase):
    """Smallest possible strategy: count cycles, emit no stimulation."""

    def __init__(self) -> None:
        super().__init__()
        self._cycles = 0

    def process(self) -> None:
        # One control cycle. self.joints, self.contacts, self.params are
        # already populated by the framework. self.ems_output stays at its
        # default (all muted) — this strategy produces no stimulation.
        self._cycles += 1
        if self._cycles % 100 == 0:
            print(f"[MinimalStrategy] cycle {self._cycles}")


if __name__ == "__main__":
    launch(MinimalStrategy)
