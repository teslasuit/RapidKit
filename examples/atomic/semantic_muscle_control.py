# SPDX-License-Identifier: MIT
"""
Semantic Muscle Addressing and Stimulation

Two things are demonstrated:

    1. Query the muscle map semantically. ``ControlStrategyBase.muscles`` is a
       ``MuscleMap`` instance (see ``teslasuit_rapidkit/muscle_map.py``). You can
       ask it for muscles by side or body region, list all configured muscles,
       or resolve a name to the underlying SDK channel IDs.

    2. Write stimulation commands by name. ``self.ems_output`` is an
       ``EmsData`` dataclass with one ``EMSParamData`` slot per muscle
       (``quadriceps_left``, ``gastrocnemius_right``, …). Setting a slot is
       all it takes — the framework reads ``self.ems_output`` after
       ``process()`` and routes it through the stimulator.

The framework auto-wires ``suit_handler.muscle_map`` onto
``strategy.muscles`` before the first cycle, so no engine subclass
is needed — just pass the strategy class to ``orchestrator.launch()``.

The strategy toggles the left quadriceps on/off on a ~1 Hz cycle.

How to observe success:
    - Teslasuit is connected, the subject is wearing it, and the left-quad
      electrodes are in contact.
    - Run ``python examples/atomic/semantic_muscle_control.py``.
    - At startup the console prints the full list of configured muscles and
      the channel IDs that ``MuscleMap`` resolved for ``quadriceps_left``.
    - The left quadriceps should pulse on/off at 1 Hz.
    - Press Ctrl-C to stop.

⚠️  Do not run this on a subject who has not been prepped for stimulation.
    Start with a low amplitude (this example uses 20%).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase
from teslasuit_rapidkit.data.types import EMSParamData
from teslasuit_rapidkit.muscle_map import MuscleMap
from teslasuit_rapidkit.orchestrator import launch


class SemanticMuscleDemoStrategy(ControlStrategyBase):
    """Toggle the left quadriceps on/off at 1 Hz using semantic muscle names."""

    TARGET_MUSCLE = "quadriceps_left"
    CYCLES_PER_TOGGLE = 50  # 0.5 s on, 0.5 s off at 100 Hz

    # Conservative pulse parameters — tune for your subject.
    PULSE_WIDTH_US = 200
    AMPLITUDE_PCT = 20
    PERIOD_MS = 20.0

    def __init__(self) -> None:
        super().__init__()
        self._cycles = 0
        self._on = False

    def setup(self, muscles: MuscleMap = None, suit=None, config: dict = None) -> None:
        super().setup(muscles=muscles, suit=suit, config=config)
        if self.muscles is None:
            raise RuntimeError(
                "SemanticMuscleDemoStrategy requires a MuscleMap — "
                "call strategy.setup(muscles=suit_handler.muscle_map)."
            )
        print("[SemanticMuscleDemoStrategy] MuscleMap loaded:")
        print(f"  hardware:  {self.muscles.hardware_version}")
        print(f"  muscles:   {self.muscles.list_muscles()}")
        print(f"  left side: "
              f"{[m.name for m in self.muscles.by_side('left')]}")
        print(f"  upper_leg: "
              f"{[m.name for m in self.muscles.by_region('upper_leg')]}")
        print(f"  channels for {self.TARGET_MUSCLE}: "
              f"{self.muscles.get_channels(self.TARGET_MUSCLE)}")

    def process(self) -> None:
        self._cycles += 1

        # Toggle state every CYCLES_PER_TOGGLE ticks.
        if self._cycles % self.CYCLES_PER_TOGGLE == 0:
            self._on = not self._on
            print(f"[SemanticMuscleDemoStrategy] {self.TARGET_MUSCLE} "
                  f"{'ON' if self._on else 'OFF'}")

        # Write stimulation by anatomical name — no channel arithmetic.
        if self._on:
            self.ems_output.quadriceps_left = EMSParamData(
                IsMuted=False,
                PulseWidth=self.PULSE_WIDTH_US,
                Amplitude=self.AMPLITUDE_PCT,
                Period=self.PERIOD_MS,
            )
        else:
            self.ems_output.quadriceps_left = EMSParamData(
                IsMuted=True, PulseWidth=0, Amplitude=0, Period=0.0
            )


if __name__ == "__main__":
    launch(SemanticMuscleDemoStrategy)
