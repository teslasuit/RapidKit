# SPDX-License-Identifier: MIT
"""
Data adapter for GUI shared-memory polling.

Encapsulates SharedRingBuffer connection, auto-reconnect, and rolling
deque buffers so widgets never need to touch IPC details directly.
"""

import time
import numpy as np
from collections import deque
from typing import Dict, Deque, Optional, List

from ..ipc.buffer import SharedRingBuffer


class DataAdapter:
    """Manages shared-memory polling and rolling data buffers for GUI widgets.

    Features:
        - Auto-reconnect on every poll tick (non-blocking)
        - Configurable field list — only buffers fields the app actually uses
        - Fixed-size deques for O(1) rolling windows
        - Exposes numpy arrays for direct pyqtgraph consumption

    Args:
        buffer_name: Shared memory identifier (must match backend writer)
        frame_dtype: numpy dtype describing each frame
        fields: List of field names to buffer (must exist in frame_dtype).
                Omitted fields are ignored during update.
        max_points: Rolling window length (default 150 ≈ 1.5 s at 100 Hz)
        capacity: SharedRingBuffer slot count (must match backend)
    """

    def __init__(
        self,
        buffer_name: str,
        frame_dtype,
        fields: List[str],
        max_points: int = 150,
        capacity: int = 1000,
    ):
        self._buffer_name = buffer_name
        self._frame_dtype = frame_dtype
        self._capacity = capacity
        self._buffer: Optional[SharedRingBuffer] = None
        self._connected = False

        self.max_points = max_points
        self.start_time = time.time()
        self.time_buffer: Deque[float] = deque(maxlen=max_points)

        # One deque per requested field
        self.fields = list(fields)
        self.buffers: Dict[str, Deque[float]] = {
            f: deque(maxlen=max_points) for f in self.fields
        }

    # ── Connection ────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self, max_attempts: int = 3) -> bool:
        """Try to attach to the backend's shared memory buffer.

        Args:
            max_attempts: Number of retries with 100 ms sleep between.
        """
        for _ in range(max_attempts):
            try:
                self._buffer = SharedRingBuffer(
                    dtype=self._frame_dtype,
                    capacity=self._capacity,
                    name=self._buffer_name,
                    create=False,
                )
                self._connected = True
                return True
            except FileNotFoundError:
                time.sleep(1)
            except Exception:
                time.sleep(1)
        return False

    def _try_reconnect(self):
        """Single non-blocking reconnect attempt (called every poll tick)."""
        try:
            self._buffer = SharedRingBuffer(
                dtype=self._frame_dtype,
                capacity=self._capacity,
                name=self._buffer_name,
                create=False,
            )
            self._connected = True
        except Exception:
            pass

    # ── Polling ───────────────────────────────────────────────────

    def poll(self):
        """Read the latest frame and append values to rolling buffers.

        Call this once per GUI tick (~30 Hz). If the buffer is not
        connected, a silent reconnect is attempted automatically.
        """
        if not self._connected or self._buffer is None:
            self._try_reconnect()
            return

        try:
            frame = self._buffer.read_latest_frame()
            if frame is None:
                return

            self.time_buffer.append(time.time() - self.start_time)

            field_names = (
                frame.dtype.names
                if hasattr(frame.dtype, "names") and frame.dtype.names
                else []
            )

            for field in self.fields:
                if field in field_names:
                    try:
                        value = frame[field]
                        self.buffers[field].append(self._to_float(value))
                    except Exception:
                        self._append_last_or_zero(field)
                else:
                    self._append_last_or_zero(field)

        except Exception:
            # Buffer may have been destroyed — mark disconnected
            self._connected = False

    # ── Public accessors ──────────────────────────────────────────

    def get_time(self) -> np.ndarray:
        """Time array for plotting (seconds since start)."""
        return np.array(self.time_buffer)

    def get(self, field: str) -> Optional[np.ndarray]:
        """Return rolling array for *field*, or ``None`` if unknown."""
        buf = self.buffers.get(field)
        if buf is None:
            return None
        return np.array(buf)

    @property
    def has_data(self) -> bool:
        return self._connected and len(self.time_buffer) > 0

    def cleanup(self):
        """Release shared memory handle."""
        if self._buffer is not None:
            try:
                self._buffer.cleanup_shared_memory()
            except Exception:
                pass
            self._connected = False

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _to_float(value) -> float:
        if isinstance(value, (np.integer, np.floating)):
            return float(value)
        if isinstance(value, np.ndarray):
            return float(value.item()) if value.size == 1 else float(value[0])
        return float(value)

    def _append_last_or_zero(self, field: str):
        buf = self.buffers[field]
        buf.append(buf[-1] if len(buf) > 0 else 0.0)
