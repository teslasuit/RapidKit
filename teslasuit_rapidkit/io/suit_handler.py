# SPDX-License-Identifier: MIT
"""
Teslasuit hardware interface for mocap, haptic, and FES control.

SuitHandler manages the single hardware connection to a Teslasuit device and
exposes subsystem references (haptic, mocap, PPG) and the MuscleMap.

This is the thin hardware layer. Data acquisition and the three-phase cycle
(collect → process → distribute) live in DataStreamer.
"""
from pathlib import Path
from typing import List

from teslasuit_sdk import ts_api
from ..data.types import CustomPlayable
from ..muscle_map import MuscleMap


class SuitHandler:
    """
    Hardware interface for Teslasuit device communication.

    Establishes a single connection to the Teslasuit and provides access to
    its subsystems. Used by DataStreamer (for sensor data) and Stimulator
    (for EMS output via ``self.muscle_map``).

    Attributes:
        api:            TsApi instance
        suit:           Connected suit device
        layout:         Haptic/electric channel layout
        bones:          Bone structure list from SDK mapper
        muscle_map:     MuscleMap — semantic name → resolved channel IDs (T2.5)
        haptic:      Haptic/electrical stimulation subsystem
        streamer:    Motion capture subsystem
        ppg:         Photoplethysmography subsystem (may be absent on some suits)
    """

    def __init__(self, muscle_map_config: str = None):
        """Initialize Teslasuit connection, subsystems, and MuscleMap.

        Args:
            muscle_map_config: Path to muscle map JSON config file.
                               Defaults to the Teslasuit 4.x layout
                               (``rapidkit/config/muscle_map_4R.json``);
                               an XR5 config can be passed in to switch hardware.
        """
        if muscle_map_config is None:
            muscle_map_config = str(
                Path(__file__).resolve().parent.parent / "config" / "muscle_map_4R.json"
            )

        # Initialize SDK
        self.api = ts_api.TsApi()
        self.asset_manager = self.api.asset_manager
        self.device_manager = self.api.get_device_manager()
        self.suit = self.device_manager.get_or_wait_last_device_attached()
        print('Suit is connected.')

        # Subsystem references (single connection)
        self.haptic = self.suit.haptic
        self.streamer = self.suit.mocap
        self.ppg = self.suit.ppg

        # Resolve bone layout, then build semantic muscle map
        self.layout = self.api.mapper.get_haptic_electric_channel_layout(
            self.suit.get_mapping()
        )
        self.bones = self.api.mapper.get_layout_bones(self.layout)
        self.muscle_map = MuscleMap(muscle_map_config, self.api, self.layout, self.bones)


    # ── Hardware Control Methods ──────────────────────────────────

    def mocap_calibrate_skeleton(self):
        """Calibrate mocap skeleton."""
        self.streamer.calibrate_skeleton()

    def get_raw_snapshot(self):
        """Capture a raw IMU data snapshot from all body segments."""
        return self.streamer.get_raw_data_on_ready()

    def haptic_play_touch(self, playable):
        """Play haptic feedback pattern.

        Args:
            playable: Haptic asset or pattern to execute
        """
        self.haptic.play_touch(playable)

    def stop_player(self):
        """Stop haptic player (safe to call even if the player was never initialized)."""
        print('Stop player')
        try:
            self.haptic.stop_player()
        except Exception:
            pass

    def start_mocap_streaming(self):
        """Start mocap data streaming."""
        self.streamer.start_streaming()

    def stop_mocap_streaming(self):
        """Stop mocap data streaming."""
        self.streamer.stop_streaming()

    def start_ppg_streaming(self):
        """Start PPG raw + processed data streaming.

        Uses ``start_raw_streaming()`` which subscribes to both processed
        (heart rate) and raw (photodiode) callbacks internally.
        """
        self.ppg.start_raw_streaming()

    def stop_ppg_streaming(self):
        """Stop PPG data streaming (safe to call even if PPG was never started)."""
        try:
            self.ppg.stop_raw_streaming()
        except Exception:
            pass

    # ── Custom haptic library factories ──────────────────────────────
    #
    # Build CustomPlayable slots for a HapticLibrary. Both factories
    # leave the playable muted; LibraryStimulator unmutes/fires it from
    # the engine loop based on the slot's ``IsMuted`` field.

    def load_haptic_asset(self, file_path: str, looped: bool = False) -> CustomPlayable:
        """Load a pre-recorded haptic asset and wrap it as a CustomPlayable.

        For ``looped=True`` the SDK loops playback and the resulting
        playable is pre-armed (``play_playable`` called, currently muted)
        so ``LibraryStimulator`` only needs to toggle the mute state.
        For ``looped=False`` (default) the asset plays once per
        ``play_playable`` call — ``LibraryStimulator`` re-fires it on
        every mute→unmute edge.

        Args:
            file_path: Path to the ``.hpt`` asset file.
            looped:    Whether the SDK should loop the asset (default False).

        Returns:
            CustomPlayable with a positive ``playable_id`` and ``IsMuted=True``.
        """
        asset_id = self.asset_manager.load_asset_from_path(file_path)
        sdk_id = self.haptic.create_playable(asset_id, is_looped=looped)
        playable_id = int(sdk_id.value) if hasattr(sdk_id, "value") else int(sdk_id)
        # NOTE: the playable is intentionally NOT started here. On this SDK
        # build, ``set_playable_muted(id, True)`` is silently ignored when
        # the playable hasn't yet been played, and ``play_playable`` always
        # starts in the unmuted state — so any "pre-arm muted, then play"
        # sequence ends up audibly firing at startup. ``LibraryStimulator``
        # starts the playable lazily on the first mute→unmute edge instead.
        return CustomPlayable(playable_id=playable_id, IsMuted=True, is_looped=looped)

    def create_haptic_touch(
        self,
        bone_id: int,
        channel_list: List[int],
        period: float,
        amplitude: int,
        pulse_width: int,
        duration: int = 100,
    ) -> CustomPlayable:
        """Build a looped EMS-parameter touch on the given bone/channels.

        The playable is created, marked looped, muted, and started — so
        ``LibraryStimulator`` only needs to toggle ``set_playable_muted``
        each time the strategy flips ``slot.IsMuted``. Mirrors the
        creation pattern used by
        :class:`rapidkit.io.stimulator.Stimulator` for EMS muscles.

        ``duration`` only sets one iteration length (the playable is
        looped immediately after creation), so any positive integer works.

        Args:
            bone_id:       Index into ``self.bones`` selecting the target bone.
            channel_list:  Indices into the bone's channel list selecting
                           which channels of the bone to drive.
            period:        Stimulation period (μs).
            amplitude:     Stimulation amplitude (%).
            pulse_width:   Pulse width (μs).
            duration:      Single-iteration length in ms (default 100).

        Returns:
            CustomPlayable with a positive ``playable_id``, ``IsMuted=True``,
            ``is_looped=True``.
        """
        bone_contents = self.api.mapper.get_bone_contents(self.bones[bone_id])
        channel_ids = [
            c.value if hasattr(c, 'value') else c
            for c in (bone_contents[i] for i in channel_list)
        ]
        sdk_params = self.haptic.create_touch_parameters(
            int(period), int(amplitude), int(pulse_width),
        )
        sdk_id = self.haptic.create_touch(sdk_params, channel_ids, duration)
        playable_id = int(sdk_id.value) if hasattr(sdk_id, "value") else int(sdk_id)
        self.haptic.set_playable_looped(playable_id, True)
        # Intentionally NOT calling ``play_playable`` here — see the note in
        # ``load_haptic_asset``. The SDK ignores ``set_playable_muted(True)``
        # on a not-yet-playing playable, and ``play_playable`` itself always
        # starts in the unmuted state, so any pre-arm sequence fires audibly
        # at startup. ``LibraryStimulator`` starts the playable lazily on
        # the first mute→unmute edge from the strategy.
        return CustomPlayable(playable_id=playable_id, IsMuted=True, is_looped=True)
