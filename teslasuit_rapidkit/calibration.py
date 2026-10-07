# SPDX-License-Identifier: MIT
"""
MoCap Calibration API.

Exposes programmatic control over Teslasuit skeleton calibration:
trigger calibration and export the reference frame.

Usage::

    engine = ClosedLoopEngine(control_strategy=MyStrategy())

    result = engine.calibration.calibrate()
    if not result.success:
        sys.exit(f"Calibration failed: {result.message}")

    engine.calibration.export(path="./data")
    engine.run()
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CalibrationResult:
    """Result of a calibration attempt."""
    success: bool
    timestamp: float    # When calibration was performed (time.time())
    message: str = ""   # Human-readable status message


class CalibrationAPI:
    """
    Framework API for managing MoCap calibration.

    Exposed as ``engine.calibration`` on ``ClosedLoopEngine``.
    """

    def __init__(self, suit_handler) -> None:
        """
        Args:
            suit_handler: SuitHandler instance (provides SDK access)
        """
        self._suit = suit_handler
        self._is_calibrated: bool = False
        self._last_result: Optional[CalibrationResult] = None
        self._reference_frame_raw = None    # Raw SDK dict — used by export()

    # ── Properties ────────────────────────────────────────────────

    @property
    def is_calibrated(self) -> bool:
        """Whether calibration has been successfully performed this session."""
        return self._is_calibrated

    @property
    def last_result(self) -> Optional[CalibrationResult]:
        """Result from the most recent calibration attempt, or None."""
        return self._last_result

    # ── Public API ────────────────────────────────────────────────

    def calibrate(self) -> CalibrationResult:
        """
        Trigger skeleton calibration (blocking).

        The subject must be standing in I-pose when this is called.
        Waits for the SDK to complete calibration, then captures a raw
        IMU snapshot for export.

        Returns:
            CalibrationResult — success flag, timestamp, and status message
        """
        try:
            # Blocking SDK call — subject must be in I-pose
            self._suit.mocap_calibrate_skeleton()

            # Capture reference frame immediately after calibration
            self._reference_frame_raw = self._suit.get_raw_snapshot()

            self._is_calibrated = True
            self._last_result = CalibrationResult(
                success=True,
                timestamp=time.time(),
                message="Calibration completed successfully",
            )

        except Exception as exc:
            self._is_calibrated = False
            self._last_result = CalibrationResult(
                success=False,
                timestamp=time.time(),
                message=f"Calibration failed: {exc}",
            )

        return self._last_result

    def export(self, path: str, filename_prefix: str = "calibration_") -> None:
        """
        Save the calibration reference frame to a timestamped CSV file.

        Args:
            path: Directory to save the file
            filename_prefix: Prefix for the output filename (timestamp appended)

        Raises:
            RuntimeError: If calibrate() has not been called successfully
        """
        if not self._is_calibrated or self._reference_frame_raw is None:
            raise RuntimeError("Cannot export: calibration has not been performed")

        from .data.init_utils import write_calibration_to_csv
        write_calibration_to_csv(
            self._reference_frame_raw,
            filename=os.path.join(path, filename_prefix),
        )
