# 11 — In-Play Edge Strategies: Latency Arbitrage & Weather Mispricing (feasibility)

Honest, skeptical assessment of two proposed in-play "edge" strategies **against our
actual setup** (free data only; FastF1 historical; Polymarket the only free in-play
odds source with thin liquidity; no free low-latency odds feed; no free tick-level
bet venue). Read alongside [05-live-data-sources.md](05-live-data-sources.md) (feed
latency/risk) and [07-polymarket-backtest.md](07-polymarket-backtest.md) (we already
have **no pre-race edge over the market**).

> **Framing the owner will recognise:** latency arbitrage requires you to be the
> *fastest* informed participant on a venue with *fillable* liquidity, against a
> counterparty who *cannot* pull quotes faster than you act. F1 retail betting
> violates all three. This is the opposite of the microstructure where latency arb
> works (co-located equities/futures). The signals below are real **research signals**;
> the *latency-arb execution* is a fantasy on our infra. The salvageable products are
> calibration / companion / paper-trading tools.

---

## Strategy 1 — Real-time undercut/overcut latency arbitrage

**Premise:** model live differential tyre-deg + pit-loss to detect when a chaser
enters the undercut window, and bet the winner/leader/next-laps market *before the
book reprices the pit cycle*.

### (a) Is the SIGNAL real and backtestable on our free data? — **Yes, partially.**

The undercut/overcut mechanic is genuinely modellable and we already have the physics
([02-race-strategy.md](02-race-strategy.md)): green pit loss ≈ 21 s (decomposed into
standstill ~1.9 s + in-lap ~3.0 s + out-lap ~16 s), fresh-tyre out-lap advantage
1–2 s/lap decaying, the Stackelberg cover-vs-extend leader-follower game, and SC/VSC
pit-loss discounts (~0.45×/~0.6×). FastF1 gives everything needed to *backtest the
signal* on ~85 races (2018+): per-lap & per-sector times, stint/compound/tyre-age,
positions/gaps, and `CarData` (speed/throttle/brake/DRS/gear).

**Concrete backtest sketch on FastF1 (the honest version):**

1. **Reconstruct live state per lap** from `laps` + `pos_data`: for each (chaser C,
   leader L) pair on the same compound family, compute gap `Δt`, both cars' tyre age,
   and a fitted per-stint **degradation slope** `β` (s/lap) from a rolling regression
   of clean (non-traffic, non-in/out, fuel-corrected) lap times vs tyre age. Fuel
   correction uses the circuit fuel coefficient (0.03–0.04 s/kg) from doc 02.
2. **Undercut-window predictor:** the model says C nets the place if
   `Σ_window (fresh-tyre advantage) − Δt_loss_diff > Δt_gap`, where the fresh-tyre
   advantage integral uses C's projected out-lap delta and L's projected on-old-tyre
   pace over the cycle. Output `p_swap = σ(score)`.
3. **Label** from the actual race: did C come out ahead of L within N laps of the pit
   cycle? (FastF1 positions give ground truth.)
4. **Benchmark vs a naive gap model** (e.g. "undercut works iff `Δt < 21 s`" or a
   logistic on raw gap only). The scientific question is whether differential-deg +
   out-lap modelling beats the naive gap model in AUC/Brier on held-out races.
   **This is a clean, forward-chained, leak-free backtest** and is worth doing — it
   directly strengthens the Strategy Lab regardless of betting.

**Honest caveats on the signal:** (i) n is small — ~85 races, and *contested* pit
battles per race are few, so usable samples are in the low hundreds, not thousands;
guard against overfitting with circuit-level pooling and simple models. (ii) Out-lap
pace and traffic-on-rejoin are the **least physically-grounded** part (doc 02 §7);
they dominate the actual swap. (iii) The deg slope is only well-estimated *after*
several green laps on the stint — early-stint detection is noisy exactly when you'd
want to act.

### (b) Is the live EXECUTION (latency arb vs a bookmaker) achievable? — **No. Not on our infra, and arguably not on any retail infra.** Brutally:

1. **We have no fast, fillable odds venue.** Betfair is dropped (paid/account-gated).
   Traditional sportsbooks are **one-way** (you take *their* price; you cannot post a
   resting order), and they **kill your bet in the acceptance spool** if a material
   event occurs in the 3–8 s window — which is *exactly* a pit stop or position swap.
   So the bet you most want to place is the bet they will most reliably void.
2. **You are not faster than the book.** The "edge" assumes you see the pit stop
   before the book does. You don't. Bookmakers trade off the **same** official timing
   data (or faster commercial feeds) and watch the world feed; the F1 SignalR feed is
   ~100–500 ms transport but **FastF1's client is record-to-file, not real-time**
   (doc 05) — to be live you'd need a custom `signalrcore` client, which is
   unsanctioned and IP-blocked. Even built perfectly, you'd be *level with* the book,
   not ahead. Courtsiding-style latency edges exist only because a *human at the venue*
   beats a *broadcast delay*; here the book is on the wire feed, not the broadcast.
3. **Markets suspend on exactly the events you're trading.** In-running motorsport
   markets get suspended/repriced during pit windows, incidents, SC/VSC and the
   pit-cycle itself. The moment your signal fires is the moment the market is
   suspended or the price has already gapped.
4. **Liquidity to fill does not exist for micro-markets.** Even where Polymarket lists
   per-race F1 markets (winner, pole, fastest lap, podium, H2H, safety-car, red-flag),
   the **book is shallow** and during live play depth is thin (Polymarket's own sports
   research notes shallow depth as a binding arbitrage constraint; spreads blow out
   post-event). "Next pit" / "next-laps position swap" micro-markets effectively
   **don't exist** as liquid retail products. There is nothing to hit in size.
5. **Polymarket isn't a latency venue anyway.** It's a CLOB with off-chain matching +
   on-chain settlement; round-trip and gas/settlement frictions are seconds+, and
   resting MM liquidity is sparse on F1. You will not win a millisecond race there.

**Verdict on execution:** pure latency arbitrage is **infeasible**. There is no venue
where a free-data retail user is simultaneously faster than the book, able to post or
fill, and not suspended at the decisive moment.

### (c) Salvageable version — **a companion/strategy tool + Polymarket paper-trade calibration.**

- **Live undercut/overcut advisor (companion feature):** surface `p_swap` and the
  undercut-window countdown in the app during a race (driven by the ~3 s OpenF1 paid
  feed *if/when* justified, else delayed SignalR for a local demo). Sells the quant
  story without claiming a betting edge. This is the natural extension of the Strategy
  Lab and is **the recommended prototype.**
- **Polymarket-only "slow alpha", not latency arb:** if our pit-cycle model is genuinely
  better-calibrated than the *thin* live Polymarket winner/leader price between events
  (not in the millisecond after one), that's a **medium-frequency mispricing** edge,
  capped hard by liquidity. Test it as **paper trades** against historical Polymarket
  `prices-history` first (doc 07 infra), measuring CLV against the price 1–5 min later.
  Treat any positive result as a research finding, not a live trading plan.
- **Markets that actually exist in-play for F1 (where, honest):** *winner, podium,
  pole/quali, fastest lap, constructor winner, driver H2H, safety-car (yes/no),
  red-flag* — listed on Polymarket per-race and on mainstream sportsbooks in-play.
  *Next pit-stop lap / next-lap position swap* are **not** real liquid retail markets.
  Number-of-pit-stops and "will there be a SC/VSC" props exist pre-race at books but
  are coarse, not pit-cycle-latency-tradeable.

---

## Strategy 2 — Weather micro-climate / track-evolution mispricing

**Premise:** scrape hyper-local sector-level weather + track-state; bet rain-sensitive
props (fastest lap, over/under pit stops, etc.) while the book still prices "dry."

### (a) Is the SIGNAL real and backtestable? — **Track-evolution: yes. "One sector wet" micro-edge: no.**

**FastF1 Weather kills the sector-specific premise.** `session.weather_data` is a
**single weather station per circuit**, ~1-minute granularity, columns: `AirTemp`,
`TrackTemp`, `Humidity`, `Pressure`, `Rainfall` (**bool**, not mm), `WindSpeed`,
`WindDirection`, `Time`. There is **no sector-resolved weather** in our data — F1's
own feed is one station. So "bet because sector 3 is wet but the book prices dry" is
**not obtainable** from any free source: neither FastF1 nor circuit-level forecast APIs
give per-corner rainfall. The premise of beating the book on *sub-circuit* spatial
resolution is a fantasy on free data.

**What IS real and backtestable: circuit-level track evolution / grip.** With FastF1
weather + laps we can model:

- **Track evolution:** lap-time `t_lap` falls over a session as rubber goes down; fit
  `t_lap ~ f(track_temp, session_progress, fuel, tyre_age)` and quantify the grip
  trend. Backtestable across all sessions (FP/Q/R) 2018+.
- **Rain transition model:** `Rainfall` bool flips + `TrackTemp`/`Humidity` deltas mark
  wet onset; model the lap-time penalty and compound-crossover timing (slick→inter).
  This is the genuinely valuable, sourced signal and feeds the Strategy Lab's SC/rain
  Monte Carlo (doc 02 §5). **Backtest sketch:** label sessions with rain onset times
  from `Rainfall`; regress lap-time inflation and pit-rate response; validate the
  model's crossover-lap prediction against actual stops.

### (b) Free hyper-local weather sources (concrete, with URLs)

| Source | URL | Granularity | Free? | Use |
|---|---|---|---|---|
| **FastF1 `session.weather_data`** | https://docs.fastf1.dev/core.html | 1 station/circuit, ~1 min, `Rainfall` bool | yes | ground-truth track-side history for backtest |
| **Open-Meteo Forecast** | https://open-meteo.com/en/docs | point lat/lon, hourly + **15-min** (EU/NA), no key | yes | live-ish circuit forecast (precip prob/mm, temp) |
| **Open-Meteo Historical (ERA5)** | https://open-meteo.com/en/docs/historical-weather-api | point, hourly, 1940+ | yes | backtest weather context vs FastF1 |
| **Open-Meteo Historical-Forecast** | https://open-meteo.com/en/docs/historical-forecast-api | archived forecasts, 2022+ | yes | "what did the forecast say pre-session?" leak-free |
| **OpenWeatherMap** | https://openweathermap.org/api | point, key (free tier) | partial | fallback / minutely precip nowcast (limited) |

All are **circuit/point-level**, never sub-circuit. Open-Meteo is the pick (no key,
15-min in EU/NA where most circuits are, historical+forecast for leak-free backtests).
Note granularity mismatch: Open-Meteo forecast precip is hourly-ish/15-min and modelled,
whereas FastF1's `Rainfall` is a coarse trackside bool — they're complementary, not
interchangeable, and neither resolves "which corner is wet."

### (c) Is there an executable edge? — **No durable latency edge; a modest forecast-timing angle at best; mainly a companion/visualisation feature.**

- **The book is not slower than you on rain.** Sportsbooks employ meteorologists and
  trade the same public forecasts; "the book still prices dry while it's raining" is
  not a real standing inefficiency — and the instant rain is visible, **markets
  suspend** (rain is a maximal-uncertainty event; in-running F1 markets go off).
- **Open-Meteo gives you no informational lead over a professional book.** Any edge
  would have to come from *better modelling of the consequence* (e.g. crossover timing,
  pit-count distribution under marginal conditions), not from *seeing the weather
  first*. That's a slow, pre-race prop-calibration edge at most, capped by the same
  thin Polymarket liquidity — and our doc-07 result says we don't currently beat the
  market even pre-race.
- **Sector-wet premise is dead on free data** (single-station feed), as above.

### Salvageable version

- **Track-evolution & rain-transition companion view:** plot grip evolution
  (`track_temp` + rubbering-in) and a wet-onset/crossover-lap predictor in the app.
  High portfolio value, zero execution risk, fully backed by FastF1 + Open-Meteo.
- **Rain-prop calibration (paper/research):** compare our rain-conditioned prop model
  (number of stops, "will it rain during race", fastest-lap regime) to historical
  Polymarket/forecast pricing as a calibration study — a research signal, not a live
  edge.

---

## Verdicts

| Strategy | Signal real & backtestable? | Live execution on our setup? | What it actually is |
|---|---|---|---|
| **1 — Undercut/overcut latency arb** | **Yes** (FastF1 deg + pit-cycle model; clean leak-free backtest vs naive gap model) | **No** — no fast fillable venue, you're not faster than the book, markets suspend on the exact event, micro-markets have no liquidity | **Backtest-only research signal → companion advisor.** Latency-arb claim is a **gimmick**; the strategy model is real. |
| **2 — Weather micro-climate mispricing** | **Track-evolution / rain-transition: yes. Sector-specific: no** (FastF1 = 1 station/circuit; no free sub-circuit data) | **No** — book isn't slower on forecasts; markets suspend on rain; sector premise infeasible | **Companion/visualisation + slow prop calibration.** Sub-sector edge is a **fantasy**; circuit grip/rain model is a **real research signal**. |

**Worth prototyping (in order):**
1. **Undercut/overcut backtest** — `p_swap` model vs naive gap baseline on FastF1
   (leak-free, forward-chained). Strongest quant story; feeds the Strategy Lab.
2. **Track-evolution + rain-transition companion view** — FastF1 weather + Open-Meteo;
   pure upside, no execution risk.
3. **Polymarket paper-trade harness** — score both models' implied vs actual price
   *minutes later* (CLV) on historical `prices-history`. If — and only if — that shows
   persistent mispricing beyond the thin spread, revisit live; expect it won't, per
   doc 07.

**Do NOT build:** a live latency-arbitrage bet-placement bot. There is no free
(or cheap-retail) configuration where we are faster than the book, able to fill, and
unsuspended at the decisive moment. Frame these as **analytics/decision-support and
calibration**, consistent with the honest "no edge over the outright market" stance
already in docs 07 and 09.

---

### Sources
- F1 SignalR feed latency & TV delay: [undercut-f1 (variable delay TUI)](https://github.com/JustAman62/undercut-f1), [matteocelani/f1-telemetry (SignalR→WS)](https://github.com/matteocelani/f1-telemetry), [F1 Delayed Live Timing extension](https://chromewebstore.google.com/detail/f1-delayed-live-timing/gchagbhdnlcnmkhplddglibfdjbbeclg)
- In-play bet delay / acceptance spool & suspension: [Gambling Commission — in-play/in-running betting](https://www.gamblingcommission.gov.uk/licensees-and-businesses/guide/in-play-or-in-running-betting), [In-play bet delays (operator strategy)](https://www.linkedin.com/posts/gareth-crook-sportsbook_-activity-7407336832406953984-7nX1), [arbusers — in-play bet delay](https://arbusers.com/in-play-bet-delay-t6296/)
- Latency-arb / courtsiding reality: [Courtsiding — Wikipedia](https://en.wikipedia.org/wiki/Courtsiding), [Betfair in-play delay explained](https://caanberry.com/betfair-exchange-in-play-delay-explained/)
- F1 in-play markets that exist: [Polymarket F1 (per-race winner/pole/FL/podium/H2H/SC/red-flag)](https://polymarket.com/sports/f1), [SportyTrader — F1 bet types (pit-stop count, SC, rain props)](https://www.sportytrader.com/en/sports-betting/guide/what-bets-can-you-expect-on-f1/)
- Polymarket CLOB liquidity/depth: [QuantVPS — Polymarket CLOB](https://www.quantvps.com/blog/polymarket-clob-central-limit-order-book), [Arbitrage Analysis in Polymarket NBA Markets (arXiv) — shallow depth as binding constraint](https://arxiv.org/pdf/2605.00864), [CLOB v2 liquidity rewards](https://crypto.news/polymarket-rolls-out-clob-v2-with-1m-liquidity-rewards-to-harden-prediction-markets/)
- FastF1 Weather schema (single station, 1-min, `Rainfall` bool): [FastF1 core docs](https://docs.fastf1.dev/core.html), [FastF1 #26 weather data](https://github.com/theOehrly/Fast-F1/issues/26)
- Free weather APIs: [Open-Meteo](https://open-meteo.com/), [Forecast API (15-min)](https://open-meteo.com/en/docs), [Historical-Forecast API](https://open-meteo.com/en/docs/historical-forecast-api), [OpenWeatherMap](https://openweathermap.org/api)
- Internal: [05-live-data-sources.md](05-live-data-sources.md), [07-polymarket-backtest.md](07-polymarket-backtest.md), [02-race-strategy.md](02-race-strategy.md)
