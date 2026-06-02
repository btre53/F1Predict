# F1Predict

A portfolio-grade Formula 1 **race-prediction, strategy, and scenario** engine — a
mechanistic Monte-Carlo race simulator, a calibrated strategy optimiser, and an honest,
fully-documented attempt to find a betting edge (spoiler: the market is hard to beat, and
this repo proves it rather than hiding it).

**Stack:** FastAPI + `uv` (Python 3.12, Polars, NumPy) backend · React + Vite + Tailwind
frontend · free data only (FastF1, Jolpica/Ergast, Polymarket). 24 backend tests, CI on
every push.

---

## What makes it interesting: the honest-research arc

Most "F1 prediction" projects claim 98% accuracy (in-sample leakage) and stop there. This
one is built like a real quant study — pre-registered, forward-chained, leak-free — and it
reports the negative results in full:

- A model **bake-off** (grid+quali baseline, PL-Glicko rating, Kalman pace-filter, LightGBM)
  showed all candidates cluster around the same accuracy and **barely beat a 10-line
  grid+qualifying baseline**. The signal is the grid.
- There is **no edge versus the pre-race outright market** (it's efficient, ~0.95 corr) — and
  **none 12 hours out** either (the line is already sharp post-qualifying).
- An **in-play** win-probability model is *well-calibrated* but, on a detrended lead-lag test,
  **does not lead** the (thin, slow) Polymarket — the apparent edge was common-trend
  co-convergence. Cleanly killed.
- **Market-making** those props is negative-EV for a retail maker (decoded fee/rewards math).

The full write-up is 15 short, sourced briefs in [`docs/science/`](docs/science/README.md) —
the most distinctive part of the project. What *does* hold up is the **calibration** and the
**interpretable strategy tooling**, which is where the app leans.

## The app (6 tabs)

| Tab | What it does |
|---|---|
| **Strategy Lab** | Pit-strategy optimiser, undercut/overcut calculator, Stackelberg cover-vs-extend. Calibrated per-circuit tyre + fuel models. |
| **Scenario Runner** | "What would you do?" live strategic calls — safety-car pit-vs-stay, undercut, cover/extend. Transparent, calibrated reasoning (the anti-black-box). |
| **Predictor** | 10k-sim Monte-Carlo race forecast with a survival/**hazard DNF model**, finishing-position heatmap. |
| **Explorer** | Animated historical race replay from real lap data. |
| **Markets** | Calibration backtest (Brier/log-loss/reliability) + model-vs-Polymarket, with a live market panel that degrades to a committed snapshot. |
| **Explainer** | In-app explanation of every model with the math. |

## Run it

```bash
# Backend  (http://localhost:8000)
cd backend && uv sync && uv run uvicorn app.main:app --port 8000

# Frontend (http://localhost:5173)
cd frontend && npm install && npm run dev

# Tests
cd backend && uv run pytest
```

The app runs entirely off the **committed data artifacts** in `backend/data/` (lap data,
calibration, backtests) — no network or API keys required for any core feature. Live data
(FastF1 ingest, Polymarket) is optional and **fails safe**: if a feed is unavailable or its
format has changed, the app falls back to the last committed snapshot rather than breaking.

## Live, but resilient by construction

It's a live app — it shows current Polymarket prices and auto-updates after each race
weekend — but built so a feed change or outage is a non-event, not a fire drill. The
maintenance headache with data apps comes from *brittle* live features, so every live path
is **resilient + observable**:

- **Live markets, snapshot fallback.** `/markets/live` derives the upcoming race from the
  schedule and fetches its Polymarket winner/pole markets; if the feed is down or its slug
  format drifts (or it's the off-season), it serves the last committed snapshot, labelled
  with its source + timestamp — the tab never errors.
- **Auto-update as a self-healing pipeline.** The post-race refresh
  (`app/etl/refresh.py`) is idempotent and runs as a **scheduled GitHub Action**
  (`.github/workflows/ingest.yml`), not a server cron to babysit: it ingests the new race,
  recalibrates, refits the DNF hazard, refreshes the market snapshot, runs the tests, and
  **only commits the new data if everything is green**. A bad week commits nothing (the app
  keeps serving last-good data) and emails you a red ✗.
- **Observable.** `/health/data` reports the latest ingested race + snapshot age, so silent
  staleness shows up instead of hiding. A FastF1 **schema-contract test** flags upstream
  shape changes before they break ingest.
- **CI** (`.github/workflows/ci.yml`) runs the tests + a production build on every push.
- Core tabs (strategy, scenario, predictor, replay) are **deterministic** off committed data,
  so they work forever regardless of any live feed.

## Layout

```
backend/   FastAPI app: engine/ (sim, strategy, physics), models/ (bake-off, hazard,
           racecraft), etl/ (FastF1/Polymarket ingest), api/. Data in data/*.parquet.
frontend/  React + Vite + Tailwind SPA (src/components/ per tab).
docs/      science/ (15 research briefs), ROADMAP, CURRENT_STATE, TODO.
```

## Data & credits

Free sources only. Physics/pit/tyre/safety-car parameters seeded from Heilmeier et al. (2020),
*"Application of Monte Carlo Methods … Race Simulation,"* Applied Sciences 10(12):4229
([TUMFTM/race-simulation](https://github.com/TUMFTM/race-simulation)). Lap/telemetry data via
[FastF1](https://github.com/theOehrly/Fast-F1); results via Jolpica/Ergast; market prices via
Polymarket's public CLOB. Not affiliated with Formula 1.
