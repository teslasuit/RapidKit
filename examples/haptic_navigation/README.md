# Haptic Navigation

**Directional haptic cues — arrow keys fire haptic events on different parts of the wearer's body.**

**Hardware required:** Teslasuit 4.x or XR5, powered, on the same WiFi network as the host.
**Full docs:** [documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks)

---

## Run it

```bash
python -m examples.haptic_navigation.main
```

A small GUI window appears. Arrow keys fire haptic cues:

- **↑** — belly
- **↓** — back
- **←** — left shoulder
- **→** — right shoulder

Multiple arrows can be held simultaneously.

Press **Ctrl-C** in the launching shell to stop.

---

## What to look for

- The GUI window has focus; pressing arrow keys produces a tactile
  pulse the wearer can feel on the corresponding body region.
- Releasing a key silences that cue immediately (within ~10 ms).
- Multiple cues fire simultaneously without interfering.

---

## Files

| File | Purpose |
|---|---|
| [`main.py`](main.py) | Entry point — `orchestrator.launch()` with the strategy and GUI runner |
| [`haptic_navigation_strategy.py`](haptic_navigation_strategy.py) | `HapticNavigationStrategy(ControlStrategyBase)` — populates `HapticLibrary` slots in `setup()`, toggles slot mutes in `process()` |
| [`haptic_navigation_types.py`](haptic_navigation_types.py) | `NavCues(HapticLibrary)` slot definitions; `NavControlMessage` direction flags |
| [`gui/main.py`](gui/main.py) | PyQt5 window with arrow-key event handling |

---

## Modify it

This example anchors the **`HapticLibrary` extension point**. To
build your own custom-haptic application:

1. Subclass `HapticLibrary` and declare named `CustomPlayable` slots
   (see [haptic_navigation_types.py](haptic_navigation_types.py)).
2. In your strategy's `setup()`, populate slots via
   `self.suit.create_haptic_touch()` or `self.suit.load_haptic_asset()`.
3. In `process()`, toggle `slot.IsMuted` on/off based on your inputs.

For the framework concept, see [documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks).
