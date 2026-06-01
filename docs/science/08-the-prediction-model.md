# 08 — What *Is* the Prediction Model?

A plain, honest description of what kind of model F1Predict actually is, what each
part is calibrated on, and — importantly — what it is **not**.

## It is a mechanistic Monte Carlo simulator, not a trained black-box

F1Predict is **not** a single supervised ML model that maps features → win
probability (no neural net, no end-to-end gradient-boosted classifier). It is a
**generative, mechanistic simulator**: it *plays out* each race lap-by-lap,
~10,000 times, with random events, and **counts** how often each driver finishes
where. The probabilities are frequencies over simulated races, not the output of a
learned probability function.

This is the same family as the academic reference (Heilmeier/TUM) — a "forward
simulation" — as opposed to (a) a discriminative ML model (logistic/boosted trees on
features) or (b) a Bayesian hierarchical rating model.

## What each component is calibrated ("trained") on

The simulator's *inputs* are calibrated from real **2023–24 F1 data (FastF1)**,
component by component. Most are simple statistical fits, not heavy ML:

| Component | Method | Calibrated from |
|---|---|---|
| **Base lap time** (per circuit) | fastest fuel-corrected clean lap | race laps (or FP laps in the leak-free backtest) |
| **Tyre degradation** (3-phase θ curve, per circuit×compound) | bounded least-squares fit (`scipy` SLSQP) on fuel-corrected, stint-relative lap times | race long runs (FP long runs in the leak-free version) |
| **Per-team tyre multiplier** | linear regression of deg-vs-age slope per team ÷ field slope | race laps |
| **Driver pace offset** | each driver's 20th-percentile fuel-corrected pace vs the field median | race laps (prior races only, in the leak-free version) |
| **Fuel effect** | physics (linear ~0.03 s/kg) | domain knowledge (not fit) |
| **Safety-car model** | empirical count/start/duration distributions | TUM published params (2014–19) |
| **Execution noise** | positively-skewed (skew-normal) | literature (state-space paper); σ hand-set |
| **Race-form variance** (`FORM_SIGMA_S`) | hand-set hyperparameter | tuned via the market backtest |

So "what is it trained on?" → **real 2023–24 F1 race (and practice) timing data**,
used to *calibrate physical/statistical coefficients*, not to train one big model.

## How a prediction is produced

Given a circuit (its calibrated params) and a grid of drivers (pace offset, starting
position, team tyre multiplier, a strategy), the engine runs 10,000 simulated races.
Each simulated lap, every driver's time = base + fuel + tyre-deg(×team) + compound
offset + driver pace + skewed noise; safety cars, DNFs, pit stops, and a whole-race
"form" offset are sampled. Drivers are ranked by cumulative time each sim → counts →
win/podium/points probabilities and the finishing-position distribution.

## What it is **NOT** (and known limits)

- **No LightGBM / ML residual layer (yet).** The original research doc proposed one;
  it is an *unbuilt roadmap item*. Today the model is deterministic physics +
  calibrated coefficients + stochastic sampling. There is no learned residual.
- **No overtaking / track-position model.** Drivers are ranked purely by cumulative
  time, so a faster car passes freely. This is the single biggest weakness — it means
  the model **over-weights raw season pace and under-weights the actual grid**, which
  is why it tends to favour the same driver every race and **loses to the market**.
- **Overconfident** (tempered, not fixed) — see the backtests.

## Why this design (the trade-off)

A learned discriminative model might *predict* slightly better, but it would be a
black box — useless for the strategy/explainer use-case that is the heart of this
app. The mechanistic simulator is fully **interpretable**: every number traces to a
physics or strategy reason, which is exactly what powers the Strategy Lab, the
Explainer, and the "what-if" capability. The backtests (`docs/science/07`,
`forward_backtest.py`) are how we keep it honest about how good its *predictions*
actually are: leak-free top-pick accuracy **31.7%**, and the market beats it — so we
trust it for **strategy insight**, not for beating betting markets.
