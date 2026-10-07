# SPDX-License-Identifier: MIT
"""
Haptic Proximity Radar example — entry point.

Run::

    python examples/haptic_proximity_radar/main.py
    # or
    python -m examples.haptic_proximity_radar.main

Drag the target inside the disc to fire continuous haptic cues:
    direction → which body zone fires (belly / back / L / R shoulder)
    distance  → cue strength (close = strong, far = silent)
"""
from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from multiprocessing import freeze_support

from teslasuit_rapidkit.orchestrator import launch

from examples.haptic_proximity_radar.gui.main import gui_main
from examples.haptic_proximity_radar.proximity_radar_strategy import (
    ProximityRadarStrategy,
)


if __name__ == "__main__":
    freeze_support()
    try:
        launch(
            ProximityRadarStrategy,
            gui_runner=gui_main,
            lsl_enabled=False,
        )
    except RuntimeError as exc:
        # The backend subprocess raises RuntimeError when hardware init
        # times out or the engine crashes during startup (typical cause:
        # no Teslasuit attached, or the SDK can't find a device). Turn
        # the multi-line stack trace into a single actionable line so the
        # operator knows what to check.
        print()
        print("[HapticProximityRadar] Backend failed to start:")
        print(f"  {exc}")
        print()
        print("Common causes:")
        print("  - Teslasuit not connected / powered / paired")
        print("  - Teslasuit SDK not installed or not on PATH")
        print("  - Another process is holding the suit handle")
        print()
        print("Re-run with the suit attached, or set a longer "
              "hardware_init_timeout in main.py.")
        sys.exit(1)
    except KeyboardInterrupt:
        # Ctrl-C during startup or shutdown — clean exit without a trace.
        print("\n[HapticProximityRadar] Interrupted.")
        sys.exit(130)
