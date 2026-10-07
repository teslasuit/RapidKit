# SPDX-License-Identifier: MIT
"""
Vestibular Training example — entry point.

Run::

    python examples/vestibular_training/main.py
    # or
    python -m examples.vestibular_training.main

The suit's motion-capture stream drives real-time postural sway detection.
Haptic cues on the suit surface tell the patient which way they are leaning.
"""
from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from multiprocessing import freeze_support

from teslasuit_rapidkit.orchestrator import launch

from examples.vestibular_training.gui.main import gui_main
from examples.vestibular_training.vestibular_training_strategy import (
    VestibularTrainingStrategy,
)


if __name__ == "__main__":
    freeze_support()
    try:
        launch(
            VestibularTrainingStrategy,
            gui_runner=gui_main,
            lsl_enabled=False,
        )
    except RuntimeError as exc:
        print()
        print("[VestibularTraining] Backend failed to start:")
        print(f"  {exc}")
        print()
        print("Common causes:")
        print("  - Teslasuit not connected / powered / paired")
        print("  - Teslasuit SDK not installed or not on PATH")
        print("  - Another process is holding the suit handle")
        print()
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[VestibularTraining] Interrupted.")
        sys.exit(130)
