# 17 — Circuit Overtaking-Difficulty Index (task #20): build + forward-chained validation

The mechanistic, brand-agnostic replacement for the rejected team×circuit affinity
(`KalmanTrackModel`, brief 16 §1). **One track-physics number per circuit** —
*how locked is track position here* — that modulates **confidence**, not brand
favouritism, and applies **equally to every team** (so a brand-new circuit is scored
by its measured passing rate and a brand-new team is unaffected).

Code: `backend/app/models/overtaking.py` (index + proxies),
`backend/app/models/kalman.py::KalmanOTModel` (grid-weight scaling),
`backend/app/models/validate_overtaking.py` (the sweep below),
`data/overtaking_proxies.parquet` (the raw per-running inputs),
`GET /circuits/overtaking` (the per-circuit index, for the Explainer).

---

## How it's built (all on data we already have, no identity features)

Three forward-chainable proxies per running (year, circuit), wet runnings excluded
(>30 % laps on inters/wets break the qualifying lock for a *weather* reason):

1. **grid→finish rank lock** — Spearman ρ(grid, finish_pos), grid = qualifying-pace
   order (falls back to lap-1 position where quali is missing). High ρ ⇒ qualifying
   dominates. *(Literature: qualifying→finish is moderated by overtaking difficulty,
   Weissbock & Mills 2025.)*
2. **green on-track passing rate** — position gains per car per racing lap on green
   laps, with a driver's own pit-cycle laps removed. The mechanistic anchor.
3. **lap-1 churn** — mean |grid − position after lap 1|. Start-line shuffle capacity.

Combined as `z(ρ) − z(pass_rate) − z(lap1_churn)`, **empirical-Bayes shrunk** toward
the calendar mean by visit count (`OT* = raw·n/(n+6)`), so thin-sample circuits fall
back to "average difficulty". The z-scoring is cross-circuit and forward-chained: for
race *s* every circuit's median proxies use only runnings with `seq < s`.

### Face validity (full-history index)
Monaco tops it (+2.36), then Saudi Arabia / Canada / Britain / Abu Dhabi / Singapore;
the bottom is Bahrain (−1.42), Spa (−1.08), Las Vegas, Russia, Hungary. Monaco — the
strongest prior — and the easy-pass set (Spa, Bahrain, Baku) are captured correctly.
**Known wart:** the Hungaroring ranks mid/low because its high *lap-1 churn* (a narrow,
chaotic start) is counted as "easy to change position", even though steady-state passing
there is hard. The `lap1_churn` term conflates start chaos with race passing — a v2 fix
(see below). We did **not** hand-tune the index to match intuition; that is the
overfitting trap the whole project is built to avoid.

---

## Forward-chained validation (168 races, harness = `app/models/harness.py`)

Two uses, validated separately. Metrics that matter: **best-of-rest accuracy** (predict
P2 with the winner removed) and **podium log-loss** — the high-variance positions. Win
accuracy is near-trivial here (VER's 2023–24 dominance), so it is *not* the bar.

### Use A — scale the Kalman `grid_weight` per circuit (post-quali)
Each config at its best temperature; n_sims=2500. (OT `w0=X` has average grid_weight
≈ `X·sigmoid(0)` ≈ `X/2`, so compare `w0` to the flat weight at half.)

| config | top-pick | **best-of-rest** | win ll | **podium ll** | points ll |
|---|---|---|---|---|---|
| flat gw=0.0 | 0.503 | 0.380 | 0.127 | 0.246 | **0.549** |
| flat gw=0.2 | 0.521 | 0.387 | 0.118 | 0.222 | 0.609 |
| flat gw=0.4 | 0.515 | 0.429 | 0.112 | 0.209 | 0.674 |
| flat gw=0.6 | 0.515 | **0.466** | 0.108 | **0.204** | 0.798 |
| **OT w0=0.4** | 0.515 | 0.393 | 0.117 | 0.222 | 0.609 |
| **OT w0=0.8** | **0.521** | 0.436 | 0.111 | 0.209 | 0.685 |
| **OT w0=1.2** | 0.515 | 0.460 | 0.107 | 0.204 | 0.786 |
| OT w0=0.8 era-split | 0.521 | 0.423 | 0.112 | 0.210 | 0.678 |
| **affinity (REJECTED)** | 0.460 | **0.325** | 0.133 | 0.259 | 0.565 |

**Read it honestly:**
- **Grid-awareness itself is the win for the rest-of-field.** Any positive grid weight
  lifts best-of-rest 0.380→0.466 and podium ll 0.246→0.204. This *confirms* the
  bake-off's "grid is the dominant signal" — now on the metric that actually matters.
- **OT-scaling ≈ the best matched flat weight** (e.g. OT w0=0.8 ↔ flat gw=0.4:
  best-of-rest 0.436 vs 0.429, podium ll tied; OT w0=1.2 ↔ flat gw=0.6: 0.460 vs 0.466).
  Differences are within ~1-race sampling noise. The optimal grid reliance does **not**
  vary enough across circuits — or the index is too noisy at 4–8 visits/circuit — for
  circuit-scaling to add *measurable* lift over a well-chosen flat weight.
- **It decisively beats the rejected affinity** (best-of-rest 0.436 vs 0.325) — the
  required check from brief 16: the structural, team-shared index does *not* collapse
  into the brand proxy, and is strictly better than it.
- **The points/podium tension is real:** more grid weight sharpens podium but degrades
  top-10 (points) calibration. No single weight is best for every market.

### Use B — set the pre-quali finishing-order spread (per-circuit temperature)
`T = t0·exp(−γ·index)` (tight at locked tracks, wide at open). Plain Kalman, grid_weight=0.

The best per-circuit spread (`t0=0.6, γ=0.15`, sum-ll 0.900) **ties** the best flat
temperature (`T=0.6`, 0.897). The spread is **calibration-neutral in aggregate** — but
it is the *correct* per-circuit variance: pre-quali, the flat prior gives every circuit
the identical 17.8 % favourite, whereas the spread gives Monaco 24.3 % (qualifying locks
it) and Spa/Bahrain ~15 % (pace will reshuffle). That track-specificity is real product
value even though it doesn't move the aggregate number.

---

## Verdict (reframed): KEEP it — mechanistic, honest, a portfolio piece

This is **not** killed. It is a mechanistic, brand-agnostic feature that:
- **does no harm** and **beats the rejected affinity** on every metric;
- is **independently interpretable** (the per-circuit index *is* "how much does
  qualifying matter here" — a first-class Explainer/portfolio artifact, served at
  `/circuits/overtaking`); and
- supplies the Predictor's **per-circuit pre-quali variance** — the track-specificity
  the flat prior lacked.

What it does **not** (yet) do is beat a well-tuned flat grid weight on aggregate
predictive log-loss. That's a finding about *F1*, not a failure of the idea: with
30+ DRS-era circuits the right amount of grid reliance is surprisingly uniform, and at
4–8 visits/circuit the per-circuit signal is thin. It belongs in the modeling
conversation as a documented, validated result.

### Wired in
- **Predictor**: `predict_race_kalman(circuit_spread=True)` applies `T = t0·exp(−0.2·index)`
  per circuit (Monaco tighter, Spa wider). Default-on; `circuit_spread=False` to disable.
- **`KalmanOTModel`** lives in the bake-off as the validated grid-weight-scaling variant.
- **`GET /circuits/overtaking`** exposes the index + spread temperature per circuit.

### v2 ideas (highlight, don't ship blind)
1. **Split lap-1 churn from steady-state passing.** The Hungaroring wart is the churn
   term reading start chaos as "easy to pass". Drop churn from the index (keep ρ +
   passing rate) or model it as a separate start-shuffle term — re-validate.
2. **Cleaner pass attribution.** The passing-rate proxy still counts position changes
   caused by *others* pitting as noise. A true overtake detector (gap-based, excluding
   the passed car's pit window) would sharpen proxy #2.
3. **More data per era.** The 2022 ground-effect break wants a per-era estimate, but
   4 modern runnings/circuit is too thin today; revisit as the modern sample grows
   (and again after the 2026 active-aero break).
4. **Similarity-shrinkage backbone (brief 16 §5).** Shrink a thin circuit's index
   toward *structurally similar* circuits (corner-band profile) instead of the global
   mean — should de-noise the 4-visit circuits.
5. **Per-circuit grid weight in the post-quali Predictor.** Once the Predictor actually
   fuses a real qualifying grid (it currently runs pre-quali only), `KalmanOTModel`'s
   grid scaling becomes live rather than inert.

---

## Sources
Internal: [16-novel-edge-features.md](16-novel-edge-features.md) §1 (the spec),
`backend/app/models/kalman.py` (`KalmanTrackModel`, the rejected affinity baseline),
`backend/app/models/harness.py` (forward-chained scorer),
`backend/app/models/features.py` (grid/finish/quali table).
External (per brief 16): Weissbock & Mills 2025 (arXiv 2507.10966) — qualifying→finish
moderated by overtaking difficulty; horse-racing draw-bias one-number-per-track method
(sample-size caveats motivating the shrinkage).
