# 18 — Structural Safety-Car / Caution Index (task #21): build + forward-chained validation

Brief 16 §3, built. A **race-level SC prior from measurable track structure** — not
circuit identity — that a brand-new street circuit would inherit from its *structure*
once raced, applied equally to every team.

Code: `backend/app/models/sc_index.py` (model + forward-chained eval),
wired into `predict_kalman.py` (`RaceSimResult.sc_probability`) and served at
`GET /circuits/safety-car`. SC label = any lap with `track_status` ∈ {4,6,7} (SC/VSC),
via `hazard._sc_active_laps`. Structural features reuse `overtaking_proxies.parquet`.

---

## How it's built (≤4 pre-registered terms, no identity features)

Per race, P(any SC) from a small logistic:
- **`circ_pass`** — median green on-track passing rate over the circuit's *prior*
  runnings (low passing ⇒ narrow/walled ⇒ more cautions). The structural anchor.
- **`circ_churn`** — median lap-1 churn over prior runnings (start-funnel chaos).
- **`circ_rate`** — empirical-Bayes shrunk per-circuit historical P(any SC) (the
  brand-proxy term, shrunk hard toward the calendar mean by visit count).
- **`wet`** — race ran >30 % laps on wet/inter rubber. *Contemporaneous* (a true
  pre-race prior needs a rain forecast — see v2).

All forward-chained (each circuit's features use only `seq < s`); unseen circuits fall
back to the calendar median. We estimate a **prior intensity**, never "SC in the next N
laps" (near-Poisson noise — the trap doc 10 flagged).

---

## Forward-chained validation (142 scored races)

| model | Brier | log-loss |
|---|---|---|
| **base rate** (constant 0.726) | **0.2159** | **0.6298** |
| per-circuit shrunk rate (brand proxy) | 0.2194 | 0.6435 |
| structure-only (`circ_pass`+`circ_churn`+`wet`) | 0.2170 | 0.6335 |
| full (structure + shrunk circ_rate) | 0.2165 | 0.6329 |

Coefficients (full, log-odds): `circ_rate +2.29`, `wet +0.53`, `circ_pass −0.18`,
`circ_churn −0.01`. Signs are all mechanistically correct (less passing → more SC; wet →
more SC), and `circ_churn` carries ~nothing.

**The honest headline: nothing beats the base rate.** At the race level, whether a given
race throws a caution is dominated by race-day randomness; the structural and historical
terms don't improve probabilistic prediction over "72.6 % of races have one." The
per-circuit rate is actually *worse* than the base rate (it over-commits to thin-sample
circuits that then don't conform). Predicting the SC **count** (`n_periods`) is the same
story: forward-chained MAE 0.824 (per-circuit shrunk) vs 0.821 (flat mean) — a tie.

**But the cross-sectional structure is real and strong.** Pooled, per-circuit:
`SC-rate ~ passing-rate r = −0.39`, `n_periods ~ passing-rate r = −0.43`, and
`n_periods ~ passing-rate (per-race) r = −0.34`. Walled/street circuits genuinely have
more cautions — the *ordering* is right (Baku 0.79, Jeddah 0.78, Mexico/Qatar 0.77 high;
Hungary 0.63, Spain 0.66, Japan 0.67 low). What's missing is *race-level predictability*,
not the structural relationship — because SC is a Poisson shock on top of that ordering.

---

## Verdict (reframed): KEEP it — correct ordering, honest about what it can't do

Per the owner's bar (don't bin mechanistic features; explain why they underperform):
this is a **kept, brand-agnostic structural index** whose value is the **cross-sectional
ordering** (r ≈ −0.4), used for:
- **Sim / scenario realism** — the engine should fire more cautions at Baku than Hungary;
  the structural prior supplies that ordering (the Predictor showed a hardcoded
  `sc_probability = 0.0` before this).
- **Explainer / Methodology page** — "chaos-prone circuits", a clean structural story.

What it is **not**: a calibrated race-level SC *predictor*. It does not beat the base
rate, so we do not claim an edge — the displayed prior is honestly within base-rate
noise, used for ordering/realism. This converges with doc 10's near-Poisson warning and
doc 11's single-station-weather limit.

### Wired in
- **Predictor**: `RaceSimResult.sc_probability` now = `sc_index.sc_probability(circuit)`
  (fail-safe to 0). Monaco 0.73, Baku 0.79, Hungary 0.63.
- **`GET /circuits/safety-car`** exposes the per-circuit prior for the Explainer.
- `refresh.py` refits the model + busts its cache on ingest.

### v2 ideas
1. **A-priori geometry from `get_circuit_info()`** — corner count / corner density / lap
   distance + a street-circuit flag give a structural prior for a *never-raced* circuit
   (our current `circ_pass`/`circ_churn` need ≥1 prior running). Shared pull with #22.
2. **Rain forecast, not a contemporaneous wet flag** — Open-Meteo historical-forecast for
   a leak-free pre-race rain probability (doc 11), so `wet` becomes predictive not just
   explanatory.
3. **Lap-window SC *intensity* into the sim** — feed `n_periods` (not just the binary) as
   the sim's expected caution count for richer Scenario Runner realism.
4. **Cause-split** — separate lap-1-contact cautions (start-funnel) from mid-race debris;
   the structural drivers differ and may be individually more predictable.

---

## Sources
Internal: [16-novel-edge-features.md](16-novel-edge-features.md) §3 (the spec),
[10-novel-approaches.md](10-novel-approaches.md) (SC is near-Poisson; don't forecast
short-horizon), [11-inplay-latency-and-weather.md](11-inplay-latency-and-weather.md)
(single-station weather), [15-hazard-dnf-model.md](15-hazard-dnf-model.md) +
`backend/app/models/hazard.py` (`_sc_active_laps`, the SC-restart pathway this feeds),
[17-overtaking-difficulty-index.md](17-overtaking-difficulty-index.md) (the passing-rate
proxy reused here). External (per brief 16): Axiora / f1technical SC-by-circuit;
DeepWiki incident-probability models.
