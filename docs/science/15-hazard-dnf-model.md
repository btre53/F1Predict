# 15 — Survival/Hazard DNF Model (brief 10 §2)

Replaces the Monte Carlo sim's **flat per-race retirement rate** (`montecarlo.DriverParams.
dnf_prob = 0.08`, same for everyone) with a **discrete-time hazard** that makes DNF risk
lap- and context-dependent. Motivation: attrition is a huge driver of finishing-position
props (points-finish, podium-without-favourite, top-6/10) and of the sim's realism — and a
flat rate can't say "a back-of-grid car on lap 1 is far more likely to retire than the pole
sitter at half-distance."

**Model** (`app/models/hazard.py`): `P(DNF on lap k | survived to k) = sigmoid(beta·x)`,
logistic, on a pre-registered ≤6-term covariate set (overfitting is the enemy at ~105 races):
`lap_fraction`, `early_lap (k≤2)`, `is_sc_restart`, `grid_norm`, `team_prior` (empirical-Bayes
shrunk constructor DNF rate, forward-chained), `era ((year−2018)/8)`. DNF flag + cause come
from FastF1 results `ClassifiedPosition`/`Status` (offline, `data/results.parquet`: 2099
car-races, 193 DNFs — 142 mechanical, 45 collision). Person-lap survival table = 98,823 rows.

## Results — forward-chained over 90 races (leak-free)

| Metric | hazard | flat baseline |
|---|---|---|
| per-race **P(DNF)** Brier | **0.0790** | 0.0824 |
| per-race **P(DNF)** logloss | **0.337** | 0.399 |
| per-lap hazard logloss | 0.0101 | 0.0107 |

The hazard model **beats the flat rate** — modestly on Brier, **16% on logloss** (the
calibration metric that matters), by knowing *which* cars are at risk. Per-lap Brier is
uninformative (events are ~0.2%/lap, so everything rounds to zero).

**Coefficients (log-odds, full-data fit):**

| term | coef | reading |
|---|---|---|
| grid_norm | **+2.18** | back of grid = much higher attrition (the dominant signal) |
| early_lap | **+1.42** | first-lap contact spike |
| lap_fraction | −1.14 | conditional on surviving the start, per-lap risk *falls* — DNFs are front-loaded |
| era | −0.36 | modern cars finish more often |
| is_sc_restart | −0.24 | restarts not distinctly riskier here (weak) |
| team_prior | −0.10 | ~nil — **collinear with grid** (weak teams start at the back), so grid absorbs it |

**Predicted spread (vs the old flat 0.08 for everyone):** pole **2.7%**, P5 4.1%, P10 7.0%,
P15 11.7%, P20 **19.4%** (Ferrari, 2024, 60 laps). Far more realistic attrition.

## Status & integration

- **Validated and pluggable.** `fit_full_model()` → `(clf, team_prior)`; `race_dnf_prob(...,
  grid, team, year, total_laps)` returns a pre-race per-car P(DNF) — a **drop-in for the sim's
  flat `dnf_prob`**. (Wiring it into `montecarlo.py`/`GridEntry` is the next integration step,
  not yet done.)
- **Honest limits:** team reliability is collinear with grid, so we don't get an independent
  constructor-reliability signal beyond starting position; `is_sc_restart` carries little.
  Cause split (mechanical vs collision) is captured in the data but not yet used as separate
  hazards — a future refinement.
- **Why it matters now:** sharper attrition feeds the **props** lane (the surviving edge
  candidate) and the **scenario runner's** SC/DNF realism — not the (null) in-play trade.
  It also lets the WPA harness (brief 13) be re-run with a smarter DNF jump intensity for an
  event-window lead re-test.

_Artifacts: `app/models/hazard.py`, `app/etl/results.py`, `data/results.parquet`._
