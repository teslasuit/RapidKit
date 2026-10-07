# SPDX-License-Identifier: MIT
"""
Haptic Navigation example — entry point.

Run::

    python examples/haptic_navigation/main.py
    # or
    python -m examples.haptic_navigation.main

Arrow keys in the GUI fire haptic cues on the wearer:
    ↑ belly · ↓ back · ← left shoulder · → right shoulder
Multiple directions can be held simultaneously.
"""
from __future__ import annotations

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from multiprocessing import freeze_support

from teslasuit_rapidkit.orchestrator import launch

from examples.haptic_navigation.gui.main import gui_main
from examples.haptic_navigation.haptic_navigation_strategy import HapticNavigationStrategy


if __name__ == "__main__":
    freeze_support()
    launch(
        HapticNavigationStrategy,
        gui_runner=gui_main,
        lsl_enabled=False,
    )
