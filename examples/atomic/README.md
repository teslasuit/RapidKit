# Atomic Examples

Single-file, copy-pasteable examples that each demonstrate one FES Framework
concern. Every file here imports only from the public `rapidkit.*` API
and runs as a standalone script against a real Teslasuit.

For a complete GUI + multi-process integrated application built on these same
primitives, see [`../elbow_flexion/`](../elbow_flexion).

## Files

| File | What it shows |
|---|---|
| [`minimal_closed_loop.py`](./minimal_closed_loop.py) | Smallest possible `ControlStrategyBase` subclass; hands off to `orchestrator.launch()` for the standard closed-loop cycle |
| [`reading_sensor_data.py`](./reading_sensor_data.py) | Named dataclass access to `self.joints` (biomech) and `self.contacts` (step detector) each cycle — no buffer parsing |
| [`semantic_muscle_control.py`](./semantic_muscle_control.py) | `MuscleMap` semantic queries (`by_side`, `by_region`, `list_muscles`) and writing stimulation by muscle name via `self.ems_output.quadriceps_left = EMSParamData(...)` |
| [`lsl_streaming.py`](./lsl_streaming.py) | Enables the 7 LSL outlets (for LabRecorder-based session recording) and registers an external LSL inlet via `ExternalInputManager` |
| [`calibration_gate.py`](./calibration_gate.py) | Uses `engine.calibration.calibrate()` headlessly, then gates the control strategy on `result.success` |

## How to run

From the repo root, with the Teslasuit connected and powered on:

```bash
python examples/atomic/minimal_closed_loop.py
python examples/atomic/reading_sensor_data.py
python examples/atomic/semantic_muscle_control.py
python examples/atomic/lsl_streaming.py
python examples/atomic/calibration_gate.py
```

Each file prepends the repo root to `sys.path` so it also works when invoked
directly from this folder.

Hit **Ctrl-C** to stop any of them. The framework cleans up hardware state
(mocap streaming, stimulation, external inlets) unconditionally on exit.

## Hardware requirement

All examples target real hardware. There is no mock / simulator path — if the
Teslasuit is not connected, `SuitHandler` construction will fail during engine
initialisation.

## When `launch()` is not enough

`minimal_closed_loop.py` and `reading_sensor_data.py` use
`rapidkit.orchestrator.launch()` — the recommended dual-process entry
point. The other three drop down to `ClosedLoopEngine` directly because they
need one of:

- **`semantic_muscle_control.py`** — wire `suit_handler.muscle_map` onto
  `strategy.muscles` in an `on_start()` override (the engine does not do this
  automatically).
- **`lsl_streaming.py`** — pass an `ExternalInputManager` to the engine; this
  isn't exposed through `launch()`.
- **`calibration_gate.py`** — call `engine.calibration.calibrate()` before
  `engine.run()`.

Use these patterns as a template when your own application outgrows
`launch()`.
