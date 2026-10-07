# SPDX-License-Identifier: MIT
"""FES Framework — Closed-loop functional electrical stimulation for Teslasuit."""
__version__ = "0.1.0"

from .engine import ClosedLoopEngine
from .calibration import CalibrationAPI, CalibrationResult
from .control.strategy_base import ControlStrategyBase
from .muscle_map import MuscleMap, MuscleInfo
from .data.types import (
    ControlMessage, UtilityMessage, EmsData, EMSParamData,
    EMSCalibrationData, EmsMultiplierData, BiomechanicalData,
    StepDetectorData, RawData, ProcessedData,
)
from .io.suit_handler import SuitHandler
from .io.data_streamer import DataStreamer
from .io.stimulator import Stimulator
from .io.lsl_streamer import LSLStreamer
from .io.lsl_inlet import LSLInlet, ExternalInputManager, ExternalInputAdapter
from .ipc.buffer import SharedRingBuffer
from .ipc.queue_handler import QueueHandler
