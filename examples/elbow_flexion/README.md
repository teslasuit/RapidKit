# Elbow Flexion FES — comprehensive example

**A complete PID-controlled FES application for elbow flexion. Uses biceps and triceps as an agonist/antagonist pair, an FFT-based PID auto-tuner, and a PyQt5 GUI with control sliders and live plots.**

**Hardware required:** Teslasuit 4.x or XR5, connected and powered; subject seated, elbows free to move 0–135°.
**Full docs:** [documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks)

---

## Run it

```bash
python -m examples.elbow_flexion.main
```

Workflow:

1. Stand/sit in T-pose, click **Calibrate (T-pose)**.
2. Pick the active arm (Left or Right radio).
3. Set the desired angle slider.
4. Adjust the amplitude slider down before enabling FES.
5. Tick **Enable FES (master)**.
6. Either tune Kp/Ki/Kd manually with the sliders or click
   **Auto-tune PID** — when the status shows `DONE`, the suggested
   gains have been applied.
7. Optionally enable **Mirror opposite arm** — the active arm now
   tracks the contralateral arm's angle.

Press **Ctrl-C** in the launching shell to stop.

---

## What to look for

- The active elbow tracks the slider setpoint via PID-driven
  biceps/triceps stimulation.
- Auto-tune ramps Kp upward, detects sustained oscillation via FFT,
  and writes Ziegler–Nichols gains back into the control message.
- Mirror mode makes one arm follow the other.
- Pulse-width plots show the live PID output as a stimulation
  waveform.

---

## Files

| File | Role |
|---|---|
| [`main.py`](main.py) | Dual-process launcher (backend subprocess + GUI main process) |
| [`backend_mainloop.py`](backend_mainloop.py) | `ElbowBackendMainloop(ClosedLoopEngine)` — wires strategy, control message, shared-memory buffer |
| [`elbow_control_strategy.py`](elbow_control_strategy.py) | `ElbowFlexionPIDStrategy(ControlStrategyBase)` — per-cycle PID + auto-tuner |
| [`elbow_utils.py`](elbow_utils.py) | `SimplePID` (clamped PID with anti-windup) + `FFTAutoTuner` (Ziegler–Nichols state machine) |
| [`elbow_types.py`](elbow_types.py) | `ElbowControlMessage` + `shared_memory_frame_elbow` numpy dtype |
| [`elbow_init_utils.py`](elbow_init_utils.py) | Factory + frame packer |
| [`gui/main_window.py`](gui/main_window.py) | `ElbowMainWindow` — two tabs + signal wiring |
| [`gui/data_handler.py`](gui/data_handler.py) | Reads `'elbow_buffer'` each GUI tick and buffers rolling plot data |
| [`gui/tabs/control_tab.py`](gui/tabs/control_tab.py) | Sliders, arm radio, mirror toggle, auto-tune + calibrate buttons |
| [`gui/tabs/plot_tab.py`](gui/tabs/plot_tab.py) | Angle-vs-setpoint + pulse-width plots via pyqtgraph |

---

## Safety notes

- Default amplitude is **100%** across the full 0–100% slider range.
  **Lower it before enabling FES** if the operator prefers to ramp
  up from a gentler baseline.
- The master FES toggle routes through the framework's FES-active
  guard — when off, all stimulation is muted at the engine level.
- The auto-tuner caps Kp at 3.0 and has a 30 s hard time limit.
- Pulse width is clamped to 300 μs in the strategy.

See the safety guidance in [documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks).

---

## Modify it

This example is a starting point for any **continuous joint-angle
tracking** application — knee, ankle, wrist, shoulder. The
strategy and utility classes are deliberately self-contained; lift
them wholesale into your own application directory and modify in
place.

For a guided walkthrough see [documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks).

---

## Heritage

Ported from a standalone research prototype that built directly on the
Teslasuit SDK. The framework integration replaced raw-quaternion
math with `BiomechanicalData.ElbowFlexExt*`, replaced direct
`haptic_play_touch()` calls with `self.ems_output.*` writes, and
folded three QTimers into one engine cycle.
