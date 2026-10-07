# SPDX-License-Identifier: MIT
"""
Haptic Navigation example — data types.

Defines the per-direction control message sent by the operator GUI and the
typed haptic library that holds the four navigation-cue playables (belly,
back, left shoulder, right shoulder).

The four direction fields are independent booleans so the operator can hold
multiple keys simultaneously (e.g. ↑+← to fire belly + left shoulder).
"""
from dataclasses import dataclass, field

from teslasuit_rapidkit.data.types import ControlMessage, CustomPlayable, HapticLibrary


@dataclass
class NavigationControlMessage(ControlMessage):
    """Operator-driven directional cues.

    Each boolean is toggled by the GUI on key down/up; the strategy maps each
    to the IsMuted state of the matching haptic slot. ``intensity_pct`` scales
    all four cues uniformly via the ``amplitude_mult`` field on each playable.
    """
    forward:  bool = False   # ↑ — belly haptic
    backward: bool = False   # ↓ — back haptic
    left:     bool = False   # ← — left shoulder haptic
    right:    bool = False   # → — right shoulder haptic
    intensity_pct: int = 60


@dataclass
class NavigationHaptics(HapticLibrary):
    """Four named haptic slots, one per navigation direction."""
    belly:          CustomPlayable = field(default_factory=CustomPlayable)
    back:           CustomPlayable = field(default_factory=CustomPlayable)
    left_shoulder:  CustomPlayable = field(default_factory=CustomPlayable)
    right_shoulder: CustomPlayable = field(default_factory=CustomPlayable)
