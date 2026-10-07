# Generic GUI

**Reference PyQt5 GUI template wired to the framework's reusable widget toolkit. No application-specific control logic.**

**Hardware required:** Teslasuit 4.x or XR5 (the GUI runs without one but data plots will be empty).
**Full docs:** [documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks)

---

## Run it

```bash
python -m examples.generic_gui.main
```

A two-or-three-tab PyQt5 window appears (Overview / Sensor Data /
Connection). Press **Ctrl-C** in the launching shell to stop.

---

## What to look for

- The Overview tab shows per-muscle toggles and amplitude sliders.
- The Sensor Data tab plots bilateral joint angles in real time
  (once data is flowing through `SharedRingBuffer`).
- The Connection tab shows a coloured indicator: green when the
  backend is alive, red when it isn't.
- The strategy is a no-op (`DummyStrategy`), so flipping muscle
  toggles in the Overview tab won't actually fire stimulation.

---

## Files

| File | Purpose |
|---|---|
| [`main.py`](main.py) | All wiring in one file — strategy, GUI process, dtype, tab composition, launch |

The widgets it consumes live in
[`teslasuit_rapidkit/gui/`](../../teslasuit_rapidkit/gui/):

- `FesApp` — main application class
- `DataAdapter` — `SharedRingBuffer` reader
- `OverviewTab`, `SensorDataTab` — pre-built tabs
- `FesWidget` — base class for custom tabs

---

## Modify it

This example anchors **GUI scaffolding from scratch**. To build your
own application's GUI:

1. Replace `DummyStrategy` with your own `ControlStrategyBase` subclass.
2. Update `FRAME_DTYPE`, `BUFFERED_FIELDS`, `MUSCLES`, and
   `SENSOR_SERIES` to match what your application actually
   controls and reads.
3. Subclass `FesWidget` for any custom tabs you need.

For the framework concept and a guided walkthrough, see
[documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks).
