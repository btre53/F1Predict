# The model journey — notes for the website write-up

_Raw material for a visitor-facing "how we built this model" story: from the first naive sim,
through the bake-off, to the decoupling deep-dive we're doing now — and the metrics that judged
every step. Bullet notes; to be turned into prose + visuals later. Newest learnings at the bottom._

## Act 1 — the naive start
- We began with a **mechanistic Monte Carlo**: simulate every car's lap times (pace + fuel +
  tyre + pit stops), rank by total race time. The intuitive "physical" model.
- It **lost badly** forward-chained (~31.7% top-pick vs the market's ~36%). Lesson #1: a detailed
  physical sim that predicts a high-dimensional intermediate (every car, every lap) compounds
  small errors and is over-confident — more physics ≠ better probabilities.

## Act 2 — the bake-off (let the data pick the model)
- Built a **forward-chained, calibration-first harness**: for each race in time order, predict
  using only strictly-prior races, score, then fold the result in. Leak-free by construction.
- Tested: grid+quali **baseline**, **PL-Glicko** rating, **Kalman** car+driver pace filter,
  **LightGBM** ranker, the mechanistic sim, and a team×circuit **affinity**.
- Result: they all cluster ~63% top-pick and barely beat a 10-line grid+quali baseline.
  **The signal is the grid / qualifying.** The **Kalman won** (best-calibrated, online, interpretable).
- Affinity was **rejected** (overfit at ~6 visits/circuit); kept as a documented negative.

## Act 3 — the honest negatives (what doesn't work, kept on the record)
- **No edge vs the pre-race market** (it's efficient). **No in-play edge** (our live prob is
  calibrated but lags the market ~90s). **No timing edge** at T-12h. **Market-making is -EV.**
- **Telemetry driving-style doesn't separate racecraft** from the car at a reliable grain.
- We keep every negative — the honesty IS the product (the "anti-AWS": every number explainable).

## Act 4 — mechanistic, brand-agnostic features (track physics, not brand bias)
- **Overtaking-difficulty index** (#20): one track number → per-circuit finishing spread + grid weight.
- **Structural safety-car prior** (#21): caution likelihood from street-ness (realism, not edge).
- **Hazard DNF model**: per-driver retirement risk (grid/first-lap/era) beats a flat 8%.
- **Car-DNA corner bands**: interpretable but not predictive over scalar pace (Explainer-only).
- **Weather-as-variance** (science/21): rain doesn't raise DNF and the wet favourite is already
  calibrated — but it scrambles WHO SCORES, so we widen only the points market in the wet.

## Act 5 — the decoupling deep-dive (where we are now)
- **The flagship sim, rebuilt right:** anchor it to the Kalman pace + **ensemble** so a learned
  weight can never make it worse than the rank model. The guarantee is proven forward-chained.
- **Found the bug that made the old sim "very wrong":** it re-applied a per-team tyre multiplier
  on top of Kalman pace (which already includes tyre management) → it crowned gentle-tyre teams
  regardless of speed. Removing it + calibrating the pace scale → the sim now beats the rank model.
- **The core idea:** the Kalman "strength" is a LUMP (fit on quali + finish) that conflates pace,
  tyre deg, reliability, racecraft, strategy. We're **decoupling it into measured components**,
  each traceable to observed data — never a generic "Team X is good on tyres" claim:
  - **Clean-air race pace** — fuel/tyre-corrected pace on un-trafficked laps (OpenF1 gaps).
  - **Dirty-air penalty** — MEASURED non-linear curve (worse the closer you are; +1.15s glued →
    0 by 3s), strongly per-circuit (slipstream tracks shrug it off; high-speed-corner / can't-pass
    tracks bite hardest) — it's the *type* of speed, not raw speed.
  - **Per-car tyre deg** — MEASURED from each car's own fuel-corrected stint slopes (not a team
    label). Proven a reproducible property (prior→next Spearman 0.305), ~±0.1 s/lap/lap spread —
    a real, modest effect, traceable to specific stints.
  - **Reliability** — DECOUPLED (`net_dnf`): a retirement no longer drags down the car's *pace*
    strength; reliability lives only in the hazard DNF model. Forward-chained calibration-neutral
    (the double-count was real but small) → adopted as the cleaner, more correct model.
  - **Grid** — we used to call "grid" the lap-1 timing-line position, which is *post-start* — it
    only matches the official grid 30% of the time (mean 1.7-place shuffle baked in). Swapped in
    the OFFICIAL grid (Jolpica, penalties applied); the lap-1 delta is now its own thing →
  - **Start performance** = official grid − lap-1 position. A big lap-1 shuffle (2.7 places std)
    but only a weak persistent driver skill (Spearman 0.13) — mostly variance, small per-driver
    bias (STR/MAG good starters, BOT/GRO poor — face-valid).
- **Free data that makes it traceable:** FastF1, Open-Meteo (weather), **OpenF1** (real gap-to-car-
  ahead, free historical), Jolpica (DNF causes). Prior art (Heilmeier/TUMFTM, state-space tyre
  models) validates the recipe.

## The metrics — how we judged every step (give this its own section on the site)
- **Forward-chained, leak-free**: predict each race from only its past; never sees the future.
- **Calibration-first**: a single temperature tuned on win log-loss; report **Brier + log-loss +
  reliability** for win / podium / points.
- **Best-of-the-rest accuracy**: predict P2 with the actual winner removed — the high-variance
  signal that matters given one car's dominance (the winner is near-trivial = pole).
- **Top-pick accuracy**, **per-race DNF log-loss** (vs a flat rate), and **vs the market** (Brier).
- For the sim specifically: judge on **best-of-rest / podium / points / props**, not who-wins.

## Visual ideas for the site
- The bake-off table (done, in FINDINGS). The ensemble slider (done). The animated rain (done).
- NEW: the dirty-air curve (penalty vs gap, with a per-circuit selector — slipstream vs high-speed).
- NEW: a "decomposition" diagram — the lumped strength fanning out into measured components.
- NEW: a forward-chaining animation (the train moving race by race, never looking ahead).
