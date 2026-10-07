# SPDX-License-Identifier: MIT
"""
Closed-Loop FES Engine.

Generic main loop for closed-loop FES control.  The engine assembles all
standard backend components (SuitHandler, DataStreamer, Stimulator, LSLStreamer,
QueueHandler) automatically.  Only the control strategy — which is
user-specific — **must** be provided.

Advanced users can override any default component by passing it explicitly.

Loop timing is governed by the Teslasuit SDK's blocking data-ready calls
(~100 Hz).  There is no software-based frequency regulation — the hardware
IS the clock.  ``sample_rate`` is metadata used by LSL stream info and
diagnostics only.

The engine orchestrates a strict per-cycle data flow:
    1. Collect sensor data     (DataStreamer.run_cycle)
    2. Poll external inputs    (ExternalInputManager, if configured)
    3. Handle IPC messages     (QueueHandler, if configured)
    4. Execute control logic   (ControlStrategyBase.run_strategy)
    5. Output stimulation      (Stimulator.run_stimulator;
                                LibraryStimulator if strategy.haptic_library set)
    6. Stream via LSL          (LSLStreamer, if configured)
    7. Post-cycle hook         (on_cycle_complete, override for custom logic)

Subclass and override hooks (on_start, on_stop, on_cycle_complete,
on_utility_message, on_control_message) to add application-specific behavior.
"""
from __future__ import annotations

import logging

from .data.init_utils import (
    init_ControlMessage,
    init_EmsData,
    init_EMSCalibrationData,
    init_UtilityMessage,
)
from .calibration import CalibrationAPI
from .io.suit_handler import SuitHandler
from .io.data_streamer import DataStreamer
from .io.stimulator import Stimulator, LibraryStimulator
from .io.lsl_streamer import LSLStreamer

logger = logging.getLogger(__name__)

# Sentinel value placed on the utility queue to request graceful shutdown.
STOP_SENTINEL = "__STOP__"


class ClosedLoopEngine:
    """Closed-loop FES engine with auto-assembled backend components.

    By default, the engine creates all standard hardware and backend
    components internally.  Only the **control strategy** (your subclass
    of ``ControlStrategyBase``) must be provided.

    Any default component can be overridden by passing it explicitly
    (e.g. a custom ``DataStreamer`` subclass for signal filtering).

    Loop timing is governed entirely by the Teslasuit SDK (blocking
    ``get_*_on_ready`` calls at ~100 Hz).  ``sample_rate`` is metadata
    only — it does NOT regulate execution frequency.

    Attributes:
        suit_handler:       SuitHandler — hardware interface
        calibration:        CalibrationAPI — mocap calibration trigger and quality check
        data_streamer:      DataStreamer — three-phase sensor cycle
        control_strategy:   ControlStrategyBase — user control logic
        stimulator:         Stimulator — EMS output
        lsl_streamer:       LSLStreamer — LSL outlet manager
        external_inputs:    ExternalInputManager | None — external device inlets
        queue_handler:      QueueHandler | None — IPC message queues
        sample_rate:        float — nominal hardware rate (metadata for LSL/diagnostics)
        control_message:    ControlMessage — current control parameters
        utility_message:    UtilityMessage — current utility/system state
        ems_data:           EmsData — current stimulation output
        ems_calibration_data: EMSCalibrationData — calibration ranges
        cycle_count:        int — total cycles executed since run()

    Hooks (override in subclass):
        on_start()              — called once before the first cycle
        on_stop()               — called once after the loop exits
        on_utility_message(msg) — called when a new utility message arrives
        on_control_message(msg) — called when a new control message arrives
        on_cycle_complete()     — called at the end of every cycle

    Example (minimal headless usage — only strategy required)::

        engine = ClosedLoopEngine(control_strategy=MyStrategy())
        engine.run()

    Example (with custom DataStreamer and LSL enabled)::

        engine = ClosedLoopEngine(
            control_strategy=MyStrategy(),
            data_streamer=MyCustomStreamer(suit_handler),
            lsl_enabled=True,
        )
        engine.run()
    """

    def __init__(
        self,
        control_strategy,
        *,
        suit_handler=None,
        data_streamer=None,
        stimulator=None,
        lsl_streamer=None,
        lsl_enabled: bool = False,
        external_inputs=None,
        queue_handler=None,
        control_queue=None,
        utility_queue=None,
        sample_rate: float = 100.0,
    ):
        """Initialise the engine, auto-creating default components as needed.

        Only ``control_strategy`` is required.  All other components are
        created automatically unless explicitly provided.

        Args:
            control_strategy:  ControlStrategyBase subclass instance (REQUIRED)
            suit_handler:      SuitHandler override (default: auto-created)
            data_streamer:     DataStreamer override (default: auto-created with suit_handler)
            stimulator:        Stimulator override (default: auto-created)
            lsl_streamer:      LSLStreamer override (default: auto-created; see lsl_enabled)
            lsl_enabled:       Enable LSL outlet streaming (default False, GDPR).
                               Ignored if lsl_streamer is provided explicitly.
            external_inputs:   Optional ExternalInputManager for inlets
            queue_handler:     QueueHandler override (default: auto-created if queues given)
            control_queue:     Multiprocessing queue for control messages (GUI → Backend).
                               If provided (and queue_handler is None), a QueueHandler is created.
            utility_queue:     Multiprocessing queue for utility messages (bidirectional).
                               If provided (and queue_handler is None), a QueueHandler is created.
            sample_rate:       Nominal hardware rate in Hz — metadata only (default 100.0)
        """
        # ── Control strategy (required) ───────────────────────────
        self.control_strategy = control_strategy

        # ── Hardware interface ────────────────────────────────────
        self.suit_handler = suit_handler if suit_handler is not None else SuitHandler()

        # ── Calibration API ───────────────────────────────────────
        self.calibration = CalibrationAPI(self.suit_handler)

        # ── Data streamer ─────────────────────────────────────────
        if data_streamer is not None:
            self.data_streamer = data_streamer
        else:
            self.data_streamer = DataStreamer(self.suit_handler)

        # ── Stimulator ────────────────────────────────────────────
        if stimulator is not None:
            self.stimulator = stimulator
        else:
            self.stimulator = Stimulator()

        # ── Haptic library stimulator (no-op until strategy.haptic_library is set)
        self.library_stimulator = LibraryStimulator()

        # ── LSL streamer ──────────────────────────────────────────
        if lsl_streamer is not None:
            self.lsl_streamer = lsl_streamer
        else:
            self.lsl_streamer = LSLStreamer(
                sample_rate=sample_rate,
                enabled=lsl_enabled,
                ppg_available=self.data_streamer.ppg_available,
            )

        # ── Queue handler (IPC) ──────────────────────────────────
        if queue_handler is not None:
            self.queue_handler = queue_handler
        elif control_queue is not None or utility_queue is not None:
            from .ipc.queue_handler import QueueHandler
            self.queue_handler = QueueHandler(
                control_queue=control_queue, utility_queue=utility_queue,
            )
        else:
            self.queue_handler = None

        # ── External inputs ───────────────────────────────────────
        self.external_inputs = external_inputs

        # ── Metadata ──────────────────────────────────────────────
        self.sample_rate = sample_rate

        # ── Framework-managed state ───────────────────────────────
        self.control_message = init_ControlMessage()
        self.utility_message = init_UtilityMessage()
        self.ems_data = init_EmsData()
        self.ems_calibration_data = init_EMSCalibrationData()

        # ── Runtime state ─────────────────────────────────────────
        self._running: bool = False
        self.cycle_count: int = 0

    # ══════════════════════════════════════════════════════════════
    # Lifecycle
    # ══════════════════════════════════════════════════════════════

    def run(self) -> None:
        """Start the main loop (blocking).

        Call this from the backend subprocess.  The loop runs until
        :meth:`stop` is called (e.g. from a hook or another thread).

        Loop timing is governed by the Teslasuit SDK's blocking
        data-ready calls (~100 Hz).  No software throttle is applied.

        Shutdown order:
            1. ``on_stop()`` — developer hook (application cleanup)
            2. Framework cleanup — stops mocap streaming, closes external
               inputs (always runs, even if ``on_stop()`` raises)
        """
        logger.info(
            "ClosedLoopEngine starting (hardware-governed timing, sample_rate=%.1f Hz)",
            self.sample_rate,
        )

        if not self.calibration.is_calibrated:
            logger.warning(
                "Starting ClosedLoopEngine without calibration. "
                "MoCap data may be inaccurate. "
                "Call engine.calibration.calibrate() before engine.run()."
            )

        self._running = True
        self.cycle_count = 0

        try:
            # Auto-wire strategy: populate muscles + suit handle from suit_handler.
            # ``suit`` lets the strategy build its haptic_library via
            # suit.create_haptic_touch / suit.load_haptic_asset in setup().
            self.control_strategy.setup(
                muscles=self.suit_handler.muscle_map,
                suit=self.suit_handler,
            )

            # If the strategy populated a haptic_library, register its
            # slot layout with the LSL outlet now (channel labels = slot
            # field names, locked for the rest of streaming).
            if self.control_strategy.haptic_library is not None:
                self.lsl_streamer.configure_haptic_library_outlet(
                    self.control_strategy.haptic_library,
                )

            self.on_start()

            while self._running:
                # ── Per-cycle data flow ───────────────────────────

                # 1. Collect → Process → Distribute (DataStreamer three-phase cycle)
                self.data_streamer.run_cycle()

                # 2. Poll external inputs and wire into strategy
                if self.external_inputs is not None:
                    self.control_strategy.external_data = self.external_inputs.pull_all()

                # 3. Handle IPC messages (queue-based)
                if self.queue_handler is not None:
                    self._poll_messages()

                # 4. Control strategy
                self.control_strategy.run_strategy(
                    self.control_message,
                    self.data_streamer.biomechanical_data,
                    self.data_streamer.step_detector_data,
                    self.ems_data,
                    fes_active=self.utility_message.FesIsActive,
                    processed_data=self.data_streamer.processed_data,
                )

                # 5. Stimulation output
                self.stimulator.run_stimulator(self.suit_handler, self.ems_data)

                # 5b. Custom haptic playables (only if the strategy declared a library)
                if self.control_strategy.haptic_library is not None:
                    self.library_stimulator.run_stimulator(
                        self.suit_handler, self.control_strategy.haptic_library,
                    )

                # 6. LSL streaming
                self.lsl_streamer.stream_all_data(
                    self.data_streamer.biomechanical_data,
                    self.data_streamer.step_detector_data,
                    self.ems_data,
                    self.control_message,
                    self.utility_message,
                    self.data_streamer.processed_data,
                    self.data_streamer.raw_data,
                    heart_rate_data=self.data_streamer.heart_rate_data,
                    hrv_data=self.data_streamer.hrv_data,
                    raw_ppg_data=self.data_streamer.raw_ppg_data,
                    haptic_library=self.control_strategy.haptic_library,
                )

                # 7. Post-cycle hook
                self.on_cycle_complete()

                self.cycle_count += 1

        except KeyboardInterrupt:
            logger.info("ClosedLoopEngine interrupted by user")
        finally:
            # Developer hook first (may raise — framework cleanup still runs)
            try:
                self.on_stop()
            except Exception:
                logger.exception("Error in on_stop() hook")

            # Framework cleanup (unconditional)
            self._cleanup()
            self._running = False
            logger.info(
                "ClosedLoopEngine stopped after %d cycles", self.cycle_count
            )

    def stop(self) -> None:
        """Signal the engine to stop after the current cycle completes."""
        self._running = False

    @property
    def is_running(self) -> bool:
        """Whether the main loop is currently executing."""
        return self._running

    # ══════════════════════════════════════════════════════════════
    # IPC message handling
    # ══════════════════════════════════════════════════════════════

    def _poll_messages(self) -> None:
        """Poll IPC queues, drain to latest, and dispatch to hooks.

        Drains each queue completely so that rapid sender updates
        (e.g. GUI slider drags) skip stale intermediate values and
        the engine always sees the most recent message.

        A ``STOP_SENTINEL`` string on the utility queue triggers
        graceful shutdown (used by the orchestrator).
        """
        # Drain utility queue to latest message
        latest_utility = None
        while True:
            msg = self.queue_handler.get_utility_message()
            if msg is None:
                break
            if isinstance(msg, str) and msg == STOP_SENTINEL:
                self.stop()
                return
            latest_utility = msg

        if latest_utility is not None:
            # Pickle round-trips drop _on_change; rebind so any backend
            # write to utility_message auto-publishes back to the GUI.
            latest_utility._on_change = self.queue_handler.send_utility_message
            self.queue_handler.utility_message = latest_utility
            self.utility_message = latest_utility
            self.on_utility_message(latest_utility)

        # Drain control queue to latest message
        latest_control = None
        while True:
            msg = self.queue_handler.get_control_message()
            if msg is None:
                break
            latest_control = msg

        if latest_control is not None:
            # Same rebind as utility_message — restores the auto-send
            # callback that pickle stripped during the GUI → backend hop,
            # so strategies that write back to params (e.g. closed-loop
            # telemetry) reach the GUI without manual qh.send_* calls.
            latest_control._on_change = self.queue_handler.send_control_message
            self.queue_handler.control_message = latest_control
            self.control_message = latest_control
            self.on_control_message(latest_control)

    # ══════════════════════════════════════════════════════════════
    # Framework cleanup (unconditional)
    # ══════════════════════════════════════════════════════════════

    def _cleanup(self) -> None:
        """Stop all hardware and close all resources.

        Called automatically after every ``run()`` exit (normal, exception,
        or Ctrl-C).  Runs **after** ``on_stop()`` so developer cleanup
        always executes first.  Each step is guarded individually so a
        failure in one does not prevent the others.
        """
        # Stop mocap streaming
        try:
            self.suit_handler.stop_mocap_streaming()
        except Exception:
            logger.exception("Error stopping mocap streaming")

        # Stop PPG streaming (if available)
        if self.data_streamer.ppg_available:
            try:
                self.suit_handler.stop_ppg_streaming()
            except Exception:
                logger.exception("Error stopping PPG streaming")

        # Stop stimulation (mute all channels)
        try:
            self.suit_handler.stop_player()
        except Exception:
            logger.exception("Error stopping stimulation player")

        # Close external input connections
        if self.external_inputs is not None:
            try:
                self.external_inputs.close_all()
            except Exception:
                logger.exception("Error closing external inputs")

    # ══════════════════════════════════════════════════════════════
    # Overridable hooks
    # ══════════════════════════════════════════════════════════════

    def on_start(self) -> None:
        """Called once before the first cycle.

        Override to perform one-time setup (e.g. open log files, print
        banner, configure strategy-specific state).

        Note: ``strategy.setup(muscles=suit_handler.muscle_map)`` is called
        automatically by the framework before this hook.

        Default: no-op.
        """

    def on_stop(self) -> None:
        """Called once after the loop exits, before framework cleanup.

        Override to perform application-specific teardown (e.g. close log
        files, save state, flush buffers).

        You do NOT need to stop mocap streaming or close external inputs
        here — the engine handles that automatically after this hook returns.

        Default: no-op.
        """

    def on_utility_message(self, message) -> None:
        """Called when a new utility message arrives from the IPC queue.

        Override to react to system-state changes (e.g. calibration requests,
        recording toggles).

        Args:
            message: The new UtilityMessage instance.  Already stored as
                     ``self.utility_message`` before this hook is called.

        Default: no-op.
        """

    def on_control_message(self, message) -> None:
        """Called when a new control message arrives from the IPC queue.

        Override to react to parameter changes (e.g. log new values,
        validate ranges).

        Args:
            message: The new ControlMessage instance.  Already stored as
                     ``self.control_message`` before this hook is called.

        Default: no-op.
        """

    def on_cycle_complete(self) -> None:
        """Called at the end of every cycle, after all framework steps.

        Override to add application-specific post-processing (e.g. write
        to shared memory for GUI, collect timing metrics, check stop
        conditions).

        Default: no-op.
        """
