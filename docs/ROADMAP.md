# F1Predict — Build Roadmap & Todo List

A portfolio-grade F1 race prediction, replay, and strategy-evaluation web app.
Backend: Python (FastAPI, NumPy, LightGBM, scipy). Frontend: React + Vite + TS +
Tailwind. Data: FastF1 + Jolpica + OpenF1 → Postgres. Deploy: Docker Compose on a
Hetzner VPS behind Caddy.

The science foundation lives in [`docs/science/`](science/README.md).

## Six app surfaces (tabs)

1. **Strategy Lab** ⭐ (build first) — compare pit strategies; undercut/overcut;
   Stackelberg cover-vs-extend; optimizer; outcome distributions.
2. **Predictor** — set grid + conditions → 10k Monte Carlo → win/podium/points
   probabilities, finishing heatmap, P10/P50/P90.
3. **Explorer** — historical race replay (animated tower, gap chart, tyre/pit
   timeline) + strategy lookback across past GPs.
4. **Live** — OpenF1 ingest (poll/backfill) + live strategy calls.
5. **Markets** — Polymarket model-vs-market edge dashboard (paper mode).
6. **Explainer** — renders `docs/science/` content for visitors.

---

## Step-by-step todo list

Legend: `[ ]` todo · `[~]` in progress · `[x]` done

### Phase 0 — Foundations & scaffold
- [x] Research the science; write `docs/science/` explainers (+ 04 spec validation)
- [x] Scaffold repo: backend (uv/FastAPI), frontend (Vite/React/TS), docker-compose
- [x] Postgres schema (era-partitioned, from research doc §1) — `app/db/schema.sql`
- [x] Config & settings (pydantic-settings), `.env.example`
- [x] Health-check endpoint + frontend hitting it (end-to-end smoke test)

### Phase 1 — Data foundation (ETL)
- [x] FastF1 ingest client (offline batch, cached) → normalized Polars frames (`app/etl/fastf1_client.py`)
- [x] Batch ingest → Parquet archive (`app/etl/ingest.py`); 15.8k laps / 5 circuits / 2023–24
- [x] Fuel-correction + stint-relative degradation residuals in the ETL
- [x] Calibrate per-circuit base lap + 3-phase tyre θ-params from real long runs (`app/etl/calibrate.py`)
- [x] Calibration store + `/circuits` API + Strategy Lab wired to calibrated data
- [ ] Jolpica client for canonical results/schedules/standings (driver/car pace offsets)
- [ ] Expand backfill to full 2022–2024 calendar; load Parquet → Postgres serving layer
- [ ] Calibrate compound *pace offsets* (cross-stint) — currently data-driven shape + seed offset

### Phase 2 — Engine (physics → residual → Monte Carlo)
- [x] Deterministic physics layer: base pace + linear fuel + tyre deg (circuit-specific)
- [x] Tyre-degradation calibration: 3-phase bounded SLSQP fit on real FP/race long runs
- [x] Skewed-t execution-noise sampler (positive skew) — fast Azzalini generation
- [x] Vectorized NumPy Monte Carlo (drivers × sims); SC count/start/duration sampling; DNF; grid + form variance
- [x] Driver pace offsets from real data (`calibrate_drivers`); 1.2s for a 10k-sim race
- [ ] LightGBM residual model on physics errors (era-invariant features)
- [ ] Validation harness: Brier / log-loss / CRPS / calibration plots, forward-chained
- [ ] Overtaking / track-position constraint (currently cumulative-time ranking — documented limitation)

### Phase 3 — Strategy Lab (first user-facing surface) ⭐
- [x] Strategy representation (stints, compounds, pit laps) + race-time evaluation
- [x] Fast `RaceModel` scorer + 3-lap-block coarse search + ±2-lap refine
- [x] Fuel-amplified tyre wear (softs-late realism; breaks order degeneracy)
- [x] Undercut/overcut calculator (threshold from deg + pit loss + gap)
- [x] Stackelberg cover-vs-extend (first-order backward reasoning; DP solver TODO)
- [x] Pit-loss model: decomposed standstill + in/out-lap, green/VSC/SC scaling
- [x] API endpoints: `/strategy/evaluate`, `/strategy/optimize`, `/strategy/undercut`
- [x] Strategy Lab UI: ranked cards, tyre timeline, undercut sliders (delta-first metric)
- [x] Strategy Lab UI: manual strategy builder (calibrated) + lap-time profile chart + Stackelberg cover/extend panel

### Phase 4 — Explorer (historical replay)
- [x] Replay API `/replay/races` + `/replay/race`: per-lap positions/gaps/tyres/pit/track-status
- [x] Animated replay UI: position tower (Framer Motion reorder), play/scrub/speed, tyre + pit + status
- [ ] Gap chart / track-map SVG (position tower shipped; richer viz later)
- [ ] Strategy lookback: re-run the optimizer on a historical race; compare to reality

### Phase 5 — Predictor  (brought forward — built alongside Phase 2)
- [x] Predictor API `/predict/race`: calibrated grid → finishing distributions
- [x] Predictor UI: win/podium/points bars + finishing-position heatmap + SC probability
- [ ] Grid editor (set qualifying order) + per-driver strategy assignment
- [ ] Scenario overrides ("rain on lap 30", SC injection, red flag)

### Phase 6 — Live  (data-source decision: see docs/science/05-live-data-sources.md)
- [ ] OpenF1 **paid** MQTT/WSS ingest worker (`paho-mqtt` + OAuth2 token refresh) — primary
- [ ] Direct F1 SignalR client behind a flag (sub-1s, eyes-open ToS/maintenance risk) — fallback
- [ ] Post-session FastF1 backfill as source of truth; predictive-extrapolator for dropouts
- [ ] Live dashboard + live strategy calls (SSE/WebSocket to frontend)
- [ ] (optional) TracingInsights ETL source for corner geometry + tyre-deg cross-check

### Phase 7 — Markets (paper mode)  ⟵ this is the gate for any paid data spend
- [x] **Calibration backtest (zero cost):** model probs vs real outcomes across 46
      races — Brier/log-loss/calibration, leave-one-race-out driver pace, vs grid baseline
- [x] Polymarket Gamma/CLOB read client + vig-removal (`devig`) + fractional Kelly (display)
- [x] Markets UI: scores, calibration plot, per-race table, live de-vig panel (graceful when no markets)
- [ ] **Finding to act on:** model is *overconfident on top picks* (predicts ~92% win,
      observed 61%) and only ties the grid baseline on win Brier → temper win probs /
      raise form variance; real edge (if any) is in podium/points + live repricing
- [ ] Compare vs real historical market prices when a data source is available (CLV)
- [ ] Only after a proven edge: consider the €10/mo OpenF1 live tier for in-race repricing

### Phase 8 — Polish & deploy
- [ ] Visual design pass (broadcast-style dark F1 UI, team colours, track maps)
- [x] Explainer tab — curated in-app explanation of the models (8 concept cards + math drill-downs)
- [ ] Dockerize, Caddy auto-TLS, deploy to Hetzner; nightly ETL cron
- [ ] README + portfolio write-up

---

## Key calibrated parameters to seed (from research)

| Parameter | Seed value | Source |
|---|---|---|
| Fuel sensitivity `k_fuel` | 0.030 s/kg (circuit 0.025–0.040) | rule of thumb / TUM |
| Fuel burn | ~1.6 kg/lap (circuit-specific) | TUM / consumption data |
| Green pit loss | ~21 s (decomposed) | TUM Catalunya 2019 |
| SC pit-loss multiplier | ~0.45× (drive portion only) | TUM |
| SC count distribution | [0.455, 0.413, 0.099, 0.033] | TUM `pars_mcs.ini` |
| SC start timing | [0.364, 0.136, 0.136, 0.08, 0.193, 0.091] | TUM |
| Hard/Medium deg rate | ~0.05 s/lap | state-space paper / FIA |
| Execution noise σ | 0.20–0.35 s, skewed-t (positive skew) | state-space paper |
| Monte Carlo iterations | 10,000 | Heilmeier |
