# Haptic Proximity Radar

A continuous-direction, distance-modulated haptic example for the Teslasuit 4R.

The operator sees a top-down view of the wearer at the center of a circular
"sphere". A draggable target object lives anywhere inside that disc. The suit
fires a continuous haptic cue whose:

- **Channel (which body zone fires)** is selected by the **angle** from the
  wearer to the object.
- **Intensity (pulse width × amplitude)** is driven by the **radial distance**
  — close = strong, far = silent.

It is the continuous analogue of the discrete arrow-key cues in
[`examples/haptic_navigation`](../haptic_navigation/), and reuses its vendored
Jura font assets.

**Hardware required:** Teslasuit 4R, connected and powered.
**Full docs:** [documentation.teslasuit.io/frameworks](https://documentation.teslasuit.io/frameworks)

---

## Run it

```bash
python -m examples.haptic_proximity_radar.main
```

A top-down radar window appears with a draggable target puck. Drag it around
the disc to change which body zone fires and how strong the cue is. Press
**Esc** to stop all zones; **Ctrl-C** in the launching shell to exit.

---

## Concept

```
                 N (forward)
                 belly
                   │
       W ──────────●──────────  E  (right shoulder)
   (left shoulder) │
                   │
                  back
                   S
```

- Wearer is the dot at the disc center.
- Target object can be dragged anywhere within radius `R`.
- Direction → which body zone fires (with a cosine-weighted blend on the
  boundaries so adjacent zones crossfade smoothly).
- Distance → how strong the cue is. At `r ≥ r_silence` (default 0.95·R) all
  zones are muted.

## Signal mapping

Let `(x, y)` be the object position relative to the wearer, `R` the disc radius.

- `r       = clamp(|p| / R, 0, 1)`
- `θ       = atan2(y, x)`            (0 = right / east; π/2 = forward / north)
- `prox    = clamp(1 − r, 0, 1)`
- Per zone with center angle `θ_zone`:
  - `w_zone = max(0, cos(θ − θ_zone))²`
  - `amp_mult = master · prox · w_zone`
  - `pw_mult  = 0.5 + 0.5 · prox`
  - `IsMuted  = (prox == 0) or (w_zone < ε)`

Cardinal positions excite exactly one zone; 45° positions excite the two
neighbours at equal weight (≈0.5 each).

## Bone / channel mapping (Teslasuit 4R)

Same map as `haptic_navigation`, verified on the reference suit:

| Body area              | bone_id | channels      | direction (θ_zone) |
|------------------------|---------|---------------|--------------------|
| Abdomen (belly)        | 8       | 0..7          | forward  (+π/2)    |
| Back                   | 11      | 0..7          | backward (−π/2)    |
| Left upper-arm front   | 12      | 0..2          | left     (+π)      |
| Right upper-arm front  | 14      | 0..2          | right    (0)       |


