# SPDX-License-Identifier: MIT
"""
Reference Orchestrator — Dual-Process FES Application Launcher.

Shows how to set up a complete FES application using ClosedLoopEngine:
  - Backend process running the closed-loop engine
  - Optional GUI/interface process communicating via multiprocessing queues
  - Graceful shutdown on Ctrl-C or programmatic stop

This is a **reference implementation** — copy and adapt for your own
application.  See the ``examples/`` directory for complete applications
built on this pattern.
"""
from __future__ import annotations

import signal
from multiprocessing import Event, Process, Queue, freeze_support
from typing import Optional, Type

from .engine import ClosedLoopEngine, STOP_SENTINEL
from .control.strategy_base import ControlStrategyBase


def _wait_for_event(event: Event, backend: Process, timeout: float,
                    label: str) -> None:
    """Wait for *event*, but abort early if *backend* dies.

    Polls ``backend.is_alive()`` every 0.25 s so that a subprocess crash
    is detected promptly instead of waiting the full *timeout*.

    Args:
        event:   The multiprocessing.Event to wait on.
        backend: The backend Process to monitor.
        timeout: Maximum seconds to wait.
        label:   Human-readable description for error messages.

    Raises:
        RuntimeError: If the backend exits or the timeout expires before
                      the event is set.
    """
    elapsed = 0.0
    poll_interval = 0.25
    while elapsed < timeout:
        if event.wait(timeout=poll_interval):
            return  # event was set — success
        elapsed += poll_interval
        if not backend.is_alive():
            raise RuntimeError(
                f"Backend process exited unexpectedly while waiting for {label}"
            )
    raise RuntimeError(f"{label} timed out after {timeout}s")


def run_engine_process(
    strategy_class: Type[ControlStrategyBase],
    control_queue: Optional[Queue] = None,
    utility_queue: Optional[Queue] = None,
    *,
    lsl_enabled: bool = False,
    external_input_streams: Optional[list] = None,
    external_input_timeout: float = 5.0,
    calibrate_event: Optional[Event] = None,
    calibration_done_event: Optional[Event] = None,
    calibration_required: bool = False,
    ready_event: Optional[Event] = None,
) -> None:
    """Run the ClosedLoopEngine in a subprocess.

    This function is the ``target`` for ``multiprocessing.Process``.
    Only the strategy class is required — the engine auto-creates all
    other backend components (SuitHandler, DataStreamer, Stimulator, etc.).

    Args:
        strategy_class: Your ControlStrategyBase subclass (will be instantiated here)
        control_queue:  Optional queue for control messages (GUI → Backend)
        utility_queue:  Optional queue for utility messages (bidirectional)
        lsl_enabled:    Whether to enable LSL outlet streaming (default False)
        external_input_streams: Optional list of LSL stream names to register
                                as external inputs (built in-process to avoid pickling)
        external_input_timeout: Seconds to wait for each external stream (default 5.0)
        calibrate_event: If set, the backend waits on this event before running
                         calibration.  The main process should set() it after the
                         user confirms they are in I-pose.
        calibration_done_event: If set, the backend signals this event once
                                calibration is complete (success or failure).
                                The main process should wait on it before
                                starting the GUI.
        calibration_required: If True, raise RuntimeError when calibration
                              fails or quality is below threshold (instead of
                              continuing with a warning).
        ready_event:     If set, the backend signals this event once hardware
                         initialisation is complete (before calibration).
    """
    print("[Backend] Initialising engine (hardware auto-detected)…")

    # Build ExternalInputManager in-process (pylsl objects can't be pickled)
    external_inputs = None
    if external_input_streams:
        from .io.lsl_inlet import ExternalInputManager
        external_inputs = ExternalInputManager()
        for name in external_input_streams:
            try:
                external_inputs.add(name, timeout=external_input_timeout)
                print(f"[Backend] Registered external input: {name}")
            except TimeoutError:
                print(f"[Backend] WARNING: Stream '{name}' not found "
                      f"(timeout={external_input_timeout}s) — skipping")
            except ValueError as exc:
                print(f"[Backend] WARNING: Could not add '{name}': {exc}")

    engine = ClosedLoopEngine(
        control_strategy=strategy_class(),
        control_queue=control_queue,
        utility_queue=utility_queue,
        lsl_enabled=lsl_enabled,
        external_inputs=external_inputs,
    )

    # Signal that hardware initialisation is complete
    if ready_event is not None:
        ready_event.set()

    # Interactive calibration — wait for main process to confirm I-pose
    if calibrate_event is not None:
        print("[Backend] Waiting for calibration signal…")
        calibrate_event.wait()   # blocks until main process sets the event
        result = engine.calibration.calibrate()
        print(f"[Backend] Calibration: {result.message}")
        calibration_abort = False
        if not result.success:
            if calibration_required:
                print("[Backend] ERROR: Calibration failed — aborting")
                calibration_abort = True
            else:
                print("[Backend] WARNING: Calibration failed — continuing anyway")
        # Signal main process before potentially exiting
        if calibration_done_event is not None:
            calibration_done_event.set()
        if calibration_abort:
            return

    print(f"[Backend] Starting engine (LSL {'ON' if lsl_enabled else 'OFF'})")
    engine.run()
    # engine.run() handles all cleanup internally (mocap, stimulation, external inputs)
    print("[Backend] Shutdown complete")


def launch(
    strategy_class: Type[ControlStrategyBase],
    *,
    gui_runner=None,
    lsl_enabled: bool = False,
    hardware_init_timeout: float = 30.0,
    external_input_streams: Optional[list] = None,
    external_input_timeout: float = 5.0,
    calibrate: bool = False,
    calibration_required: bool = False,
) -> None:
    """Launch a dual-process FES application.

    Creates IPC queues, starts the backend engine in a subprocess, and
    optionally runs a GUI/interface in the main process.

    Only the strategy class is required — all other backend components
    are auto-created by the engine.

    Args:
        strategy_class:      ControlStrategyBase subclass to use
        gui_runner:          Optional callable ``f(control_queue, utility_queue)``
                             that runs the interface (blocking).  If None, the
                             backend runs headless until Ctrl-C.
        lsl_enabled:         Whether to enable LSL outlet streaming
        hardware_init_timeout: Max seconds to wait for hardware init (default 30).
                               Raises RuntimeError if exceeded.
        external_input_streams: Optional list of LSL stream names to register
                                as external inputs.  Built inside the backend
                                subprocess (pylsl objects are not picklable).
        external_input_timeout: Seconds to wait for each external stream (default 5.0)
        calibrate:           Run interactive MoCap calibration before the control
                             loop.  Prompts the user to stand in I-pose (in the
                             main process), then signals the backend to calibrate
                             and reports quality.  Non-aborting on failure
                             (unless ``calibration_required=True``).
        calibration_required: If True (and ``calibrate=True``), abort with
                              RuntimeError when calibration fails or quality is
                              below threshold.  For a hard quality gate without
                              the orchestrator, use ``ClosedLoopEngine`` directly
                              (see ``examples/atomic/calibration_gate.py``).

    Example (headless)::

        from teslasuit_rapidkit.orchestrator import launch
        from my_strategy import MyStrategy

        launch(MyStrategy, lsl_enabled=True)

    Example (with GUI)::

        launch(MyStrategy, gui_runner=my_gui_main)

    Example (with external LSL inputs)::

        launch(MyStrategy, external_input_streams=["ForcePlate_GRF", "EEG_Alpha"])

    Example (with calibration)::

        launch(MyStrategy, calibrate=True)

    Example (with mandatory calibration)::

        launch(MyStrategy, calibrate=True, calibration_required=True)
    """
    freeze_support()

    # IPC queues (created whether or not GUI is used — lightweight)
    control_queue = Queue()
    utility_queue = Queue()

    # Synchronisation primitives
    ready_event = Event()
    calibrate_event = Event() if calibrate else None
    calibration_done_event = Event() if calibrate else None

    # Start backend in subprocess
    print("[Orchestrator] Starting backend process…")
    backend = Process(
        target=run_engine_process,
        args=(strategy_class, control_queue, utility_queue),
        kwargs=dict(
            lsl_enabled=lsl_enabled,
            external_input_streams=external_input_streams,
            external_input_timeout=external_input_timeout,
            calibrate_event=calibrate_event,
            calibration_done_event=calibration_done_event,
            calibration_required=calibration_required,
            ready_event=ready_event,
        ),
    )
    backend.start()

    # Wait for hardware initialisation (detects early crashes via polling)
    try:
        _wait_for_event(ready_event, backend, hardware_init_timeout,
                        "hardware initialisation")
    except RuntimeError:
        backend.terminate()
        backend.join(timeout=5)
        raise
    print("[Orchestrator] Backend process ready")

    # Calibration prompt runs in main process (stdin is reliable here)
    if calibrate_event is not None:
        input("[Orchestrator] Stand in I-pose, then press Enter to calibrate... ")
        calibrate_event.set()  # signal backend to proceed with calibration
        # Wait for calibration to finish before starting GUI
        _wait_for_event(calibration_done_event, backend, timeout=60.0,
                        label="calibration")
        print("[Orchestrator] Calibration complete")

    try:
        if gui_runner is not None:
            print("[Orchestrator] Starting interface…")
            gui_runner(control_queue, utility_queue)
        else:
            # Headless mode — wait for Ctrl-C
            print("[Orchestrator] Running headless (Ctrl-C to stop)")
            signal.signal(signal.SIGINT, signal.default_int_handler)
            backend.join()  # blocks until backend exits
    except KeyboardInterrupt:
        print("\n[Orchestrator] Shutting down…")
    finally:
        # Graceful shutdown: send stop sentinel, then wait before hard kill
        if backend.is_alive():
            print("[Orchestrator] Requesting graceful shutdown…")
            try:
                utility_queue.put(STOP_SENTINEL, timeout=1)
            except Exception:
                pass  # queue may be full or broken — fall through to terminate
            backend.join(timeout=5)
        if backend.is_alive():
            print("[Orchestrator] Forcing backend termination…")
            backend.terminate()
            backend.join(timeout=5)
            if backend.is_alive():
                backend.kill()
                backend.join()
        print("[Orchestrator] Shutdown complete")
