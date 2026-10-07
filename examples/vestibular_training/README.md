# Vestibular Training Example

Balance rehabilitation via haptic biofeedback using the Teslasuit.

This example extends the FES Framework into sensory substitution rehabilitation.
The Teslasuit's motion capture detects postural sway in real time; when the
patient's trunk angle exceeds a configurable stability boundary, vibrotactile cues on the
suit surface indicate the direction of lean, substituting for the impaired vestibular signal.

## Clinical use case

Patients with vestibular disorders (stroke, TBI, labyrinthitis, age-related degeneration)
who have difficulty judging upright posture. Continuous haptic feedback during standing
tasks can accelerate sensorimotor re-learning.

## Run it

```bash
python -m examples.vestibular_training.main
```

**Hardware required:** Teslasuit 4.x or XR5, connected and powered.
**Full docs:** [documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks)

## How it relates to the framework

Uses `ControlStrategyBase` — the same plugin interface as every other example in this
repo — but routes output to the haptic actuator API instead of EMS channels. Demonstrates
that the framework's output layer is not limited to electrical stimulation.
