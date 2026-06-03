# Model Roadmap — parked improvements & open questions

_Not blocking deployment._ The app ships with the model documented in `docs/MODEL.md`. This
file is the **post-deploy hobby backlog**: ideas to try, open questions from the research, and
the design for the "ambitious structural sim" — to be picked up in dedicated sessions, with
the Explainer write-ups of *what we changed and why* as an ongoing portfolio thread.

**Ground rules (unchanged):** mechanistic + brand-agnostic features only; forward-chained
validation; score on best-of-rest / podium (not win — VER 23/24 dominance makes win trivial);
keep a feature even if it only ties the baseline (document why), but don't make it the default
unless it beats a tuned baseline.

---

> **STATUS (2026-06-03): scaffolded — see `docs/science/22`.** The anchor+ensemble design
> below is built (`app/models/structural_sim.py` + `validate_structural_sim.py`). The
> **guarantee is proven forward-chained**: best ensemble weight w=0 (never worse than the rank
> model), pure sim reproduces the documented "loses badly" history. The **first-cut physics adds
> no skill on win/podium/points** (every w>0 degrades them), so it's kept as the scaffold, not
> flipped to production. v2 = score the **prop markets** the rank model can't produce (pit-window,
> podium-without-fav, lead-laps), per-car best-response strategy, calibrate-before-blend. The
> machinery makes all of that safe (anything added is ensembled behind w → worst case = anchor).

## The ambitious structural sim (per-driver lap-time → strategy-aware pit sim → field MC)

The natural "impressive" model: simulate every car's lap times (pace + fuel + tyre age +
traffic), let each optimise its pit strategy, Monte-Carlo the race seeded by Kalman pace +
hazard DNF + structural SC timing. **We have most of the pieces** (Strategy Lab lap-time/pit
engine, hazard, SC prior, overtaking index) but the closest existing version (the mechanistic
`montecarlo.py`) **underperformed the simple Kalman rank model** forward-chained (~31.7% vs
~63% top-pick). Here is **why it's flawed for prediction, and how to make it both complex and
accurate** — the design for a future build.

### Why it underperforms (the honest failure modes)
1. **Error compounding.** It predicts a high-dimensional *intermediate* (every car, every lap)
   and integrates; the rank model predicts the *target* (finishing order) directly. Small
   per-lap biases × ~57 laps × 20 cars compound into large order errors.
2. **Latent, endogenous strategy.** Pre-race we don't observe starting tyres or planned stops;
   teams choose optimally *and react* in-race. A fixed-strategy sim misprices systematically.
3. **Chaotic low-frequency events.** SC timing is near-Poisson (briefs 18/21) and reshuffles
   everything; undercut/overcut depend on traffic/track position we can't resolve pre-race.
   These add **variance, not accuracy**.
4. **Calibration.** Physically detailed sims tend to be over-confident (the old sim: ~92% on a
   ~61% favourite). More physics ≠ better-calibrated probabilities.
5. **The ceiling is real.** All our evidence: finishing order is mostly **grid + car pace**.
   The sim's extra physics buys little *on average for who-wins* — but it is genuinely valuable
   for **props** (pit-window, podium-without-favourite, points) and **scenario what-ifs**.

### How to make it complex AND accurate (the fix)
- **Anchor + ensemble.** Seed per-car pace from the **Kalman strengths** (inherits the rank
  model's calibration), then **blend the sim's finishing distribution with the rank model's**
  with a learned weight (Benter-style). This guarantees it is **≥ the rank model** — you can't
  do worse than the anchor, and the physics only helps.
- **Optimise strategy per car inside the field sim** (the Strategy Lab engine already does
  single-car optimisation; lift it to a best-response / Stackelberg field).
- **Monte-Carlo SC timing** from the structural SC **intensity** (#21) + a **dirty-air pace
  penalty** for traffic. Accept these widen intervals (good for props), not sharpen the mean.
- **Calibrate the output** (temperature / variance) forward-chained; **judge on prop logloss**
  (pit-window, podium-without-fav, points), not top-pick.
- **Re-target the goal:** ship it as the **props + scenario + Explainer** engine, with the
  rank model as the headline-order anchor. That's an impressive, interpretable, physically
  grounded model that is provably not worse than the baseline.

---

## Open questions (from the research, briefs 16–20)
1. **Energy-proxy tyre wear** — does `∫|a_lat|·v` / `∫|a_long|·v` per lap (free FastF1) improve
   degradation prediction beyond the tyre-age polynomial? (brief 20 open Q1)
2. **QSS racing-line accuracy** — can curvature/line from ~10 Hz X/Y give a QSS profile that
   adds predictive skill over the lap-wise model? (brief 20 open Q2; current first-cut tracks
   shape corr ~0.85 but is ~20–30% fast on lap time)
3. **Per-circuit degradation re-fit** — extend the per-compound era fit (#8A: log is *not* best
   for 2022+; linear/quadratic win) to per-circuit, and wire it into the sim's tyre model.
4. ~~**Weather-as-variance** (brief 16 §4) — Open-Meteo rain as a distribution-spread + DNF
   multiplier.~~ **DONE (2026-06-03), see `docs/science/21`.** Built the leak-free ETL
   (`app/etl/weather.py`, ERA5 archive, 13/14 vs FastF1 trackside). Findings: **DNF multiplier
   dead** (no wet/dry difference); **win/podium spread rejected** (the wet favourite is already
   calibrated); **but the points (top-10) market is over-confident in the wet** and a points-only
   wet widening beats the baseline (wet points ll 0.558→0.517) at zero cost — **wired** into
   `predict_kalman` (`weather_spread`, `T_points=T·(1+0.5·wet)`) + `GET /circuits/weather`.
5. **Temperature proxy** from single-station air/track temp + driving intensity — recover any
   MF-evo thermal sensitivity, or too coarse? (brief 20 open Q4)
6. ~~**Tyre warm-up**~~ **SCOPED (2026-06-03), verdict: DEFER.** Measured the first-laps-of-stint
   excess vs settled pace over 3757 stints: it's **confounded with the fresh-tyre advantage**
   (fresh AND cold → effects partly cancel: mean +0.31 / median −0.32 s/lap) and the track-temp
   dependence is weak (Spearman −0.15). Not cleanly separable without tyre-temp telemetry we lack
   — keep deferred (the unavailable-data tier).

## Why the sim trails the rank model on WIN/PODIUM — and how to close it (researched 2026-06-03)

The final comparison: the sim wins order-accuracy (best-of-rest) but LOSES win/podium log-loss.
Root cause (research-backed, brief sources below): the sim applies its stochastic terms
(dirty-air, SC shuffle, start jitter, per-lap noise, DNF) at **field-average magnitude, not
conditioned on car/driver strength**, so it over-disperses the FRONT — the dominant car's win
prob gets pulled toward the field. A Plackett-Luce rating model is implicitly heteroskedastic the
right way (win prob is a *saturating* function of the strength gap), so it nails dominant cars; a
physics sim re-rolls position every lap, giving trailing cars repeated independent chances to
leapfrog (error compounding). The same uniform noise is ~correct for the midfield → best-of-rest
is fine. So the owner's intuition is right: we're effectively applying penalties to the top cars
that they'd actually shrug off (their car/tech lets them clear traffic, warm tyres, avoid errors).

**Prioritized, free-data-measurable fixes (the path to beating the rank model at the front):**
1. ~~**Strength-dependent dirty-air** — scale the wake down for strong cars.~~ **TESTED, REJECTED
   at the per-lap grain (2026-06-03, brief 25, `dirty_air.strength_dependent_dirty_air`).** The data
   says the OPPOSITE: a STRONG car loses MORE per lap in traffic (1.31 s vs 0.46 s for a slow car)
   because being held-up by a slower car dominates any aero benefit. So this fix points the wrong
   way. **The real lever is #2 / track-position PERSISTENCE** (a clean-air leader is near-unpassable;
   the sim shuffles the lead too easily). Great explainability by-product: a fast car stuck in
   traffic bleeds ~1.3 s/lap = why track position/qualifying is gold. (Untested: do strong cars
   *clear* traffic faster — needs overtake-event detection, the honest next probe.)
2. **Car-dependent overtake threshold** from measured top-speed + DRS ΔSpeed (FastF1). Michelin:
   the pace advantage needed for a 20% overtake is ~1.3 s/lap, but ~0.2 s with DRS — so a fast,
   draggy-low car becomes correctly near-unpassable, killing spurious lead changes vs dominant cars.
3. **Heteroskedastic execution noise** — scale the skewed-noise σ + slow-tail by driver rating
   (elite drivers have lower lap-time variance + fewer errors). Cheap; tightens the front.
4. **Team-specific reliability hazard** (per team/PU, NOT per driver — reliability is car/era, not
   driver, per f1metrics) — stop a field-uniform DNF rate over-penalizing the reliable top teams.
5. **Team pit-stop execution** distribution (stationary time per team from pit timing) — removes
   pace-misattribution from slow stops.
6. **SC shuffle conditioned on track-position/gap** (a leader with a pit cushion keeps the lead) —
   lower confidence.

Validation loop: implement #1–#3, re-run forward-chained WIN/PODIUM log-loss; expect the front
tail to tighten toward the rank model while best-of-rest holds. Sources: Heilmeier/TUMFTM sim
(MDPI 2020), Michelin overtaking model (1.3s→0.2s DRS), f1metrics reliability, Henderson&Kirrane
P-L. NB: all of these only pay once the sim is anchored on the **clean-air pace** (not the lumped
strength) — else they re-introduce double-counts (cf. task #15).

## Other improvement ideas
- **Qualifying-prediction model** — predict the grid, then condition the race on it (closes the
  pre-quali gap probabilistically; today we only fuse the grid once quali has happened).
- ~~**Market-anchored ensemble (Benter)**~~ **DONE (2026-06-03), see `docs/science/23`.**
  Validated `probability.benter_blend` forward-chained over 23 Polymarket-priced races: an
  equal model+market blend beats **both** in-sample (0.161 vs model 0.177 / market 0.166) → the
  model carries independent signal; but out-of-sample the blend beats our model (0.175 vs 0.178)
  yet not the market (0.174) — calibration tool, not a market edge. v2: re-fit as the priced
  sample grows; per-market blend; add bookmaker odds.
- **The points/grid over-sharpening tension** — higher grid weight sharpens win/podium but
  degrades points (top-10) calibration; try a **per-market temperature** (separate for
  win/podium vs points) instead of one global T.
- **Per-circuit grid_w0 tuning** for the overtaking-scaled grid weight (#20) — currently a flat
  w0=0.8 scaled by the index; could tune w0 forward-chained.
- **Regime-switching plumbing** (brief 10) — wet/dry, SC/green regimes as sim modes.
- **Car-DNA (#22) as a prior**, not a predictor — its corner-band factors could *initialise* the
  Kalman car term for a new team/car before any 2026 race (cold-start), even though it carried
  no incremental predictive lift on its own.

## Data sources to add (all free)
- **Open-Meteo historical-forecast** — leak-free pre-race rain probability (for #4 above).
- **Pirelli compound allocation** per race — constrains the strategy sim.
- **FP long-run pace** — already ingested (`practice.parquet`); underused in the Predictor.
- Sprint sessions; per-circuit pit-lane loss (derivable from our laps).

---

_When picking any of these up: branch, validate forward-chained on best-of-rest/podium, write
the Explainer note (what changed + why + the number), and only flip the production default if it
beats the tuned baseline. Otherwise keep it documented and move on._
