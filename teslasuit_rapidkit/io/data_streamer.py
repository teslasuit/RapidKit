# SPDX-License-Identifier: MIT
"""
Data streamer with three-phase cycle for Teslasuit sensor data.

DataStreamer handles all sensor data acquisition through a strict
collect → process → distribute cycle. It receives a SuitHandler reference
(composition) and uses it to read SDK data.

Users subclass DataStreamer and override process() to inject custom logic
(signal filtering, custom step detection, external data fusion, etc.).

Biomechanical-angle collection — ON by default
==============================================
``self.biomechanical_data`` (the 29 joint angles consumed via the
strategy's ``self.joints``) is refreshed every cycle by default. The
underlying SDK call ``get_biomechanical_angles_on_ready()`` runs the
inverse-kinematics solver and is the single most expensive call in
the per-cycle pipeline, but we leave it ON because surprising users
with all-zero joint angles is a worse default than the IK cost.

**Performance opt-out.** If your strategy never reads ``self.joints``
(e.g. haptic-only, foot-contact-only, raw-IMU-only) you can turn the
IK collection off to save the per-cycle SDK wait time::

    # 1) Programmatically — from an engine subclass that knows it
    #    doesn't need joint angles:
    self.data_streamer.set_biomech_collection(False)

    # 2) Dynamically from a GUI toggle, via UtilityMessage
    #    (see ``on_utility_message`` in your engine subclass):
    utility_message.BiomechanicalDataCollectionIsActive = False
    # then in on_utility_message():
    self.data_streamer.set_biomech_collection(
        message.BiomechanicalDataCollectionIsActive
    )
"""
from __future__ import annotations


import os
import time
from typing import TYPE_CHECKING

from ..data import init_utils as data_utils

if TYPE_CHECKING:
    from ..data.types import (
        BiomechanicalData, ProcessedData, StepDetectorData, RawData,
        HeartRateData, HRVData, RawPPGData,
    )
    from .suit_handler import SuitHandler



class DataStreamer:
    """
    Three-phase data acquisition cycle for Teslasuit sensor data.

    Lifecycle per cycle (called by BackendMainloop each iteration):
        1. Collect   (framework-owned) — read SDK, parse ctypes → dataclasses
        2. Process   (user-overridable) — custom processing hook
        3. Distribute (framework-owned) — make data available to consumers

    Users subclass DataStreamer and override process() for custom logic.
    All sensor data is available as class attributes during process().

    Attributes (populated after collect phase):
        biomechanical_data: BiomechanicalData — 29 joint angles, refreshed
                            every cycle. Collection is ON by default; use
                            ``set_biomech_collection(False)`` to skip the
                            expensive SDK IK call when your strategy
                            doesn't read joint angles.
        processed_data:     ProcessedData     — 20 bone positions/rotations
        step_detector_data: StepDetectorData  — foot contact booleans
        raw_data:           RawData           — raw IMU sensor data (20 bones)
        heart_rate_data:    HeartRateData     — heart rate (if PPG available)
        hrv_data:           HRVData           — heart rate variability (if PPG available)
        raw_ppg_data:       RawPPGData        — raw photodiode samples (if PPG available)
        ppg_available:      bool              — whether PPG sensor is present

    Performance note:
        ``get_biomechanical_angles_on_ready()`` is the most expensive call
        in the per-cycle pipeline (it runs the SDK inverse-kinematics
        solver). It runs by default so that ``self.joints.*`` works
        without ceremony; apps that never read joint angles should call
        ``set_biomech_collection(False)`` to claw back the SDK wait time.

    Args:
        suit_handler: SuitHandler instance providing hardware access
    """

    # Number of raw PPG samples to keep per engine cycle.
    # PPG sensor runs at 200 Hz, engine at 100 Hz → 2 samples per cycle.
    _PPG_RAW_SAMPLES = 2

    def __init__(self, suit_handler):
        """Initialize data streamer with hardware reference and data containers.

        Args:
            suit_handler: SuitHandler instance (composition, not inheritance)
        """
        self.suit_handler: SuitHandler = suit_handler

        # Data containers (owned by DataStreamer, updated in-place each cycle)
        self.biomechanical_data: BiomechanicalData = data_utils.init_BiomechanicalData()
        self.processed_data: ProcessedData = data_utils.init_ProcessedData()
        self.step_detector_data: StepDetectorData = data_utils.init_StepDetectorData()
        self.raw_data: RawData = data_utils.init_RawData()

        # PPG data containers (populated only when PPG sensor is present)
        self.heart_rate_data: HeartRateData = data_utils.init_HeartRateData()
        self.hrv_data: HRVData = data_utils.init_HRVData()
        self.raw_ppg_data: RawPPGData = data_utils.init_RawPPGData()

        # Raw SDK staging (intermediate ctypes data, not part of public API)
        self._raw_biomechanics = None
        self._raw_skeleton = None
        self._raw_step_detector = None
        self._raw_sensor_data = None

        # Biomechanical-angle collection gate. ON BY DEFAULT.
        #
        # When True (default), _collect() calls the SDK IK solver every
        # cycle to refresh ``self.biomechanical_data`` (the 29 joint
        # angles surfaced to the strategy as ``self.joints``).
        #
        # When False, that SDK call — the single most expensive one in
        # the per-cycle pipeline — is skipped entirely, and
        # ``self.biomechanical_data`` keeps its previous values (all
        # zeros if nothing else has set them).
        #
        # Apps that never read ``self.joints.*`` (haptic-only,
        # foot-contact-only, raw-IMU-only) should turn this OFF for the
        # measurable per-cycle CPU savings. Apps that do read joint
        # angles should leave it on (the default).
        #
        # Toggle via:
        #   * ``self.set_biomech_collection(active: bool)`` — programmatic
        #   * ``UtilityMessage.BiomechanicalDataCollectionIsActive`` — GUI
        #     toggle, wired by the application via ``on_utility_message``
        self._collect_biomech: bool = True

        # Start mocap streaming via suit_handler
        self.suit_handler.start_mocap_streaming()

        # Try to start PPG — not every suit version has the sensor.
        # The SDK may silently accept start_raw_streaming() even when no PPG
        # hardware exists (returns all-zero data forever), so we probe for
        # real data during a short warm-up window before declaring success.
        self.ppg_available = False
        try:
            self.suit_handler.start_ppg_streaming()
            self.ppg_available = self._probe_ppg_sensor()
        except Exception:
            self.ppg_available = False

        if self.ppg_available:
            print("PPG sensor detected — streaming at 200 Hz")
        else:
            self.suit_handler.stop_ppg_streaming()
            print("No PPG sensor on this suit — PPG features disabled")


    # ── PPG Hardware Probe ──────────────────────────────────────────

    _PPG_PROBE_TIMEOUT_S = 2.0
    _PPG_PROBE_INTERVAL_S = 0.1

    def _probe_ppg_sensor(self) -> bool:
        """Poll the PPG subsystem briefly to distinguish real hardware from a ghost stream.

        Returns True only if at least one non-zero heart-rate reading or
        non-empty raw photodiode buffer appears within the probe window.
        """
        ppg = self.suit_handler.ppg
        deadline = time.monotonic() + self._PPG_PROBE_TIMEOUT_S

        while time.monotonic() < deadline:
            try:
                ppg_data = ppg.get_data()
                if ppg_data.number_of_nodes > 0 and ppg_data.nodes:
                    node = ppg_data.nodes[0]
                    if node.heart_rate != 0 or node.is_heart_rate_valid:
                        return True

                raw = ppg.get_data_raw()
                if raw.number_of_nodes > 0 and raw.nodes:
                    node = raw.nodes[0]
                    if node.sample_size > 0:
                        return True
            except Exception:
                return False

            time.sleep(self._PPG_PROBE_INTERVAL_S)

        return False

    # ── Three-Phase Cycle ─────────────────────────────────────────

    def run_cycle(self):
        """Execute one complete collect → process → distribute cycle.

        Called once per backend loop iteration. Do NOT override this method.
        """
        self._collect()
        self.process()
        self._distribute()

    # ── Phase 1: Collect (framework-owned, do NOT override) ───────

    def _collect(self):
        """Phase 1: Read all sensor data from Teslasuit SDK and parse to dataclasses.

        Reads via suit_handler.streamer (mocap subsystem):
          - Raw IMU sensor data (20 bones)
          - Skeleton bone positions/rotations (20 bones)
          - Biomechanical joint angles (29 angles)
          - Foot contacts (2 booleans)

        If PPG sensor is present, also reads (non-blocking):
          - Heart rate + validity flag
          - HRV metrics (mean_rr, sdnn, rmssd, …)
          - Raw photodiode data (last 2 samples at 200 Hz)

        After this method, all data attributes contain fresh values from the SDK.
        """
        mocap = self.suit_handler.streamer

        # Read raw ctypes data from SDK (blocking calls)
        self._raw_sensor_data = mocap.get_raw_data_on_ready()
        self._raw_skeleton = mocap.get_skeleton_data_on_ready()
        if self._collect_biomech:
            self._raw_biomechanics = mocap.get_biomechanical_angles_on_ready()
        self._raw_step_detector = mocap.get_foot_contacts_on_ready()

        # Parse ctypes → dataclasses (in-place update)
        if self._collect_biomech:
            data_utils.parse_ctypes_to_dataclass(
                self._raw_biomechanics, self.biomechanical_data
            )
        self._update_step_data(self._raw_step_detector)
        data_utils.update_inplace(self._raw_skeleton, self.processed_data)
        data_utils.update_inplace(self._raw_sensor_data, self.raw_data)

        # PPG collection (non-blocking, guarded)
        if self.ppg_available:
            self._collect_ppg()

    def _update_step_data(self, ts_foot_contacts):
        """Parse foot contact booleans from SDK struct.

        Args:
            ts_foot_contacts: Foot contacts data from Teslasuit SDK
        """
        self.step_detector_data.left_foot_contact = bool(
            ts_foot_contacts.left_foot
            if hasattr(ts_foot_contacts, 'left_foot') else False
        )
        self.step_detector_data.right_foot_contact = bool(
            ts_foot_contacts.right_foot
            if hasattr(ts_foot_contacts, 'right_foot') else False
        )

    def _collect_ppg(self):
        """Collect PPG data non-blocking from SDK callbacks.

        Reads the latest cached values from the PPG subsystem:
          - Processed heart rate from the first node
          - HRV metrics from the HRV callback
          - Raw photodiode data (last ``_PPG_RAW_KEEP_SAMPLES`` samples)

        PPG runs at ~200 Hz vs the engine's ~100 Hz, so approximately 2 raw
        samples accumulate per engine cycle. We keep the last 2 to avoid
        losing data.
        """
        ppg = self.suit_handler.ppg

        # Heart rate (non-blocking — returns latest callback data)
        ppg_data = ppg.get_data()
        if ppg_data.number_of_nodes > 0 and ppg_data.nodes:
            node = ppg_data.nodes[0]
            self.heart_rate_data.heart_rate = node.heart_rate
            self.heart_rate_data.is_heart_rate_valid = bool(node.is_heart_rate_valid)
            self.heart_rate_data.timestamp = node.timestamp

        # HRV (non-blocking)
        hrv = ppg.get_hrv()
        self.hrv_data.mean_rr = hrv.mean_rr
        self.hrv_data.sdnn = hrv.sdnn
        self.hrv_data.sdsd = hrv.sdsd
        self.hrv_data.rmssd = hrv.rmssd
        self.hrv_data.sd1 = hrv.sd1
        self.hrv_data.sd2 = hrv.sd2
        self.hrv_data.hlf = hrv.hlf

        # Raw photodiode data (non-blocking — keep last N samples)
        raw = ppg.get_data_raw()
        if raw.number_of_nodes > 0 and raw.nodes:
            node = raw.nodes[0]
            n = node.sample_size
            keep = self._PPG_RAW_SAMPLES
            start = max(0, n - keep)

            self.raw_ppg_data.ir_data = [node.ir_data[i] for i in range(start, n)]
            self.raw_ppg_data.red_data = [node.red_data[i] for i in range(start, n)]
            self.raw_ppg_data.blue_data = [node.blue_data[i] for i in range(start, n)]
            self.raw_ppg_data.green_data = [node.green_data[i] for i in range(start, n)]
        else:
            self.raw_ppg_data.ir_data = []
            self.raw_ppg_data.red_data = []
            self.raw_ppg_data.blue_data = []
            self.raw_ppg_data.green_data = []

    # ── Configuration setters ─────────────────────────────────────

    def set_biomech_collection(self, active: bool) -> None:
        """Toggle biomechanical-angle collection in _collect() at runtime.

        Controls whether ``self.biomechanical_data`` (the strategy's
        ``self.joints``) is refreshed each cycle. **Defaults to ON** so
        that strategies that read joint angles work out of the box.

        Turn it OFF as a deliberate performance optimisation when your
        strategy doesn't read ``self.joints.*``: the underlying SDK call
        (``get_biomechanical_angles_on_ready`` → inverse-kinematics
        solver) is the single most expensive call in the per-cycle
        pipeline. Skipping it claws back a measurable amount of per-
        cycle SDK wait time.

        When ``active=True`` (default):
            * ``_collect()`` calls the SDK IK solver each cycle.
            * ``self.biomechanical_data`` is refreshed every cycle (~100 Hz).

        When ``active=False`` (performance opt-out):
            * ``_collect()`` skips the SDK IK call.
            * ``self.biomechanical_data`` keeps its previous values
              (all zeros on a fresh DataStreamer). Anything in your
              strategy that reads ``self.joints.*`` will see those
              stale values — flat-line plot in the GUI is the classic
              symptom of accidentally turning it off.

        Args:
            active: True to enable IK collection (default), False to
                    skip the SDK call for performance.

        Examples:
            Wired to a GUI checkbox via ``UtilityMessage``::

                def on_utility_message(self, message):
                    self.data_streamer.set_biomech_collection(
                        message.BiomechanicalDataCollectionIsActive
                    )

            Force-off in an app that never reads ``self.joints``::

                class HapticOnlyEngine(ClosedLoopEngine):
                    def __init__(self, **kw):
                        super().__init__(**kw)
                        # Strategy is purely haptic — IK is wasted work.
                        self.data_streamer.set_biomech_collection(False)
        """
        self._collect_biomech = bool(active)

    # ── Phase 2: Process (user-overridable hook) ──────────────────

    def process(self):
        """Phase 2: Custom processing hook. Override in subclass.

        Default: no-op (pass-through). All collected data flows directly
        to the distribute phase unchanged.

        When overriding, you have read/write access to:
            self.biomechanical_data  — joint angles (modify in place)
            self.processed_data      — bone positions/rotations
            self.step_detector_data  — foot contacts
            self.raw_data            — raw IMU data
            self.suit_handler        — hardware access (read-only recommended)

        Example:
            class MyDataStreamer(DataStreamer):
                def process(self):
                    # Custom step detection using knee angle threshold
                    if self.biomechanical_data.KneeFlexExtR > 20.0:
                        self.step_detector_data.right_foot_contact = False

                    # Low-pass filter on hip angle
                    self.biomechanical_data.HipFlexExtR = my_filter(
                        self.biomechanical_data.HipFlexExtR
                    )
        """
        pass

    # ── Phase 3: Distribute (framework-owned, do NOT override) ────

    def _distribute(self):
        """Phase 3: Make processed data available to downstream consumers.

        Currently no-op because dataclasses are updated in-place during
        collect and process phases. Downstream consumers hold references
        to the same objects.

        This phase exists as an explicit architectural slot for future
        needs (e.g., data validation, snapshot copies, event dispatch).
        """
        pass

    # ── Calibration ───────────────────────────────────────────────

    def calibrate_and_write(self, path, filename="mocap_calibration_data_"):
        """Calibrate mocap system and write reference frame to CSV file.

        .. deprecated::
            Legacy method retained for backward compatibility with older
            GUI clients.
            Does NOT update ``engine.calibration`` state (is_calibrated stays
            False, no quality check is performed).  New code should use
            ``engine.calibration.calibrate()`` and ``engine.calibration.export()``
            instead.

        Args:
            path: Directory path for output file
            filename: Filename prefix (timestamp appended automatically)
        """
        self.suit_handler.mocap_calibrate_skeleton()
        data = self.suit_handler.streamer.get_raw_data_on_ready()
        if path is not None:
            filename = os.path.join(path, filename)
        data_utils.write_calibration_to_csv(data, filename=filename)
