# 27 — Pole-market backtest: does the most deterministic session leak an edge?

_Task #28. Qualifying is the most predictable part of an F1 weekend — the pole sitter is far more
foreseeable than the race winner — so the pole market is the best remaining edge candidate. We
tested our pre-quali grid model against Polymarket's pole price. Honest verdict: **still no edge.**_

## Setup (leak-free, forward-chained)

For every race with a Polymarket **driver pole** market we compare two pre-qualifying forecasts:

- **MODEL** — the pre-quali Kalman pole probability (`predict_quali`): car μ + driver μ with **no
  this-weekend quali fused**, Plackett-Luce sampled at the qualifying temperature (T=0.35, tighter
  than the race's 0.5). Forward-chained: each race is predicted from strictly-prior races only.
- **MARKET** — the de-vigged Polymarket pole price snapshotted **just before qualifying starts**
  (the leak-free cutoff — the market hasn't seen the session either).

…scored against who actually took pole (official grid == 1). Code: `validate_quali_market.py`,
discovery in `polymarket.season_pole_markets()` (→ `data/quali_market_backtest.json`).

## Finding all of them: enumerate, don't guess

The trap here is **discovery**. Polymarket has used two different slug conventions for the same
market — `<gp>-grand-prix-pole-winner` (mid-2025) and `f1-<gp>-grand-prix-driver-pole-position-
<date>` (late-2025 onward) — and labels several circuits by a different name than FastF1 does
(Imola → "italy", São Paulo → "brazilian", Mexico City → "mexican"). A first pass that guessed one
slug pattern from the schedule found only **9** markets and silently dropped the rest.

The fix is to **enumerate the ground truth**: `_all_pole_events()` pages the entire Polymarket
**Formula 1 tag** (id 435) and keeps every driver-pole event under either naming convention, then
`season_pole_markets()` joins each event to the race it resolves just after, **purely by date**
(nearest preceding race within 12 days). Temporal matching sidesteps every name quirk. That lifts
coverage to **every priced race we have results for: n = 23** (all of 2025 from Miami on — Polymarket
had no pole market before round 6, and skipped Monza — plus the five 2026 rounds in our data).
Constructor-pole, **sprint-shootout pole** (a *different* target — the sprint grid, which our race-
grid model doesn't forecast), practice and fastest-lap markets are excluded by design.

## Result (n = 23)

| | model | market |
|---|---|---|
| pole Brier | 0.045 | **0.039** |
| top-pick accuracy | 26% | **30%** |
| agree on favourite | — | 52% |

- **No edge.** The market is better calibrated (Brier 0.039 vs 0.045) — the same finding as the
  winner market (0.049 vs 0.054) and the in-play WPA test, now on a real sample, not n=9. The
  "qualifying is more deterministic → smaller gap" hypothesis did **not** pay out: the gap is
  comparable to the win market, not smaller.
- **2025 qualifying was genuinely wild** — poles were spread across VER, PIA, NOR, RUS and LEC, so
  *both* forecasters were poor at top-pick (market 30%, model 26%). When the favourite is barely a
  1-in-3 shot, calibration is all that separates the two — and the market wins it. The model leaned
  on the standings-pace leader (NOR/RUS/PIA); the surprises (RUS at Canada, VER's late-season
  street-circuit poles, three ANT poles in early 2026) beat model and market alike.
- The model is **competitive, not buried** — within ~0.006 Brier of an efficient market it never
  sees the quali session for, built only from prior-race pace. That's the consistent story:
  well-calibrated and transparent, no alpha.

## Why no edge here either (the structural reason)

Our pre-quali model and the market's pre-quali price are *both* grid forecasts built from the same
public history. We bring nothing the market lacks before the session runs (no private practice
telemetry, no track-evolution read). The only place a grid edge could live is **quali-specific
signal the season-pace model ignores** — Q3 track evolution, run-order/timing, fuel-load games,
single-lap vs long-run car balance. Those are real, but they're v2 and only worth chasing if a gap
appears; this sample shows none.

## v2 (only if a gap ever shows)

- Track-evolution / Q3 run-order term (the grippier-later effect on street circuits).
- Single-lap car balance distinct from race pace (a car can be quali-strong, race-weak).
- **Sprint-shootout pole** is a separate, untapped market (sprint-qualifying-pole-winner, ~6 races):
  it needs the sprint-quali grid as the target, which we don't currently model — a v2 data + model
  add, not a re-skin of this.
- Re-run as the sample grows — n=23 is enough to say "no edge in 2025", not enough to rule out a
  small one. The discovery + backtest are wired to auto-extend on each new priced race.
