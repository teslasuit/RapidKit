# SPDX-License-Identifier: MIT
"""
Initialization utilities for dataclasses.

Provides factory functions to create dataclass instances with default values and
serialization/deserialization utilities for CSV storage.
"""
from . import types as data_types
from dataclasses import is_dataclass, fields
from ctypes import Structure
import datetime
import csv
from typing import Optional

def init_UtilityMessage(_on_change=None):
    """Create UtilityMessage with default values."""
    from pathlib import Path
    # Default path: project_root/data
    project_root = Path(__file__).parent.parent.parent
    default_folder_path = str(project_root / "data")
    
    return data_types.UtilityMessage(
        FesIsActive=False,
        RecordingIsActive=False,
        CalibrationLoopIsActive=False,
        FolderPath=default_folder_path,
        TSAPIStepDetectionIsActive=True,
        # Biomechanical-angle collection runs in DataStreamer by default
        # (the strategy's ``self.joints`` is refreshed each cycle).  Set
        # this to False from a GUI toggle when the strategy doesn't need
        # joint angles — DataStreamer will skip the expensive SDK IK call
        # and reclaim per-cycle CPU.  See DataStreamer.set_biomech_collection.
        BiomechanicalDataCollectionIsActive=True,
    )


def init_ControlMessage(_on_change=None):
    """Create empty base ControlMessage.

    Applications with their own control-message subclass should provide
    their own factory function instead (see ``ControlMessage`` docstring).
    """
    return data_types.ControlMessage()


def init_EMSParamData():
    """Create EMSParamData with safe defaults (muted, 200μs pulse, 1kHz)."""
    return data_types.EMSParamData(
        IsMuted=True,
        PulseWidth=200,
        Period=1000.0,
        Amplitude=0
    )

def init_EmsData():
    """Create EmsData for all 20 muscle groups with safe defaults (muted, 200 µs pulse)."""
    return data_types.EmsData(
        quadriceps_left=init_EMSParamData(),
        quadriceps_right=init_EMSParamData(),
        hamstring_left=init_EMSParamData(),
        hamstring_right=init_EMSParamData(),
        gastrocnemius_left=init_EMSParamData(),
        gastrocnemius_right=init_EMSParamData(),
        tibialis_anterior_left=init_EMSParamData(),
        tibialis_anterior_right=init_EMSParamData(),
        gluteus_left=init_EMSParamData(),
        gluteus_right=init_EMSParamData(),
        deltoid_left=init_EMSParamData(),
        deltoid_right=init_EMSParamData(),
        biceps_left=init_EMSParamData(),
        biceps_right=init_EMSParamData(),
        triceps_left=init_EMSParamData(),
        triceps_right=init_EMSParamData(),
        wrist_flexors_left=init_EMSParamData(),
        wrist_flexors_right=init_EMSParamData(),
        wrist_extensors_left=init_EMSParamData(),
        wrist_extensors_right=init_EMSParamData(),
    )

def init_EmsMultiplierData():
    """Create EmsMultiplierData with default calibration range [0.0, 1.0]."""
    return data_types.EmsMultiplierData(
        minimum=0.0,
        maximum=1.0
    )

def init_EMSCalibrationData():
    """Create EMSCalibrationData for all 20 muscle groups with default range [0.0, 1.0]."""
    return data_types.EMSCalibrationData(
        quadriceps_left=init_EmsMultiplierData(),
        quadriceps_right=init_EmsMultiplierData(),
        hamstring_left=init_EmsMultiplierData(),
        hamstring_right=init_EmsMultiplierData(),
        gastrocnemius_left=init_EmsMultiplierData(),
        gastrocnemius_right=init_EmsMultiplierData(),
        tibialis_anterior_left=init_EmsMultiplierData(),
        tibialis_anterior_right=init_EmsMultiplierData(),
        gluteus_left=init_EmsMultiplierData(),
        gluteus_right=init_EmsMultiplierData(),
        deltoid_left=init_EmsMultiplierData(),
        deltoid_right=init_EmsMultiplierData(),
        biceps_left=init_EmsMultiplierData(),
        biceps_right=init_EmsMultiplierData(),
        triceps_left=init_EmsMultiplierData(),
        triceps_right=init_EmsMultiplierData(),
        wrist_flexors_left=init_EmsMultiplierData(),
        wrist_flexors_right=init_EmsMultiplierData(),
        wrist_extensors_left=init_EmsMultiplierData(),
        wrist_extensors_right=init_EmsMultiplierData(),
    )

def init_StepDetectorData():
    """Create StepDetectorData with both feet in contact (standing/default state)."""
    return data_types.StepDetectorData(
        left_foot_contact=True,
        right_foot_contact=True
    )

def init_Acceleration():
    """Create Acceleration with zero vector (m/s²)."""
    return data_types.Acceleration(
        x=0.0,
        y=0.0,
        z=0.0
    )

def init_Gyroscope():
    """Create Gyroscope with zero angular velocity (rad/s)."""
    return data_types.Gyroscope(
        x=0.0,
        y=0.0,
        z=0.0,
    )

def init_Q6Quaternion():
    """Create Q6Quaternion with zero rotation (w=0 — not a valid unit quaternion; use as placeholder only)."""
    return data_types.Q6Quaternion(
        w=0.0,
        x=0.0,
        y=0.0,
        z=0.0,
    )

def init_LinearAcceleration():
    """Create LinearAcceleration with zero vector (gravity-removed, m/s²)."""
    return data_types.LinearAcceleration(
        x=0.0,
        y=0.0,
        z=0.0
    )

def init_BonePosition():
    """Create BonePosition at origin (metres)."""
    return data_types.BonePosition(
        x=0.0,
        y=0.0,
        z=0.0
    )

def init_BoneRotation():
    """Create BoneRotation with zero quaternion (placeholder — not a valid unit quaternion)."""
    return data_types.BoneRotation(
        w=0.0,
        x=0.0,
        y=0.0,
        z=0.0
    )

def init_SensorData():
    """Create SensorData with zero IMU readings for a single bone."""
    return data_types.SensorData(
        boneId=0,
        q6=init_Q6Quaternion(),
        accel=init_Acceleration(),
        gyro=init_Gyroscope(),
        linear_accel=init_LinearAcceleration()
    )

def init_MocapBoneData():
    """Create MocapBoneData at origin with zero rotation for a single bone."""
    return data_types.MocapBoneData(
        position=init_BonePosition(),
        rotation=init_BoneRotation(),
    )

def init_BiomechanicalData():
    """Create BiomechanicalData with all 29 joint angles zeroed (anatomical neutral)."""
    return data_types.BiomechanicalData(
            PelvisTilt=0.0,
            PelvisList=0.0,
            PelvisRotation=0.0,
            HipFlexExtR=0.0,
            HipAddAbdR=0.0,
            HipRotR=0.0,
            KneeFlexExtR=0.0,
            AnkleFlexExtR=0.0,
            AnkleProSupR=0.0,
            HipFlexExtL=0.0,
            HipAddAbdL=0.0,
            HipRotL=0.0,
            KneeFlexExtL=0.0,
            AnkleFlexExtL=0.0,
            AnkleProSupL=0.0,
            ElbowFlexExtR=0.0,
            ForearmProSupR=0.0,
            WristFlexExtR=0.0,
            WristDeviationR=0.0,
            ElbowFlexExtL=0.0,
            ForearmProSupL=0.0,
            WristFlexExtL=0.0,
            WristDeviationL=0.0,
            ShoulderAddAbdR=0.0,
            ShoulderRotR=0.0,
            ShoulderFlexExtR=0.0,
            ShoulderAddAbdL=0.0,
            ShoulderRotL=0.0,
            ShoulderFlexExtL=0.0,
    )

def init_RawData():
    """Create RawData with zero IMU readings for all 20 body segments."""
    return data_types.RawData(
        timestamp=0.0,
        Hips=init_SensorData(),
        LeftUpperLeg=init_SensorData(),
        RightUpperLeg=init_SensorData(),
        LeftLowerLeg=init_SensorData(),
        RightLowerLeg=init_SensorData(),
        LeftFoot=init_SensorData(),
        RightFoot=init_SensorData(),
        Spine=init_SensorData(),
        Chest=init_SensorData(),
        UpperChest=init_SensorData(),
        Neck=init_SensorData(),
        Head=init_SensorData(),
        LeftShoulder=init_SensorData(),
        RightShoulder=init_SensorData(),
        LeftUpperArm=init_SensorData(),
        RightUpperArm=init_SensorData(),
        LeftLowerArm=init_SensorData(),
        RightLowerArm=init_SensorData(),
        LeftHand=init_SensorData(),
        RightHand=init_SensorData(),
    )

def init_ProcessedData():
    """Create ProcessedData at origin with zero rotation for all 20 body segments."""
    return data_types.ProcessedData(
        Hips=init_MocapBoneData(),
        LeftUpperLeg=init_MocapBoneData(),
        RightUpperLeg=init_MocapBoneData(),
        LeftLowerLeg=init_MocapBoneData(),
        RightLowerLeg=init_MocapBoneData(),
        LeftFoot=init_MocapBoneData(),
        RightFoot=init_MocapBoneData(),
        Spine=init_MocapBoneData(),
        Chest=init_MocapBoneData(),
        UpperChest=init_MocapBoneData(),
        Neck=init_MocapBoneData(),
        Head=init_MocapBoneData(),
        LeftShoulder=init_MocapBoneData(),
        RightShoulder=init_MocapBoneData(),
        LeftUpperArm=init_MocapBoneData(),
        RightUpperArm=init_MocapBoneData(),
        LeftLowerArm=init_MocapBoneData(),
        RightLowerArm=init_MocapBoneData(),
        LeftHand=init_MocapBoneData(),
        RightHand=init_MocapBoneData(),
    )

def parse_ctypes_to_dataclass(ctypes_struct, dataclass_instance):
    """
    Convert ctypes Structure or enum dict to dataclass by matching field names.

    Args:
        ctypes_struct: ctypes Structure instance or dict with enum keys
        dataclass_instance: Dataclass instance to populate

    Returns:
        Populated dataclass instance
    """
    # Handle dictionary with enum keys (e.g., TsBiomechanicalIndex)
    if isinstance(ctypes_struct, dict):
        for key, value in ctypes_struct.items():
            # Extract the enum name (e.g., TsBiomechanicalIndex.PelvisTilt -> "PelvisTilt")
            field_name = key.name if hasattr(key, 'name') else str(key)
            
            # Set the field if it exists in the dataclass
            if hasattr(dataclass_instance, field_name):
                setattr(dataclass_instance, field_name, value.value)
            else:
                print(f'Warning: Field "{field_name}" not found in dataclass')
    else:
        # Handle regular ctypes Structure
        for field in dataclass_instance.__dataclass_fields__.keys():
            if hasattr(ctypes_struct, field):
                setattr(dataclass_instance, field, getattr(ctypes_struct, field))
            else:
                print(f'Warning: Field "{field}" not found in ctypes structure')
    
    return dataclass_instance

def update_inplace(source, target_dataclass):
    """
    Update dataclass in-place from ctypes Structure or dict.
    
    Handles nested structures, pointers, and automatic timestamp propagation.
    
    Args:
        source: ctypes Structure, dict of structures, or field mappings
        target_dataclass: Dataclass instance to update in-place
    """
    
    def _extract_field_name(key):
        """Extract clean field name from various key types (including enums)"""
        if hasattr(key, "name"):  # Handle enum keys
            return key.name
        return str(key)
    
    def _extract_value(value):
        """Extract actual value from ctypes objects"""
        # Check if it's a ctypes value with a .value attribute
        if hasattr(value, 'value') and not isinstance(value, Structure):
            return value.value
        return value
    
    def _update_single_field(struct_value, dataclass_value, field_name):
        """Update a single field, handling nested structures"""
        # Extract the actual value from ctypes objects
        struct_value = _extract_value(struct_value)
        
        # Handle pointer to structure
        pointee_type = getattr(type(struct_value), "_type_", None)
        if pointee_type and issubclass(pointee_type, Structure):
            if bool(struct_value):
                if is_dataclass(dataclass_value):
                    update_inplace(struct_value.contents, dataclass_value)
                else:
                    setattr(target_dataclass, field_name, struct_value.contents)
            else:
                setattr(target_dataclass, field_name, None)
            return True
        
        # Handle nested structure -> nested dataclass
        if isinstance(struct_value, Structure) and is_dataclass(dataclass_value):
            update_inplace(struct_value, dataclass_value)
            return True
        
        # Direct assignment for simple types
        setattr(target_dataclass, field_name, struct_value)
        return True
    
    # Dictionary mode: iterate through bone_id -> structure mappings
    if isinstance(source, dict):
        latest_timestamp = None
        
        for bone_id, structure in source.items():
            # Map bone_id to dataclass field name (handle enum keys)
            field_name = _extract_field_name(bone_id)
            
            # Extract timestamp for later propagation (extract the actual value from ctypes)
            if hasattr(structure, "timestamp"):
                latest_timestamp = _extract_value(structure.timestamp)
            
            if hasattr(target_dataclass, field_name):
                target_field = getattr(target_dataclass, field_name)
                
                # Handle Structure objects
                if isinstance(structure, Structure):
                    if is_dataclass(target_field):
                        update_inplace(structure, target_field)
                    else:
                        setattr(target_dataclass, field_name, structure)
                else:
                    # Handle simple ctypes values or primitives
                    extracted_value = _extract_value(structure)
                    setattr(target_dataclass, field_name, extracted_value)
        
        # Propagate timestamp to top-level dataclass
        if latest_timestamp is not None and hasattr(target_dataclass, 'timestamp'):
            target_dataclass.timestamp = latest_timestamp
        return
    
    # Single structure mode: field-by-field mapping
    if isinstance(source, Structure):
        if not is_dataclass(target_dataclass):
            raise TypeError(f"Target must be dataclass, got {type(target_dataclass)}")
        
        # Get available ctypes fields
        source_fields = {name for name, _ in getattr(source, "_fields_", [])}
        
        # Update matching dataclass fields
        for field_info in fields(target_dataclass):
            field_name = field_info.name
            if field_name not in source_fields:
                continue
            
            source_value = getattr(source, field_name)
            target_value = getattr(target_dataclass, field_name)
            
            _update_single_field(source_value, target_value, field_name)
        return
    
    # Invalid input type
    raise TypeError(f"Source must be ctypes.Structure or dict, got {type(source)}")

def init_HeartRateData():
    """Create HeartRateData with default values."""
    return data_types.HeartRateData(
        heart_rate=0,
        is_heart_rate_valid=False,
        timestamp=0,
    )

def init_HRVData():
    """Create HRVData with default values."""
    return data_types.HRVData(
        hrv=0.0,
        mean_rr=0.0,
        sdnn=0.0,
        sdsd=0.0,
        rmssd=0.0,
        sd1=0.0,
        sd2=0.0,
        hlf=0.0,
    )

def init_RawPPGData():
    """Create RawPPGData with empty sample lists."""
    return data_types.RawPPGData(
        ir_data=[],
        red_data=[],
        blue_data=[],
        green_data=[],
    )

def init_all_dataclasses():
    """Create all dataclass types with default values. Returns dict of instances."""
    return {
        'UtilityMessage': init_UtilityMessage(),
        'ControlMessage': init_ControlMessage(),
        'EmsData': init_EmsData(),
        'EMSCalibrationData': init_EMSCalibrationData(),
        'StepDetectorData': init_StepDetectorData(),
        'BiomechanicalData': init_BiomechanicalData(),
        'RawData': init_RawData(),
        'ProcessedData': init_ProcessedData(),
        'HeartRateData': init_HeartRateData(),
        'HRVData': init_HRVData(),
        'RawPPGData': init_RawPPGData(),
    }

def flatten_structure(obj):
    """Flatten a single ctypes Structure into a dictionary."""
    result = {}
    if hasattr(obj, '_fields_'):
        for field_name, field_type in obj._fields_:
            value = getattr(obj, field_name)
            if hasattr(value, '_fields_'):  # Nested Structure
                nested = flatten_structure(value)
                for a, b in nested.items():
                    result[f'{field_name}_{a}'] = b
            else:
                result[field_name] = value
    return result

def flatten_dict(obj_dict):
    """Flatten dict of ctypes Structures to single-level dict."""
    result = {}
    
    for key in obj_dict.keys():
        obj = obj_dict[key]
        if hasattr(obj, '_fields_'):
            nested = flatten_structure(obj)
            for field_name, value in nested.items():
                result[f'{key}_{field_name}'] = value
        else:
            result[key] = obj
    
    return result

def write_calibration_to_csv(dataclass, filename=None):
    """Write calibration data to timestamped CSV file."""
    flattened_data = flatten_dict(dataclass)
    if filename is None:
        filename = f'test_data_{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.csv'
    else:
        filename = filename+f'{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.csv'
    
    with open(filename, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=flattened_data.keys())
        writer.writeheader()
        writer.writerow(flattened_data)
        file.close()
    print(f"Dataclass written to {filename}")

    