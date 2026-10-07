# teslasuit-rapidkit

A Python framework for building closed-loop applications on Teslasuit hardware.

You write the control algorithm. The framework handles hardware connection, sensor data parsing, anatomical muscle routing, multi-process orchestration, calibration, and lab recording integration.

```python
from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase
from teslasuit_rapidkit.data.types import EMSParamData
from teslasuit_rapidkit.orchestrator import launch

class StanceQuadStrategy(ControlStrategyBase):
    def process(self) -> None:
        if self.contacts.right_foot_contact:
            self.ems_output.quadriceps_right = EMSParamData(
                IsMuted=False, Amplitude=40, PulseWidth=200, Period=20.0,
            )

if __name__ == "__main__":
    launch(StanceQuadStrategy)
```

That is a complete FES application: stimulate the right quadriceps whenever the right foot contacts the ground, running at ~100 Hz with hardware-paced timing.

Full documentation, including the guided getting-started walkthrough, lives at
[documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks).
This README covers the essentials for getting a first application running.

---

## Requirements

- **OS:** Windows 10 or 11, 64-bit
- **Python:** 3.8 or higher
- **Hardware:** Teslasuit (4.x or XR5)
- **Software:** Teslasuit Control Center and Teslasuit Studio installed and running

---

## Installation

**1. Install the Teslasuit Python SDK.** RapidKit builds on top of it but does not
bundle or redistribute it — it ships with Teslasuit Studio, not PyPI. Follow the
official [Python API getting-started guide](https://documentation.teslasuit.io/docs/apis/python/introduction/getting-started)
to install it into your Python environment before continuing.

**2. Install RapidKit.** Clone this repository, then install from the project root:

```bash
git clone <this-repository-url> teslasuit-rapidkit
cd teslasuit-rapidkit
pip install .
```

For local development, use an editable install so source changes take effect immediately:

```bash
pip install -e .
```

With the optional GUI dependencies (PyQt5, pyqtgraph, matplotlib):

```bash
pip install -e ".[gui]"
```

Verify the install:

```bash
python -c "import teslasuit_rapidkit; print(teslasuit_rapidkit.__version__)"
```

---

## Quickstart

### 1. Subclass `ControlStrategyBase` and implement `process()`

`process()` is called every cycle (~100 Hz). Read sensor data from `self.joints`, `self.contacts`, `self.params`, and `self.external_data`. Write stimulation commands to `self.ems_output`.

```python
from teslasuit_rapidkit.control.strategy_base import ControlStrategyBase
from teslasuit_rapidkit.data.types import EMSParamData

class MyStrategy(ControlStrategyBase):
    def process(self) -> None:
        # self.joints      → 29 joint angles (BiomechanicalData)
        # self.contacts    → foot contact events (StepDetectorData)
        # self.params      → runtime parameters from GUI (ControlMessage)
        # self.ems_output  → write stimulation commands here (EmsData)
        if self.contacts.right_foot_contact:
            self.ems_output.quadriceps_right = EMSParamData(
                IsMuted=False, Amplitude=40, PulseWidth=200, Period=20.0,
            )
```

### 2. Launch

```python
from teslasuit_rapidkit.orchestrator import launch

launch(MyStrategy)
```

`launch()` starts a backend subprocess with the engine loop and optionally a GUI in the main process:

```python
launch(MyStrategy, gui_runner=my_gui_main, lsl_enabled=True)
```

### 3. (Optional) Add calibration

```python
launch(MyStrategy, calibrate=True)
```

The orchestrator prompts the subject to stand in I-pose, then signals the backend to calibrate MoCap before the control loop starts.

---

## Core concepts

### `ControlStrategyBase`

The only class you need to subclass. Implement `process()` for per-cycle logic. Override lifecycle hooks for setup and teardown:

| Hook | When called |
|---|---|
| `setup(muscles, suit)` | Once before the first cycle — build haptic assets, load configs |
| `process()` | Every cycle (~100 Hz) — your control logic lives here |

### `ClosedLoopEngine`

Powers the main loop. Auto-assembles all backend components (`SuitHandler`, `DataStreamer`, `Stimulator`, `LSLStreamer`, `QueueHandler`) from the strategy you provide. Use directly when you need more control than `launch()` gives:

```python
from teslasuit_rapidkit.engine import ClosedLoopEngine

engine = ClosedLoopEngine(control_strategy=MyStrategy())
result = engine.calibration.calibrate()
engine.run()
```

### `MuscleMap`

Translates anatomical muscle names (`quadriceps_left`, `tibialis_anterior_right`, …) to Teslasuit hardware channel IDs. Loaded automatically from the bundled `muscle_map_4R.json`. Pass a custom JSON path to `SuitHandler` to target XR5 hardware.

### `SharedRingBuffer`

Zero-copy shared memory ring buffer for streaming data between the backend subprocess and a GUI process without pickling overhead.

### LSL integration

Enable LabStreamingLayer outlets for session recording with any LSL-compatible recorder (e.g. LabRecorder):

```python
launch(MyStrategy, lsl_enabled=True)
```

Seven outlets are opened: joint angles, step detector, EMS parameters, control message, utility message, raw sensor data, PPG.

---

## GUI scaffold

Install with the `[gui]` extra to use the PyQt5 base application (`FesApp`) and reusable widgets (`FesToggle`, `CalibrationPanel`, `LivePlot`, `MuscleControlCard`, …) that wire directly to `QueueHandler` for IPC.

```python
from teslasuit_rapidkit.gui.app import FesApp
from teslasuit_rapidkit.gui.tabs.overview_tab import OverviewTab

def run_gui(control_queue, utility_queue):
    app = FesApp(
        control_queue=control_queue,
        utility_queue=utility_queue,
        title="My FES Application",
        tabs=[("Overview", OverviewTab)],
    )
    app.run()

launch(MyStrategy, gui_runner=run_gui)
```

---

## Examples

Six runnable example applications live under [`examples/`](examples/):

| Example | What it shows |
|---|---|
| [`atomic/`](examples/atomic/) | Five single-file, copy-pasteable demos — one per framework concern |
| [`elbow_flexion/`](examples/elbow_flexion/) | Complete PID-controlled FES application with GUI, auto-tuner, and a full backend/GUI process split |
| [`generic_gui/`](examples/generic_gui/) | Reference PyQt5 GUI template wired to the framework's reusable widget toolkit |
| [`haptic_navigation/`](examples/haptic_navigation/) | Directional haptic cues fired by keyboard input |
| [`haptic_proximity_radar/`](examples/haptic_proximity_radar/) | Continuous direction/distance-modulated haptic cueing driven by a draggable target |
| [`vestibular_training/`](examples/vestibular_training/) | Balance-rehabilitation haptic biofeedback from real-time postural sway |

Each example has its own README with run instructions. See
[documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks)
for guided walkthroughs.

---

## Package layout

```
teslasuit_rapidkit/       ← framework package (import as teslasuit_rapidkit)
├── engine.py             ← ClosedLoopEngine — the main loop
├── orchestrator.py       ← launch() — dual-process entry point
├── calibration.py        ← CalibrationAPI
├── muscle_map.py         ← MuscleMap (name → hardware channel)
├── control/              ← ControlStrategyBase
├── data/                 ← BiomechanicalData, EmsData, ControlMessage, …
├── io/                   ← SuitHandler, DataStreamer, Stimulator, LSLStreamer
├── ipc/                  ← SharedRingBuffer, QueueHandler
├── gui/                  ← optional PyQt5 scaffold (requires [gui] extra)
└── config/               ← muscle_map_4R.json (bundled package data)

examples/                 ← six runnable example applications (see Examples above)
```

The Teslasuit Python SDK (`teslasuit_sdk`) is a separate install — see
Installation above — and is not part of this repository.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Found a vulnerability? See [SECURITY.md](SECURITY.md) for how to report it.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE)
