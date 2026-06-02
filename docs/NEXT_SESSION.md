# Next-session handoff prompt

Paste the block below into a fresh session to continue.

---

I'm continuing work on **F1Predict** (`C:\Users\Rober\Documents\Programming\F1 prediction`),
a portfolio-grade F1 prediction / strategy / scenario web app (FastAPI + uv backend, Polars
not pandas; React/Vite/Tailwind "Pit Wall" frontend; free data only). **Read first, in order:**
`docs/CURRENT_STATE.md`, `docs/TODO.md`, `docs/science/16-novel-edge-features.md`, and skim
`docs/science/README.md` (briefs 01–16).

## Where we are (short)
The app is **6 working tabs** (Predictor, Strategy Lab, Scenario Runner, Explorer, Markets,
Explainer) on GitHub at **github.com/btre53/F1Predict** (private). Current work is on branch
**`maintainability-and-resilience`** (11 commits, pushed; a PR can be opened from the push URL).
`main` still only has the initial commit — **decide whether to merge the branch to main.**

Recent big moves (this is all done + committed):
- **Predictor now uses a time-local Kalman car+driver model** (`app/models/predict_kalman.py`,
  wired to `/predict/race`, temperature 0.5). It replaced a naive pooled `drivers.json` sim that
  had the 2024 grid (Perez at Red Bull). Roster comes from the latest season in the data.
- **Data is current through 2026 R5** (168 races; `app.etl.refresh` catches up new races). The
  roster is the real 2026 grid (Audi, Cadillac, HAM→Ferrari, ANT→Mercedes, PER→Cadillac).
- **Pit Wall redesign** integrated (pw-* CSS in `frontend/src/styles/pitwall.css`, coexists with
  Tailwind `index.css`). **Scenario Runner**: 5 scenarios (SC pit-vs-stay, undercut, cover/extend,
  1-vs-2-stop, rain crossover). **Track viewer**: real GPS outlines + multi-car positional replay
  (`/replay/track`, `/replay/positions`; cached for 5 demo 2024 GPs).
- **Next-race auto-select** (`/calendar/next`, FastF1 schedule, no scraping) — Predictor opens on Monaco.
- **Maintainability/resilience**: live markets degrade to a committed snapshot; `/health/data`
  heartbeat; CI (`.github/workflows/ci.yml`); scheduled weekend ingest (`ingest.yml`).

## Outstanding TODOs (recommended order)
0. **#20 Overtaking-difficulty index — DONE (KEPT).** Built `app/models/overtaking.py` (one
   brand-agnostic track-physics number/circuit: grid→finish Spearman lock + green passing rate +
   lap-1 churn, forward-chained + EB-shrunk, wet excluded), `KalmanOTModel` in `kalman.py`,
   `validate_overtaking.py`, `data/overtaking_proxies.parquet`, `GET /circuits/overtaking`, 5 tests.
   Verdict (writeup **`docs/science/17`**): scored on best-of-rest/podium (NOT win — VER 23/24
   dominance), it **beats the rejected affinity decisively** but **≈ a tuned flat grid weight** on
   aggregate (grid-reliance is near-uniform across DRS-era circuits). KEPT per owner: wired the
   per-circuit pre-quali spread into the Predictor (`circuit_spread=True`); index served for the
   Explainer. **v2 ideas in brief 17** (split lap-1 churn — the Hungaroring wart; gap-based pass
   attribution; per-era estimates; similarity-shrinkage; per-circuit grid weight once quali is fused).
2. **#23 Polymarket probabilities on the track viewer.** Show model prob · market prob · gap on the
   Explorer leaderboard as cars circulate. Head start: 2024 in-play winner-price curves already exist
   in `data/inplay_probe.json` (1-min de-vigged) — wire those onto the replay for those races now;
   live version polls `/markets/live`. Depends on the track viewer (done) + #18 for more history.
3. **#15 Methodology & Findings in-app page** — render the `docs/science` briefs as a first-class
   tab (the honest-research showcase; strongest portfolio signal). Pure static content, pitwall style.
4. **#18 Ingest 2025/2026 Polymarket market history** — extend `market_backtest` beyond the 2024
   11-race set (slugs via `polymarket.next_race_event_slugs` pattern) for the Markets tab + #23.
5. **#21 Structural SC/caution index** (brief 16 §2) — measurable SC prior (wall-proximity proxy,
   lap-1 incidents, pit clustering, weather) folded into `app/models/hazard.py`.
6. **#22 Car-DNA corner-band decomposition** (brief 16 §3) — ≤4 physical factors from telemetry via
   `get_circuit_info()`, projected onto a circuit's corner demand. Highest overfit risk: must be
   shape-normalized (relative to the car's own mean pace) and killed if it doesn't beat scalar pace.

## Key context / gotchas
- **The honest findings are settled — don't relitigate** (briefs 01–16): no edge vs the outright
  market, none in-play (detrended lead-lag null), none at T-12h, market-making is negative-EV,
  telemetry-style ≠ racecraft, and the naive team×circuit affinity overfits. The model's value is
  calibration + interpretable tooling, not betting edge. The new features (#20–22) must be
  **mechanistic + forward-chain-validated + brand-agnostic** ("low-speed cornering speed → Monaco",
  never "Ferrari → Monaco") and killed if they don't beat the baseline.
- **2026 is the OOS "lockbox"** from the research phase. That phase concluded, so using 2026 for the
  *live product* is fine — just don't claim fresh out-of-sample validation on 2026.
- **FastF1 has 2026 data** — load by ROUND NUMBER (`get_session(2026, 5, 'R')`), not event name, and
  use `.laps` (F1 API), not `.results` (Ergast-backed, empty for recent seasons). Schedule via
  `get_event_schedule(year)` is offline/cached. Jolpica (`api.jolpi.ca`) is flaky (timeouts) — avoid.
- **Polymarket 2026 slugs** are `f1-<race>-grand-prix-<market>-<YYYY-MM-DD>` (old form was
  `<race>-grand-prix-winner`). `polymarket.next_race_event_slugs()` derives them from the schedule.
- **Worktree isolation is NOT available in this environment** — you can't run two code-editing
  subagents in parallel safely (they share the tree). Run code builds sequentially; only read-only /
  docs agents (e.g. research) parallelize.
- **Windows gotchas:** restart the API by killing the PID on port 8000 (no `--reload`); use
  `http://localhost:5173` (Vite binds IPv6). Dev servers may still be running from last session.
- **Track positions cache** is ~0.8 MB/race (`data/track_positions.json`, 5 demo races committed).
  Extend via `uv run python -m app.etl.build_track_outlines --year <Y>` + `... build_track_positions
  --year <Y>` (needs network). Gitignore it if it balloons.
- Tech: `uv run` for python; Polars not pandas; don't add comments/types to code you didn't change;
  no emojis. 29 backend tests pass (`cd backend && uv run pytest`); `cd frontend && npm run build`.
- Models implement `reset/predict/update`; harness `app/models/harness.py`. Kalman + the rejected
  `KalmanTrackModel` are in `app/models/kalman.py`; hazard DNF in `hazard.py`.
