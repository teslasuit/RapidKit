# SPDX-License-Identifier: MIT
"""
Vestibular Training example — data types.

The strategy reads PelvisTilt (sagittal) and PelvisList (frontal) directly
from self.joints, so the control message carries only operator-configurable
parameters — boundary geometry, intensity, and the calibrated neutral offset.

Haptic slot names mirror the zone convention from haptic_navigation /
haptic_proximity_radar (belly / back / left_shoulder / right_shoulder) so the
bone/channel mapping is identical across all three examples.
"""
from dataclasses import dataclass, field

from teslasuit_rapidkit.data.types import ControlMessage, CustomPlayable, HapticLibrary


@dataclass
class VestibularControlMessage(ControlMessage):
    """Operator-configurable parameters for the vestibular training session.

    Sway data flows from the suit sensor through self.joints in the strategy
    and through the ring buffer in the GUI — not through this message.

    Fields
    ------
    boundary_sagittal_deg:
        Stability limit in the sagittal plane (forward/backward), degrees.
        Haptic cues fire when |corrected PelvisTilt| exceeds this value.
    boundary_frontal_deg:
        Stability limit in the frontal plane (left/right), degrees.
        Haptic cues fire when |corrected PelvisList| exceeds this value.
    master_intensity_pct:
        Global amplitude multiplier for all haptic zones (0–100).
    neutral_sagittal_deg:
        Calibrated neutral PelvisTilt — subtracted from live readings.
        Set by the CALIBRATE action in the GUI.
    neutral_frontal_deg:
        Calibrated neutral PelvisList — subtracted from live readings.
        Set by the CALIBRATE action in the GUI.
    """
    boundary_sagittal_deg: float = 8.0
    boundary_frontal_deg:  float = 6.0
    master_intensity_pct:  int   = 60
    neutral_sagittal_deg:  float = 0.0
    neutral_frontal_deg:   float = 0.0
    # Telemetry written by the strategy each tick so the GUI can render
    # the live sway dot without a separate shared-memory ring buffer.
    pelvis_tilt_deg: float = 0.0
    pelvis_list_deg: float = 0.0
    suit_present:    bool  = False


@dataclass
class VestibularHaptics(HapticLibrary):
    """Four named haptic slots mapping cardinal sway directions to body zones.

    Zone → sway convention (error-signal: cue fires on the side of the lean):
        belly          forward lean  (+PelvisTilt)
        back           backward lean (−PelvisTilt)
        left_shoulder  left lean     (−PelvisList)
        right_shoulder right lean    (+PelvisList)
    """
    belly:          CustomPlayable = field(default_factory=CustomPlayable)
    back:           CustomPlayable = field(default_factory=CustomPlayable)
    left_shoulder:  CustomPlayable = field(default_factory=CustomPlayable)
    right_shoulder: CustomPlayable = field(default_factory=CustomPlayable)
