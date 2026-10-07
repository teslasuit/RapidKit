# SPDX-License-Identifier: MIT
"""
Control Strategy Base Class

ABC for FES control strategies. Subclass and implement process() to define control logic.

Data flow each cycle (orchestrated by run_strategy):
    Framework writes: self.joints, self.contacts, self.external_data, self.params
    User reads those attributes, writes stimulation commands to: self.ems_output
    Framework copies self.ems_output → ems_data (with FES active guard)

Usage:
    class MyFESStrategy(ControlStrategyBase):
        def process(self) -> None:
            if self.contacts.right_foot_contact:
                self.ems_output.quadriceps_right = EMSParamData(
                    IsMuted=False, PulseWidth=200, Amplitude=50, Period=20.0
                )

    strategy = MyFESStrategy()
    # Each cycle in the control loop:
    strategy.run_strategy(control_message, biomechanical_data, step_detector_data, ems_data)
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ..data.types import (ControlMessage, EmsData, HapticLibrary,
                           BiomechanicalData, StepDetectorData, EMSParamData)

if TYPE_CHECKING:
    from ..muscle_map import MuscleMap
    from ..io.suit_handler import SuitHandler


class ControlStrategyBase(ABC):
    """Abstract base class for FES control strategies.

    Subclass this and implement process() to create a custom strategy.

    Attributes set by framework before each process() call:
        joints:        BiomechanicalData — 29 joint angles (from DataStreamer).
                       Refreshed each cycle by default. If your app never
                       reads joint angles, call
                       ``data_streamer.set_biomech_collection(False)`` to
                       skip the expensive SDK IK call and save per-cycle
                       CPU; ``self.joints.*`` will then stay at zero.
        contacts:      StepDetectorData  — foot contact booleans (from DataStreamer)
        external_data: dict              — {stream_name: ExternalSample | None}
                                          empty dict until LSL inlets are registered
        params:        ControlMessage    — application-specific stimulation parameters
                                          (subclass defines fields, e.g. MyControlMessage)

    Attribute written by process():
        ems_output: EmsData — desired stimulation commands; framework reads this after process()

    Semantic muscle access (T2.5):
        muscles: MuscleMap — provides by_side() / by_region() queries and channel resolution.
                             Set via setup(muscles=muscle_map_instance).

    Haptic presets (optional):
        haptic_library: HapticLibrary — user-defined named CustomPlayable slots.
                                        Populate in setup() via self.suit factories;
                                        toggle slot.IsMuted in process() to fire / silence.
        suit:           SuitHandler — exposed in setup() so the user can build
                                      the haptic library (suit.create_haptic_touch /
                                      suit.load_haptic_asset) and access raw subsystems.
    """

    def __init__(self):
        # Input slots — populated by run_strategy() before each process() call
        self.joints: BiomechanicalData = BiomechanicalData()
        self.contacts: StepDetectorData = StepDetectorData()
        self.external_data: dict = {}      # T2.11 placeholder: LSL inlets via ExternalInputManager
        self.params: ControlMessage = None
        # Per-bone position/rotation for 20 segments, set by run_strategy.
        # Stays None for unit tests / synthetic invocations.
        self.skeleton = None

        # Output slot — user writes here; framework reads after process()
        self.ems_output: EmsData = EmsData()

        # Semantic muscle map (MuscleMap instance set via setup(); None until wired)
        self.muscles: MuscleMap = None

        # Hardware handle (set via setup(); used to build haptic_library, etc.)
        self.suit: SuitHandler = None

        # Optional haptic preset library — set in setup() if the strategy
        # uses custom haptic playables. Driven by LibraryStimulator each
        # cycle when non-None.
        self.haptic_library: HapticLibrary = None

    def setup(self, muscles: MuscleMap = None, suit: SuitHandler = None,
              config: dict = None) -> None:
        """One-time initialization called automatically by the engine before the first cycle.

        The framework calls this with ``muscles=suit_handler.muscle_map`` and
        ``suit=suit_handler`` so that ``self.muscles`` and ``self.suit`` are
        available in ``on_start()`` and ``process()``.  Override to add custom
        setup logic (load config, build ``self.haptic_library``, allocate
        internal state, etc.).  Always call ``super().setup(muscles, suit)``
        when overriding.

        Args:
            muscles: MuscleMap instance from SuitHandler (T2.5).
                     Provides semantic muscle queries: self.muscles.by_side("left"), etc.
            suit:    SuitHandler instance — exposes haptic factories
                     (``create_haptic_touch``, ``load_haptic_asset``) and
                     raw subsystems for advanced use cases.
            config:  Strategy-specific configuration dict
        """
        if muscles is not None:
            self.muscles = muscles
        if suit is not None:
            self.suit = suit

    @abstractmethod
    def process(self) -> None:
        """Execute one control cycle.

        Read sensor data from:
            self.joints        — BiomechanicalData (joint angles)
            self.contacts      — StepDetectorData (foot contacts)
            self.external_data — dict of external LSL samples (empty until T2.11)
            self.params        — ControlMessage (stimulation parameters)

        Write desired stimulation to:
            self.ems_output    — EmsData (set EMSParamData for each muscle group)

        Example:
            def process(self) -> None:
                if self.contacts.right_foot_contact:
                    self.ems_output.quadriceps_right = EMSParamData(
                        IsMuted=False, PulseWidth=200, Amplitude=50, Period=20.0
                    )

                # Access external force plate data (empty until T2.11)
                grf = self.external_data.get("ForcePlate_GRF")
                vertical_force = grf.data[2] if grf else 0.0
        """

    def run_strategy(self,
                     control_message: ControlMessage,
                     biomechanical_data: BiomechanicalData,
                     step_detector_data: StepDetectorData,
                     ems_data: EmsData,
                     fes_active: bool = True,
                     processed_data=None) -> None:
        """Orchestrate one control cycle. Called by ClosedLoopEngine each iteration.

        Stores data references on self (no copying), calls process(), then writes
        ems_output → ems_data with FES active guard.

        Do NOT override this method — implement process() instead.

        Args:
            control_message:      ControlMessage with FES parameters
            biomechanical_data:   BiomechanicalData from DataStreamer (29 joint angles)
            step_detector_data:   StepDetectorData from DataStreamer (foot contacts)
            ems_data:             EmsData to be updated with output stimulation commands
            fes_active:           Global FES toggle from UtilityMessage (default True)
            processed_data:       Optional ProcessedData (per-bone position/rotation
                                  for 20 segments) — exposed as ``self.skeleton``.
                                  ``None`` outside the engine (e.g. unit tests).
        """
        # Store data references (no setattr copying — same objects DataStreamer owns)
        self.joints = biomechanical_data
        self.contacts = step_detector_data
        self.params = control_message
        self.skeleton = processed_data

        # Execute user control logic
        self.process()

        # Write ems_output → ems_data with FES active guard
        _apply_ems_output(fes_active, self.ems_output, ems_data)


# Pre-allocated muted EMS parameters — reused every cycle when FES is inactive
# to avoid creating 20 new EMSParamData objects per cycle at 100Hz.
_MUTED = EMSParamData(IsMuted=True, PulseWidth=0, Amplitude=0, Period=0)


def _apply_ems_output(fes_active: bool, source: EmsData, target: EmsData) -> None:
    """Copy EMS output to target, or mute all muscle groups if FES is inactive.

    Args:
        fes_active: Whether FES stimulation is enabled
        source:     EmsData written by the strategy's process() method
        target:     EmsData owned by BackendMainloop (passed to Stimulator)
    """
    for muscle in EmsData.__dataclass_fields__:
        if fes_active:
            setattr(target, muscle, getattr(source, muscle))
        else:
            setattr(target, muscle, _MUTED)
