# SPDX-License-Identifier: MIT
"""
Haptic Navigation strategy — translate operator key state into haptic cues.

Holds four looped CustomPlayable slots (one per navigation direction). On
each cycle the strategy reads the four direction booleans on the control
message and toggles the matching slot's ``IsMuted`` field; LibraryStimulator
in the engine drives the SDK on the resulting edges.

No EMS is produced — ``self.ems_output`` is left at the default (all muted).

Bone / channel mapping (Teslasuit 4.x)
--------------------------------------
Verified against the operator's body-area channel table::

    Body area              bone_id  bone-channel IDs
    -------------------    -------  -----------------
    Abdomen                   8     0, 1, 2, 3, 4, 5, 6, 7
    Back                     11     0, 1, 2, 3, 4, 5, 6, 7
    Left Upper arm front     12     0, 1, 2
    Right Upper arm front    14     0, 1, 2

The "left/right shoulder" cues drive the upper-arm-front bones — that is
the deltoid region of the suit and is the most natural place a wearer
feels a "turn left/right" prompt. Forward / backward use the full 8-channel
abdomen / back arrays for a strong, unambiguous torso cue.

A bone inventory is printed during ``setup()`` so the mapping can be
re-checked on a different 4.x unit, on XR5, or on a future hardware
revision.
"""
import logging

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase

from .haptic_navigation_types import NavigationHaptics


logger = logging.getLogger(__name__)

_ZONES = {
    "belly":          {"bone_id":  8, "channels": [0, 1, 2, 3, 4, 5, 6, 7]},
    "back":           {"bone_id": 11, "channels": [0, 1, 2, 3, 4, 5, 6, 7]},
    "left_shoulder":  {"bone_id": 12, "channels": [0, 1, 2]},
    "right_shoulder": {"bone_id": 14, "channels": [0, 1, 2]},
}

_BASE_PERIOD_US: int = 20_000
_BASE_AMP_PCT:   int = 60
_BASE_PW_US:     int = 200


_DIAGONAL_PW_MULT: float = 0.7


class HapticNavigationStrategy(ControlStrategyBase):
    """Drive four haptic zones from the operator's arrow keys."""

    def __init__(self) -> None:
        super().__init__()
        # Track per-zone (active, pw_mult) state so we only print on edges.
        # Prime with the resting state so the first process() call doesn't
        # log a spurious STOP for every zone.
        self._last_state: dict = {name: (False, 1.0) for name in _ZONES}

        # This example produces haptic-only output — process() never writes
        # self.ems_output. EMSParamData defaults to IsMuted=False, so without
        # this pre-mute every cycle would tell the EMS Stimulator that all
        # 20 muscles are active with zero parameters; on real hardware that
        # can come out as a continuous low-level stim. Set the mute once
        # here and never touch ems_output again.
        for muscle_name in self.ems_output.__dataclass_fields__:
            getattr(self.ems_output, muscle_name).IsMuted = True

    def setup(self, muscles=None, suit=None, config=None) -> None:
        super().setup(muscles=muscles, suit=suit, config=config)
        if suit is None:
            return

        self._log_bone_inventory(suit)

        lib = NavigationHaptics()
        for name, zone in _ZONES.items():
            slot = self._try_build_zone(suit, name, zone)
            if slot is not None:
                setattr(lib, name, slot)
        self.haptic_library = lib

    @staticmethod
    def _log_bone_inventory(suit) -> None:
        """Print one line per bone — list index, SDK enum, side, channel count.

        Use this output to pick valid ``bone_id`` / ``channels`` values for
        ``_ZONES``. Without it, choosing channel indices is guesswork.
        """
        mapper = suit.api.mapper
        print("[HapticNavigation] Bone inventory (list_idx | sdk_enum | side | channels):")
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
        """Attempt to build one zone's haptic touch; warn and skip on failure.

        A bone with too few channels for the configured slice raises
        ``IndexError`` inside the SDK wrapper; we catch broadly so a single
        misconfigured zone never takes down the whole example.
        """
        bone_id = zone["bone_id"]
        channels = zone["channels"]
        try:
            num_bones = len(suit.bones)
            if not 0 <= bone_id < num_bones:
                print(f"[HapticNavigation] WARNING: zone '{name}' bone_id={bone_id} "
                      f"out of range (suit has {num_bones} bones) — skipping.")
                return None
            num_ch = suit.api.mapper.get_bone_number_of_contents(suit.bones[bone_id])
            if any(ch >= num_ch for ch in channels):
                print(f"[HapticNavigation] WARNING: zone '{name}' channels {channels} "
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
            print(f"[HapticNavigation] WARNING: failed to build zone '{name}' "
                  f"(bone_id={bone_id}, channels={channels}): {exc} — skipping.")
            return None

    def process(self) -> None:
        if self.params is None or not hasattr(self.params, "forward"):
            return
        if self.haptic_library is None:
            return

        lib = self.haptic_library
        flags = {
            "belly":          bool(self.params.forward),
            "back":           bool(self.params.backward),
            "left_shoulder":  bool(self.params.left),
            "right_shoulder": bool(self.params.right),
        }
        # When two or more directions are held at once the operator is
        # asking for a diagonal cue. Drop pulse width on every active zone
        # so the combined sensation isn't overwhelming.
        active_count = sum(flags.values())
        active_pw_mult = _DIAGONAL_PW_MULT if active_count >= 2 else 1.0
        amp_mult = float(self.params.intensity_pct) / float(_BASE_AMP_PCT)

        for name, active in flags.items():
            slot = getattr(lib, name)
            slot.IsMuted          = not active
            slot.amplitude_mult   = amp_mult
            slot.pulse_width_mult = active_pw_mult if active else 1.0
            self._log_edge(name, active, active_pw_mult)

    def _log_edge(self, zone: str, active: bool, pw_mult: float) -> None:
        """Print on (active, pw_mult) transitions only — quiet on steady state."""
        new_state = (active, pw_mult if active else 1.0)
        if self._last_state.get(zone) == new_state:
            return
        self._last_state[zone] = new_state
        if active:
            spec = _ZONES.get(zone, {})
            tag = "  (diagonal)" if pw_mult < 1.0 else ""
            print(
                f"[HapticNav] FIRE  {zone:<14} "
                f"bone={spec.get('bone_id')} "
                f"channels={spec.get('channels')} "
                f"pw_mult={pw_mult:.2f}{tag}"
            )
        else:
            print(f"[HapticNav] STOP  {zone}")
