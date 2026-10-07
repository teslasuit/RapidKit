# SPDX-License-Identifier: MIT
"""
EMS Stimulator — one looped playable per muscle, rebuilt on parameter change.

Resolves semantic muscle names to hardware channels via
``SuitHandler.muscle_map`` and keeps exactly one active Teslasuit haptic
playable per muscle. The playable is marked ``looped`` so continuous
stimulation does not need per-cycle re-arming. When the controller
produces new ``(Period, Amplitude, PulseWidth)`` values, the stimulator
creates a fresh looped playable with those params, starts it, and then
**only removes (does not stop) the superseded playable**.

Why "remove, no stop": calling ``stop_playable`` on the just-superseded
id touches hardware channel state and was empirically observed to cause
audible/perceptible stim dropouts when the PID hunted at ~100 Hz. By the
time we call ``remove_playable(old_id)``, ``play_playable(new_id)`` has
already taken over those channels, so the old id is no longer driving
the hardware — ``remove_playable`` is then a registry-only delete and
does not glitch the live channel.

Per-cycle SDK cost at steady state:

* Muscle with params changing every cycle (elbow PID hunting):
  ``create_touch`` + ``play_playable`` + ``remove_playable`` = 3 calls.
* Muscle with stable params (steady-state window, PID saturated):
  **0** calls (the looped playable keeps running).
* Muscle muted: 0 calls.
* Mute / unmute edge: 1 ``set_playable_muted`` call.

The alternative multiplier-based design (``MultiplierStimulator``) is
preserved below as a fallback for future use — it has a cheaper hot path
(one ``set_playable_multipliers`` per param change instead of three
calls) but requires picking correct base values and unit conventions.

Data flow per cycle::

    BackendMainloop → stimulator.run_stimulator(suit_handler, ems_data)
      → for each muscle in suit.muscle_map:
          - if muted: toggle mute on edge, skip rest
          - if active & (no playable OR params changed):
              create new looped playable, play it, remove the old one
          - if active & params unchanged: nothing to do
"""

import logging

from ..data.types import EmsData, HapticLibrary

logger = logging.getLogger(__name__)

# Concrete duration passed to ``create_touch``. The playable is marked
# looped immediately after creation, so the value only affects the
# length of one iteration of the loop — any positive integer works.
_TOUCH_DURATION_MS: int = 100


class Stimulator:
    """EMS stimulation controller (option D: rebuild-on-change, looped).

    Maps semantic muscle names to Teslasuit SDK haptic channels via
    ``SuitHandler.muscle_map`` and keeps one looped playable per muscle.
    Parameter changes trigger a fresh ``create_touch`` + ``play_playable``
    + ``remove_playable(old)`` sequence. No ``stop_playable`` is ever
    called on the hot path — see the module docstring for the rationale.

    Usage::

        stimulator = Stimulator()
        # each cycle:
        stimulator.run_stimulator(suit_handler, ems_data)
    """

    def __init__(self):
        """Initialize stimulator with empty per-muscle caches."""
        # muscle name -> active Teslasuit playable ID (looped).
        self.playable_ids_dict: dict = {}
        # muscle name -> last (Period, Amplitude, PulseWidth) tuple that
        # was written to the SDK. Lets us skip rebuilding the playable
        # when the controller output is steady.
        self._last_params: dict = {}
        # muscle name -> last mute state written to the SDK. Lets us call
        # ``set_playable_muted`` only on edges.
        self._last_muted: dict = {}

    # ── Cycle method (called each iteration by BackendMainloop) ─────────────

    def run_stimulator(self, suit, ems_data: EmsData) -> None:
        """Drive EMS for one cycle.

        Single-pass over ``suit.muscle_map``. For each muscle:

        * If muted (or no EmsData entry): toggle mute on the edge and
          skip further SDK work.
        * If active and either (a) we've never built a playable for this
          muscle or (b) its params changed since the previous cycle:
          create a fresh looped playable, start it, then
          ``remove_playable`` the superseded one (no stop).
        * If active and params unchanged: no SDK calls.

        Args:
            suit:     SuitHandler — provides ``suit.muscle_map`` and
                      ``suit.haptic``.
            ems_data: Current EMS parameters (written by
                      ``ControlStrategy.process()``).
        """
        haptic = suit.haptic

        for muscle_info in suit.muscle_map:
            name = muscle_info.name
            muscle_data = getattr(ems_data, name, None)
            should_be_muted = (muscle_data is None) or bool(muscle_data.IsMuted)
            old_id = self.playable_ids_dict.get(name)

            if should_be_muted:
                # Pause on the edge only. We keep the playable around so a
                # later unmute with the same params can skip the create.
                # NOTE: set_playable_muted only zeroes volume metadata — the
                # SDK keeps streaming touch events to the hardware regardless.
                # set_playable_paused actually halts the loop iteration and is
                # the correct primitive for "stop without removing".
                if old_id is not None and not self._last_muted.get(name, True):
                    haptic.set_playable_paused(old_id, True)
                    self._last_muted[name] = True
                continue

            current_params = (
                int(muscle_data.Period),
                int(muscle_data.Amplitude),
                int(muscle_data.PulseWidth),
            )
            params_changed = current_params != self._last_params.get(name)

            if old_id is None or params_changed:
                # Build + start a fresh looped playable. play_playable
                # must come before remove_playable so the new asset has
                # taken over the channels by the time the old one is
                # released; otherwise there is a (tiny) gap where neither
                # is driving the channels.
                sdk_params = haptic.create_touch_parameters(*current_params)
                new_id = haptic.create_touch(
                    sdk_params, muscle_info.channel_ids, _TOUCH_DURATION_MS,
                )
                haptic.set_playable_looped(new_id, True)
                haptic.play_playable(new_id)

                # Release the superseded playable, registry-only.
                # remove_playable without a preceding stop_playable avoids
                # the hardware-channel glitch that stop caused when the
                # PID was hunting at ~100 Hz.
                if old_id is not None:
                    try:
                        haptic.remove_playable(old_id)
                    except Exception:  # pylint: disable=broad-except
                        logger.exception(
                            "Error removing superseded playable for %s", name,
                        )

                self.playable_ids_dict[name] = new_id
                self._last_params[name] = current_params
                self._last_muted[name] = False
            elif self._last_muted.get(name, True):
                # Params unchanged but we were paused — cheap resume.
                haptic.set_playable_paused(old_id, False)
                self._last_muted[name] = False


class LibraryStimulator:
    """Haptic playable runner driven by a :class:`HapticLibrary`.

    Iterates over ``CustomPlayable`` slots each cycle and acts only on
    edges (no SDK calls when state is steady).

    Per-cycle behaviour for each slot:

    * Multipliers — if any of ``(period_mult, amplitude_mult,
      pulse_width_mult)`` changed since the previous cycle, build a
      multiplier object via ``haptic.create_touch_multipliers`` and
      apply it via ``haptic.set_playable_multipliers``. Applied before
      any mute change so a one-shot fired on this same tick uses the
      new multipliers. Applied uniformly to looped and one-shot slots.
    * Mute edge:

        * ``is_looped=True``: each edge issues one ``set_playable_muted``.
          The playable is pre-armed by
          :meth:`SuitHandler.create_haptic_touch` /
          ``load_haptic_asset(..., looped=True)`` (created, looped,
          muted, played) so mute is the only toggle the runner needs.
        * ``is_looped=False`` (one-shot asset): mute→unmute edge fires
          ``play_playable``; unmute→mute edge is a no-op (the asset has
          already finished playing).

    Slots with ``playable_id <= 0`` are skipped (uninitialised).
    """

    def __init__(self) -> None:
        # playable_id -> last IsMuted value seen on the slot
        self._last_muted_by_id: dict[int, bool] = {}
        # playable_id -> last (period_mult, amplitude_mult, pulse_width_mult)
        # tuple written to the SDK. Missing key means "not yet set" and
        # forces a first-tick set_playable_multipliers call so the SDK
        # is brought into agreement with the slot's declared multipliers.
        self._last_multipliers_by_id: dict[int, tuple] = {}
        # Tracks looped playables that have already had ``play_playable``
        # called at least once. The SuitHandler factory leaves looped
        # playables created-but-not-playing because pre-arming muted is
        # unreliable on the current SDK; we play them lazily on the first
        # mute→unmute edge and toggle mute on subsequent edges.
        self._started_ids: set = set()

    def run_stimulator(self, suit, haptic_library: HapticLibrary) -> None:
        haptic = suit.haptic

        for _name, playable in haptic_library.iter_playables():
            playable_id = int(playable.playable_id)
            if playable_id <= 0:
                continue

            # 1. Multiplier edge — applied before any mute change so that
            # one-shots fired on the same tick pick up the new values.
            multipliers = (
                float(playable.period_mult),
                float(playable.amplitude_mult),
                float(playable.pulse_width_mult),
            )
            if multipliers != self._last_multipliers_by_id.get(playable_id):
                sdk_multipliers = haptic.create_touch_multipliers(*multipliers)
                haptic.set_playable_multipliers(playable_id, sdk_multipliers)
                self._last_multipliers_by_id[playable_id] = multipliers

            # 2. Mute edge.
            should_be_muted = bool(playable.IsMuted)
            last_muted = self._last_muted_by_id.get(playable_id, True)

            if should_be_muted == last_muted:
                continue

            if playable.is_looped:
                # First mute→unmute edge for a looped playable: the factory
                # left it created-but-not-playing (so it can't fire by
                # accident at startup). Start it now; the SDK plays new
                # playables in the unmuted/unpaused state, which is what
                # we want. Subsequent edges toggle PAUSE on the still-
                # running loop.
                #
                # We use ``set_playable_paused``, not ``set_playable_muted``:
                # on the current Teslasuit SDK build, ``muted`` only zeroes
                # the volume metadata but the underlying touch events keep
                # streaming to the wearer, so muting a looped touch does
                # not actually silence it. ``paused`` halts loop iteration
                # and is the correct primitive for "stop without removing".
                if not should_be_muted and playable_id not in self._started_ids:
                    haptic.play_playable(playable_id)
                    self._started_ids.add(playable_id)
                else:
                    haptic.set_playable_paused(playable_id, should_be_muted)
            elif not should_be_muted:
                # one-shot: mute→unmute edge fires the asset
                haptic.play_playable(playable_id)
            # one-shot mute edge: no-op (asset already finished)

            self._last_muted_by_id[playable_id] = should_be_muted


# ─────────────────────────────────────────────────────────────────────────
# Alternative implementation, preserved as a fallback.
# ─────────────────────────────────────────────────────────────────────────

# Reference base values used by MultiplierStimulator when creating each
# muscle's looped playable. Multipliers are computed as
# ``current_param / base``. Units: period in microseconds, amplitude in
# percent, pulse width in microseconds. Verify against your controller's
# output units before switching to this implementation.
_BASE_PERIOD_MKS: int = 10000  # 10 ms expressed in microseconds (μs / "mks")
_BASE_AMPLITUDE: int = 100     # percent
_BASE_PULSE_WIDTH_US: int = 100  # microseconds


class MultiplierStimulator:
    """EMS stimulation controller (option B: multiplier-based modulation).

    Creates exactly one looped playable per muscle on first encounter
    (at a fixed reference base) and modulates stimulation every cycle by
    calling ``set_playable_multipliers`` — an in-place parameter update
    that does not create, start, or stop anything.

    Hot-path cost: 1 async SDK call per muscle per param change, 0 when
    params are stable. Lower per-cycle cost than :class:`Stimulator`, but
    depends on picking base values in the correct unit system: if
    ``muscle_data.Period`` is in ms and ``_BASE_PERIOD_MKS`` is in μs,
    the effective period will be off by 1000×. Kept here as a fallback;
    switch by importing this class instead of ``Stimulator`` in
    ``teslasuit_rapidkit/engine.py``.
    """

    def __init__(self):
        self.playable_ids_dict: dict = {}
        self._last_multipliers: dict = {}
        self._last_muted: dict = {}

    def run_stimulator(self, suit, ems_data: EmsData) -> None:
        haptic = suit.haptic

        for muscle_info in suit.muscle_map:
            name = muscle_info.name
            muscle_data = getattr(ems_data, name, None)

            playable_id = self.playable_ids_dict.get(name)
            if playable_id is None:
                base_params = haptic.create_touch_parameters(
                    _BASE_PERIOD_MKS, _BASE_AMPLITUDE, _BASE_PULSE_WIDTH_US,
                )
                playable_id = haptic.create_touch(
                    base_params, muscle_info.channel_ids, _TOUCH_DURATION_MS,
                )
                haptic.set_playable_looped(playable_id, True)
                haptic.set_playable_muted(playable_id, True)
                haptic.play_playable(playable_id)
                self.playable_ids_dict[name] = playable_id
                self._last_multipliers[name] = None
                self._last_muted[name] = True

            should_be_muted = (muscle_data is None) or bool(muscle_data.IsMuted)

            if not should_be_muted:
                multipliers = (
                    float(muscle_data.Period) / _BASE_PERIOD_MKS,
                    float(muscle_data.Amplitude) / _BASE_AMPLITUDE,
                    float(muscle_data.PulseWidth) / _BASE_PULSE_WIDTH_US,
                )
                if multipliers != self._last_multipliers.get(name):
                    sdk_multipliers = haptic.create_touch_multipliers(*multipliers)
                    haptic.set_playable_multipliers(playable_id, sdk_multipliers)
                    self._last_multipliers[name] = multipliers

            if should_be_muted != self._last_muted.get(name):
                haptic.set_playable_muted(playable_id, should_be_muted)
                self._last_muted[name] = should_be_muted
