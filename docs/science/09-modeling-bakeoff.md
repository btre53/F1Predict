# 09 — Modeling Bake-off: Panel Synthesis & Experiment Plan

Synthesis of a 5-agent design panel (rating systems · quali/FP signal · statistical/ML ·
Bayesian sequential filter · prior-art survey) into a concrete, pre-registered
experiment to find a better F1 prediction model, scored against the real Polymarket
market.

## The convergent architecture (all four modeling agents agreed)

A race prediction is one pipeline with interchangeable parts:

```
time-local CAR+DRIVER pace estimate   →   strengths→order (Plackett-Luce/Harville)   →   win/podium/points probs
        ▲ (the model choice)                    ▲ (+ discounted-Harville fix)              ▲ (+ Benter market-blend)
   updated each weekend from QUALI + FP,    car ≈ 88% of variance,                    forward-chained, CLV-scored
   forward-chained (leak-free)              driver = regularized offset
```

Shared, non-negotiable findings:
- **Estimate time-LOCAL pace, not pooled season average** (our current sim's core flaw).
- **Car dominates** (~88% of finishing-order variance is the constructor); driver is a
  small regularized offset; **teammate deltas** are the clean driver signal.
- **Use qualifying** — the single biggest signal we currently ignore (quali→finish ρ≈0.76).
- **Plackett-Luce = Harville = rank-ordered logit = exploded logit** — the same model.
- **Forward-chained, leak-free; CLV vs market is the verdict; 2026 = untouched lockbox.**
- Effective sample is **~85 races**, not ~1700 rows → simple models, pre-registration,
  multiple-testing discipline. Calibration (temperature/RD) is the highest-ROI knob.

## The reality check (prior-art survey) — reframes the goal

- **No credibly profitable public F1 *outright-winner* betting model exists.** The best
  honest attempt (Shuirman) reached ~+4.6% Kelly-1% with losing seasons and wouldn't bet
  real money. Everything claiming "98% accuracy / €4k profit" is in-sample or leakage.
- **F1 outright markets are efficient** (~0.95 corr market vs odds). So our goal is NOT to
  beat the outright line. It is: **(1)** match the market's *calibration* (a big win over
  our 0.16-Brier sim), and **(2)** look for edge where it's plausible — **sub-markets /
  props** (H2H, points-finish, podium-without-favourite, top-6/top-10), mid-grid ordering,
  high-variance circuits, and live/in-race — measured by **CLV**, not in-sample ROI.
- **Two techniques to steal (the toy→competitive difference):**
  1. **Discounted Harville** (Henery/Stern; Benter's γ,δ≈0.5–0.8 power-discount on strengths
     before cascading) — fixes the favourite-over-placement bias that hurts podium/points
     calibration. Don't naively renormalize win strengths for places.
  2. **Benter market-blend** — final layer `c_i ∝ exp(α·log f_model + β·log π_market)`,
     α,β fit on holdout. Calibrates us and forces deviation from the market only where we
     have real signal. Edge metric: **ΔR² = R²(blend) − R²(market)** (simulation-free).

## The bake-off (candidates, all sharing the PL/Harville + blend back-end)

| # | Model (pace engine) | Why | Effort |
|---|---|---|---|
| 0 | **Grid + quali-gap calibrated logit** (baseline) | "Is it just the grid?" — likely closes most of the Brier gap alone | small |
| 1 | **PL-Glicko rating** (car+driver, online, forward-chained) | Simple, fast, drops into our harness; the rating brief gave ready code | small-med |
| 2 | **Kalman pace-filter** (car+driver state; FP→quali updates; predicts quali too) | Most principled time-local estimate; quali-prediction = bonus validation surface | med-high |
| 3 | *(stretch)* **Feature-conditional Plackett-Luce / LightGBM-LambdaRank** | Higher ceiling; overfitting risk at ~85 races | med |

Each feeds: **discounted-Harville** → podium/points; **Benter blend** with Polymarket where
a market exists.

## Evaluation protocol (pre-registered)

- **Forward-chained / expanding window**, strictly chronological. Hyperparameters frozen on
  2023–24; **2025–26 out-of-sample; 2026 touched once as a lockbox.**
- **Scoring:** multiclass Brier + log-loss + reliability curves on win / podium / points
  vs actuals; **the same vs the de-vigged market** (bar ≈ 0.10); **top-pick accuracy**
  (market ≈ 36%); **CLV** vs Polymarket as the go/no-go; **ΔR²** for the blend.
- **Honesty:** race-block bootstrap CIs; pre-registered feature/hyperparameter lists;
  report the number of variants tried (multiple-testing). Effective n ≈ races, not rows.
- **Ship criterion:** out-of-sample win-Brier ≤ ~0.11, top-pick ≥ ~0.32, **CLV ≥ 0**, and a
  visibly better calibration curve than the sim. If nothing beats the market, **ship the
  best-calibrated model anyway** (huge upgrade over the sim) and **blend toward the market**;
  report the honest negative on edge.

## Reusable prior art
- Bayesian rank-ordered-logit reference code + data (Zenodo 10.5281/zenodo.7632045).
- `ohenery` (R) for Harville/Henery math to port. F1Predict (Elo→MC, LGPL — check licence).
- Shuirman's forward-chain + value-bet/Kelly harness (tighten the leakage hole he flagged).
- Constructor-dominant feature design (88/12 car/driver).

## Data scope (decided)
- **Floor at 2018** — where FastF1 gives full detail (telemetry, quali laps, FP) needed
  by the quali/FP/Kalman models. Sample = **2018–2026**, spanning two regulation eras
  (2017-era high-downforce + 2022 ground-effect). Our models are era-agnostic
  (relative car+driver strength), so the era span *tests generalizability* — a feature.
- **Pre-season testing** captured where available (FastF1 reliably ~2021+) as a weak,
  sandbag-prone signal — used only to **seed each season-opener prior**.
- Backfill is staged across FastF1's 500-calls/hour limit (self-resuming loop).
- Odds for backtesting: Polymarket 2024+; pre-2024 odds pending the data-sourcing agent.

## Recommended first build
Baseline (#0) + PL-Glicko rating (#1) with discounted-Harville + the Benter market-blend,
run through the existing `forward_backtest.py` / `market_backtest.py` harness against the
sim's 0.16 Brier — the first real head-to-head. Then add the Kalman filter (#2).
