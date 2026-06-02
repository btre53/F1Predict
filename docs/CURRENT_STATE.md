# Current State — F1Predict

_Last updated: 2026-06-02 (mechanistic features #20 + #21 + #22 built/validated; #20 merged to main)_

## Latest session (cont.) — #22 car-DNA corner-band — built, validated, KEPT as Explainer-only
- **Built the car-DNA corner-band decomposition** (task #22, brief 16 §2, the flagship
  anti-brand idea): `app/models/car_dna.py` — decompose qualifying telemetry into
  shape-normalized corner-speed-band factors (low/med/high/straight) × per-circuit demand;
  suitability = car DNA · circuit demand (leave-one-circuit-out). 2024 sample, 12 circuits,
  238 car-circuits, cached to `data/car_dna.parquet` (telemetry ~10s/session). `GET /cars/dna`.
- **Verdict** (writeup **`docs/science/19`**): the decomposition is **real + interpretable**
  (Monaco 0% straight / Monza 55%; McLaren+VER strong in slow corners, Alpine/Sauber on
  straights — correct for 2024) but **ZERO incremental predictive lift over scalar pace**
  (corr with quali deviation −0.01). The crux: naive shape-normalization (÷ lap-mean) is
  scalar pace in disguise (corr 0.92); a cross-band demean fixed it (0.92→0.18), and once
  honestly purged of pace, the corner-band fit predicts ~nothing. Exactly brief 16 §2's
  "most likely to disappoint" prediction.
- **KEPT as Explainer-only** (owner's keep-it bar): NOT wired into the predictor (no lift,
  would add overfit risk); served at `/cars/dna` as honest portfolio content. **41 backend
  tests pass** (3 new in `test_car_dna.py`; the scalar-pace-removal guard is the key test).
- **v2** (brief 19): multi-season sample, traction/braking sub-factors (not yet measured),
  validate on race pace, tie telemetry to tyre-deg/lap-time physics (the deterministic-engine
  lane — a dedicated research pass is warranted; see the deep-research note below).

## Earlier this session (cont.) — #21 structural SC index — built, validated, KEPT for ordering
- **Built the structural safety-car index** (task #21, brief 16 §3): `app/models/sc_index.py`
  — race-level P(any SC) from measurable track structure (street-ness via low passing rate +
  high lap-1 churn, reusing `overtaking_proxies.parquet`) + a wet flag + EB-shrunk per-circuit
  rate, forward-chained. SC label = track_status ∈ {4,6,7} via `hazard._sc_active_laps`.
- **Forward-chained verdict** (writeup **`docs/science/18`**): **nothing beats the base rate**
  (structure logloss 0.6335 vs base 0.6298; count MAE tie) — SC is a near-Poisson race-day
  shock (converges with doc 10). **But the cross-sectional structure is real** (per-circuit
  SC-rate ~ passing-rate r=−0.39, n_periods r=−0.43): Baku 0.79 / Jeddah 0.78 high, Hungary
  0.63 low — correct ordering.
- **KEPT for the ordering** (owner's keep-it bar): wired as the Predictor's per-circuit SC
  prior (`RaceSimResult.sc_probability`, was hardcoded **0.0**; Monaco 0.73, Baku 0.79, Hungary
  0.63), served at **`GET /circuits/safety-car`** for the Explainer. Honestly NOT an edge — the
  prior sits within base-rate noise; value is realism + interpretability. `refresh.py` refits it
  on ingest. **38 backend tests pass** (4 new in `test_sc_index.py`). On branch
  `mechanistic-features` (off main); **#21 NOT yet committed** as of this line — committing next.
- **v2** (brief 18): a-priori geometry from `get_circuit_info()` for never-raced circuits
  (shared pull with #22), rain *forecast* not a contemporaneous flag, feed SC count into the sim.

## Earlier this session (#20 overtaking-difficulty index — built, forward-chain-validated, KEPT, MERGED to main)
- **Built the mechanistic, brand-agnostic overtaking-difficulty index** (task #20, brief 16 §1):
  `app/models/overtaking.py` — ONE track-physics number/circuit (grid→finish Spearman lock +
  green on-track passing rate + lap-1 churn), forward-chained + empirical-Bayes shrunk, wet
  runnings excluded. `data/overtaking_proxies.parquet` holds the raw per-running inputs.
  Face validity: Monaco tops (+2.36), Spa/Bahrain/Baku correctly low. Known wart: Hungaroring
  ranks mid/low because lap-1 churn reads its chaotic start as "easy to pass" (v2 fix noted).
- **Forward-chained validation** (`app/models/validate_overtaking.py`, `KalmanOTModel` in
  `kalman.py`) — full writeup **`docs/science/17`**. **Reframed per owner: scored on
  best-of-rest / podium, NOT win** (VER 23/24 dominance makes win near-trivial). Findings:
  grid-awareness itself lifts best-of-rest 0.380→0.466 + podium ll 0.246→0.204; **OT-scaling
  ≈ the best matched flat grid weight** (within ~1-race noise) but **beats the rejected
  affinity decisively** (best-of-rest 0.436 vs 0.325). The per-circuit spread is
  calibration-neutral in aggregate but gives correct per-circuit variance.
- **VERDICT: KEPT, not killed** (owner's call: mechanistic features stay in the modeling
  conversation as portfolio pieces even when they don't beat a tuned baseline; note v2, don't
  bin). Wired in: **Predictor** uses a per-circuit spread (`predict_race_kalman(circuit_spread=
  True)`, `T=t0·exp(−0.2·index)`) — Monaco favourite 17.8%→24.3%, Spa/Bahrain→~15% (pre-quali
  the flat prior gave every circuit an identical 17.8% fav). **`GET /circuits/overtaking`**
  exposes the index for the Explainer. `refresh.py` rebuilds the proxies + busts caches (incl.
  `_ot_index`, `_proxy_table`, `_fitted`) on ingest. **34 backend tests pass** (5 new in
  `test_overtaking.py`); frontend untouched (Explainer wiring of the index is #15's job).
- **v2 ideas** (in brief 17): split lap-1 churn from steady-state passing (the Hungaroring fix),
  true gap-based pass attribution, per-era estimates as the modern sample grows, similarity-
  shrinkage backbone for thin circuits, per-circuit grid weight once the Predictor fuses a real
  quali grid (it currently runs pre-quali only — grid_weight is inert there).

## Earlier session (track-affinity experiment + Scenario Runner expand + mechanistic-features research)
- **Track-affinity: built, validated, REJECTED** (`KalmanTrackModel` in `kalman.py`, commit 2ce9181).
  Forward-chained over 168 races it made every metric worse (win logloss 0.128→0.139). Kept as a
  documented negative; NOT wired in. The honest lever stays qualifying.
- **Scenario Runner expanded + restyled to pitwall** (cc13f8d): 5 scenarios now (safety car,
  undercut, cover-vs-extend, 1-vs-2-stop fork, rain crossover). New `strategy.rain_crossover`,
  `/scenario/stop-fork` + `/scenario/rain-crossover`. Deleted dead `CoverExtendPanel.tsx`. 27 tests.
- **Mechanistic edge-feature research** (`docs/science/16`, 225348d): ranked anti-brand features —
  #1 **overtaking-difficulty index** (per-circuit shrunk grid→finish lock + passing rate + lap-1
  churn; tunes Kalman grid_weight + per-circuit spread — the principled replacement for the rejected
  affinity), #2 structural SC index (into hazard.py), #3 car-DNA corner-band decomposition (telemetry,
  highest overfit, must beat scalar pace or kill). Task #20 tracks the build-first one.
- **Track viewer DONE** (#19, 995fe4b): real GPS outlines (`/replay/track`), real sector times in
  `/replay/race`, per-car X/Y `/replay/positions` + multi-car TrackMap (20 team-coloured dots on the
  real outline; graceful single-dot fallback for uncached races). Position cache built for 5 demo
  2024 GPs (data/track_positions.json ~4MB; regenerable via `build_track_positions --year/--circuit`).
  Verified visually (Bahrain 2024). 29 tests pass.
- **Research follow-ups queued** (tasks #20-23): overtaking-difficulty index (build-first), structural
  SC index, car-DNA corner-band, and Polymarket probs on the track viewer (we already hold 2024
  in-play curves in `data/inplay_probe.json` for the replay overlay).
- Worktree isolation is unavailable in this env, so parallel CODE agents aren't safe — builds run
  sequentially (#14 done → #19 now); only read-only/doc agents run truly parallel.

## Earlier this session (Kalman Predictor + 2026 data catch-up + next-race auto-select)
- **FIXED the stale Predictor.** Root cause: it used `drivers.json` = `calibrate_drivers()` =
  a flat all-time POOLED mean (Perez/Red-Bull, VER dominant — the 2024 grid). Replaced with a
  time-local **Kalman car+driver** model: `app/models/predict_kalman.py` forward-chains the
  filter over all races, roster from the latest season, moved drivers inherit the new car
  (car+driver split), PL sampling + hazard DNF → full distribution. `/predict/race` now uses it.
  Temperature 0.5 (forward-chained calibrated). Pre-quali spread is honestly tight (~18% fav),
  sharpens once a quali grid is fused. The OLD mechanistic `engine/predict.predict_race` + the
  bake-off models were always proper (car/driver, forward-chained) — only the Predictor *tab*
  was wired to the naive pooled sim. That's fixed.
- **Data caught up to 2026.** FastF1 HAS 2026 (my earlier "no" was a bad query — name mismatch +
  `.results` vs `.laps`). Ran `app.etl.refresh`: archive now 2018–2026, **168 R races**, 2025
  complete + 2026 R1–5. Roster is the **real 2026 grid**: Audi, Cadillac, HAM→Ferrari, ANT→
  Mercedes, **PER→Cadillac** (correct, not stale). Recalibrated 36 circuits.
- **Next-race auto-select** (no scraping): `/calendar/next` from the FastF1 schedule; the
  Predictor defaults to the upcoming race (Monaco, round 6) with a "NEXT" affordance.
- **Calibration robustness** (exposed by fuller/sparser data): `_slope` drops non-finite rows +
  catches LinAlgError (fixed the SVD crash that aborted the post-ingest recalibrate); per-circuit
  tyre fit falls back to the seed curve when degradation isn't monotone after warm-up.
- Committed on branch `maintainability-and-resilience` (fe7a33f). 24 tests pass.

## Earlier this session (pushed to GitHub + maintainability/resilience + pitwall redesign)
- **On GitHub:** private repo **github.com/btre53/F1Predict**, one root repo (backend+frontend+docs).
  `main` has the initial commit; current work is on branch **`maintainability-and-resilience`**.
- **Maintainability + live-resilience layer (committed on the branch).** Live features kept but made
  robust + observable (the user's call: live service, low-maintenance via graceful degradation):
  - `/markets/live` is **live-first with a committed snapshot fallback** (`data/markets_snapshot.json`).
    Discovery derives the upcoming race's slugs from the FastF1 schedule (robust to Polymarket slug
    drift); falls back to the snapshot when the feed is down/off-season. New `fetch_f1_markets_live`,
    `next_race_event_slugs`, snapshot helpers in `polymarket.py`. Verified it pulls Monaco live.
  - **`/health/data`** heartbeat (latest ingested race + snapshot age) = observability.
  - **Scheduled GitHub Action `ingest.yml`** = the robust weekend cron (refresh→test→commit only if
    green; self-healing, auto-reverting). `refresh.py` also refits the hazard cache + snapshot.
  - **CI `ci.yml`** (pytest + frontend build), **FastF1 schema-contract test** (gated to ingest),
    root **README** (honest-findings story), **.gitattributes**.
- **Pitwall redesign INTEGRATED (uncommitted — diff shown, awaiting OK).** Dropped in the
  `design_handoff_pitwall` `src/**` (5 components replaced + `charts/` + `pitwall.css`), fonts +
  `data-theme=dark` in index.html, the 3 optional `ReplaySlot` sector fields in `api.ts`. Re-added
  the Scenario Runner tab. **Build green, bundle 744→246 KB, runs with no console errors** (verified
  via Playwright — Strategy Lab renders fully with live data). Handoff folder + zip gitignored.

## Prior session (Scenario Runner headline feature + hazard wiring + Monaco capture)
- **Scenario Runner BUILT — the new headline feature (6th tab).** The "anti-AWS": transparent,
  calibrated strategy calls instead of a black-box probability. New engine `safety_car_decision()`
  in `strategy.py` (pit-now-under-SC vs stay-out — captures the real nuance: pit only if a stop was
  due soon; fresh tyres → stay) + `/scenario/safety-car` endpoint + schemas + 2 unit tests.
  Frontend `components/ScenarioRunner.tsx` (SC centerpiece + undercut + cover/extend as selectable
  scenarios), wired into `App.tsx`. 24 backend tests pass; frontend builds; endpoint verified 200.
- App is now **6 working tabs**. Remaining before launch: deploy (Docker/Caddy/Hetzner) + the
  `fetch_f1_markets` 2026-slug fix.

## Earlier this session (hazard DNF + wiring + Monaco capture infra + MM verdict)
- **Hazard DNF WIRED into the production sim.** `engine/predict.py` calls
  `hazard.apply_to_grid(grid, year=2025, total_laps=...)` (fail-safe lazy import to dodge the
  engine→models→etl→engine cycle), so the Predictor now uses per-driver DNF (pole ~2% vs P20
  ~16%) instead of flat 0.08. 22 tests pass. (Backtests still use flat DNF — research artifacts.)
- **Props/CLV test DROPPED** — every edge thread is null; modeling-exploration arc CONCLUDED.
  Remaining work is deploy/polish + the (unbuilt) scenario runner.
- **Hazard DNF model DONE** (`app/models/hazard.py`, `app/etl/results.py`, `data/results.parquet`,
  brief 15). Discrete-time logistic hazard, forward-chained over 90 races, **beats the flat 0.08
  baseline** (per-race P(DNF) logloss 0.337 vs 0.399). Grid (+2.18) + first-lap (+1.42) dominate;
  pole 2.7% vs P20 19.4% DNF. `race_dnf_prob()` is a drop-in for the sim's flat `dnf_prob` (wiring
  into `montecarlo.py` is the next step). team_prior ~nil (collinear with grid).
- **Pre-race T-12h edge test: NULL.** Early line ≈ closing line (Brier 0.096 vs 0.095; median move
  0.008/driver). T-12h is post-quali, so the market already has our only signal. No timing edge.
- **Polymarket MM verdict: negative-to-zero EV for retail** (brief 14, agent). `sports_fees_v2`
  exists (maker rebate 25% of a ≤0.75% taker fee) but rewards are UNFUNDED on F1 markets and
  adverse selection on a news-gapping binary dominates. The +EV path is *taking* on a real model
  edge (>fee), not making. Don't build an MM bot.
- **Monaco 2026 capture infra DONE** (Monaco is **this Sun 2026-06-07 13:00 UTC**): `app/etl/
  live_capture.py` (Polymarket winner/pole/SC/constructor → CSV, smoke-tested live) +
  `app/etl/live_timing.py` (FastF1 SignalR recorder for replay). Runbook: `docs/MONACO_DOGFOOD.md`.
  NOTE: 2026 is the OOS lockbox — capture/dogfood only, do NOT train on it. `fetch_f1_markets`
  needs a 2026-slug-format fix (discovery missed the new `f1-…-2026-06-07` slugs).

## This session (in-play step 1 + research)
- **Telemetry → racecraft validation DONE (the decisive free gate).** New code:
  `app/models/racecraft_signatures.py` (lap-level, no API) + `app/models/telemetry_signatures.py`
  (sub-lap car telemetry, 8-race sample → `data/telemetry_sig.parquet`). Full writeup:
  **`docs/science/12-telemetry-racecraft-validation.md`**. **Result = AMBER, leaning negative
  on the paid-telemetry premise:** racecraft is a *real* skill (teammate-netted quali↔PGAE
  r≈0, so it's NOT just one-lap pace), but at lap resolution it surfaces almost only as a
  **race-pace delta** (r≈−0.3 per-race / −0.5 per-driver) that is **confounded with clean air**
  (gaining positions → faster laps; effect vs cause unresolved). Tyre-mgmt, consistency, traffic
  carry ~nothing. Sub-lap telemetry style carries ~nothing at the reliable n=152 grain (the
  apparent per-driver hits are traffic-exposure artifacts). **A paid live-telemetry feed would
  mostly re-derive race pace + position we already get free from lap timing → low marginal value.**
- **Two research briefs added:** `10-novel-approaches.md` (in-play WPA-as-martingale is the one
  credible edge; + survival/hazard DNF; + time-rank-duality car/driver split) and
  `11-inplay-latency-and-weather.md` (undercut latency-arb & weather ideas: signals backtestable,
  live execution infeasible, sector-weather premise dead; salvage as decision-support).
- **In-play step 2 DONE — PASS.** `app/etl/inplay_probe.py` (→ `data/inplay_probe.json`)
  pulled the CLOB `prices-history` curve at 1-min fidelity across the race window for all 11
  2024 winner markets. **All 11/11 move in-play**; the winner's price climbs gradually mid-race
  every time (median +0.675; São Paulo VER 0.075→0.99 over ~3h; British HAM event-jump). 2402
  real moves over ~31k points. **An in-play benchmark exists.** Caveat: it's the price curve,
  not executable depth (thin liquidity) — and repricing may lag on-track events (= the edge).
- **In-play step 3 DONE — NULL (the edge thesis is killed, cheaply).** Built the WPA backtest:
  `app/etl/inplay_backtest.py` (state reconstruction → vectorized live win-prob MC →
  Polymarket alignment → calibration + lead-lag), → `data/inplay_backtest.json`, writeup
  `docs/science/13-inplay-wpa-backtest.md`. Live prob is **well-calibrated** (Brier ~0.048,
  comparable to the market) but **does NOT lead it**: the detrended increment cross-correlation
  is flat at every lag (≈0, n=6824). The headline CLV (+0.46) was common-trend co-convergence —
  the reverse placebo was +0.36. Structural: a lap-completion engine lags real-time ~90s. This
  converges with briefs 11 (latency-arb inexecutable) and 12 (telemetry low-value): **three
  threads, one negative — no exploitable in-play edge, do not pay for OpenF1.**
- **Net direction:** the in-play *trading* thesis is closed. Surviving value: (a) ship the live
  win-prob as a calibrated race-companion OVERLAY (engagement, "anti-AWS"); (b) pivot modeling
  to PROPS/sub-markets + a survival/hazard DNF model (brief 10 §2), the lane still plausibly
  holding edge. Telemetry stays an Explainer-only feature.

## Where we are
The 5-tab app + mechanistic sim are built. We then **pivoted into a serious modeling
exploration** to find a better, validated F1 predictor. **Read `docs/TODO.md` and
`docs/science/09-modeling-bakeoff.md` first** — they hold the live plan and the panel
synthesis. Quick facts:
- **The mechanistic Monte Carlo sim loses badly** (forward-chained top-pick 31.7%; the
  market beats it 18% vs 36%). It's been superseded by the bake-off models for prediction.
- **Model bake-off** (`backend/app/models/`): a shared forward-chained, calibration-first
  harness scoring a **baseline (grid+quali)**, a **PL-Glicko rating**, a **Kalman
  pace-filter**, and **LightGBM**. On the fair 80-race sample (2018–19 + 2023–25):
  **all cluster ~63% top-pick** and barely beat the 10-line grid+quali baseline.
  **The signal is the grid/qualifying** — the panel's core warning, proven. Grid-awareness
  was the key fix for the rating/Kalman models.
- **Best-of-rest + PGAE eval lenses** added — the *winner* is ~trivial (pole); the real
  variance is the rest-of-field. **Racecraft rating** (`racecraft.py`, strokes-gained
  analog, car-netted) sanity-passes (HAM top, ALB high). Validated as a metric, not a
  better prediction *target* (it's a reparameterization — see `docs/science/strokes`).
- **No edge vs the pre-race outright market** (confirmed). Edge, if any, is **in-play +
  props** — the current direction (see TODO "Immediate next").
- **Telemetry is captured but UNUSED** (`speed_st`); deliberate v1 deferral.
- **Cron wired in**: `app.etl.refresh` + APScheduler in `app/main` (off by default,
  `F1P_REFRESH_ENABLED`). Same `model.update(race)` hook is the per-race retrain.
- 6 research briefs in `docs/science/` (live-data, prior-art, AWS, historical-data/odds,
  strokes-gained) + 09 (bake-off plan). Data backfill 2018→2025 still staging across the
  FastF1 500-calls/hour limit (a self-resuming loop is running).

## Working tabs (5 of 6)
- **Strategy Lab** — optimizer + undercut + Stackelberg cover/extend; manual strategy
  builder (calibrated) + lap-time profile chart; delta-first metric.
- **Predictor** — 10k-sim Monte Carlo, win/podium/points + finishing-position heatmap.
- **Explorer** — animated historical race replay (real data, position tower + scrub).
- **Markets** — calibration backtest (46 races, Brier/log-loss/calibration plot, per-race
  table, vs grid baseline) + live Polymarket de-vig panel (read-only/paper).
- **Explainer** — curated in-app explanation of every model (8 cards + math drill-downs).
- (Live still "soon".)
- 22 backend tests pass. **Data: 24 circuits, 46 races (2023–24) + 37k FP1/FP2 laps
  (`practice.parquet`), free sources only.**
- **Per-team tyre management** calibrated (`team_tyres.json`, `/api/tyres/teams`):
  McLaren/Mercedes gentle ×0.60, Haas/Sauber harsh ×1.3–1.6; applied per-driver in
  the Monte Carlo via `GridEntry.deg_multiplier`.
- Active build chunk + sequencing tracked in **docs/TODO.md** (FP/per-team done;
  forward-chaining backtest + interactive explainer + real Polymarket backtest next).

## Key backtest finding (act on this)
The model is **overconfident on its top picks**: it predicts ~92% win for its
favourite but the favourite wins ~61% of the time, and it only *ties* the naive
grid-favourite baseline on win Brier. Outright-win is grid-dominated; the real edge
(if any) is in podium/points and live in-race repricing. Fix: temper win
probabilities / raise `FORM_SIGMA_S` in montecarlo. This is the honest gate result —
no evidence yet to justify paying for live data.

## Hard constraint: cost-neutral
The project must run on **free data**. The only paid option on the table is the
OpenF1 live tier (~€10/mo), and it is **deferred indefinitely** — needed only for
true live in-race ingestion, and only justified if a **zero-cost backtest** (our
model probabilities vs historical Polymarket prices + de-vigged bookmaker lines)
shows a real edge that covers the cost. Everything built so far and the next
several phases need **no paid data**. Keep any paid/live path behind a flag,
default OFF. See the Markets phase notes in ROADMAP.md.

## What this is
A portfolio-grade F1 race prediction / replay / strategy-evaluation web app, to be
deployed on a small Hetzner VPS. Built from the original research doc
(`F1Predict_ Stochastic Race Simulation Engine.md`), validated and corrected by
independent research (see `docs/science/`).

## What's done
- **Research + science docs** (`docs/science/01-04`): lap-time model, race strategy,
  data sources/2026 regs, and a point-by-point validation of the original doc.
  These double as the future in-app Explainer content.
- **Roadmap** (`docs/ROADMAP.md`): 6 tabs, 8 phases, seeded parameters.
- **Backend** (`backend/`, FastAPI + uv, Python 3.12):
  - `app/engine/params.py` — calibrated parameters (TUM-seeded), era/compound enums.
  - `app/engine/tyres.py` — three-phase degradation + bounded SLSQP calibration.
  - `app/engine/physics.py` — deterministic baseline (base + fuel + tyre).
  - `app/engine/noise.py` — positively-skewed (skew-normal) execution noise.
  - `app/engine/strategy.py` — **Strategy Lab core**: fast vectorized `RaceModel`
    scorer, coarse-grid + refine optimizer, undercut calc, Stackelberg cover/extend.
  - `app/api/` — `/api/health`, `/strategy/evaluate`, `/strategy/optimize`,
    `/strategy/undercut`.
  - `app/db/schema.sql` — era-partitioned Postgres schema.
  - 9 passing smoke tests (`uv run pytest`).
- **Frontend** (`frontend/`, Vite + React + TS + Tailwind v4):
  - Dark broadcast-style F1 UI, 6-tab shell (Strategy Lab live; others "soon").
  - Strategy Lab: circuit + max-stops controls, ranked strategy cards with tyre
    timeline bars, undercut calculator with debounced sliders.
- **Infra**: `docker-compose.yml` (db + api + web), `backend/Dockerfile`, `.env.example`.
- **Phase 1 ETL (done)** — real data now drives the Strategy Lab:
  - `app/etl/fastf1_client.py` — load a session → normalized Polars frame (pandas→Polars at the edge).
  - `app/etl/ingest.py` — batch backfill → `data/laps.parquet` (15.8k laps, 5 circuits, 2023–24 FP2/FP3/R).
  - `app/etl/calibrate.py` — fuel-correct + stint-relative residuals → per-circuit base lap + 3-phase
    tyre θ-params → `data/calibration.json`.
  - `app/engine/calibration_store.py` + `GET /api/circuits` + `circuit_name` on `/strategy/optimize`.
  - UI loads calibrated circuits and shows a "CALIBRATED FROM REAL DATA" badge.
  - Verified: Bahrain base 1:31.6, avg race pace 1:34.6/lap, realistic SOFT deg ~0.05 s/lap.

## Key design decisions (from user feedback)
- **Headline metric = delta to optimal + avg lap time**, NOT absolute race time
  (users think in deltas/lap times). See `delta_to_best_s`, `avg_lap_s`.
- **Speed matters for sliders**: optimizer rewritten to a precomputed `RaceModel`
  (base+fuel is constant across strategies; only tyre wear + pit loss differ) →
  ~157ms for a 66-lap 2-stop search (was 23s). Sliders debounced ~90ms.
- **Fuel-amplified tyre wear** (`WEAR_FUEL_SENSITIVITY=0.30`): heavy car wears tyres
  faster, so the optimizer realistically runs **softs late**. Breaks the
  order-degeneracy that made permutations tie.

## Gotchas
- **`uvicorn --reload` does not reliably hot-reload on this Windows setup** and its
  reloader parent respawns stale workers. To restart the API cleanly: kill the
  python process holding port 8000 (find via `Get-NetTCPConnection -LocalPort 8000`,
  then `Stop-Process`), then start `uv run uvicorn app.main:app --port 8000` WITHOUT
  `--reload`. An orphaned socket can show a dead PID as the listener — kill the
  parent uv-python process to free it.
- **Vite dev binds IPv6 `::1` only** → use `http://localhost:5173` (not 127.0.0.1)
  for Playwright/curl.
- Fast optimizer scorer vs full per-lap `evaluate_strategy` differ by <1s (the
  scorer uses stint-average fuel for the wear multiplier). Rankings are
  self-consistent; absolute totals differ slightly by design.
- No DB is required yet — the engine runs on calibrated params from Parquet. ETL
  (FastF1 → Postgres) is a later phase.
- **Measuring timed UI behaviour via Playwright is unreliable** — tool-call latency
  means many real seconds pass between a `sleep` and a snapshot, so the browser
  keeps animating. The Explorer playback looked "too fast" but was correct at
  450ms/lap (verified via in-page `console.log` of elapsed/lap). Verify timing with
  in-page logs, not wall-clock sleeps. Playback uses a wall-clock-derived lap
  (`startLap + floor(elapsed/speed)`) so it's immune to timer stacking / StrictMode.

## How to run
- Backend: `cd backend && uv run uvicorn app.main:app --port 8000`
- Frontend: `cd frontend && npm run dev` → http://localhost:5173
- Tests: `cd backend && uv run pytest`
- ETL (offline): `uv run python -m app.etl.ingest` then `uv run python -m app.etl.calibrate`
  - Full calendar: `uv run python -m app.etl.ingest --seasons 2023 2024` (race sessions only)
  - One event: `uv run python -m app.etl.ingest 2024 Monaco`
  - Backtest (after calibrate): `uv run python -m app.etl.backtest` → `data/backtest.json`
  - FastF1 cache lives in `backend/.cache/fastf1`; artifacts in `backend/data/`.

## Next priorities (see docs/TODO.md)
Modeling arc is concluded (all edge threads null). The work now is product + ship:
1. **Commit the pitwall redesign** to the branch (diff shown, awaiting user OK ± deleting the 6
   dead component files: StintBar/LapTimeChart/LapTimeBuilder/StrategyBuilder/TeamTyreOverlay/
   TyreSandbox.tsx — superseded by `charts/Charts.tsx`).
2. **Restyle the Scenario Runner to pitwall** (it works but is still in old Tailwind styling) and
   **expand it** (#14): rain crossover, VSC-vs-SC, 1-vs-2-stop fork, dirty-air. Deterministic.
3. **Methodology & Findings page** (#15) — render the docs/science briefs in-app (honest showcase).
4. **Optional backend fidelity patches** (`design_handoff_pitwall/backend_patch/`): `real_sectors.md`
   (~5 lines in `replay.py` → true sector times) and `track_outline.md` (FastF1 GPS circuit outlines
   + `/replay/track` endpoint). Frontend already prefers real data when present; falls back otherwise.
5. **Deploy** (Hetzner + Caddy + the scheduled-ingest Action). Merge branch → main first.

## Gotchas (this session)
- **Repo structure:** ONE root git repo (an abandoned empty `backend/.git` was moved to
  `../_f1predict_backend_empty_git_backup`). Don't re-init inside backend/.
- **Polymarket 2026 slugs** changed format to `f1-<race>-grand-prix-<market>-<YYYY-MM-DD>` (old
  `<race>-grand-prix-winner` is 2024/25). `next_race_event_slugs()` derives them from the schedule;
  if a race name mismatches Polymarket's, add it to `_SLUG_ALIASES` in `polymarket.py`.
- **Pitwall + Tailwind coexist:** new components use `pw-*` classes (pitwall.css via App.tsx);
  ScenarioRunner still uses Tailwind (index.css via main.tsx). Both stylesheets load. Don't remove
  index.css until ScenarioRunner is restyled.
- **`design_handoff_pitwall/` + `claude design.zip`** are gitignored reference material (on disk for
  reference, not committed).
