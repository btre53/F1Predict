# 25 — Does a stronger car lose less in dirty air? (the win/podium-gap probe)

_Task #23. The final comparison (brief 22) showed the physics sim trails the rank model on
win/podium log-loss — research suggested it over-disperses the front because it applies
field-average penalties to cars that should shrug them off. We tested the headline fix —
"stronger cars lose less in dirty air, so scale the wake penalty by strength" — directly on the
data. **Verdict: rejected for the per-lap penalty, but it produced a great explainability finding.**_

## Method

`dirty_air.strength_dependent_dirty_air()`. For every 2023+ following-lap (OpenF1 gap-to-car-ahead
within 0–4 s), take the fuel/tyre-corrected lap-time EXCESS over that car's own clean-air baseline,
and bucket by the **following car's strength** — its own clean-air pace gap to the race's fastest
(STRONG < 0.5 %, MID 0.5–1.5 %, SLOW > 1.5 %). Report the close-gap (< 1 s) penalty per bucket.

## Result — the opposite of the hypothesis

| Following car | close-gap (<1 s) penalty | by gap: 0–0.5s / 0.5–1s / 1–1.5s |
|---|---|---|
| **STRONG** (fast car) | **1.31 s/lap** | 1.66 / 1.26 / 0.62 |
| MID | 0.76 s/lap | 1.24 / 0.67 / 0.43 |
| SLOW | 0.46 s/lap | 0.98 / 0.36 / 0.24 |

A **stronger** car loses **more** per lap stuck in traffic, not less. The reason is a confound we
flagged up front: a fast car stuck behind a slower one is being **held up**, and that pace-mismatch
loss dwarfs any aerodynamic-wake benefit. So the naive fix — `L_max = L0·(1 − α·strength)`, scaling
the wake down for strong cars — is **rejected by the data** at the per-lap grain.

## What it means

1. **For the model (honest negative):** scaling the dirty-air wake by strength would make the sim
   *worse*, not better — it points the wrong way. The win/podium over-dispersion is **not** fixed
   by a strength-scaled per-lap wake.
2. **The real lever is track-position PERSISTENCE, not the per-lap wake.** The over-dispersion
   comes from the sim shuffling the clean-air leader backwards too easily (noise/SC re-rolls
   position every lap); a rating model implicitly keeps a dominant car in front. The fix is an
   overtake-threshold / "a clean-air leader with a pace surplus is near-unpassable" model — a
   bigger change, and one this per-lap measurement does **not** support shortcutting. Left as the
   open lever (MODEL_ROADMAP).
3. **The explainability win (why this was worth doing):** the finding quantifies *why track
   position is gold*. A fast car stuck in traffic bleeds **~1.3 s/lap** — that's the concrete cost
   of starting/being out of position, and exactly why qualifying dominates finishing order and why
   the leader checking out into clean air is so decisive. It's also why the rank model wins at the
   front: it bakes in "fast cars qualify ahead and stay ahead," while the sim keeps re-rolling the
   lead and then — by our own number — makes the shuffled-back fast car pay 1.3 s/lap.

## Caveat / v2

The per-lap penalty conflates **aero wake** with **being-held-up**; the held-up effect dominates
for strong cars. The agent's outcome-level hypothesis (strong cars *clear* traffic faster via
DRS/top speed, so lose less *total*) is untested here — it needs **overtake-event detection**
(laps-stuck-behind by strength, from lap-to-lap position changes), not the per-lap penalty. That
is the honest next probe before any strength-aware overtake model.
