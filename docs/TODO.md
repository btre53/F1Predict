# F1Predict — TODO / Roadmap

_Updated mid-modeling-exploration. The app (5 tabs) is built; we pivoted into a
serious modeling effort to find a better, validated predictor._

## Done
- **App**: Strategy Lab, Predictor, Explorer, Markets, Explainer (5 tabs, live).
- **Mechanistic sim** + calibration ETL (FastF1 → Parquet/JSON), backtests
  (in-sample, forward-chained, real Polymarket model-vs-market).
- **Model bake-off** (`app/models/`): shared forward-chained calibration-first harness;
  baseline (grid+quali), PL-Glicko **rating**, **Kalman** pace-filter, **LightGBM** ranker.
  Result: all cluster ~63% top-pick; **grid is the dominant signal**; fancy models barely
  beat a 10-line grid+quali baseline. Best-of-rest + PGAE eval lenses added.
- **Racecraft rating** (`racecraft.py`): car-netted positions-gained-above-expectation
  (strokes-gained analog). Sanity-passes (HAM top, ALB high). Validated as a metric.
- **Auto-refresh cron** wired into the app (`app.etl.refresh` + APScheduler, off by default).
- 5 research briefs: live-data sources, prior-art, AWS Insights, historical data/odds,
  strokes-gained (all in `docs/science/`).

## Next — consolidation
- [x] ~~Market-CLV / props test~~ — **DROPPED.** Every edge thread came back null (outright,
      in-play lead, T-12h, MM economics). No more "find an edge" work is worth doing; the honest
      conclusion is in. The modeling-exploration arc is CONCLUDED.
- [x] **Hazard DNF wired into the sim** — `predict.py` now sets per-driver `dnf_prob` from
      `hazard.apply_to_grid()` (pole ~2% vs P20 ~16%, was flat 0.08). Fail-safe lazy import.
- [ ] **Consolidate the winning model into the app** (optional) — wire the grid-aware rating model
      (+ racecraft feature) behind the Predictor; or temper the sim's overconfidence (VER ~84% win).
- [ ] **Deploy** (Dockerize + Caddy + the cron) — was parked; now the main remaining work.
      Pre-deploy: fix `fetch_f1_markets` 2026-slug discovery; verify docker build + frontend build.
- [x] **Scenario / what-if runner — BUILT (the headline feature).** New "Scenario Runner" tab.
      New engine piece `safety_car_decision()` (pit-now-under-SC vs stay-out, the live SC fork) +
      `/scenario/safety-car` endpoint + 2 unit tests; frontend `ScenarioRunner.tsx` with the SC
      decision as centerpiece plus undercut + cover/extend as selectable scenarios. 24 tests pass,
      frontend builds. The "anti-AWS": transparent, calibrated strategy calls.
- [ ] **Hazard wiring into backtests** (optional) — backtest.py/forward_backtest.py still use flat
      DNF (research artifacts); production Predictor uses hazard.
- [ ] **DEPLOY** — now the main remaining work. Pre-deploy: fix `fetch_f1_markets` 2026-slug
      discovery; verify docker build + frontend build; smoke-test the running app (incl. Scenario
      tab); then Dockerize + Caddy + cron on Hetzner.

## Immediate next (start the next session here)
The in-play direction, gated by cheap validation steps — each gates the next:
- [x] **1. Validate telemetry → racecraft (free, decisive). DONE — see
      `docs/science/12-telemetry-racecraft-validation.md`.** AMBER, leaning negative on the
      paid-feed premise. Racecraft is a *real* skill (distinct from one-lap pace: teammate-netted
      quali↔PGAE r≈0), but at lap resolution it shows up almost only as a **race-pace delta**
      (r≈−0.3/−0.5) that is **confounded with clean air** (gaining positions → faster laps).
      Tyre-mgmt/consistency/traffic carry ~nothing; sub-lap telemetry style carries ~nothing
      at the reliable n=152 grain (apparent per-driver hits are traffic-exposure artifacts).
      **Conclusion: a paid live-telemetry feed would mostly re-derive race pace + position we
      already get free from lap timing — low marginal value for live racecraft prediction.**
      New code: `app/models/racecraft_signatures.py`, `app/models/telemetry_signatures.py`.
- [x] **2. Check Polymarket in-play actually moves. DONE — PASS.** `app/etl/inplay_probe.py`
      pulled the CLOB `prices-history` curve at 1-min fidelity across the race window for all
      **11** 2024 winner markets (→ `data/inplay_probe.json`). **All 11/11 show genuine in-play
      movement**; the eventual winner's price climbs in every race (median +0.675), gradually
      and mid-race, not just at settlement (e.g. São Paulo VER 0.075→0.16→0.26→0.56→0.87→0.99
      over ~3h as he charged from P17; British HAM event-jump on the lead change). 2402 real
      moves (>0.005) across 30,990 in-play points (~7.8% of 1-min steps). **A real in-play
      benchmark exists to score against.** OPEN CAVEAT: `prices-history` is the price curve,
      NOT executable depth — thin liquidity means filling at size is a separate unsolved
      question; and the repricing may LAG on-track events (that lag is the edge to measure).
- [x] **3. In-play WPA backtest. DONE — NULL result (clean kill).** See
      `docs/science/13-inplay-wpa-backtest.md`, `app/etl/inplay_backtest.py`,
      `data/inplay_backtest.json`. Built state-reconstruction + a vectorized live win-prob MC +
      Polymarket alignment. Live prob is **well-calibrated** (Brier ~0.048, comparable to market),
      but the **detrended increment cross-correlation is flat at every lag (≈0, n=6824)** — our
      engine does **NOT lead** the market. The apparent CLV (+0.46) was common-trend co-convergence
      (reverse placebo +0.36). Structural reason: a lap-completion engine lags real-time ~90s by
      construction. Converges with briefs 11 & 12. **No exploitable in-play edge; do not pay for
      OpenF1.** Ship the live prob as a calibrated companion overlay; pivot to props + hazard DNF.
- [x] **3b. Survival/hazard DNF model. DONE — beats the flat baseline.** See
      `docs/science/15-hazard-dnf-model.md`, `app/models/hazard.py`, `app/etl/results.py`,
      `data/results.parquet`. Discrete-time logistic hazard, forward-chained over 90 races:
      per-race P(DNF) logloss 0.337 vs flat 0.399 (16% better). Grid (+2.18) + first-lap (+1.42)
      dominate; pole 2.7% vs P20 19.4% DNF (was flat 0.08). `race_dnf_prob()` is a drop-in for the
      sim's flat `dnf_prob`. team_prior ~nil (collinear with grid). NEXT integration: wire into
      `montecarlo.py`; optional: cause-split hazards; re-run WPA event-window lead test.

## Investigate (research-first) — DONE, see briefs 10/11/12
- [x] **A. Race-companion mode + in-play betting model** — researched (briefs 11/12).
      Telemetry→racecraft is amber (brief 12): live telemetry has low marginal value; the
      edge thesis is fast race-state reaction, not telemetry. Live latency-arb execution is
      infeasible for retail (brief 11); the companion/CLV-paper-trade version survives. Still
      gated on step 2 (does Polymarket in-play actually move). Caveat unchanged: thin liquidity.
- [x] **B. Novel modeling approaches** — researched (brief 10). Shortlist: (1) in-play WPA as
      martingale, (2) survival/hazard DNF, (3) regime-switching as plumbing, (4) car-DNA
      telemetry factors as *interpretable features only*, (5) time-rank-duality car/driver split.
      Traps flagged: outright-edge claims, per-driver reliability params, deep nets on telemetry,
      in-race look-ahead leakage. See brief 10 for the prototype order.

## Parked / background
- 2018–22 historical backfill (staged across FastF1 rate-limit windows) — running.
- Pre-season testing ingest (season-opener priors) — pending.
- Telemetry ingest (currently captured `speed_st` but unused) — gated on investigation A.
