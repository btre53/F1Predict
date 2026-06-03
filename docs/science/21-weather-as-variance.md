# 21 — Weather as variance (does rain help the model?)

_Roadmap open-Q #4 / brief 16 §4. The roadmap flagged this as "the cheapest likely real
win." Verdict: **a real win, but a narrow one** — not where the intuition pointed._

## The hypothesis

Weather is an **exogenous race-day shock**: it isn't caused by car/driver quality, it's
known (broadly) at lights-out, and folklore says it (a) causes more retirements and (b)
shuffles the order ("anything can happen in the rain"). So the natural model use is **not**
a who-wins term but a **variance** term:

- **H1 (spread):** rain widens the finishing distribution → on wet races, widen the
  Plackett-Luce temperature (be less confident) and win/podium/points calibration improves.
- **H2 (DNF):** rain raises retirements → scale the hazard-DNF probability by a wet term.

## The data (free, leak-free)

`app/etl/weather.py` → `data/weather.parquet`, one row per race (2018–2026, 168 races).

- **Signal:** realized **race-window precipitation (mm)** from the Open-Meteo **ERA5
  archive** (`archive-api.open-meteo.com`), windowed to the race's local start hour → +3 h
  using the FastF1 schedule. Honest caveats:
  - Open-Meteo's archived *forecast* endpoint does **not** populate
    `precipitation_probability` for past dates and only covers ~2022+; ERA5 realized
    precipitation is the one signal consistent across all years. Realized precip is mildly
    optimistic vs a pure ex-ante forecast, but weather is exogenous and broadly known
    pre-race, so it's a defensible leak-free stand-in. The deploy path for a *future* race
    swaps in the live forecast into the same column.
  - ERA5 **under-measures convective intensity** (2022 Monaco / 2021 Spa deluges read as
    ~0.1–0.5 mm/h). So the **binary wet flag is the robust signal**; the mm magnitude is a
    soft ordering only.
- **Cross-check vs ground truth:** the Open-Meteo wet flag agrees with **FastF1's own
  trackside `weather_data.Rainfall`** on **13/14** sampled races (the one miss, 2024 Italian,
  is a grid-cell drizzle that never reached the F1 sensor). The artifact is trustworthy.

Wet rate ≈ 29% of races (any measurable race-window precip), stable across seasons.

## What we found

Forward-chained over 163 scored races (`app/models/validate_weather.py`): chain the Kalman
once, then re-score win/podium/points under temperature policies `T(race)=T0·(1+k·rain)`,
splitting metrics into **WET / DRY** (DRY is untouched by construction, k·0=0).

### H2 (DNF): **dead.**

| | DNF rate | n (car-races) |
|---|---|---|
| Dry | 0.0926 | 1436 |
| Wet | 0.0916 | 655 |
| Moderate+ rain (≥0.5 mm/h) | 0.0876 | 217 |

No wet/dry difference — if anything moderate rain retires *fewer* cars. Modern reliability
plus wet running behind the safety car (lower speeds, red-flag resets) cancels the "more
crashes" intuition. **No wet DNF multiplier.**

### H1 (spread): rain disrupts the **front and the midfield-scoring**, not the whole order.

Descriptively, wet races do **not** shuffle the overall grid→finish order more (Spearman
ρ 0.68 dry vs 0.70 wet vs 0.72 moderate+ — essentially flat). But the **pole→win
conversion collapses**: 0.588 dry → 0.469 wet → **0.353** in moderate+ rain. The disruption
is concentrated at the extremes, not spread through the field.

Re-scoring (binary wet intensity, `T0=0.5`; logloss, lower better):

| k (wet widening) | WET win | WET podium | WET **points** | DRY (all markets) |
|---|---|---|---|---|
| **0.0 (baseline)** | **0.1279** | **0.2494** | 0.5577 | 0.129 / 0.250 / 0.530 |
| 0.5 | 0.1413 | 0.2765 | **0.5170** | (unchanged) |
| 1.0 | 0.1513 | 0.3003 | 0.5218 | (unchanged) |
| 2.0 | 0.1638 | 0.3327 | 0.5495 | (unchanged) |

Two clean results:

1. **Win/podium: widening HURTS, monotonically.** And note the baseline WET win logloss
   (0.1279) is already *better* than dry (0.1292) — the model is **not** over-confident on
   the wet favourite (wet races often have a clear wet-weather ace). The pole→win drop is
   real but thin (17 moderate+ races) and the MC at `T0=0.5` already carries enough win
   spread. **Do not widen win/podium in the wet.**
2. **Points (top-10): the model is specifically over-confident in the wet** — baseline wet
   points logloss 0.5577 vs dry 0.5303 — and a **wet-only widening closes exactly that gap**,
   monotonically to ~0.517 at k=0.5 (binary) / k≈2 (continuous). Rain scrambles **who scores
   in the midfield**, and this is the one place the model needs more humility. This is
   *weather-conditional*, not a global points miscalibration: dry points are already
   well-calibrated; only the wet gap needs closing.

## Verdict — KEPT as a **per-market (points-only) wet widening**, + a realism/Explainer number

Per the project rules (keep mechanistic/exogenous features that beat baseline *on their
market*; document honest negatives; don't make a default unless it beats the tuned
baseline):

- **DNF multiplier — rejected** (no signal). Documented negative.
- **Win/podium wet spread — rejected** (hurts; the wet favourite is already calibrated).
  Documented negative.
- **Points wet spread — KEPT.** A wet-only widening of the **points** market
  (`T_points = T0·(1+0.5·wet)` → 0.75 in the wet) beats the baseline on wet points logloss
  (0.5577→0.517) and on overall points (0.5384→0.5264), at **zero cost** to win/podium
  (left untouched) and to dry races. This also motivates the roadmap's separate
  **per-market temperature** idea — weather is its first concrete use case.
- **Rain probability as a realism number** — surfaced on the prediction (like the structural
  SC prior) for the Explainer: "wet race → wider who-scores spread." Honest, not an edge.

## How it's wired

- `app/etl/weather.py` — the ETL + FastF1 cross-check + `weather_map()` lookup. `refresh.py`
  rebuilds it on ingest.
- `predict_kalman` — looks up this race's wet flag; when `weather_spread=True` (flag-gated)
  the **points** market is sampled at the wet-widened temperature in a second PL pass, while
  win/podium/the finishing distribution stay at the base temperature. The result carries
  `rain_prob` / `wet` for the Explainer.

## v2 / open

- A true **ex-ante forecast** column (Open-Meteo forecast API) for live/upcoming races, vs
  the ERA5 realized stand-in used for backtesting.
- **Intermediate/extreme-wet tyre regime** in the structural sim (brief 16 §4): rain as a
  sim *mode* (the `rain_crossover` engine already exists) rather than only a spread term.
- The points-spread is modest and the wet sample is ~48 races — revisit as the modern wet
  sample grows; consider a continuous intensity once ERA5's convective under-measurement is
  corrected (e.g. blend radar/station precip).
