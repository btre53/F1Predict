# Next-session handoff prompt

Paste the block below into a fresh session to continue.

---

I'm continuing work on **F1Predict** (`C:\Users\Rober\Documents\Programming\F1 prediction`),
a portfolio-grade F1 prediction/strategy web app (FastAPI + uv backend, React/Vite/Tailwind
frontend, Polars not pandas, free data only, eventual Hetzner deploy). **Read these first,
in order:** `docs/CURRENT_STATE.md`, `docs/TODO.md`, `docs/science/13-inplay-wpa-backtest.md`,
`docs/science/10-novel-approaches.md`, and skim `docs/science/README.md` (briefs 01–13).

**Where we are (short version):** the 5-tab app + a mechanistic Monte-Carlo sim are built,
but the sim loses to the market. A model bake-off (`backend/app/models/`) showed all models
cluster ~63% top-pick and barely beat a 10-line grid+quali baseline — **the signal is the
grid/qualifying**, and there's **no edge vs the pre-race outright market**. We then chased the
**in-play** direction through three cheap, decisive validation gates — and **closed it**:

- **Step 1 — telemetry → racecraft (brief 12): AMBER.** Racecraft (car-netted PGAE) is a real
  skill (distinct from quali pace) but at lap resolution shows up only as a clean-air-confounded
  race-pace delta; sub-lap telemetry style adds ~nothing. A paid live-telemetry feed would mostly
  re-derive race pace + position we already get free. Code: `app/models/racecraft_signatures.py`,
  `telemetry_signatures.py`.
- **Step 2 — does Polymarket move in-play? (probe): YES.** All 11/11 2024 winner markets reprice
  live (winner's price climbs gradually mid-race; `app/etl/inplay_probe.py`, `data/inplay_probe.json`).
- **Step 3 — in-play WPA backtest (brief 13): NULL.** A state-reconstructed live win-prob MC
  (`app/etl/inplay_backtest.py`) is well-calibrated (Brier ~0.048, ~market) but the **detrended
  increment cross-correlation is flat at every lag (≈0, n=6824)** — it does NOT lead the market.
  The CLV that looked good was common-trend co-convergence (reverse placebo nearly as high). A
  lap-completion engine structurally lags ~90s. This converges with briefs 11 (latency-arb
  inexecutable) & 12 — **three threads, one negative. The in-play TRADING thesis is closed; do
  NOT pay for OpenF1.**

Two background research briefs also landed: `docs/science/10-novel-approaches.md` (in-play WPA,
survival/hazard DNF, regime-switching, car-DNA factors, time-rank-duality) and
`11-inplay-latency-and-weather.md` (undercut latency-arb & weather ideas — signals backtestable,
live execution infeasible).

**Today — the surviving lanes (do these in order):**

1. **Build the survival/hazard DNF model** (brief 10 §2, `docs/TODO.md` step 3b) — the
   highest-value next build. Replace the flat TUM DNF rate with a **discrete-time hazard**:
   logistic `P(DNF on lap k | survived to k)` on a TINY pre-registered covariate set (≤5 terms:
   `lap_fraction`, `is_SC_restart`, `grid`/pack density, a regularized constructor reliability
   prior, maybe a season smooth for the era trend). DNF status/cause comes from Jolpica results
   (note: `api.jolpi.ca` was timing out last session — retry with long timeouts or cache).
   Validate forward-chained (Brier/log-loss on per-race DNF) vs the flat-rate baseline. This
   improves finishing-position **props** (the surviving edge lane) and plugs into the existing
   Monte Carlo sim's DNF draw.

2. **Then a props / sub-markets CLV test** (brief 10, `docs/TODO.md` "consolidation") — H2H,
   points-finish, podium-without-favourite, top-6/top-10 vs Polymarket, forward-chained, CLV as
   the verdict. This is where edge is still plausible after the outright + in-play nulls.

Optional/parallel: ship the (well-calibrated) live win-prob from `inplay_backtest.py` as a
calibrated **race-companion overlay** (engagement feature, the "anti-AWS" — matches the market,
doesn't claim to beat it). Keep telemetry as an Explainer/car-DNA feature only.

**Technical notes:** data in `backend/data/*.parquet` (`laps.parquet` = Q+R 2018–2025, 105 races;
`practice.parquet` = FP). Polymarket access + de-vig in `app/etl/polymarket.py`; in-play curves
cached in `data/inplay_probe.json`. FastF1 has a 500-calls/hour limit (cache lives in
`backend/.cache/fastf1`). Models implement `reset/predict/update`; harness `app/models/harness.py`.
Use `uv run`, Polars, no pandas. Don't re-run the heavy backtests unless needed. When the hazard
model lands, the WPA harness (`inplay_backtest.py`) can be re-run with an **event-window lead
test** (does a smarter engine lead specifically on DNF/SC jumps, even though it can't on average?).
