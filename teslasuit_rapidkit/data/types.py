# SPDX-License-Identifier: MIT
"""
Data structures for FES framework.

Defines dataclasses for biomechanical data, sensor readings, EMS control, step detection,
and inter-process messages.

Naming conventions:
    - PascalCase fields (e.g. KneeFlexExtR, LeftUpperLeg): mirror Teslasuit SDK enum names.
      Required by ``parse_ctypes_to_dataclass`` which matches field names to SDK attributes.
    - snake_case fields (e.g. quadriceps_left, left_foot_contact): framework-owned names.
      Used in EmsData, StepDetectorData, and other framework-defined structures.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Callable, Iterable, List, Optional, Tuple


@dataclass
class UtilityMessage:
    """System state and control flags exchanged between GUI and Backend.

    Fields:
        FesIsActive:                    Master FES enable. When False the stimulator
                                        mutes all output regardless of strategy commands.
        RecordingIsActive:              Whether the session recorder is running.
        CalibrationLoopIsActive:        Whether the calibration loop is active (blocks
                                        normal FES control while running).
        FolderPath:                     Root directory for data output (recordings, logs).
        TSAPIStepDetectionIsActive:     Use Teslasuit SDK native step detection (default).
        VUStepDetectionIsActive:        Use VU-algorithm software step detection.
        ModelBasedStepDetectionIsActive: Use ML-model-based step detection.

    Only one step detection mode should be active at a time.
    """
    _on_change: Optional[Callable[['UtilityMessage'], None]] = field(default=None, repr=False, compare=False, hash=False, init=False)
    FesIsActive: bool
    RecordingIsActive: bool
    CalibrationLoopIsActive: bool
    FolderPath: str
    TSAPIStepDetectionIsActive: bool
    BiomechanicalDataCollectionIsActive: bool

    def __setattr__(self, name, value):
        """Trigger callback on field changes for automatic message sending."""
        object.__setattr__(self, name, value)
        if name != '_on_change' and hasattr(self, '_on_change') and self._on_change:
            self._on_change()

    def __getstate__(self):
        state = self.__dict__.copy()
        if "_on_change" in state:
            del state["_on_change"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._on_change = None


def _default_stim_params() -> dict:
    """Default per-muscle stimulation parameter dict.

    Standard keys:
        is_active (bool):      Whether this muscle is enabled for stimulation
        frequency (float):     Stimulation frequency (Hz)
        amplitude (int):       Stimulation amplitude (%)
        pulse_width (int):     Pulse width (microseconds)
        stance_start (float):  Start of stance-phase window (0.0–1.0)
        stance_end (float):    End of stance-phase window (0.0–1.0)
        swing_start (float):   Start of swing-phase window (0.0–1.0)
        swing_end (float):     End of swing-phase window (0.0–1.0)

    Users may add custom keys — the framework does not inspect individual
    muscle dicts.
    """
    return {
        'is_active': False,
        'frequency': 0,
        'amplitude': 0,
        'pulse_width': 0,
        'stance_start': 0.0,
        'stance_end': 0.0,
        'swing_start': 0.0,
        'swing_end': 0.0,
    }


@dataclass
class ControlMessage:
    """Base control message for FES parameters (GUI → control strategy).

    Empty by default — subclass to define application-specific stimulation
    parameters.  The framework does not inspect the contents; it only passes
    the message through from the IPC queue to the control strategy.

    The ``_on_change`` callback fires on any field assignment, enabling
    automatic queue-send from the GUI process.

    See ``_default_stim_params()`` for a convenient per-muscle dict factory.

    Example (application-specific subclass)::

        @dataclass
        class MyControlMessage(ControlMessage):
            leftQuadStim: dict = field(default_factory=_default_stim_params)
            rightQuadStim: dict = field(default_factory=_default_stim_params)
    """
    _on_change: Optional[Callable[['ControlMessage'], None]] = field(default=None, repr=False, compare=False, hash=False, init=False)

    def __setattr__(self, name, value):
        """Trigger callback on field changes for automatic message sending."""
        object.__setattr__(self, name, value)
        if name != '_on_change' and hasattr(self, '_on_change') and self._on_change:
            self._on_change()

    def __getstate__(self):
        state = self.__dict__.copy()
        if "_on_change" in state:
            del state["_on_change"]
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._on_change = None


@dataclass
class EMSParamData:
    """Single muscle stimulation parameters (mute, pulse width, period, amplitude).

    ``IsMuted`` defaults to ``True`` so that an unwritten ``EmsData()`` slot is
    silent on hardware. A strategy that does not touch ``self.ems_output`` (or
    only writes a subset of muscles) will leave the rest muted instead of
    requesting zero-parameter stimulation, which the EMS ``Stimulator`` would
    otherwise materialise as a looped touch on every muscle.
    """
    IsMuted: bool = True
    PulseWidth: int = 0 #mks
    Period: float = 0.0 # ms
    Amplitude: int = 0 # %

@dataclass
class EmsData:
    """EMS stimulation parameters for all 20 muscle groups (semantic snake_case names)."""
    # Lower body
    quadriceps_left:          EMSParamData = field(default_factory=EMSParamData)
    quadriceps_right:         EMSParamData = field(default_factory=EMSParamData)
    hamstring_left:           EMSParamData = field(default_factory=EMSParamData)
    hamstring_right:          EMSParamData = field(default_factory=EMSParamData)
    gastrocnemius_left:       EMSParamData = field(default_factory=EMSParamData)
    gastrocnemius_right:      EMSParamData = field(default_factory=EMSParamData)
    tibialis_anterior_left:   EMSParamData = field(default_factory=EMSParamData)
    tibialis_anterior_right:  EMSParamData = field(default_factory=EMSParamData)
    gluteus_left:             EMSParamData = field(default_factory=EMSParamData)
    gluteus_right:            EMSParamData = field(default_factory=EMSParamData)
    # Upper body
    deltoid_left:             EMSParamData = field(default_factory=EMSParamData)
    deltoid_right:            EMSParamData = field(default_factory=EMSParamData)
    biceps_left:              EMSParamData = field(default_factory=EMSParamData)
    biceps_right:             EMSParamData = field(default_factory=EMSParamData)
    triceps_left:             EMSParamData = field(default_factory=EMSParamData)
    triceps_right:            EMSParamData = field(default_factory=EMSParamData)
    wrist_flexors_left:       EMSParamData = field(default_factory=EMSParamData)
    wrist_flexors_right:      EMSParamData = field(default_factory=EMSParamData)
    wrist_extensors_left:     EMSParamData = field(default_factory=EMSParamData)
    wrist_extensors_right:    EMSParamData = field(default_factory=EMSParamData)

@dataclass
class EmsMultiplierData:
    """Calibration range for EMS intensity (min/max multipliers)."""
    minimum: float = 0.0
    maximum: float = 0.0

@dataclass
class EMSCalibrationData:
    """Calibration intensity range (min/max multipliers) for all 20 muscle groups."""
    # Lower body
    quadriceps_left:          EmsMultiplierData = field(default_factory=EmsMultiplierData)
    quadriceps_right:         EmsMultiplierData = field(default_factory=EmsMultiplierData)
    hamstring_left:           EmsMultiplierData = field(default_factory=EmsMultiplierData)
    hamstring_right:          EmsMultiplierData = field(default_factory=EmsMultiplierData)
    gastrocnemius_left:       EmsMultiplierData = field(default_factory=EmsMultiplierData)
    gastrocnemius_right:      EmsMultiplierData = field(default_factory=EmsMultiplierData)
    tibialis_anterior_left:   EmsMultiplierData = field(default_factory=EmsMultiplierData)
    tibialis_anterior_right:  EmsMultiplierData = field(default_factory=EmsMultiplierData)
    gluteus_left:             EmsMultiplierData = field(default_factory=EmsMultiplierData)
    gluteus_right:            EmsMultiplierData = field(default_factory=EmsMultiplierData)
    # Upper body
    deltoid_left:             EmsMultiplierData = field(default_factory=EmsMultiplierData)
    deltoid_right:            EmsMultiplierData = field(default_factory=EmsMultiplierData)
    biceps_left:              EmsMultiplierData = field(default_factory=EmsMultiplierData)
    biceps_right:             EmsMultiplierData = field(default_factory=EmsMultiplierData)
    triceps_left:             EmsMultiplierData = field(default_factory=EmsMultiplierData)
    triceps_right:            EmsMultiplierData = field(default_factory=EmsMultiplierData)
    wrist_flexors_left:       EmsMultiplierData = field(default_factory=EmsMultiplierData)
    wrist_flexors_right:      EmsMultiplierData = field(default_factory=EmsMultiplierData)
    wrist_extensors_left:     EmsMultiplierData = field(default_factory=EmsMultiplierData)
    wrist_extensors_right:    EmsMultiplierData = field(default_factory=EmsMultiplierData)
@dataclass
class StepDetectorData:
    """Foot contact state from step detector (left/right foot on ground)."""
    left_foot_contact: bool = True
    right_foot_contact: bool = True

@dataclass
class Acceleration:
    """3D acceleration vector (m/s²)."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

@dataclass
class Gyroscope:
    """3D angular velocity vector (rad/s)."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

@dataclass
class Q6Quaternion:
    """Quaternion orientation (w, x, y, z)."""
    w: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

@dataclass
class LinearAcceleration:
    """3D linear acceleration without gravity (m/s²)."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

@dataclass
class BonePosition:
    """3D bone position in space."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

@dataclass
class BoneRotation:
    """Bone rotation as quaternion (w, x, y, z)."""
    w: float = 0.0
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

@dataclass
class SensorData:
    """Raw IMU sensor data from single bone (quaternion, accel, gyro)."""
    boneId: int = 0 #BoneId integer
    q6: Q6Quaternion = field(default_factory=Q6Quaternion)
    accel: Acceleration = field(default_factory=Acceleration)
    gyro: Gyroscope = field(default_factory=Gyroscope)
    linear_accel: LinearAcceleration = field(default_factory=LinearAcceleration)

@dataclass
class MocapBoneData:
    """Processed mocap data for single bone (position and rotation)."""
    position: BonePosition = field(default_factory=BonePosition)
    rotation: BoneRotation = field(default_factory=BoneRotation)

@dataclass
class BiomechanicalData:
    """Biomechanical joint angles (degrees) for full body — 29 angles.

    All values in degrees. Field names mirror Teslasuit SDK enum names exactly
    (required by ``parse_ctypes_to_dataclass``). Suffix R/L = Right/Left side.

    Sign conventions (OpenSim-compatible):
        FlexExt:   positive = flexion, negative = extension
        AddAbd:    positive = adduction, negative = abduction
        Rot:       positive = internal rotation, negative = external rotation
        ProSup:    positive = pronation, negative = supination
        Deviation: positive = radial deviation, negative = ulnar deviation

    Pelvis (3 DOF):
        PelvisTilt, PelvisList, PelvisRotation

    Lower body per side — R/L (6 DOF each):
        HipFlexExt, HipAddAbd, HipRot, KneeFlexExt, AnkleFlexExt, AnkleProSup

    Upper body per side — R/L (5 DOF each):
        ElbowFlexExt, ForearmProSup, WristFlexExt, WristDeviation,
        ShoulderAddAbd, ShoulderRot, ShoulderFlexExt
    """
    PelvisTilt: float = 0.0
    PelvisList: float = 0.0
    PelvisRotation: float = 0.0
    HipFlexExtR: float = 0.0
    HipAddAbdR: float = 0.0
    HipRotR: float = 0.0
    KneeFlexExtR: float = 0.0
    AnkleFlexExtR: float = 0.0
    AnkleProSupR: float = 0.0
    HipFlexExtL: float = 0.0
    HipAddAbdL: float = 0.0
    HipRotL: float = 0.0
    KneeFlexExtL: float = 0.0
    AnkleFlexExtL: float = 0.0
    AnkleProSupL: float = 0.0
    ElbowFlexExtR: float = 0.0
    ForearmProSupR: float = 0.0
    WristFlexExtR: float = 0.0
    WristDeviationR: float = 0.0
    ElbowFlexExtL: float = 0.0
    ForearmProSupL: float = 0.0
    WristFlexExtL: float = 0.0      
    WristDeviationL: float = 0.0
    ShoulderAddAbdR: float = 0.0
    ShoulderRotR: float = 0.0
    ShoulderFlexExtR: float = 0.0
    ShoulderAddAbdL: float = 0.0
    ShoulderRotL: float = 0.0
    ShoulderFlexExtL: float = 0.0

@dataclass
class RawData:
    """Raw sensor data from all 20 body segments (IMU readings)."""
    timestamp: int = 0
    Hips: SensorData = field(default_factory=SensorData)
    LeftUpperLeg: SensorData = field(default_factory=SensorData)
    RightUpperLeg: SensorData = field(default_factory=SensorData)
    LeftLowerLeg: SensorData = field(default_factory=SensorData)
    RightLowerLeg: SensorData = field(default_factory=SensorData)
    LeftFoot: SensorData = field(default_factory=SensorData)
    RightFoot: SensorData = field(default_factory=SensorData)
    Spine: SensorData = field(default_factory=SensorData)
    Chest: SensorData = field(default_factory=SensorData)
    UpperChest: SensorData = field(default_factory=SensorData)
    Neck: SensorData = field(default_factory=SensorData)
    Head: SensorData = field(default_factory=SensorData)
    LeftShoulder: SensorData = field(default_factory=SensorData)
    RightShoulder: SensorData = field(default_factory=SensorData)
    LeftUpperArm: SensorData = field(default_factory=SensorData)
    RightUpperArm: SensorData = field(default_factory=SensorData)
    LeftLowerArm: SensorData = field(default_factory=SensorData)
    RightLowerArm: SensorData = field(default_factory=SensorData)
    LeftHand: SensorData = field(default_factory=SensorData)
    RightHand: SensorData = field(default_factory=SensorData)

@dataclass
class ProcessedData:
    """Processed mocap data for all 20 body segments (position and rotation)."""
    Hips: MocapBoneData = field(default_factory=MocapBoneData)
    LeftUpperLeg: MocapBoneData = field(default_factory=MocapBoneData)
    RightUpperLeg: MocapBoneData = field(default_factory=MocapBoneData)
    LeftLowerLeg: MocapBoneData = field(default_factory=MocapBoneData)
    RightLowerLeg: MocapBoneData = field(default_factory=MocapBoneData)
    LeftFoot: MocapBoneData = field(default_factory=MocapBoneData)
    RightFoot: MocapBoneData = field(default_factory=MocapBoneData)
    Spine: MocapBoneData = field(default_factory=MocapBoneData)
    Chest: MocapBoneData = field(default_factory=MocapBoneData)
    UpperChest: MocapBoneData = field(default_factory=MocapBoneData)
    Neck: MocapBoneData = field(default_factory=MocapBoneData)
    Head: MocapBoneData = field(default_factory=MocapBoneData)
    LeftShoulder: MocapBoneData = field(default_factory=MocapBoneData)
    RightShoulder: MocapBoneData = field(default_factory=MocapBoneData)
    LeftUpperArm: MocapBoneData = field(default_factory=MocapBoneData)
    RightUpperArm: MocapBoneData = field(default_factory=MocapBoneData)
    LeftLowerArm: MocapBoneData = field(default_factory=MocapBoneData)
    RightLowerArm: MocapBoneData = field(default_factory=MocapBoneData)
    LeftHand: MocapBoneData = field(default_factory=MocapBoneData)
    RightHand: MocapBoneData = field(default_factory=MocapBoneData)

@dataclass
class HeartRateData:
    """Heart rate data from chest strap (bpm)."""
    heart_rate: int = 0
    is_heart_rate_valid: bool = False
    timestamp: int = 0

@dataclass
class HRVData:
    """Heart rate variability data from chest strap.

    All interval-based fields in milliseconds.

    Fields:
        hrv:     Overall HRV score (composite, device-specific).
        mean_rr: Mean R-R interval (ms) — inverse of average heart rate.
        sdnn:    Standard deviation of all R-R intervals (ms) — overall HRV.
        sdsd:    Standard deviation of successive R-R differences (ms).
        rmssd:   Root mean square of successive R-R differences (ms) — parasympathetic tone.
        sd1:     Poincaré plot short-axis SD — short-term variability.
        sd2:     Poincaré plot long-axis SD — long-term variability.
        hlf:     High-to-low frequency power ratio — sympatho-vagal balance.
    """
    hrv: float = 0.0
    mean_rr: float = 0.0
    sdnn: float = 0.0
    sdsd: float = 0.0
    rmssd: float = 0.0
    sd1: float = 0.0
    sd2: float = 0.0
    hlf: float = 0.0

@dataclass
class RawPPGData:
    """Raw PPG sensor data from chest strap (red/infrared light levels)."""
    ir_data: List[int] = field(default_factory=list)
    red_data: List[int] = field(default_factory=list)
    blue_data: List[int] = field(default_factory=list)
    green_data: List[int] = field(default_factory=list)

@dataclass
class CustomPlayable:
    """One named slot in a :class:`HapticLibrary`.

    Holds the SDK playable id, the desired mute state, looped flag, and
    three live-modulation multipliers applied via
    ``haptic.set_playable_multipliers`` whenever they change.

    Looped vs. one-shot determines what
    :class:`teslasuit_rapidkit.io.stimulator.LibraryStimulator` does on each
    mute→unmute edge:

    * ``is_looped=True`` — the factory pre-arms the playable
      (``play_playable`` already called, currently muted).
      ``set_playable_muted`` toggles audibility. Used for parameter-based
      touches built by :meth:`SuitHandler.create_haptic_touch` and for
      pre-recorded assets loaded with ``looped=True``.
    * ``is_looped=False`` — ``play_playable`` is re-fired on every
      mute→unmute edge. Used for one-shot pre-recorded assets loaded via
      :meth:`SuitHandler.load_haptic_asset` with ``looped=False``.

    Multipliers (``period_mult``, ``amplitude_mult``, ``pulse_width_mult``)
    scale the underlying playable's parameters at runtime — the strategy
    can mutate them from ``process()`` to drive live intensity changes
    without recreating the playable. Default ``1.0`` is a unity scale.
    Apply uniformly to both touch-built and asset-loaded playables.

    Default ``playable_id=0`` and ``IsMuted=True`` mean "uninitialised /
    silent" — overwritten when the user assigns a slot from a SuitHandler
    factory.
    """
    playable_id: int = 0
    IsMuted: bool = True
    is_looped: bool = True
    period_mult: float = 1.0
    amplitude_mult: float = 1.0
    pulse_width_mult: float = 1.0


@dataclass
class HapticLibrary:
    """Base for a typed haptic playable store. Subclass to declare named slots.

    Mirrors the :class:`ControlMessage` pattern — empty base, subclass
    adds slots of type :class:`CustomPlayable`. Populate slots in
    ``ControlStrategyBase.setup()`` via the SuitHandler factory methods
    (``suit.load_haptic_asset`` / ``suit.create_haptic_touch``); from
    ``process()`` toggle ``slot.IsMuted`` to fire / silence the playable.

    The engine drives playback automatically each cycle via
    :class:`teslasuit_rapidkit.io.stimulator.LibraryStimulator` — no explicit
    ``play_playable`` calls from user code.

    Example::

        @dataclass
        class ArmHaptics(HapticLibrary):
            biceps_burst:  CustomPlayable = field(default_factory=CustomPlayable)
            reach_forward: CustomPlayable = field(default_factory=CustomPlayable)

        # in strategy.setup():
        self.haptic_library = ArmHaptics()
        self.haptic_library.reach_forward = self.suit.load_haptic_asset("assets/reach.tsasset")
        self.haptic_library.biceps_burst  = self.suit.create_haptic_touch(
            bone_id=12, channel_list=[1],
            period=20.0, amplitude=60, pulse_width=200,
        )

        # in strategy.process():
        self.haptic_library.biceps_burst.IsMuted = False  # fire
    """

    def iter_playables(self) -> Iterable[Tuple[str, "CustomPlayable"]]:
        """Iterate over named CustomPlayable slots in this library."""
        for f in fields(self):
            if f.name.startswith("_"):
                continue
            value = getattr(self, f.name, None)
            if isinstance(value, CustomPlayable):
                yield f.name, value



# ── Standard shared-memory frame dtypes ───────────────────────────
#
# Pre-built numpy dtypes for SharedRingBuffer.  Import the one that
# matches the data your backend writes.  Applications that need a
# custom layout can build their own (see examples/elbow_flexion/elbow_types.py).

import numpy as np

shared_memory_frame = np.dtype([
    ('timestamp',            'f8'),
    # BiomechanicalData (29 joint angles)
    ('PelvisTilt',           'f8'),
    ('PelvisList',           'f8'),
    ('PelvisRotation',       'f8'),
    ('HipFlexExtR',          'f8'),
    ('HipAddAbdR',           'f8'),
    ('HipRotR',              'f8'),
    ('KneeFlexExtR',         'f8'),
    ('AnkleFlexExtR',        'f8'),
    ('AnkleProSupR',         'f8'),
    ('HipFlexExtL',          'f8'),
    ('HipAddAbdL',           'f8'),
    ('HipRotL',              'f8'),
    ('KneeFlexExtL',         'f8'),
    ('AnkleFlexExtL',        'f8'),
    ('AnkleProSupL',         'f8'),
    ('ElbowFlexExtR',        'f8'),
    ('ForearmProSupR',       'f8'),
    ('WristFlexExtR',        'f8'),
    ('WristDeviationR',      'f8'),
    ('ElbowFlexExtL',        'f8'),
    ('ForearmProSupL',       'f8'),
    ('WristFlexExtL',        'f8'),
    ('WristDeviationL',      'f8'),
    ('ShoulderAddAbdR',      'f8'),
    ('ShoulderRotR',         'f8'),
    ('ShoulderFlexExtR',     'f8'),
    ('ShoulderAddAbdL',      'f8'),
    ('ShoulderRotL',         'f8'),
    ('ShoulderFlexExtL',     'f8'),
    # StepDetectorData
    ('StepDetectorRight',    'u1'),
    ('StepDetectorLeft',     'u1'),
    # Metadata
    ('backend_sample_rate',  'f4'),
])