# The Science Behind F1Predict

These documents are the calibrated, sourced foundation for everything the engine
does. They are written to serve two purposes at once:

1. **Build spec** — the concrete math, parameter values, and algorithms the
   backend implements.
2. **In-app Explainer** — each section ends with a plain-English blurb that will
   be surfaced in the app's **Explainer** tab so visitors understand the models.

> Every "explainer" blurb below is deliberately written for a smart non-expert.
> Every equation and parameter table is sourced. Where the original research
> document (`F1Predict_ Stochastic Race Simulation Engine.md`) was wrong or
> oversimplified, it is flagged with **⚠ Correction**.

## Contents

| Doc | Topic |
|---|---|
| [01-lap-time-model.md](01-lap-time-model.md) | How a lap time is built: physics baseline + ML residual + skewed noise, fuel correction, tyre degradation, driver/car pace separation, validation |
| [02-race-strategy.md](02-race-strategy.md) | Pit strategy, undercut/overcut, Stackelberg game theory, optimization (MINLP/DP), safety-car modeling, pit-loss economics, dirty air, 2026 strategy shifts |
| [03-data-and-2026.md](03-data-and-2026.md) | Data sources (FastF1, OpenF1, Jolpica), the 2026 regulations (confirmed vs speculative), and Polymarket read-only market data |
| [04-spec-validation.md](04-spec-validation.md) | Point-by-point cross-check of the **original research doc** against independent research: what's corroborated, corrected, and factually wrong |
| [05-live-data-sources.md](05-live-data-sources.md) | Live-ingestion decision: SignalR vs MultiViewer vs TracingInsights vs OpenF1 paid — which to use for training vs unattended live |
| [06-f2-f3-other-series.md](06-f2-f3-other-series.md) | Expanding beyond F1: verified F2/F3 data paths (live SignalR + historical FIA PDFs), the tyre-compound gap, and WEC/MotoGP notes |
| [07-polymarket-backtest.md](07-polymarket-backtest.md) | Real model-vs-Polymarket backtest: how historic prices are retrieved, and the honest result (the market beats us → no edge) |
| [08-the-prediction-model.md](08-the-prediction-model.md) | What kind of model F1Predict actually is (a mechanistic Monte Carlo simulator), what each part is calibrated on, and what it is *not* (no trained ML layer) |
| [09-modeling-bakeoff.md](09-modeling-bakeoff.md) | 5-agent panel synthesis: the convergent car+driver/Plackett-Luce architecture, the "no one beats the outright market" reality check, and the pre-registered model bake-off plan |
| [10-novel-approaches.md](10-novel-approaches.md) | Scouting report on techniques beyond our prior work: in-play WPA-as-martingale (the one credible edge), survival/hazard DNF, regime-switching plumbing, car-DNA telemetry factors, time-rank duality |
| [11-inplay-latency-and-weather.md](11-inplay-latency-and-weather.md) | Honest verdict on undercut/overcut latency-arb and weather micro-climate ideas: signals backtestable, live latency-arb execution infeasible, sector-weather premise dead; salvageable as decision-support |
| [12-telemetry-racecraft-validation.md](12-telemetry-racecraft-validation.md) | Step 1 of the in-play plan: does car-netted racecraft show up in lap/telemetry process (not just outcome)? Amber result — only as a clean-air-confounded race-pace delta; paid live-telemetry premise not supported |
| [13-inplay-wpa-backtest.md](13-inplay-wpa-backtest.md) | Step 3: live win-prob (state-reconstructed MC) vs Polymarket. Well-calibrated but detrended lead-lag is NULL — no exploitable in-play edge. Clean kill of the edge thesis; ship as a calibrated companion overlay, pivot to props + hazard DNF |
| [14-polymarket-mm-economics.md](14-polymarket-mm-economics.md) | Can we market-make Polymarket F1 props? Verdict: negative-to-zero EV for retail. Rewards unfunded on F1 markets, maker rebate is pennies, adverse selection on a news-gapping binary dominates. The +EV path is taking when our model shows an edge > the ≤0.75% fee, not making |
| [15-hazard-dnf-model.md](15-hazard-dnf-model.md) | Discrete-time survival/hazard DNF model replacing the sim's flat 0.08. Forward-chained, beats flat baseline (logloss 0.337 vs 0.399); grid + first-lap dominate; pole 2.7% vs P20 19.4% DNF. Pluggable into the sim; feeds props + scenario realism |
| [16-novel-edge-features.md](16-novel-edge-features.md) | Mechanistic (anti-brand) edge features, ranked by signal÷overfit on our 168 races: overtaking-difficulty index (build-first, the principled replacement for the rejected team×circuit affinity), structural SC/caution index, car-DNA corner-band decomposition, weather-as-variance. Causal hypotheses + forward-chained tests |
| [17-overtaking-difficulty-index.md](17-overtaking-difficulty-index.md) | Build + forward-chained validation of brief 16 §1 (task #20). One brand-agnostic track-physics number/circuit (grid→finish lock + green passing rate + lap-1 churn). Verdict: KEPT — beats the rejected affinity decisively, supplies the Predictor's per-circuit pre-quali variance (Monaco tight, Spa wide), but ≈ a well-tuned flat grid weight on aggregate log-loss (grid-reliance is near-uniform across DRS-era circuits). Scored on best-of-rest/podium, not win. v2 ideas listed |
| [18-structural-sc-index.md](18-structural-sc-index.md) | Build + forward-chained validation of brief 16 §3 (task #21). Race-level SC prior from track structure (street-ness via low passing + high lap-1 churn) + weather, no identity. Verdict: KEPT for the ordering — structure explains the cross-sectional SC ordering (SC-rate ~ passing-rate r=−0.39; Baku/Jeddah high, Hungary low) but does NOT beat the calendar base rate for race-level prediction (SC is a near-Poisson shock). Wired as the Predictor's per-circuit SC prior (was hardcoded 0.0) for realism + Explainer, honestly not as an edge. v2 ideas listed |

## The single most important source

**Heilmeier, Graf, Betz, Lienkamp (2020),** *"Application of Monte Carlo Methods
to Consider Probabilistic Effects in a Race Simulation for Circuit Motorsport,"*
**Applied Sciences 10(12):4229** — open access, with open-source code and **real
calibrated parameter files** at [TUMFTM/race-simulation](https://github.com/TUMFTM/race-simulation).
We seed our physics, pit-loss, fuel, tyre, and safety-car parameters from this work.

## Headline corrections to the original research doc

1. **Execution noise must be positively-skewed (skewed-t), not symmetric Gaussian** —
   drivers can lose far more time than they can gain on a lap.
2. **Base lap time, fuel burn, and fuel coefficient must be circuit-specific**, not
   global constants.
3. **The "Nash equilibrium" undercut/overcut framing is mislabeled** — the correct
   primitive is a **Stackelberg cover-vs-extend** leader-follower game.
4. **Safety cars are not a flat per-lap hazard** — model count + (front-loaded)
   start-timing + duration distributions.
5. **Free OpenF1 has no live websocket** — live/streaming (MQTT/WS) is paywalled;
   the free tier is REST + historical (2023+) only.
6. **2026 energy figures were conflated** — ~8.5–9 MJ is the per-lap *harvest*
   throughput; ~4 MJ is the instantaneous battery *store* cap. Different quantities.
