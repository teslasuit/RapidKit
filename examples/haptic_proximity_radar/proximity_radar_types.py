# SPDX-License-Identifier: MIT
"""
Haptic Proximity Radar example — data types.

The operator drags a target object inside a unit disc around the wearer.
The GUI publishes the target's position in normalized radar coordinates:

    obj_x, obj_y in [-1, 1], with x² + y² <= 1
    +x = right (east) on the radar
    +y = forward (north) on the radar

The strategy maps that position to four haptic zones (belly / back /
left shoulder / right shoulder), where direction picks the channel(s)
and distance modulates pulse width × amplitude.
"""
from dataclasses import dataclass, field

from teslasuit_rapidkit.data.types import ControlMessage, CustomPlayable, HapticLibrary


@dataclass
class ProximityControlMessage(ControlMessage):
    """Operator-driven radar target state.

    ``obj_x`` / ``obj_y`` are in normalized disc coordinates; the strategy
    treats anything outside the unit circle as silent. ``master_intensity_pct``
    scales every zone uniformly (the global slider in the GUI).
    """
    obj_x: float = 0.0
    obj_y: float = 0.0
    master_intensity_pct: int = 60


@dataclass
class ProximityHaptics(HapticLibrary):
    """Four named haptic slots, one per cardinal body zone."""
    belly:          CustomPlayable = field(default_factory=CustomPlayable)
    back:           CustomPlayable = field(default_factory=CustomPlayable)
    left_shoulder:  CustomPlayable = field(default_factory=CustomPlayable)
    right_shoulder: CustomPlayable = field(default_factory=CustomPlayable)
