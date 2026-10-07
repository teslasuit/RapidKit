# SPDX-License-Identifier: MIT
"""
LSL streaming for Teslsuit data.

Provides Lab Streaming Layer outlets for real-time streaming of biomechanical,
sensor, step detection, EMS, and control data to external applications.
"""

import pylsl
import numpy as np
import time
from dataclasses import fields, asdict
from typing import Optional, Dict, Any
from ..data.types import BiomechanicalData, StepDetectorData, ProcessedData, RawData, EmsData, ControlMessage, UtilityMessage, HeartRateData, HRVData, RawPPGData, HapticLibrary, _default_stim_params


class LSLStreamer:
    """
    Lab Streaming Layer streamer for Tesla Suit data.
    
    Creates 7 LSL outlets: biomechanics, step detection, EMS, control, utility,
    skeleton, and raw sensors. Each outlet streams at configured sample rate.
    
    Streaming is disabled by default (GDPR requirement — decision 1.7).
    Outlets are always created so external consumers can discover them,
    but data is only pushed when ``enabled=True``.
    
    Push decimation was considered but rejected — since we only push suit/framework
    data (not external sources), every sample matters and decimation would lose data.
    """
    
    def __init__(self, sample_rate: float = 100.0, source_id: str = "TeslaSuit_LSL",
                 enabled: bool = False, ppg_available: bool = False):
        """
        Initialize LSL outlets for all data streams.
        
        Args:
            sample_rate: Sampling rate in Hz (default: 100)
            source_id: Unique identifier for this source
            enabled: Whether streaming is active (default: False for GDPR).
                     Outlets are always created (so consumers can discover them)
                     but data is only pushed when enabled=True.
            ppg_available: Whether the PPG sensor is present on this suit.
                           When False, PPG outlets are not created.
        """
        self.sample_rate = sample_rate
        self.source_id = source_id
        self._enabled = enabled
        self.ppg_available = ppg_available
        
        # Initialize all outlets with enhanced metadata
        # Outlets are created regardless of enabled state so consumers can discover them
        self._create_biomechanical_outlet()
        self._create_step_detector_outlet()
        self._create_ems_data_outlet()
        self._create_control_message_outlet()
        self._create_utility_message_outlet()
        self._create_skeleton_outlet()
        self._create_raw_outlet()

        # HapticLibrary outlet — deferred. The user's HapticLibrary subclass
        # determines the channel layout (one channel per CustomPlayable slot,
        # labelled with the slot name). Configured at runtime by the engine
        # via configure_haptic_library_outlet() once strategy.setup() has
        # populated the library.
        self.haptic_library_outlet = None
        self.haptic_library_info = None
        self.haptic_library_channel_names: list = []

        # PPG outlets — only created when the suit has a PPG sensor
        if self.ppg_available:
            self._create_ppg_heart_rate_outlet()
            self._create_ppg_hrv_outlet()
            self._create_ppg_raw_outlet()
        else:
            self.ppg_hr_outlet = None
            self.ppg_hrv_outlet = None
            self.ppg_raw_outlet = None
        
        print(f"LSL Streamer initialized with {self.sample_rate} Hz sample rate")
        print(f"Source ID: {self.source_id}")
        print(f"Streaming enabled: {self._enabled}")
        print("Available outlets:")
        print(f"  - Biomechanical: {self.biomech_info.name()}")
        print(f"  - Step Detector: {self.step_info.name()}")
        print(f"  - EMS Parameters: {self.ems_info.name()}")
        if self.control_info is not None:
            print(f"  - Control Message: {self.control_info.name()}")
        else:
            print(f"  - Control Message: (deferred — call configure_control_outlet())")
        print(f"  - Utility Message: {self.utility_info.name()}")
        print(f"  - Skeleton: {self.skeleton_info.name()}")
        print(f"  - Raw Sensors: {self.raw_info.name()}")
        if self.ppg_available:
            print(f"  - PPG Heart Rate: {self.ppg_hr_info.name()}")
            print(f"  - PPG HRV: {self.ppg_hrv_info.name()}")
            print(f"  - PPG Raw: {self.ppg_raw_info.name()}")
        else:
            print("  - PPG: not available (no sensor detected)")

    # --- Flag gating properties ---

    @property
    def enabled(self) -> bool:
        """Whether LSL streaming is active."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        if value != self._enabled:
            self._enabled = value
            print(f"LSL streaming {'enabled' if value else 'disabled'}")
    
    def _create_biomechanical_outlet(self):
        """
        Create LSL outlet for 29 biomechanical joint angles.
        
        Streams pelvis, hip, knee, ankle, shoulder, elbow, wrist angles (degrees).
        """
        # Get field names from BiomechanicalData dataclass
        biomech_fields = [field.name for field in fields(BiomechanicalData) if field.name != 'timestamp']
        
        # Create stream info
        self.biomech_info = pylsl.StreamInfo(
            name="TS_Biomechanics",
            type="Biomechanical",
            channel_count=len(biomech_fields),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_double64,
            source_id=f"{self.source_id}_biomech"
        )
        
        # Add enhanced channel descriptions
        desc = self.biomech_info.desc()
        channels = desc.append_child("channels")
        for i, field_name in enumerate(biomech_fields):
            ch = channels.append_child("channel")
            ch.append_child_value("label", field_name)
            ch.append_child_value("unit", "degrees")
            ch.append_child_value("type", "angle")
            ch.append_child_value("id", str(i))
        
        # Create outlet
        self.biomech_outlet = pylsl.StreamOutlet(self.biomech_info)
        self.biomech_channel_names = biomech_fields
        
    def _create_step_detector_outlet(self):
        """
        Create LSL outlet for step detector/foot contact data with enhanced metadata.
        
        Channels:
        - left_foot_contact: Boolean flag for left foot ground contact
        - right_foot_contact: Boolean flag for right foot ground contact
        """
        # Get field names from StepDetectorData dataclass
        step_fields = [field.name for field in fields(StepDetectorData) if field.name != 'timestamp']
        
        # Create stream info
        self.step_info = pylsl.StreamInfo(
            name="TS_API_StepDetector",
            type="StepDetection",
            channel_count=len(step_fields),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_float32,  # Boolean values as integers
            source_id=f"{self.source_id}_steps"
        )
        
        # Add enhanced channel descriptions
        desc = self.step_info.desc()
        channels = desc.append_child("channels")
        for i, field_name in enumerate(step_fields):
            ch = channels.append_child("channel")
            ch.append_child_value("label", field_name)
            ch.append_child_value("unit", "boolean")
            ch.append_child_value("type", "contact")
            ch.append_child_value("id", str(i))
        
        # Create outlet
        self.step_outlet = pylsl.StreamOutlet(self.step_info)
        self.step_channel_names = step_fields

    def _create_ems_data_outlet(self):
        """Create LSL outlet for EMS parameters (20 muscle groups × 4 parameters = 80 channels)."""
        # Get muscle group names from EmsData dataclass
        muscle_fields = [field.name for field in fields(EmsData)]
        
        # Create flattened channel names for all EMS parameters
        # Each muscle has: Amplitude, PulseWidth, Period, IsMuted (in logical order)
        ems_channels = []
        for muscle_name in muscle_fields:
            ems_channels.extend([
                f"{muscle_name}_Amplitude",
                f"{muscle_name}_PulseWidth",
                f"{muscle_name}_Period",
                f"{muscle_name}_IsMuted"
            ])
        
        # Create stream info
        self.ems_info = pylsl.StreamInfo(
            name="TS_EMSParameters",
            type="EMSParameters",
            channel_count=len(ems_channels),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_float32,  # Use float32 for EMS parameters
            source_id=f"{self.source_id}_ems"
        )
        
        # Add enhanced channel descriptions
        desc = self.ems_info.desc()
        channels = desc.append_child("channels")
        for i, channel_name in enumerate(ems_channels):
            ch = channels.append_child("channel")
            ch.append_child_value("label", channel_name)
            
            # Set appropriate units and types based on channel name
            if "Amplitude" in channel_name:
                ch.append_child_value("unit", "percent")
                ch.append_child_value("type", "EMS_Amplitude")
            elif "PulseWidth" in channel_name:
                ch.append_child_value("unit", "microseconds")
                ch.append_child_value("type", "EMS_PulseWidth")
            elif "Period" in channel_name:
                ch.append_child_value("unit", "milliseconds")
                ch.append_child_value("type", "EMS_Period")
            elif "IsMuted" in channel_name:
                ch.append_child_value("unit", "boolean")
                ch.append_child_value("type", "EMS_Mute")
            
            ch.append_child_value("id", str(i))
        
        # Create outlet
        self.ems_outlet = pylsl.StreamOutlet(self.ems_info)
        self.ems_channel_names = ems_channels
        self.ems_muscle_names = muscle_fields
        
    def _create_control_message_outlet(self, control_message_class=None):
        """Create LSL outlet for control messages.

        If *control_message_class* is None, defaults to ControlMessage.
        If the class has no streamable fields (base ControlMessage is empty),
        the outlet is skipped — call ``configure_control_outlet()`` later with
        a concrete subclass.
        """
        cls = control_message_class or ControlMessage
        # Get field names from dataclass (excluding callbacks)
        control_fields = [field.name for field in fields(cls) if field.name != '_on_change']

        if not control_fields:
            # Empty ControlMessage — defer outlet creation
            self.control_outlet = None
            self.control_channel_names = []
            self.control_field_names = []
            self.control_info = None
            return
        
        # For dict fields, we need to flatten them
        _stim_keys = list(_default_stim_params().keys())
        control_channels = []
        for field_name in control_fields:
            if "Stim" in field_name:
                # Each stimulation field is a dict with named keys
                control_channels.extend(
                    f"{field_name}_{k}" for k in _stim_keys
                )
            else:
                # Simple fields
                control_channels.append(field_name)
        
        # Create stream info
        self.control_info = pylsl.StreamInfo(
            name="AppData_ControlMessage",
            type="ControlMessage",
            channel_count=len(control_channels),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_float32,
            source_id=f"{self.source_id}_control"
        )
        
        # Add enhanced channel descriptions
        desc = self.control_info.desc()
        channels = desc.append_child("channels")
        for i, channel_name in enumerate(control_channels):
            ch = channels.append_child("channel")
            ch.append_child_value("label", channel_name)
            
            # Set appropriate units and types based on channel name
            if "FesIsActive" in channel_name:
                ch.append_child_value("unit", "boolean")
                ch.append_child_value("type", "control_flag")
            elif "is_active" in channel_name:
                ch.append_child_value("unit", "boolean")
                ch.append_child_value("type", "muscle_active_flag")
            elif "frequency" in channel_name:
                ch.append_child_value("unit", "Hz")
                ch.append_child_value("type", "stimulation_frequency")
            elif "amplitude" in channel_name:
                ch.append_child_value("unit", "mA")
                ch.append_child_value("type", "stimulation_amplitude")
            elif "pulse_width" in channel_name:
                ch.append_child_value("unit", "us")
                ch.append_child_value("type", "stimulation_timing")
            elif "stance" in channel_name or "swing" in channel_name:
                ch.append_child_value("unit", "relative_time")
                ch.append_child_value("type", "stimulation_timing")
            else:
                ch.append_child_value("unit", "unitless")
                ch.append_child_value("type", "parameter")
            
            ch.append_child_value("id", str(i))
        
        # Create outlet
        self.control_outlet = pylsl.StreamOutlet(self.control_info)
        self.control_channel_names = control_channels
        self.control_field_names = control_fields

    def configure_control_outlet(self, control_message_class):
        """(Re)create the control message outlet for a specific ControlMessage subclass.

        Call this from application code (e.g. BackendMainloop) after engine init
        if using a custom ControlMessage subclass.

        Args:
            control_message_class: The dataclass type to introspect for field layout.
        """
        self._create_control_message_outlet(control_message_class)

    def configure_haptic_library_outlet(self, haptic_library: HapticLibrary):
        """Create the HapticLibrary outlet from a populated library instance.

        Four channels per ``CustomPlayable`` slot, labelled
        ``{slot}_IsMuted``, ``{slot}_period_mult``, ``{slot}_amplitude_mult``,
        ``{slot}_pulse_width_mult``. Each per-tick sample is the flat
        4×N float vector in declared field order. Format is ``cf_float32``
        (the multipliers force float; ``IsMuted`` is encoded 0.0 / 1.0).
        Slot order is locked by ``HapticLibrary.iter_playables`` (dataclass
        field order), so analysts can map column → slot name from the
        channel labels alone.

        Called by :class:`ClosedLoopEngine` once during ``run()`` setup
        when ``strategy.haptic_library is not None``. Safe to call multiple
        times — the previous outlet is dropped and a fresh one is created
        (consumers will need to re-subscribe).

        Args:
            haptic_library: A populated HapticLibrary subclass instance.
                            Slot order and names are read at this point and
                            assumed not to change for the duration of streaming.
        """
        slot_names = [name for name, _ in haptic_library.iter_playables()]

        if not slot_names:
            # No CustomPlayable slots — nothing to stream.
            self.haptic_library_outlet = None
            self.haptic_library_info = None
            self.haptic_library_channel_names = []
            return

        # Four channels per slot — IsMuted + three multipliers.
        per_slot_suffixes = ("IsMuted", "period_mult", "amplitude_mult", "pulse_width_mult")
        channel_labels = [f"{name}_{suf}" for name in slot_names for suf in per_slot_suffixes]

        self.haptic_library_info = pylsl.StreamInfo(
            name="TS_HapticLibrary",
            type="HapticLibrary",
            channel_count=len(channel_labels),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_float32,
            source_id=f"{self.source_id}_haptic_library",
        )

        desc = self.haptic_library_info.desc()
        channels = desc.append_child("channels")
        for i, label in enumerate(channel_labels):
            ch = channels.append_child("channel")
            ch.append_child_value("label", label)
            if label.endswith("_IsMuted"):
                ch.append_child_value("unit", "boolean")
                ch.append_child_value("type", "haptic_mute")
            else:
                ch.append_child_value("unit", "ratio")
                ch.append_child_value("type", "haptic_multiplier")
            ch.append_child_value("id", str(i))

        self.haptic_library_outlet = pylsl.StreamOutlet(self.haptic_library_info)
        self.haptic_library_channel_names = channel_labels
    
    def _create_utility_message_outlet(self):
        """Create LSL outlet for utility flags (recording, calibration status)."""
        # Get field names from UtilityMessage dataclass (excluding callbacks and non-numeric fields)
        # Exclude FolderPath as it's a string and not suitable for LSL streaming
        utility_fields = [field.name for field in fields(UtilityMessage) 
                         if field.name != '_on_change' and field.name != 'FolderPath']
        
        # Create stream info
        self.utility_info = pylsl.StreamInfo(
            name="AppData_UtilityMessage",
            type="UtilityMessage",
            channel_count=len(utility_fields),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_float32,  # Boolean flags as floats (0.0/1.0)
            source_id=f"{self.source_id}_utility"
        )
        
        # Add enhanced channel descriptions
        desc = self.utility_info.desc()
        channels = desc.append_child("channels")
        for i, field_name in enumerate(utility_fields):
            ch = channels.append_child("channel")
            ch.append_child_value("label", field_name)
            ch.append_child_value("unit", "boolean")
            
            # Set appropriate types based on field name
            if "Recording" in field_name:
                ch.append_child_value("type", "recording_flag")
            elif "Calibration" in field_name:
                ch.append_child_value("type", "calibration_flag")
            elif "Fes" in field_name:
                ch.append_child_value("type", "fes_control_flag")
            else:
                ch.append_child_value("type", "status_flag")
            
            ch.append_child_value("id", str(i))
        
        # Create outlet
        self.utility_outlet = pylsl.StreamOutlet(self.utility_info)
        self.utility_channel_names = utility_fields
    
    def _create_skeleton_outlet(self):
        """Create LSL outlet for 20 bones × 7 channels (position xyz + quaternion wxyz)."""
        # Get field names from ProcessedData dataclass (bone names)
        skeleton_bone_fields = [field.name for field in fields(ProcessedData) if field.name != 'timestamp']
        
        # Create flattened channel names for all bone data
        skeleton_channels = []
        for bone_name in skeleton_bone_fields:
            # Each bone has position (x,y,z) and rotation (w,x,y,z) = 7 channels
            skeleton_channels.extend([
                f"{bone_name}_pos_x",
                f"{bone_name}_pos_y", 
                f"{bone_name}_pos_z",
                f"{bone_name}_rot_w",
                f"{bone_name}_rot_x",
                f"{bone_name}_rot_y",
                f"{bone_name}_rot_z"
            ])
        
        # Create stream info
        self.skeleton_info = pylsl.StreamInfo(
            name="TS_BonePosition",
            type="BonePosition",
            channel_count=len(skeleton_channels),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_double64,
            source_id=f"{self.source_id}_boneposition"
        )
        
        # Add enhanced channel descriptions
        desc = self.skeleton_info.desc()
        channels = desc.append_child("channels")
        for i, channel_name in enumerate(skeleton_channels):
            ch = channels.append_child("channel")
            ch.append_child_value("label", channel_name)
            if "pos" in channel_name:
                ch.append_child_value("unit", "meters")
                ch.append_child_value("type", "position")
            else:  # rotation
                ch.append_child_value("unit", "quaternion")
                ch.append_child_value("type", "orientation")
            ch.append_child_value("id", str(i))
        
        # Create outlet
        self.skeleton_outlet = pylsl.StreamOutlet(self.skeleton_info)
        self.skeleton_channel_names = skeleton_channels
        self.skeleton_bone_names = skeleton_bone_fields
        
    def _create_raw_outlet(self):
        """
        Create LSL outlet for raw sensor data with enhanced metadata.
        
        Channels include all raw sensor readings from RawData dataclass.
        Each sensor location has 14 channels:
        - boneId (1 channel)
        - q6 quaternion: w,x,y,z (4 channels)  
        - accel: x,y,z (3 channels)
        - gyro: x,y,z (3 channels)
        - linear_accel: x,y,z (3 channels)
        Total: 14 channels per sensor × ~20 sensors = ~280 channels + 1 hardware timestamp = 281 channels
        """
        # Get field names from RawData dataclass (sensor location names)
        raw_sensor_fields = [field.name for field in fields(RawData) if field.name != 'timestamp']
        
        # Create flattened channel names for all sensor data
        raw_channels = []
        
        # Add hardware timestamp as first channel
        raw_channels.append("hardware_timestamp")
        
        for sensor_name in raw_sensor_fields:
            # Each sensor has: boneId + q6(4) + accel(3) + gyro(3) + linear_accel(3) = 14 channels
            raw_channels.extend([
                f"{sensor_name}_boneId",
                f"{sensor_name}_q6_w",
                f"{sensor_name}_q6_x",
                f"{sensor_name}_q6_y", 
                f"{sensor_name}_q6_z",
                f"{sensor_name}_accel_x",
                f"{sensor_name}_accel_y",
                f"{sensor_name}_accel_z",
                f"{sensor_name}_gyro_x",
                f"{sensor_name}_gyro_y",
                f"{sensor_name}_gyro_z",
                f"{sensor_name}_linear_accel_x",
                f"{sensor_name}_linear_accel_y",
                f"{sensor_name}_linear_accel_z"
            ])
        
        # Create stream info
        self.raw_info = pylsl.StreamInfo(
            name="TS_RawData",
            type="RawData",
            channel_count=len(raw_channels),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_double64,
            source_id=f"{self.source_id}_raw"
        )
        
        # Add enhanced channel descriptions
        desc = self.raw_info.desc()
        channels = desc.append_child("channels")
        for i, channel_name in enumerate(raw_channels):
            ch = channels.append_child("channel")
            ch.append_child_value("label", channel_name)
            
            # Set appropriate units based on channel type
            if "hardware_timestamp" in channel_name:
                ch.append_child_value("unit", "microseconds")
                ch.append_child_value("type", "hardware_timestamp")
            elif "boneId" in channel_name:
                ch.append_child_value("unit", "id")
                ch.append_child_value("type", "identifier")
            elif "q6" in channel_name:
                ch.append_child_value("unit", "quaternion")
                ch.append_child_value("type", "orientation")
            elif "accel" in channel_name or "linear_accel" in channel_name:
                ch.append_child_value("unit", "m/s^2")
                ch.append_child_value("type", "acceleration")
            elif "gyro" in channel_name:
                ch.append_child_value("unit", "rad/s")
                ch.append_child_value("type", "angular_velocity")
            ch.append_child_value("id", str(i))
        
        # Create outlet
        self.raw_outlet = pylsl.StreamOutlet(self.raw_info)
        self.raw_channel_names = raw_channels
        self.raw_sensor_names = raw_sensor_fields

    # ── PPG outlet creation (conditional) ─────────────────────────

    def _create_ppg_heart_rate_outlet(self):
        """Create LSL outlet for PPG heart rate data (2 channels: HR + validity)."""
        ppg_hr_channels = ['heart_rate', 'is_heart_rate_valid']

        self.ppg_hr_info = pylsl.StreamInfo(
            name="TS_PPG_HeartRate",
            type="HeartRate",
            channel_count=len(ppg_hr_channels),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_float32,
            source_id=f"{self.source_id}_ppg_hr"
        )

        desc = self.ppg_hr_info.desc()
        channels = desc.append_child("channels")
        ch = channels.append_child("channel")
        ch.append_child_value("label", "heart_rate")
        ch.append_child_value("unit", "bpm")
        ch.append_child_value("type", "heart_rate")
        ch.append_child_value("id", "0")
        ch = channels.append_child("channel")
        ch.append_child_value("label", "is_heart_rate_valid")
        ch.append_child_value("unit", "boolean")
        ch.append_child_value("type", "validity")
        ch.append_child_value("id", "1")

        self.ppg_hr_outlet = pylsl.StreamOutlet(self.ppg_hr_info)
        self.ppg_hr_channel_names = ppg_hr_channels

    def _create_ppg_hrv_outlet(self):
        """Create LSL outlet for HRV metrics (7 channels)."""
        ppg_hrv_channels = ['mean_rr', 'sdnn', 'sdsd', 'rmssd', 'sd1', 'sd2', 'hlf']

        self.ppg_hrv_info = pylsl.StreamInfo(
            name="TS_PPG_HRV",
            type="HRV",
            channel_count=len(ppg_hrv_channels),
            nominal_srate=self.sample_rate,
            channel_format=pylsl.cf_float32,
            source_id=f"{self.source_id}_ppg_hrv"
        )

        desc = self.ppg_hrv_info.desc()
        channels = desc.append_child("channels")
        units = {
            'mean_rr': 'ms', 'sdnn': 'ms', 'sdsd': 'ms', 'rmssd': 'ms',
            'sd1': 'ms', 'sd2': 'ms', 'hlf': 'ratio',
        }
        for i, name in enumerate(ppg_hrv_channels):
            ch = channels.append_child("channel")
            ch.append_child_value("label", name)
            ch.append_child_value("unit", units.get(name, "unitless"))
            ch.append_child_value("type", "HRV_metric")
            ch.append_child_value("id", str(i))

        self.ppg_hrv_outlet = pylsl.StreamOutlet(self.ppg_hrv_info)
        self.ppg_hrv_channel_names = ppg_hrv_channels

    def _create_ppg_raw_outlet(self):
        """Create LSL outlet for raw PPG photodiode data (4 channels at 200 Hz).

        Channels: ir, red, blue, green (one sample per push).
        The engine pushes ~2 samples per cycle to match the 200 Hz PPG rate.
        """
        ppg_raw_channels = ['ir', 'red', 'blue', 'green']

        self.ppg_raw_info = pylsl.StreamInfo(
            name="TS_PPG_Raw",
            type="PPGRaw",
            channel_count=len(ppg_raw_channels),
            nominal_srate=200.0,  # PPG raw runs at 200 Hz
            channel_format=pylsl.cf_double64,
            source_id=f"{self.source_id}_ppg_raw"
        )

        desc = self.ppg_raw_info.desc()
        channels = desc.append_child("channels")
        for i, name in enumerate(ppg_raw_channels):
            ch = channels.append_child("channel")
            ch.append_child_value("label", name)
            ch.append_child_value("unit", "counts")
            ch.append_child_value("type", "photodiode")
            ch.append_child_value("id", str(i))

        self.ppg_raw_outlet = pylsl.StreamOutlet(self.ppg_raw_info)
        self.ppg_raw_channel_names = ppg_raw_channels

    def _dataclass_to_sample(self, data_instance, channel_names: list, exclude_timestamp: bool = True) -> list:
        """
        Convert dataclass instance to LSL sample format.
        
        Args:
            data_instance: Dataclass instance containing the data
            channel_names: List of field names to extract
            exclude_timestamp: Whether to exclude timestamp field
            
        Returns:
            List of values in the order specified by channel_names
        """
        if data_instance is None:
            return [0.0] * len(channel_names)
        
        sample = []
        for channel_name in channel_names:
            value = getattr(data_instance, channel_name, 0.0)
            
            # Handle boolean values (including numpy.bool_) for step detector
            # Convert to float since outlet uses cf_float32
            if isinstance(value, (bool, np.bool_)):
                sample.append(float(value))
            elif isinstance(value, str):
                # Skip string values (like FolderPath) - they shouldn't be in channel_names
                # but handle gracefully if they somehow get through
                sample.append(0.0)
            else:
                sample.append(float(value) if value is not None else 0.0)
        
        return sample
    
    def _extract_skeleton_data(self, skeleton_data: ProcessedData) -> list:
        """
        Extract flattened skeleton data from nested ProcessedData structure.
        
        Each bone (MocapBoneData) contains:
        - position: BonePosition (x, y, z)
        - rotation: BoneRotation (w, x, y, z)
        
        Returns flattened list: [bone1_pos_x, bone1_pos_y, bone1_pos_z, bone1_rot_w, ...]
        """
        if skeleton_data is None:
            return [0.0] * len(self.skeleton_channel_names)
        
        sample = []
        for bone_name in self.skeleton_bone_names:
            bone_data = getattr(skeleton_data, bone_name, None)
            
            if bone_data is not None and hasattr(bone_data, 'position') and hasattr(bone_data, 'rotation'):
                # Extract position (x, y, z)
                pos = bone_data.position
                sample.extend([
                    getattr(pos, 'x', 0.0),
                    getattr(pos, 'y', 0.0), 
                    getattr(pos, 'z', 0.0)
                ])
                
                # Extract rotation (w, x, y, z)
                rot = bone_data.rotation
                sample.extend([
                    getattr(rot, 'w', 0.0),
                    getattr(rot, 'x', 0.0),
                    getattr(rot, 'y', 0.0),
                    getattr(rot, 'z', 0.0)
                ])
            else:
                # Missing bone data - fill with zeros
                sample.extend([0.0] * 7)  # 3 pos + 4 rot
        
        return sample
    
    def _extract_raw_sensor_data(self, raw_data: RawData) -> list:
        """
        Extract flattened raw sensor data from nested RawData structure.
        
        Each sensor (SensorData) contains:
        - boneId: int
        - q6: Q6Quaternion (w, x, y, z)
        - accel: Acceleration (x, y, z)
        - gyro: Gyroscope (x, y, z)
        - linear_accel: LinearAcceleration (x, y, z)
        
        Returns flattened list: [hardware_timestamp, sensor1_boneId, sensor1_q6_w, sensor1_q6_x, ...]
        """
        if raw_data is None:
            return [0.0] * len(self.raw_channel_names)
        
        sample = []
        
        # Add hardware timestamp as first channel (in microseconds)
        hardware_timestamp = getattr(raw_data, 'timestamp', 0)
        sample.append(float(hardware_timestamp))
        
        for sensor_name in self.raw_sensor_names:
            sensor_data = getattr(raw_data, sensor_name, None)
            
            if sensor_data is not None:
                # Extract boneId
                sample.append(getattr(sensor_data, 'boneId', 0))
                
                # Extract q6 quaternion (w, x, y, z)
                q6 = getattr(sensor_data, 'q6', None)
                if q6 is not None:
                    sample.extend([
                        getattr(q6, 'w', 0.0),
                        getattr(q6, 'x', 0.0),
                        getattr(q6, 'y', 0.0),
                        getattr(q6, 'z', 0.0)
                    ])
                else:
                    sample.extend([0.0] * 4)
                
                # Extract acceleration (x, y, z)
                accel = getattr(sensor_data, 'accel', None)
                if accel is not None:
                    sample.extend([
                        getattr(accel, 'x', 0.0),
                        getattr(accel, 'y', 0.0),
                        getattr(accel, 'z', 0.0)
                    ])
                else:
                    sample.extend([0.0] * 3)
                
                # Extract gyroscope (x, y, z)
                gyro = getattr(sensor_data, 'gyro', None)
                if gyro is not None:
                    sample.extend([
                        getattr(gyro, 'x', 0.0),
                        getattr(gyro, 'y', 0.0),
                        getattr(gyro, 'z', 0.0)
                    ])
                else:
                    sample.extend([0.0] * 3)
                
                # Extract linear acceleration (x, y, z) 
                linear_accel = getattr(sensor_data, 'linear_accel', None)
                if linear_accel is not None:
                    sample.extend([
                        getattr(linear_accel, 'x', 0.0),
                        getattr(linear_accel, 'y', 0.0),
                        getattr(linear_accel, 'z', 0.0)
                    ])
                else:
                    sample.extend([0.0] * 3)
            else:
                # Missing sensor data - fill with zeros
                sample.extend([0.0] * 14)  # 1 boneId + 4 q6 + 3 accel + 3 gyro + 3 linear_accel
        
        return sample
    
    def _extract_ems_data(self, ems_data: EmsData) -> list:
        """
        Extract flattened EMS data from nested EmsData structure.
        
        Each muscle group (EMSParamData) contains:
        - Amplitude: int (%) - stimulation intensity
        - PulseWidth: int (us) - pulse duration in microseconds
        - Period: float (ms) - stimulation period in milliseconds
        - IsMuted: bool - whether muscle stimulation is disabled
        
        Returns flattened list with all 4 parameters for each muscle group.
        Order: [Muscle1_Amplitude, Muscle1_PulseWidth, Muscle1_Period, Muscle1_IsMuted, 
                Muscle2_Amplitude, ...]
        """
        if ems_data is None:
            return [0.0] * len(self.ems_channel_names)
        
        sample = []
        for muscle_name in self.ems_muscle_names:
            muscle_data = getattr(ems_data, muscle_name, None)
            
            if muscle_data is not None:
                # Extract all 4 parameters in order: Amplitude, PulseWidth, Period, IsMuted
                sample.append(float(muscle_data.Amplitude) if hasattr(muscle_data, 'Amplitude') else 0.0)
                sample.append(float(muscle_data.PulseWidth) if hasattr(muscle_data, 'PulseWidth') else 0.0)
                sample.append(float(muscle_data.Period) if hasattr(muscle_data, 'Period') else 0.0)
                sample.append(float(int(muscle_data.IsMuted)) if hasattr(muscle_data, 'IsMuted') else 0.0)
            else:
                # Missing muscle data - fill with zeros (4 parameters)
                sample.extend([0.0, 0.0, 0.0, 0.0])
        
        return sample
    
    def _extract_control_message_data(self, control_data: ControlMessage) -> list:
        """
        Extract flattened control message data from ControlMessage structure.

        Each stimulation field is a dict whose keys match
        ``_default_stim_params()``.

        Returns flattened list with all control parameters.
        """
        if control_data is None:
            return [0.0] * len(self.control_channel_names)

        _stim_keys = tuple(_default_stim_params().keys())
        
        sample = []
        for field_name in self.control_field_names:
            value = getattr(control_data, field_name, None)
            
            if "Stim" in field_name and isinstance(value, dict):
                # Flatten dict stimulation parameters using standard key order
                for key in _stim_keys:
                    v = value.get(key, 0)
                    sample.append(float(int(v)) if isinstance(v, bool) else float(v))
            else:
                # Simple fields
                if isinstance(value, bool):
                    sample.append(float(int(value)))
                else:
                    sample.append(float(value) if value is not None else 0.0)
        
        return sample
    
    def stream_biomechanical_data(self, biomech_data: BiomechanicalData):
        """
        Stream biomechanical joint angle data to LSL.
        
        Args:
            biomech_data: BiomechanicalData instance containing joint angles
        """
        if not self._enabled or biomech_data is None:
            return
            
        sample = self._dataclass_to_sample(biomech_data, self.biomech_channel_names)
        timestamp = getattr(biomech_data, 'timestamp', pylsl.local_clock())
        
        try:
            self.biomech_outlet.push_sample(sample, timestamp)
        except Exception as e:
            print(f"Error streaming biomechanical data: {e}")
    
    def stream_step_detector_data(self, step_data: StepDetectorData):
        """
        Stream step detector/foot contact data to LSL.
        
        Args:
            step_data: StepDetectorData instance containing foot contact flags
        """
        if not self._enabled or step_data is None:
            return
            
        sample = self._dataclass_to_sample(step_data, self.step_channel_names)
        timestamp = getattr(step_data, 'timestamp', pylsl.local_clock())
        
        try:
            self.step_outlet.push_sample(sample, timestamp)
        except Exception as e:
            print(f"Error streaming step detector data: {e}")
    
    def stream_ems_data(self, ems_data: EmsData):
        """
        Stream EMS parameters data to LSL.
        
        Args:
            ems_data: EmsData instance containing EMS stimulation parameters
        """
        if not self._enabled or ems_data is None:
            return
            
        sample = self._extract_ems_data(ems_data)
        timestamp = pylsl.local_clock()  # EmsData doesn't have timestamp field
        
        try:
            self.ems_outlet.push_sample(sample, timestamp)
        except Exception as e:
            print(f"Error streaming EMS parameters data: {e}")
    
    def stream_control_message_data(self, control_data: ControlMessage):
        """
        Stream control message data to LSL.
        
        Args:
            control_data: ControlMessage instance containing control parameters
        """
        if not self._enabled or control_data is None or self.control_outlet is None:
            return
            
        sample = self._extract_control_message_data(control_data)
        timestamp = pylsl.local_clock()  # Control messages don't have timestamp field
        
        try:
            self.control_outlet.push_sample(sample, timestamp)
        except Exception as e:
            print(f"Error streaming control message data: {e}")
    
    def stream_haptic_library_data(self, haptic_library: HapticLibrary):
        """Push the current per-slot (IsMuted, multipliers) vector to LSL.

        Sample shape: ``[slot0_IsMuted, slot0_period_mult, slot0_amplitude_mult,
        slot0_pulse_width_mult, slot1_IsMuted, ...]`` — four floats per
        slot in dataclass field order, matching the labels written by
        :meth:`configure_haptic_library_outlet`.

        No-op if streaming is disabled, the library is None, or the outlet
        was never configured (call :meth:`configure_haptic_library_outlet`
        once at startup before pushing).

        Args:
            haptic_library: The same library instance whose layout was
                            registered via configure_haptic_library_outlet().
        """
        if (not self._enabled or haptic_library is None
                or self.haptic_library_outlet is None):
            return

        sample = []
        for _, slot in haptic_library.iter_playables():
            sample.append(1.0 if slot.IsMuted else 0.0)
            sample.append(float(slot.period_mult))
            sample.append(float(slot.amplitude_mult))
            sample.append(float(slot.pulse_width_mult))

        try:
            self.haptic_library_outlet.push_sample(sample, pylsl.local_clock())
        except Exception as e:
            print(f"Error streaming HapticLibrary data: {e}")

    def stream_utility_message_data(self, utility_data: UtilityMessage):
        """
        Stream utility message data to LSL.
        
        Args:
            utility_data: UtilityMessage instance containing utility flags
        """
        if not self._enabled or utility_data is None:
            return
            
        sample = self._dataclass_to_sample(utility_data, self.utility_channel_names)
        timestamp = pylsl.local_clock()  # Utility messages don't have timestamp field
        
        try:
            self.utility_outlet.push_sample(sample, timestamp)
        except Exception as e:
            print(f"Error streaming utility message data: {e}")
    
    def stream_skeleton_data(self, skeleton_data: ProcessedData):
        """
        Stream processed skeleton/bone data to LSL.
        
        Args:
            skeleton_data: ProcessedData instance containing skeleton data
        """
        if not self._enabled or skeleton_data is None:
            return
            
        sample = self._extract_skeleton_data(skeleton_data)
        timestamp = getattr(skeleton_data, 'timestamp', pylsl.local_clock())
        
        try:
            self.skeleton_outlet.push_sample(sample, timestamp)
        except Exception as e:
            print(f"Error streaming skeleton data: {e}")
    
    def stream_raw_data(self, raw_data: RawData):
        """
        Stream raw sensor data to LSL.
        
        The hardware timestamp from Teslasuit is included as the first channel in the data.
        The LSL timestamp uses local_clock() for synchronization with other LSL streams.
        
        Args:
            raw_data: RawData instance containing raw sensor readings
        """
        if not self._enabled or raw_data is None:
            return
            
        # Extract sensor data (includes hardware timestamp as first channel)
        sample = self._extract_raw_sensor_data(raw_data)
        
        # Use LSL local clock for stream synchronization
        timestamp = pylsl.local_clock()
        
        try:
            self.raw_outlet.push_sample(sample, timestamp)
        except Exception as e:
            print(f"Error streaming raw sensor data: {e}")

    # ── PPG streaming methods ─────────────────────────────────────

    def stream_ppg_heart_rate(self, hr_data: HeartRateData):
        """Stream heart rate data to LSL.

        Args:
            hr_data: HeartRateData with current heart rate and validity flag.
        """
        if not self._enabled or self.ppg_hr_outlet is None or hr_data is None:
            return

        sample = [float(hr_data.heart_rate), float(hr_data.is_heart_rate_valid)]
        try:
            self.ppg_hr_outlet.push_sample(sample, pylsl.local_clock())
        except Exception as e:
            print(f"Error streaming PPG heart rate: {e}")

    def stream_ppg_hrv(self, hrv_data: HRVData):
        """Stream HRV metrics to LSL.

        Args:
            hrv_data: HRVData with HRV time-domain metrics.
        """
        if not self._enabled or self.ppg_hrv_outlet is None or hrv_data is None:
            return

        sample = [
            hrv_data.mean_rr, hrv_data.sdnn, hrv_data.sdsd,
            hrv_data.rmssd, hrv_data.sd1, hrv_data.sd2, hrv_data.hlf,
        ]
        try:
            self.ppg_hrv_outlet.push_sample(sample, pylsl.local_clock())
        except Exception as e:
            print(f"Error streaming PPG HRV: {e}")

    def stream_ppg_raw(self, raw_ppg_data: RawPPGData):
        """Stream raw PPG photodiode samples to LSL.

        Pushes each sample individually so the 200 Hz outlet rate is
        maintained (typically 2 samples per engine cycle at 100 Hz).

        Args:
            raw_ppg_data: RawPPGData with ir/red/blue/green sample lists.
        """
        if not self._enabled or self.ppg_raw_outlet is None or raw_ppg_data is None:
            return
        if not raw_ppg_data.ir_data:
            return

        now = pylsl.local_clock()
        n = len(raw_ppg_data.ir_data)

        for i in range(n):
            sample = [
                float(raw_ppg_data.ir_data[i]),
                float(raw_ppg_data.red_data[i]),
                float(raw_ppg_data.blue_data[i]),
                float(raw_ppg_data.green_data[i]),
            ]
            try:
                self.ppg_raw_outlet.push_sample(sample, now)
            except Exception as e:
                print(f"Error streaming PPG raw data: {e}")
                break

    def stream_all_data(self, biomech_data: BiomechanicalData = None,
                       step_data: StepDetectorData = None,
                       ems_data: EmsData = None,
                       control_data: ControlMessage = None,
                       utility_data: UtilityMessage = None,
                       skeleton_data: ProcessedData = None,
                       raw_data: RawData = None,
                       heart_rate_data: HeartRateData = None,
                       hrv_data: HRVData = None,
                       raw_ppg_data: RawPPGData = None,
                       haptic_library: HapticLibrary = None):
        """
        Stream all data types in a single call.
        
        No-op if streaming is disabled.  PPG arguments are silently
        ignored when the suit has no PPG sensor.
        
        Args:
            biomech_data: BiomechanicalData instance
            step_data: StepDetectorData instance
            ems_data: EmsData instance
            control_data: ControlMessage instance
            utility_data: UtilityMessage instance  
            skeleton_data: ProcessedData instance
            raw_data: RawData instance
            heart_rate_data: HeartRateData instance (PPG, optional)
            hrv_data: HRVData instance (PPG, optional)
            raw_ppg_data: RawPPGData instance (PPG, optional)
        """
        if not self._enabled:
            return

        if biomech_data is not None:
            self.stream_biomechanical_data(biomech_data)
            
        if step_data is not None:
            self.stream_step_detector_data(step_data)
            
        if ems_data is not None:
            self.stream_ems_data(ems_data)
            
        if control_data is not None:
            self.stream_control_message_data(control_data)
            
        if utility_data is not None:
            self.stream_utility_message_data(utility_data)
            
        if skeleton_data is not None:
            self.stream_skeleton_data(skeleton_data)
            
        if raw_data is not None:
            self.stream_raw_data(raw_data)

        # PPG outlets (no-op when ppg_available is False)
        if heart_rate_data is not None:
            self.stream_ppg_heart_rate(heart_rate_data)

        if hrv_data is not None:
            self.stream_ppg_hrv(hrv_data)

        if raw_ppg_data is not None:
            self.stream_ppg_raw(raw_ppg_data)

        if haptic_library is not None:
            self.stream_haptic_library_data(haptic_library)
    
    def get_outlet_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all LSL outlets.
        
        Returns:
            Dictionary containing outlet information
        """
        return {
            'biomechanical': {
                'name': self.biomech_info.name(),
                'type': self.biomech_info.type(),
                'channels': len(self.biomech_channel_names),
                'channel_names': self.biomech_channel_names,
                'sample_rate': self.sample_rate,
                'description': 'Joint angles in degrees'
            },
            'step_detector': {
                'name': self.step_info.name(),
                'type': self.step_info.type(), 
                'channels': len(self.step_channel_names),
                'channel_names': self.step_channel_names,
                'sample_rate': self.sample_rate,
                'description': 'Boolean foot contact flags'
            },
            'ems_parameters': {
                'name': self.ems_info.name(),
                'type': self.ems_info.type(),
                'channels': len(self.ems_channel_names),
                'channel_names': self.ems_channel_names,
                'muscle_count': len(self.ems_muscle_names),
                'muscles': self.ems_muscle_names,
                'channels_per_muscle': 4,
                'parameters': ['Amplitude (%)', 'PulseWidth (us)', 'Period (ms)', 'IsMuted (bool)'],
                'sample_rate': self.sample_rate,
                'description': 'EMS stimulation parameters for each muscle group: Amplitude (%), PulseWidth (μs), Period (ms), IsMuted (bool)'
            },
            'control_message': {
                'name': self.control_info.name() if self.control_info else '(not configured)',
                'type': self.control_info.type() if self.control_info else 'N/A',
                'channels': len(self.control_channel_names),
                'channel_names': self.control_channel_names,
                'sample_rate': self.sample_rate,
                'description': 'FES control parameters (app-specific, configured via configure_control_outlet)'
            },
            'utility_message': {
                'name': self.utility_info.name(),
                'type': self.utility_info.type(),
                'channels': len(self.utility_channel_names),
                'channel_names': self.utility_channel_names,
                'sample_rate': self.sample_rate,
                'description': 'System status flags (recording, calibration, etc.)'
            },
            'skeleton': {
                'name': self.skeleton_info.name(),
                'type': self.skeleton_info.type(),
                'channels': len(self.skeleton_channel_names),
                'bone_count': len(self.skeleton_bone_names),
                'bones': self.skeleton_bone_names,
                'channels_per_bone': 7,
                'sample_rate': self.sample_rate,
                'description': 'Bone positions (x,y,z) and rotations (w,x,y,z)'
            },
            'raw_sensors': {
                'name': self.raw_info.name(),
                'type': self.raw_info.type(),
                'channels': len(self.raw_channel_names),
                'sensor_count': len(self.raw_sensor_names),
                'sensors': self.raw_sensor_names,
                'channels_per_sensor': 14,
                'sample_rate': self.sample_rate,
                'description': 'Raw IMU data: boneId + quaternion + accel + gyro + linear_accel'
            },
            **(
                {
                    'ppg_heart_rate': {
                        'name': self.ppg_hr_info.name(),
                        'type': self.ppg_hr_info.type(),
                        'channels': len(self.ppg_hr_channel_names),
                        'channel_names': self.ppg_hr_channel_names,
                        'sample_rate': self.sample_rate,
                        'description': 'PPG heart rate (bpm) + validity flag'
                    },
                    'ppg_hrv': {
                        'name': self.ppg_hrv_info.name(),
                        'type': self.ppg_hrv_info.type(),
                        'channels': len(self.ppg_hrv_channel_names),
                        'channel_names': self.ppg_hrv_channel_names,
                        'sample_rate': self.sample_rate,
                        'description': 'HRV time-domain metrics (mean_rr, sdnn, rmssd, …)'
                    },
                    'ppg_raw': {
                        'name': self.ppg_raw_info.name(),
                        'type': self.ppg_raw_info.type(),
                        'channels': len(self.ppg_raw_channel_names),
                        'channel_names': self.ppg_raw_channel_names,
                        'sample_rate': 200.0,
                        'description': 'Raw photodiode data (ir, red, blue, green) at 200 Hz'
                    },
                } if self.ppg_available else {}
            ),
        }
    
    def close(self):
        """
        Close all LSL outlets and clean up resources.
        """
        print("Closing LSL outlets...")
        
        # LSL outlets are automatically cleaned up when they go out of scope
        # But we can explicitly delete them
        del self.biomech_outlet
        del self.step_outlet
        del self.ems_outlet
        if self.control_outlet is not None:
            del self.control_outlet
        del self.utility_outlet  
        del self.skeleton_outlet
        del self.raw_outlet
        if self.ppg_hr_outlet is not None:
            del self.ppg_hr_outlet
        if self.ppg_hrv_outlet is not None:
            del self.ppg_hrv_outlet
        if self.ppg_raw_outlet is not None:
            del self.ppg_raw_outlet
        if self.haptic_library_outlet is not None:
            del self.haptic_library_outlet

        print("All LSL outlets closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically close outlets."""
        self.close()


if __name__ == "__main__":
    # Run test if this file is executed directly
    print("LSL Streamer module loaded")
    print("Available classes:")
    print("  - LSLStreamer: Basic LSL streaming for Tesla Suit data")
    print("  - LSLIntegratedStreamer: Integrated with MocapStreamer")
    print("  - test_lsl_streaming(): Run dummy data test")
    
