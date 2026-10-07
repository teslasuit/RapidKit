# SPDX-License-Identifier: MIT
"""
MuscleMap — Semantic Muscle-to-Hardware-Channel Mapping

Two-layer design:
  Layer 1: JSON config file (bone_index + channel_slice per muscle, one file per hardware version)
  Layer 2: MuscleMap runtime class (loads config, resolves to actual SDK channel IDs at connection time)

Consumers:
  SuitHandler  — replaces hardcoded _build_channel_map() bone-index magic
  Stimulator   — muscle_map.get_channels(name) replaces suit.channels[muscle] dict
  ControlStrategyBase — self.muscles is a MuscleMap instance; provides by_side / by_region queries
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class MuscleInfo:
    """Resolved hardware information for a single muscle group.

    Attributes:
        name:                  Semantic name, e.g. ``"quadriceps_left"``
        channel_ids:           Resolved Teslasuit SDK channel ID list
        side:                  ``"left"`` or ``"right"``
        body_region:           ``"upper_leg"``, ``"lower_leg"``, ``"hip"``, etc.
        default_period_us:      Default stimulation period in microseconds
        default_amplitude_pct:  Default stimulation amplitude (0-100 %)
        default_pulse_width_us: Default pulse width in microseconds (0-100)
    """
    name: str
    channel_ids: list
    side: str
    body_region: str
    default_period_us: int
    default_amplitude_pct: int
    default_pulse_width_us: int


class MuscleMap:
    """Semantic muscle-to-hardware-channel mapping.

    Loads a JSON config file and resolves bone indices + channel slices
    into actual Teslasuit SDK channel IDs at construction time (i.e. when the
    suit is already connected and ``api.mapper`` is available).

    Config files live in ``teslasuit_rapidkit/config/``. The framework supports
    Teslasuit 4.x and XR5 via per-version JSON configs:
      - ``muscle_map_4R.json``  — Teslasuit 4.x family (ships with the package)
      - ``muscle_map_XR5.json`` — Teslasuit XR5 (provided alongside as needed)

    Usage::

        muscle_map = MuscleMap("teslasuit_rapidkit/config/muscle_map_4R.json", api, layout, bones)
        channels = muscle_map.get_channels("quadriceps_left")   # -> [14, 15, 16]
        info     = muscle_map["quadriceps_left"]                # -> MuscleInfo(...)
        left_leg = muscle_map.by_side("left")                   # -> [MuscleInfo, ...]
        upper    = muscle_map.by_region("upper_leg")            # -> [MuscleInfo, ...]

    Iteration yields :class:`MuscleInfo` objects in config-file order::

        for muscle_info in muscle_map:
            print(muscle_info.name, muscle_info.channel_ids)

    Args:
        config_path: Path to the JSON muscle map config file.
        api:         Teslasuit ``ts_api.TsApi()`` instance (for ``api.mapper`` access).
        layout:      Haptic/electric channel layout from ``api.mapper.get_haptic_electric_channel_layout()``.
        bones:       Bone list from ``api.mapper.get_layout_bones(layout)``.
    """

    def __init__(self, config_path: str, api, layout, bones):
        self._muscles: dict[str, MuscleInfo] = {}
        self._api = api
        self._bones = bones

        with open(config_path, 'r') as f:
            config = json.load(f)

        self.hardware_version: str = config.get("hardware_version", "unknown")

        for muscle_name, spec in config["muscles"].items():
            raw_channels = []
            for bone_spec in spec["channels"]:
                raw_channels.extend(
                    self._resolve_bone_channels(api, bones, bone_spec)
                )

            channel_ids = [
                c.value if hasattr(c, 'value') else c
                for c in raw_channels
            ]

            defaults = spec.get("stimulation_defaults", {})

            self._muscles[muscle_name] = MuscleInfo(
                name=muscle_name,
                channel_ids=channel_ids,
                side=spec.get("side", "unknown"),
                body_region=spec.get("body_region", "unknown"),
                default_period_us=defaults.get("period_us", 20000),
                default_amplitude_pct=defaults.get("amplitude_pct", 0),
                default_pulse_width_us=defaults.get("pulse_width_us", 80),
            )

    @staticmethod
    def _resolve_bone_channels(api, bones, bone_spec):
        """Resolve a single ``{bone_index, channel_slice}`` spec to raw SDK
        channel objects.

        ``channel_slice`` formats:
          - ``[i]``          — single bone channel ID *i*
          - ``[start, end]`` — Python slice ``bone_contents[start:end]``
          - ``[start, null]``— slice from *start* to end of bone
          - ``[i, j, k, …]`` (len > 2) — explicit list of bone channel IDs
        """
        bone_contents = api.mapper.get_bone_contents(
            bones[bone_spec["bone_index"]]
        )
        ch = bone_spec["channel_slice"]

        if len(ch) == 1:
            return [bone_contents[ch[0]]]
        if len(ch) == 2 and ch[1] is None:
            return list(bone_contents[ch[0]:])
        if len(ch) == 2:
            return list(bone_contents[ch[0]:ch[1]])
        return [bone_contents[i] for i in ch]

    # ── Mapping protocol ─────────────────────────────────────────────────────

    def __getitem__(self, muscle_name: str) -> MuscleInfo:
        """Return :class:`MuscleInfo` by semantic name. Raises ``KeyError`` if unknown."""
        return self._muscles[muscle_name]

    def __contains__(self, muscle_name: str) -> bool:
        return muscle_name in self._muscles

    def __iter__(self):
        """Iterate over :class:`MuscleInfo` objects in config-file order."""
        return iter(self._muscles.values())

    def __len__(self) -> int:
        return len(self._muscles)

    def __repr__(self) -> str:
        return f"MuscleMap(hardware={self.hardware_version!r}, muscles={self.list_muscles()})"

    # ── Query API ────────────────────────────────────────────────────────────

    def get_channels(self, muscle_name: str) -> list:
        """Return the resolved SDK channel ID list for *muscle_name*.

        Args:
            muscle_name: Semantic name, e.g. ``"quadriceps_left"``.

        Returns:
            List of integer channel IDs.

        Raises:
            KeyError: if *muscle_name* is not in the config.
        """
        return self._muscles[muscle_name].channel_ids

    def list_muscles(self) -> list[str]:
        """Return all available muscle names in config-file order."""
        return list(self._muscles.keys())

    def by_side(self, side: str) -> list[MuscleInfo]:
        """Return all muscles on *side* (``"left"`` or ``"right"``)."""
        return [m for m in self._muscles.values() if m.side == side]

    def by_region(self, region: str) -> list[MuscleInfo]:
        """Return all muscles in *region* (e.g. ``"upper_leg"``, ``"lower_leg"``, ``"hip"``)."""
        return [m for m in self._muscles.values() if m.body_region == region]
