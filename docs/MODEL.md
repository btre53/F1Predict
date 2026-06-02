# F1Predict — the model, what we tested, and what we found

The honest, consolidated story of the predictive model: what ships, every alternative we
tried, and the findings that shaped it. Detailed evidence lives in `docs/science/` (briefs
01–20); this is the canonical summary (and the source for the in-app Methodology page).

---

## What ships: the production Predictor

A **time-local Kalman car + driver pace filter → Plackett-Luce Monte Carlo → finishing
distribution**, with mechanistic add-ons. Pipeline:

1. **Kalman pace filter** (`app/models/kalman.py`). Each **car (team)** and **driver** carries
   a Gaussian belief over pace in per-race z-units. It's **forward-chained** over every race
   (2018→2026): qualifying and finishing-position observations update the beliefs; variance
   inflates between races and at season boundaries (form drift, upgrades, rule changes). A
   moved driver inherits the **new car** (strength = car.μ + driver.μ) — the whole point of the
   car/driver split. Leak-free by construction.
2. **Pre-quali vs post-quali.** Pre-quali the strength is just car.μ + driver.μ — an honestly
   *tight* field (~18–24% favourite). **Once qualifying happens we fuse it** (`predict_kalman.py`,
   `use_quali`): the filter folds the real quali pace into each prior and adds a **circuit-scaled
   grid weight** (the overtaking index, below). This sharpens toward the grid exactly as the
   bake-off validated (best-of-rest 0.32→0.44, podium log-loss 0.27→0.21).
3. **Plackett-Luce Monte Carlo** (`probability.py`). Gumbel-max sampling = exact PL draws of the
   finishing order, at a forward-chain-calibrated **temperature** (0.5), giving the full
   per-driver finishing-position distribution (win / podium / points / P10–P90).
4. **Hazard DNF** (`hazard.py`). A discrete-time logistic survival model (grid, first-lap,
   SC-restart, team reliability, era) censors each sim — pole ~2% vs P20 ~16% DNF, replacing a
   flat 8%. Beats the flat baseline forward-chained (per-race DNF log-loss 0.337 vs 0.399).
5. **Mechanistic, brand-agnostic track features** (the research arc):
   - **Overtaking-difficulty index** (#20) — one track-physics number/circuit (grid→finish lock
     + green passing rate + lap-1 churn) that sets the **per-circuit finishing spread** (Monaco
     tight, Spa wide) and **scales the post-quali grid weight**.
   - **Structural SC prior** (#21) — per-circuit caution likelihood from street-ness; shown as
     the Predictor's `sc_probability` (realism, honest non-edge).

Everything is **free-data** (FastF1 + Polymarket for comparison only); the app degrades to a
committed snapshot when live feeds are down.

---

## The bake-off: every model we tested

A shared **forward-chained, calibration-first harness** (`app/models/harness.py`) scored each
model leak-free over 168 races. Headline: **they all cluster ~63% top-pick and barely beat a
10-line grid+quali baseline — the signal is the grid/qualifying.**

| Model | What | Verdict |
|---|---|---|
| **Baseline** | grid + quali, 10 lines | The bar everything must beat |
| **PL-Glicko rating** | sequential rating, grid-aware | ≈ baseline |
| **Kalman pace filter** | car+driver Gaussian filter | **Shipped** — best calibration, interpretable |
| **LightGBM ranker** | gradient-boosted features | ≈ baseline; less interpretable |
| **Mechanistic Monte Carlo** | per-lap pace + tyre + pit sim | **Superseded** — lost badly (~31.7% top-pick); kept for Strategy Lab |
| **Kalman + team×circuit affinity** | "does this car suit this track" | **Rejected** — overfit, made every metric worse monotonically |

**Why the Kalman won:** best-calibrated, fully online (the same `update()` is the post-race
retrain), and interpretable (a pace number per car and driver). Grid-awareness was the key fix
for the rating/Kalman models. The mechanistic sim's extra physics added noise faster than
signal for *finishing order* (see `docs/MODEL_ROADMAP.md` for why, and how a future structural
sim could be made both complex and accurate).

---

## What we found (the honest findings — settled, don't relitigate)

- **Grid / qualifying dominates finishing order.** Fancy models barely beat the grid+quali
  baseline; the winner is near-trivial (pole), the variance is in the rest-of-field.
- **No edge vs the pre-race outright market** (brief 07): the market is efficient.
- **No in-play edge** (brief 13): our live win-prob is well-calibrated (Brier ~0.048) but does
  **not lead** the market — the detrended increment cross-correlation is flat at every lag; a
  lap-completion engine structurally lags real-time ~90 s.
- **No timing edge at T-12 h** (early line ≈ closing line) and **market-making is negative-EV**
  for retail on a news-gapping binary (brief 14).
- **Telemetry driving-*style* doesn't separate racecraft** from the car at the reliable grain
  (brief 12); a paid live-telemetry feed would mostly re-derive what we get free from lap timing.
- **Team×circuit affinity overfits** (~5–8 visits/circuit is race-day variance, not stable
  suitability). The principled, brand-agnostic replacement is the **overtaking-difficulty index**
  (#20) — it modulates *confidence*, applied equally to every team, not brand favouritism.
- **Mechanistic edge features, validated honestly** (briefs 16–20): the overtaking index (kept;
  ties a tuned baseline, beats the affinity), the structural SC index (kept for ordering; SC is
  near-Poisson so it doesn't beat the base rate), car-DNA corner-bands (real + interpretable but
  zero incremental lift — Explainer only), and a per-compound tyre-degradation re-fit (finding:
  the log form is **not** best for the 2022+ ground-effect era — linear/quadratic win).

**The bottom line:** the model's value is **calibration + transparent, interpretable tooling**
(the "anti-AWS": every number is explainable), **not** a betting edge. That's the honest pitch.

---

## How it's validated (and why you can trust it)

- **Forward-chained, leak-free.** For each race in chronological order we predict using only
  strictly-prior races, score, then fold the result in. This is **stronger than a season-aware
  train/test split** — the model never sees any future race, not just future seasons.
- **Calibration-first.** We tune a single temperature on win log-loss and report reliability,
  Brier, and log-loss for win/podium/points — plus **best-of-rest accuracy** (predict P2 with
  the winner removed), the high-variance metric that actually matters given VER's 2023–24
  dominance.
- **Honest negatives are kept.** Rejected/under-performing ideas (affinity, mechanistic sim,
  in-play edge, telemetry style) are documented as findings, not hidden.

Current forward-chained numbers (post-quali, the meaningful metrics): top-pick ~0.51,
best-of-rest ~0.44, podium log-loss ~0.21. Pre-quali is honestly tighter and sharpens once a
grid is fused.

---

## Where the model could go next

Parked, post-deploy, in **`docs/MODEL_ROADMAP.md`**: the ambitious structural sim (anchored to
the Kalman + ensembled so it can't be worse), weather-as-variance, a qualifying-prediction
model, a market-anchored (Benter) ensemble, per-circuit degradation, and the open research
questions from briefs 16–20. These are an ongoing hobby, not a deployment blocker.
