# SPDX-License-Identifier: MIT
"""
LSL Inlet — Receive data from external LSL streams.

Provides non-blocking pull for use in the real-time control loop (100 Hz).
External devices (force plates, EEG, optical trackers) publish data via LSL;
this module receives it and makes it available to the control strategy.

Tasks: T2.9 (Full LSL Integration), T2.11 (External Device Input)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pylsl

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExternalSample:
    """A single sample received from an external input source.

    Attributes:
        data: Channel values. Type depends on the source stream format:
              ``list[float]`` for LSL numeric streams (cf_float32, cf_double64),
              ``list[int]`` for LSL integer streams (cf_int8/16/32),
              ``list[str]`` for LSL string streams (cf_string),
              or any list type from a custom :class:`ExternalInputAdapter`.
        timestamp: LSL timestamp (``pylsl.local_clock()`` domain).
        stream_name: Source stream / adapter name.
        channel_count: Number of channels in ``data``.
        channel_names: Optional list of channel labels (populated from
            LSL stream metadata when available).
    """
    data: list
    timestamp: float
    stream_name: str
    channel_count: int
    channel_names: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract base for non-LSL devices (T2.11)
# ---------------------------------------------------------------------------

class ExternalInputAdapter(ABC):
    """Base class for non-LSL external input sources.

    Implement this when the external device cannot publish LSL.
    The adapter must expose the same non-blocking ``pull_latest()``
    contract so it can be registered with :class:`ExternalInputManager`.

    Example::

        class MySerialAdapter(ExternalInputAdapter):
            def __init__(self, port: str):
                self._serial = serial.Serial(port, 115200)
                self._last: Optional[ExternalSample] = None

            @property
            def stream_name(self) -> str:
                return "MySerialDevice"

            def pull_latest(self) -> Optional[ExternalSample]:
                if self._serial.in_waiting:
                    raw = self._serial.readline()
                    values = [float(v) for v in raw.split(b',')]
                    self._last = ExternalSample(
                        data=values,
                        timestamp=pylsl.local_clock(),
                        stream_name=self.stream_name,
                        channel_count=len(values),
                    )
                return self._last

            def close(self):
                self._serial.close()
    """

    @property
    @abstractmethod
    def stream_name(self) -> str:
        """Unique name identifying this input source."""
        ...

    @abstractmethod
    def pull_latest(self) -> Optional[ExternalSample]:
        """Non-blocking pull of the most recent sample.

        Must return immediately (no blocking waits).
        Return ``None`` only if no data has *ever* been received.
        Otherwise return the last received sample (cached).
        """
        ...

    @abstractmethod
    def close(self):
        """Release hardware / connection resources."""
        ...


# ---------------------------------------------------------------------------
# LSL Inlet
# ---------------------------------------------------------------------------

class LSLInlet:
    """Receives data from a single external LSL stream.

    Connects to an LSL stream by name (and optionally type).
    Provides non-blocking pull for use in the real-time control loop.

    Usage::

        inlet = LSLInlet("ForcePlate_GRF", stream_type="Force")
        # ... in loop:
        sample = inlet.pull_latest()
        if sample is not None:
            ground_reaction_force = sample.data[2]  # Fz channel
    """

    def __init__(self, stream_name: str, stream_type: Optional[str] = None,
                 timeout: float = 5.0):
        """Resolve and connect to an LSL stream.

        Args:
            stream_name: Name of the LSL stream to connect to.
            stream_type: Optional type filter (e.g. ``"EEG"``, ``"Force"``).
            timeout: How long to wait for stream discovery (seconds).

        Raises:
            TimeoutError: If the stream is not found within *timeout*.
        """
        self._stream_name = stream_name
        self._stream_type = stream_type
        self._inlet: Optional[pylsl.StreamInlet] = None
        self._channel_count: int = 0
        self._channel_names: list[str] = []
        self._last_sample: Optional[ExternalSample] = None

        self._connect(timeout)

    # --- Properties ----------------------------------------------------------

    @property
    def stream_name(self) -> str:
        return self._stream_name

    @property
    def is_connected(self) -> bool:
        return self._inlet is not None

    @property
    def channel_count(self) -> int:
        return self._channel_count

    @property
    def channel_names(self) -> list[str]:
        return self._channel_names

    # --- Connection ----------------------------------------------------------

    def _connect(self, timeout: float):
        """Resolve the stream on the network and create an inlet."""
        if self._stream_type:
            predicate = f"name='{self._stream_name}' and type='{self._stream_type}'"
        else:
            predicate = f"name='{self._stream_name}'"

        logger.info("LSLInlet: Resolving stream '%s' (timeout=%.1fs)…",
                     self._stream_name, timeout)
        streams = pylsl.resolve_bypred(predicate, minimum=1, timeout=timeout)

        if not streams:
            raise TimeoutError(
                f"LSLInlet: Stream '{self._stream_name}' not found within "
                f"{timeout}s. Ensure the external device is running and publishing."
            )

        info = streams[0]
        self._channel_count = info.channel_count()
        self._inlet = pylsl.StreamInlet(info, max_buflen=1)  # 1-second buffer

        # Try to read channel labels from stream metadata
        self._channel_names = self._read_channel_names(info)

        logger.info("LSLInlet: Connected to '%s' (%d channels, %.1f Hz)",
                     info.name(), self._channel_count, info.nominal_srate())

    @staticmethod
    def _read_channel_names(info: pylsl.StreamInfo) -> list[str]:
        """Extract channel labels from LSL stream XML metadata."""
        names: list[str] = []
        desc = info.desc()
        channels_node = desc.child("channels")
        if channels_node.empty():
            return names
        ch = channels_node.child("channel")
        while not ch.empty():
            label = ch.child_value("label")
            names.append(label if label else f"ch_{len(names)}")
            ch = ch.next_sibling("channel")
        return names

    # --- Data pull -----------------------------------------------------------

    def pull_latest(self) -> Optional[ExternalSample]:
        """Non-blocking pull of the most recent sample.

        Drains all buffered samples and keeps only the last one so the
        control strategy always receives the freshest data available.

        Returns:
            :class:`ExternalSample` if data has ever been received,
            ``None`` otherwise.

        Note:
            Uses ``timeout=0.0`` — never blocks the 100 Hz loop.
            On error the last cached sample is returned.
        """
        if not self._inlet:
            return None

        sample = None
        timestamp = None
        try:
            while True:
                s, t = self._inlet.pull_sample(timeout=0.0)
                if s is None:
                    break  # Buffer empty
                sample = s
                timestamp = t
        except pylsl.LostError:
            logger.warning("LSLInlet '%s': stream lost", self._stream_name)
            return self._last_sample
        except Exception:
            logger.exception("LSLInlet '%s': error during pull", self._stream_name)
            return self._last_sample

        if sample is not None:
            self._last_sample = ExternalSample(
                data=sample,
                timestamp=timestamp,
                stream_name=self._stream_name,
                channel_count=self._channel_count,
                channel_names=self._channel_names,
            )

        return self._last_sample

    # --- Cleanup -------------------------------------------------------------

    def close(self):
        """Close the inlet connection."""
        if self._inlet:
            del self._inlet
            self._inlet = None
            logger.info("LSLInlet '%s': closed", self._stream_name)


# ---------------------------------------------------------------------------
# External Input Manager
# ---------------------------------------------------------------------------

class ExternalInputManager:
    """Manages multiple external input streams (LSL and custom adapters).

    Registered inputs are polled each cycle and their data is passed to
    the control strategy as a dictionary.

    Usage::

        manager = ExternalInputManager()
        manager.add("ForcePlate_GRF", stream_type="Force")
        manager.add("EEG_Alpha", stream_type="EEG")

        # Non-LSL device:
        manager.add_custom(MySerialAdapter(port="COM3"))

        # In the loop:
        external_data = manager.pull_all()
        # external_data == {
        #     "ForcePlate_GRF": ExternalSample(…),
        #     "EEG_Alpha": ExternalSample(…) or None,
        #     "MySerialDevice": ExternalSample(…) or None,
        # }
    """

    MAX_INPUTS = 2   # soft upper limit

    def __init__(self):
        # Unified dict: name → (LSLInlet | ExternalInputAdapter)
        self._inputs: Dict[str, LSLInlet | ExternalInputAdapter] = {}

    # --- Registration --------------------------------------------------------

    def add(self, stream_name: str, stream_type: Optional[str] = None,
            timeout: float = 5.0):
        """Register an external LSL stream as an input source.

        Args:
            stream_name: Name of the LSL stream.
            stream_type: Optional type filter.
            timeout: Stream discovery timeout (seconds).

        Raises:
            ValueError: If ``MAX_INPUTS`` already registered.
            TimeoutError: If stream not found.
        """
        self._check_capacity()
        inlet = LSLInlet(stream_name, stream_type, timeout)
        self._inputs[stream_name] = inlet

    def add_custom(self, adapter: ExternalInputAdapter):
        """Register a non-LSL external input adapter.

        Args:
            adapter: An instance of :class:`ExternalInputAdapter`.

        Raises:
            ValueError: If ``MAX_INPUTS`` already registered or name conflicts.
        """
        self._check_capacity()
        name = adapter.stream_name
        if name in self._inputs:
            raise ValueError(f"Input '{name}' is already registered")
        self._inputs[name] = adapter

    def remove(self, stream_name: str):
        """Remove and close an input source."""
        source = self._inputs.pop(stream_name, None)
        if source is not None:
            source.close()

    # --- Polling -------------------------------------------------------------

    def pull_all(self) -> Dict[str, Optional[ExternalSample]]:
        """Pull latest data from all registered inputs.

        Returns:
            Dict mapping stream name → :class:`ExternalSample` (or ``None``
            if no data has ever been received for that source).
        """
        return {
            name: source.pull_latest()
            for name, source in self._inputs.items()
        }

    # --- Utilities -----------------------------------------------------------

    @property
    def registered_streams(self) -> List[str]:
        """Names of all registered input streams."""
        return list(self._inputs.keys())

    def close_all(self):
        """Close all input connections."""
        for source in self._inputs.values():
            source.close()
        self._inputs.clear()

    def _check_capacity(self):
        if len(self._inputs) >= self.MAX_INPUTS:
            raise ValueError(
                f"Maximum {self.MAX_INPUTS} external inputs supported "
                f"(currently {len(self._inputs)} registered)"
            )

    # --- Context manager -----------------------------------------------------

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all()
