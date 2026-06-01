# 07 — Real Model-vs-Market Backtest (Polymarket)

We compare our pre-race win probabilities against the **real Polymarket market**, on
the 2024 races where coverage existed, scored against actual results. This is the
genuine "do we have edge?" test — and the market is a strong, well-calibrated
opponent.

## How the historical prices are retrieved (verified live)

- **Markets:** Polymarket F1 race-winner markets began at the **2024 British GP**.
  **11 races in 2024** overlap our results data (British → Abu Dhabi); all of 2025 is
  also covered. 2023 has **zero** Polymarket overlap.
- **Prices:** CLOB `GET /prices-history?market=<YES clobTokenId>&startTs=&endTs=&fidelity=10`.
  ⚠️ `interval=max` silently returns `[]` (window-too-long cap) — always pass explicit
  `startTs`/`endTs` (a market's whole life ≤ 14 days fits one call). No history
  pruning for closed markets; rate limits benign.
- **Pre-race snapshot:** ⚠️ Gamma `startDate` is **market-open, not race-start** — the
  pre-race odds are at the **end** of the series. We get true lights-out time from
  **Jolpica** (`/{year}/{round}/results.json`) and take the last price with
  `t ≤ race_start`.
- **De-vig:** each driver is an independent binary YES market, so ΣYES > 1 (overround
  ~1.02–1.08). We normalise by the sum (excluding the "Other" bucket) → clean
  per-driver probabilities. Driver labels join to our codes by surname.

Code: `app/etl/polymarket.py` (`prerace_devig`, `race_start_ts`, `MARKETS_2024`),
`app/etl/market_backtest.py` → `data/market_backtest.json`, served at
`/api/markets/vs-market`.

## The result (honest, and humbling)

| | Model | Market |
|---|---|---|
| Win Brier ↓ | 0.133 | **0.100** |
| Top-pick accuracy ↑ | 27% | **36%** |

**The market beats our model on every measure.** Two flaws the backtest exposed:

1. **Overconfidence** — the model originally predicted ~91% for its favourite (vs the
   market's calibrated ~30–55%). Tempering the race-form variance (`FORM_SIGMA_S`
   3.0 → 7.0) cut win Brier 0.161 → 0.133, but it's still over-peaked.
2. **Over-reliance on pooled season pace** — the model picks **the same driver
   (Norris) in every race**, because raw season-average pace dominates and there's no
   overtaking/track-position friction to make the actual starting grid matter. The
   market correctly varies its favourite race-to-race (VER, NOR, LEC, SAI, RUS).

**Conclusion:** no edge over the market — which is exactly the gate result. It
reinforces staying free (no justification to pay for live data) and is a *better*
portfolio story than a fabricated "we beat the market." Real example of market
inefficiency it did surface: **British 2024 — Hamilton won but the market priced him
at only 0.15** (the favourites were VER/NOR).

## What would close the gap (future work)

- An **overtaking / track-position model** so the actual qualifying grid matters
  (the single biggest missing piece — it's why we pick one driver every race).
- **Forward-chaining** + **FP-based pre-race tyre deg** for a fully leak-free model.
- Weight race-specific signals (grid, recent form) over season-average pace.
- Going forward, capture **live** pre-race snapshots for out-of-sample CLV on 2025+.
