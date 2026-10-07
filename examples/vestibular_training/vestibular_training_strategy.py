# SPDX-License-Identifier: MIT
"""
Vestibular Training strategy — real-time postural sway → directional haptic cues.

Reads spine tilt from self.skeleton.Spine.rotation (IMU-fused quaternion) and
converts it to pitch (sagittal lean) and roll (frontal lean) using standard ZYX
Euler decomposition.  When the corrected sway vector exits the operator-configured
stability ellipse, fires the four haptic zones with cosine²-weighted intensity so
the patient feels the strongest cue on the side of the lean.

Zone / sway convention (error-signal: cue on the lean side):
    belly          forward lean   pitch > +boundary_sagittal_deg
    back           backward lean  pitch < −boundary_sagittal_deg
    right_shoulder right lean     roll  > +boundary_frontal_deg
    left_shoulder  left lean      roll  < −boundary_frontal_deg

Cardinal angles follow the atan2 frame used in haptic_proximity_radar:
    +x = right (east), +y = forward (north).
    belly → θ = +π/2,  back → θ = −π/2,
    right_shoulder → θ = 0,  left_shoulder → θ = π.

Bone / channel mapping (Teslasuit 4R, verified on reference unit):
    Body area              bone_id  channels
    Abdomen (belly)           8     0–7
    Back                     11     0–7
    Left upper-arm front     12     0–2
    Right upper-arm front    14     0–2

No EMS is produced — self.ems_output is pre-muted in __init__.
"""
from __future__ import annotations

import logging
import math

from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase

from .vestibular_training_types import VestibularHaptics


logger = logging.getLogger(__name__)


def _wrap_180(deg: float) -> float:
    """Wrap an angle in degrees into [-180, 180]."""
    return ((deg + 180.0) % 360.0) - 180.0


def _quat_to_pitch_roll(rotation) -> tuple[float, float] | None:
    """Extract pitch (sagittal) and roll (frontal) tilt in degrees from a quaternion.

    Uses ZYX Euler convention (yaw→pitch→roll).  The Teslasuit's spine bone does
    not rest at identity — its quaternion at upright stance can be close to a
    ±180° rotation in one axis, which makes raw atan2 readings flip-flop between
    +180 and -180 with small lateral tilts.  The output is therefore wrapped to
    [-180, 180] and the operator must use the CALIBRATE button (or the GUI's
    neutral-offset sliders) to zero the patient's upright stance.

    Returns None when the rotation field is missing or uninitialised
    (all-zero quaternion).
    """
    if rotation is None:
        return None
    try:
        w = float(getattr(rotation, "w"))
        x = float(getattr(rotation, "x"))
        y = float(getattr(rotation, "y"))
        z = float(getattr(rotation, "z"))
    except (AttributeError, TypeError, ValueError):
        return None
    if w * w + x * x + y * y + z * z < 1e-9:
        return None  # uninitialised quaternion
    pitch_rad = math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))
    roll_rad  = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    return _wrap_180(math.degrees(pitch_rad)), _wrap_180(math.degrees(roll_rad))


_ZONES: dict[str, dict] = {
    "belly":          {"bone_id":  8, "channels": [0, 1, 2, 3, 4, 5, 6, 7],
                       "theta":  math.pi / 2},
    "back":           {"bone_id": 11, "channels": [0, 1, 2, 3, 4, 5, 6, 7],
                       "theta": -math.pi / 2},
    "left_shoulder":  {"bone_id": 12, "channels": [0, 1, 2],
                       "theta":  math.pi},
    "right_shoulder": {"bone_id": 14, "channels": [0, 1, 2],
                       "theta":  0.0},
}

_BASE_PERIOD_US: int   = 20_000
_BASE_AMP_PCT:   int   = 60
_BASE_PW_US:     int   = 200

# Minimum angular weight below which a zone is silenced — avoids a constant
# whisper on zones nearly perpendicular to the sway direction.
_WEIGHT_EPS: float = 0.02

# Pulse-width range (multiplier on _BASE_PW_US).
# At the exact boundary the cue is gentle (0.5); at 2× the boundary it peaks (1.0).
_PW_MULT_MIN: float = 0.5
_PW_MULT_MAX: float = 1.0

# Sway excess is clamped to this value so intensity does not grow without bound.
_MAX_EXCESS: float = 1.0


class VestibularTrainingStrategy(ControlStrategyBase):
    """Drive four haptic zones from real-time postural sway measurements."""

    def __init__(self) -> None:
        super().__init__()
        self._last_state: dict[str, tuple] = {name: (False, -1) for name in _ZONES}

        # Reference quaternion-derived angles captured on the first valid
        # streaming frame.  The Teslasuit spine bone does not rest at identity,
        # so raw atan2/asin readings can sit right on the ±180° wrap boundary
        # (causing small lateral tilts to flip between +179° and -179°).
        # Subtracting this reference anchors the published telemetry near zero
        # regardless of the suit's rest orientation; the operator's CALIBRATE
        # button still applies on top as a fine-tune.
        self._reference_angles: tuple[float, float] | None = None

        # Haptic-only example — pre-mute every EMS muscle so the EMS Stimulator
        # never receives an "active with zero parameters" frame, which on hardware
        # can manifest as continuous low-level stimulation.
        for muscle_name in self.ems_output.__dataclass_fields__:
            getattr(self.ems_output, muscle_name).IsMuted = True

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def setup(self, muscles=None, suit=None, config=None) -> None:
        super().setup(muscles=muscles, suit=suit, config=config)
        if suit is None:
            return

        self._log_bone_inventory(suit)

        lib = VestibularHaptics()
        for name, zone in _ZONES.items():
            slot = self._try_build_zone(suit, name, zone)
            if slot is not None:
                setattr(lib, name, slot)
        self.haptic_library = lib

    # ── per-tick ───────────────────────────────────────────────────────────────

    def process(self) -> None:
        if self.params is None:
            return

        # Read spine tilt from the IMU-fused skeleton quaternion.
        spine = getattr(self.skeleton, "Spine", None) if self.skeleton else None
        angles = _quat_to_pitch_roll(getattr(spine, "rotation", None) if spine else None)
        if angles is not None:
            pitch_deg, roll_deg = angles
            if self._reference_angles is None:
                # First valid frame defines the anchor — published telemetry
                # starts at ≈0 instead of wherever the spine quaternion lands.
                self._reference_angles = (pitch_deg, roll_deg)
            ref_pitch, ref_roll = self._reference_angles
            sagittal_raw = _wrap_180(pitch_deg - ref_pitch)
            frontal_raw  = _wrap_180(roll_deg  - ref_roll)
        else:
            sagittal_raw, frontal_raw = 0.0, 0.0

        # Publish telemetry so the GUI can render the live sway dot.
        self.params.pelvis_tilt_deg = float(sagittal_raw)
        self.params.pelvis_list_deg = float(frontal_raw)
        self.params.suit_present    = angles is not None

        if self.haptic_library is None:
            return

        # Apply calibrated neutral offset.
        # Use getattr with defaults — self.params starts as base ControlMessage
        # before the GUI has sent the first VestibularControlMessage.
        neutral_sag = float(getattr(self.params, "neutral_sagittal_deg", 0.0))
        neutral_frt = float(getattr(self.params, "neutral_frontal_deg",  0.0))
        sagittal = _wrap_180(sagittal_raw - neutral_sag)
        frontal  = _wrap_180(frontal_raw  - neutral_frt)

        # Normalise sway against the stability ellipse so r = 1 at the boundary.
        bnd_sag = max(0.1, float(getattr(self.params, "boundary_sagittal_deg", 8.0)))
        bnd_frt = max(0.1, float(getattr(self.params, "boundary_frontal_deg",  6.0)))
        x = frontal  / bnd_frt   # +x = right
        y = sagittal / bnd_sag   # +y = forward

        r = math.hypot(x, y)

        if r <= 1.0:
            # Patient is within the stability boundary — silence all cues.
            self._mute_all()
            return

        # Sway excess: 0 at the boundary, 1 at 2× the boundary.
        excess = min((r - 1.0) / _MAX_EXCESS, 1.0)

        theta = math.atan2(y, x)
        master_mult = float(getattr(self.params, "master_intensity_pct", _BASE_AMP_PCT)) / float(_BASE_AMP_PCT)

        lib = self.haptic_library
        for name, zone in _ZONES.items():
            slot = getattr(lib, name)
            cos_term = math.cos(theta - zone["theta"])
            w = max(0.0, cos_term) ** 2
            firing = w >= _WEIGHT_EPS
            if firing:
                slot.IsMuted          = False
                slot.amplitude_mult   = master_mult * excess * w
                slot.pulse_width_mult = _PW_MULT_MIN + (_PW_MULT_MAX - _PW_MULT_MIN) * excess
            else:
                slot.IsMuted          = True
                slot.amplitude_mult   = 0.0
                slot.pulse_width_mult = _PW_MULT_MIN
            self._log_edge(name, firing, slot.amplitude_mult)

    # ── helpers ────────────────────────────────────────────────────────────────

    def _mute_all(self) -> None:
        lib = self.haptic_library
        for name in _ZONES:
            slot = getattr(lib, name)
            if not slot.IsMuted:
                slot.IsMuted          = True
                slot.amplitude_mult   = 0.0
                slot.pulse_width_mult = _PW_MULT_MIN
            self._log_edge(name, False, 0.0)

    def _log_edge(self, zone: str, firing: bool, amp_mult: float) -> None:
        bucket = int(round(amp_mult * 10)) if firing else -1
        new_state = (firing, bucket)
        if self._last_state.get(zone) == new_state:
            return
        self._last_state[zone] = new_state
        if firing:
            spec = _ZONES[zone]
            print(
                f"[VestibularTraining] FIRE  {zone:<14} "
                f"bone={spec['bone_id']} channels={spec['channels']} "
                f"amp_mult={amp_mult:.2f}"
            )
        else:
            print(f"[VestibularTraining] STOP  {zone}")

    @staticmethod
    def _log_bone_inventory(suit) -> None:
        mapper = suit.api.mapper
        print("[VestibularTraining] Bone inventory (list_idx | sdk_enum | side | channels):")
        for list_idx, bone in enumerate(suit.bones):
            try:
                sdk_enum = mapper.get_bone_index(bone)
                side     = mapper.get_bone_side(bone)
                num_ch   = mapper.get_bone_number_of_contents(bone)
            except Exception as exc:
                print(f"  [{list_idx:2d}]  <inspection failed: {exc}>")
                continue
            print(f"  [{list_idx:2d}]  enum={sdk_enum:<3d} side={side} channels={num_ch}")

    @staticmethod
    def _try_build_zone(suit, name: str, zone: dict):
        bone_id  = zone["bone_id"]
        channels = zone["channels"]
        try:
            num_bones = len(suit.bones)
            if not 0 <= bone_id < num_bones:
                print(f"[VestibularTraining] WARNING: zone '{name}' bone_id={bone_id} "
                      f"out of range (suit has {num_bones} bones) — skipping.")
                return None
            num_ch = suit.api.mapper.get_bone_number_of_contents(suit.bones[bone_id])
            if any(ch >= num_ch for ch in channels):
                print(f"[VestibularTraining] WARNING: zone '{name}' channels {channels} "
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
            print(f"[VestibularTraining] WARNING: failed to build zone '{name}' "
                  f"(bone_id={bone_id}, channels={channels}): {exc} — skipping.")
            return None
