# 23 — Benter market-blend (does model + market beat either alone?)

_MODEL_ROADMAP "other ideas": wire `probability.benter_blend` and test it. Verdict: the model
**does** carry signal independent of the market (an equal blend beats both in-sample), but on
23 priced races we can't tune the blend to beat the market out-of-sample. A calibration tool
that improves on our own model — not a market-beating edge._

## The blend

Benter's classic horse-racing method: combine your model's probabilities with the public
market's, `c_i ∝ exp(α·log p_model + β·log p_market)`, renormalized over the field. α=1,β=0 is
pure model; α=0,β=1 is pure market. If the model has information the market lacks, the optimal
blend has α>0 and beats the market; if it's redundant, the optimum collapses to the market.

## Method (leak-free)

`app/models/validate_benter.py`. Forward-chain the production Kalman (`KalmanOTModel`,
post-quali) exactly as `market_backtest.py`, and at each Polymarket-priced race collect the
full per-driver (model win-prob, de-vigged market win-prob, did-win), aligned to drivers
priced by both. De-vig is cached to `data/benter_collect.json` (network once). Then grid-search
(α,β) in-sample, and run an expanding-window forward-chain (fit on prior priced races, apply to
the next) for the honest out-of-sample score. 23 races (Polymarket F1 winner coverage began
mid-2024).

## Results

| | win logloss | win Brier |
|---|---|---|
| Pure model | 0.1765 | 0.0545 |
| Pure market | 0.1661 | 0.0503 |
| **Best blend (α=0.75, β=0.75), in-sample** | **0.1606** | **0.0495** |

Forward-chained (expanding window, 17 held-out races):

| | win logloss |
|---|---|
| Blend (fitted α,β) | 0.1754 |
| Pure model | 0.1780 |
| Pure market | **0.1735** |

## What it means (honest)

- **The model carries independent signal.** The best in-sample blend puts *equal* weight on
  model and market (α=β) and beats **both** (0.1606 vs 0.1765 / 0.1661). If our model were
  redundant with the market the optimum would sit at β≫α. So the Kalman is not just re-deriving
  the market — it adds something.
- **But it's not a market-beating edge.** Out-of-sample the fitted blend beats our own model
  (0.1754 < 0.1780) yet still trails the pure market (0.1735). With only 23 priced races the
  (α,β) fit is too noisy to bank the in-sample gain — consistent with brief 07 (the pre-race
  market is efficient; we have no outright edge).
- **Useful as calibration, not alpha.** The blend reliably improves on *our* probabilities, so
  the honest production use is: where a live market exists, blend toward it for better-calibrated
  numbers — clearly labelled a calibration aid, not a betting signal.

## Wiring

`probability.benter_blend` is validated and ready. Recommended surface: a model · market ·
blend column in the Markets tab (the live de-vigged market is already fetched there), using a
conservative fixed α=β (in-sample optimum) and the "calibration, not edge" caption. Not wired
into the default `/predict/race` (it needs a live market and is calibration-only).

## v2

- Re-fit (α,β) as the priced-race sample grows (each season adds ~24 races) — the in-sample
  gain suggests a real, if small, independent signal worth re-testing at n≈70+.
- Blend per-market (win vs podium vs points), not just win.
- Bookmaker odds as a second market input (more history than Polymarket's 2024+ coverage).
