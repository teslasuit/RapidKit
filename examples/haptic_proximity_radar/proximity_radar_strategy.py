# SPDX-License-Identifier: MIT
"""
Haptic Proximity Radar strategy — continuous angle/distance → haptic cue.

The operator drags a target inside a unit disc around the wearer. The
strategy reads ``(obj_x, obj_y)`` from the control message and updates four
looped CustomPlayable slots (belly / back / left_shoulder / right_shoulder):

* Direction (atan2 of the target) picks the channel(s). Each zone gets a
  cosine² weight from its cardinal axis, so cardinals fire one zone clean
  and the 45° boundaries fire two neighbours at ~0.5 each.
* Distance (radial) modulates intensity. ``prox = 1 - r`` drives both the
  amplitude multiplier and (more gently) the pulse-width multiplier, so
  close = strong, far = silent.

No EMS is produced — ``self.ems_output`` is pre-muted in ``__init__`` and
never touched again.

Bone / channel mapping mirrors ``haptic_navigation`` and is verified on
the Teslasuit 4R reference unit.
"""
from __future__ import annotations

import logging
import math

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase

from .proximity_radar_types import ProximityHaptics


logger = logging.getLogger(__name__)


# Zone metadata: bone/channel layout + cardinal angle (radians, atan2 frame).
# +x = right (0), +y = forward (+π/2), -x = left (π), -y = back (-π/2).
_ZONES = {
    "belly":          {"bone_id":  8, "channels": [0, 1, 2, 3, 4, 5, 6, 7],
                       "theta":  math.pi / 2},
    "back":           {"bone_id": 11, "channels": [0, 1, 2, 3, 4, 5, 6, 7],
                       "theta": -math.pi / 2},
    "left_shoulder":  {"bone_id": 12, "channels": [0, 1, 2],
                       "theta":  math.pi},
    "right_shoulder": {"bone_id": 14, "channels": [0, 1, 2],
                       "theta":  0.0},
}

_BASE_PERIOD_US: int = 20_000
_BASE_AMP_PCT:   int = 60
_BASE_PW_US:     int = 200

# Below this proximity (1 - r), the zone is muted. Avoids a constant
# "barely there" tickle at the edge of the disc.
_PROX_SILENCE: float = 0.05

# Per-zone angular weight floor; anything below counts as "off direction"
# and the zone is muted regardless of distance.
_WEIGHT_EPS: float = 0.02

# Pulse-width range, expressed as a multiplier on _BASE_PW_US.
# Far field still feels like a tap (0.5), near field like a firm push (1.0).
_PW_MULT_MIN: float = 0.5
_PW_MULT_MAX: float = 1.0


class ProximityRadarStrategy(ControlStrategyBase):
    """Drive four haptic zones from a continuous radar target position."""

    def __init__(self) -> None:
        super().__init__()
        # Edge-log dedupe: remember the last (firing, amp_bucket) per zone.
        self._last_state: dict = {name: (False, -1) for name in _ZONES}

        # Haptic-only example — pre-mute every EMS muscle so the EMS
        # Stimulator never receives an "active with zero parameters" frame
        # (which on hardware can show up as continuous low-level stim).
        for muscle_name in self.ems_output.__dataclass_fields__:
            getattr(self.ems_output, muscle_name).IsMuted = True

    # ── lifecycle ──────────────────────────────────────────────
    def setup(self, muscles=None, suit=None, config=None) -> None:
        super().setup(muscles=muscles, suit=suit, config=config)
        if suit is None:
            return

        self._log_bone_inventory(suit)

        lib = ProximityHaptics()
        for name, zone in _ZONES.items():
            slot = self._try_build_zone(suit, name, zone)
            if slot is not None:
                setattr(lib, name, slot)
        self.haptic_library = lib

    # ── per-tick ───────────────────────────────────────────────
    def process(self) -> None:
        if self.params is None or not hasattr(self.params, "obj_x"):
            return
        if self.haptic_library is None:
            return

        x = float(self.params.obj_x)
        y = float(self.params.obj_y)
        r = min(1.0, math.hypot(x, y))
        prox = max(0.0, 1.0 - r)

        # Direction is undefined at the exact center; treat as silent.
        if r == 0.0 or prox <= _PROX_SILENCE:
            self._mute_all()
            return

        theta = math.atan2(y, x)
        master_mult = float(self.params.master_intensity_pct) / float(_BASE_AMP_PCT)

        lib = self.haptic_library
        for name, zone in _ZONES.items():
            slot = getattr(lib, name)
            # cos² weighting; clamp negative cos to 0 so the back of the
            # body never fires when the target is in front (and vice versa).
            cos_term = math.cos(theta - zone["theta"])
            w = max(0.0, cos_term) ** 2
            firing = w >= _WEIGHT_EPS
            if firing:
                slot.IsMuted = False
                slot.amplitude_mult = master_mult * prox * w
                slot.pulse_width_mult = _PW_MULT_MIN + (_PW_MULT_MAX - _PW_MULT_MIN) * prox
            else:
                slot.IsMuted = True
                slot.amplitude_mult = 0.0
                slot.pulse_width_mult = _PW_MULT_MIN
            self._log_edge(name, firing, slot.amplitude_mult)

    # ── helpers ────────────────────────────────────────────────
    def _mute_all(self) -> None:
        lib = self.haptic_library
        for name in _ZONES:
            slot = getattr(lib, name)
            if not slot.IsMuted:
                slot.IsMuted = True
                slot.amplitude_mult = 0.0
                slot.pulse_width_mult = _PW_MULT_MIN
            self._log_edge(name, False, 0.0)

    def _log_edge(self, zone: str, firing: bool, amp_mult: float) -> None:
        # Bucket amp_mult into 10 % steps so steady-state ramps don't spam.
        bucket = int(round(amp_mult * 10)) if firing else -1
        new_state = (firing, bucket)
        if self._last_state.get(zone) == new_state:
            return
        self._last_state[zone] = new_state
        if firing:
            spec = _ZONES[zone]
            print(
                f"[Radar] FIRE  {zone:<14} "
                f"bone={spec['bone_id']} channels={spec['channels']} "
                f"amp_mult={amp_mult:.2f}"
            )
        else:
            print(f"[Radar] STOP  {zone}")

    @staticmethod
    def _log_bone_inventory(suit) -> None:
        mapper = suit.api.mapper
        print("[Radar] Bone inventory (list_idx | sdk_enum | side | channels):")
        for list_idx, bone in enumerate(suit.bones):
            try:
                sdk_enum = mapper.get_bone_index(bone)
                side = mapper.get_bone_side(bone)
                num_ch = mapper.get_bone_number_of_contents(bone)
            except Exception as exc:
                print(f"  [{list_idx:2d}]  <inspection failed: {exc}>")
                continue
            print(f"  [{list_idx:2d}]  enum={sdk_enum:<3d} side={side} channels={num_ch}")

    @staticmethod
    def _try_build_zone(suit, name, zone):
        bone_id = zone["bone_id"]
        channels = zone["channels"]
        try:
            num_bones = len(suit.bones)
            if not 0 <= bone_id < num_bones:
                print(f"[Radar] WARNING: zone '{name}' bone_id={bone_id} "
                      f"out of range (suit has {num_bones} bones) — skipping.")
                return None
            num_ch = suit.api.mapper.get_bone_number_of_contents(suit.bones[bone_id])
            if any(ch >= num_ch for ch in channels):
                print(f"[Radar] WARNING: zone '{name}' channels {channels} "
                      f"exceed bone {bone_id} channel count ({num_ch}) — skipping.")
                return None
            return suit.create_haptic_touch(
                bone_id=bone_id,
                channel_list=channels,
                period=_BASE_PERIOD_US,
                amplitude=_BASE_AMP_PCT,
                pulse_width=_BASE_PW_US,
            )
        except Exception as exc:  # pylint: disable=broad-except
            print(f"[Radar] WARNING: failed to build zone '{name}' "
                  f"(bone_id={bone_id}, channels={channels}): {exc} — skipping.")
            return None
