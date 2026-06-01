# 13 — In-play WPA Backtest vs Polymarket (step 3 / brief 10 §1)

**Question:** can a fair-price engine fed from reconstructed race state produce a **live
win probability that leads** the thin/slow Polymarket winner market around on-track
events? This is *the* edge thesis (brief 10 §1). Steps 1–2 cleared the way: racecraft is
not a telemetry edge (brief 12), but the market *does* reprice live (brief: step 2,
`inplay_probe.json` — 11/11 races move). Now the real test.

**Build** (`app/etl/inplay_backtest.py`, free offline replay over the 11 2024 races with
Polymarket coverage):
1. **State reconstruction** from `laps.parquet`: per lap, each car's running position,
   cumulative time gap, recent-5-lap green pace, laps remaining, track status.
2. **Live win-prob** = a fast vectorized Monte Carlo (6k sims) over the **remaining** laps
   seeded from that state (gaps + recent pace + flat DNF hazard `h=0.0016/lap`). A
   purpose-built live engine, **not** the mechanistic sim (known miscalibration, awkward
   to re-seed mid-race). DNF/regime hooks are where briefs 10 §2/§3 plug in later.
3. **Wall-clock alignment**: race start = scheduled lights-out (`Session5DateUtc`), each
   lap stamped by cumulative leader lap-time. São Paulo (rain-delayed) flagged & excluded
   from timing tests.
4. **Score vs Polymarket** `prices-history` curves: live-prob calibration; level CLV +
   reverse placebo; and the decisive **detrended increment cross-correlation**.

## Results

**Calibration (live win-prob, pooled over all laps, n≈4.5k driver-laps):**
- ours: Brier **0.048**, logloss 0.188 — well-calibrated.
- market: Brier 0.057 at our best-guess alignment.
- **But this is alignment-sensitive:** shifting our clock vs the market sweeps the market's
  Brier from 0.066 (−10 min) to 0.045 (+10 min). So we **cannot claim a calibration edge** —
  honestly, our live prob is *comparable* to the market, which is itself a respectable result
  (a free, lap-data engine matching a live market's calibration).

**Lead-lag — the edge test:**
- Level CLV (our−mkt predicts the market's next 5-min move): mean **+0.46**.
- Reverse **placebo** (mkt−our predicts *our* next move): mean **+0.36**.
  - Our prob is a pure function of race state — it *cannot* chase the market — so this high
    placebo exposes the level CLV as mostly **common-trend co-convergence** (both series
    climb toward the same resolution), not a lead.
- **Detrended increment cross-correlation** `corr(Δour[t], Δmkt[t+lag])` on a 60s grid
  (first differences remove the shared trend; n=6824):

  | lag | −300 | −180 | −120 | −60 | 0 | +60 | +120 | +180 | +300 |
  |---|---|---|---|---|---|---|---|---|---|
  | corr | −0.02 | −0.01 | 0.00 | −0.02 | −0.02 | **+0.03** | 0.00 | −0.02 | +0.01 |

  **Flat at every lag.** No peak at positive lag. With n=6824 a lead of corr≳0.1 would be
  clearly visible; we see ~0. **Our engine does not move before the market.**

## Verdict — no exploitable in-play edge (a cheap, clean kill)

The simple WPA engine is well-calibrated but **does not lead Polymarket**. The apparent CLV
was a co-convergence artefact; the detrended test — the honest one — is null. Per brief 10's
own pre-registration, *"if it doesn't lead, we've cheaply killed the only edge thesis — also
a win."*

**Why this was nearly structural (and what it does/doesn't rule out):**
- Our engine reconstructs state from **completed laps**, so it lags real-time by up to a lap
  (~90s) by construction. A market watching the live broadcast/timing feed will not be beaten
  by a lap-completion engine. This is the core reason — and it converges with brief 12
  (telemetry's marginal value is low) and brief 11 (live latency-arb is inexecutable for
  retail). **Three independent threads, same negative.**
- **Not fully ruled out:** a *smarter* engine (hazard DNF, brief 10 §2; regime/SC detection,
  §3) reacting to specific high-information events (a contender's DNF, an SC) *might* lead on
  those rare jumps even if it can't on the average lap. The harness is built and reusable —
  re-run after the hazard/regime models land, and restrict the lead test to event windows.
  But the bar is now: show a positive detrended lead **at event timestamps**, not in aggregate.

**Recommendation:** do **not** pursue live in-play trading or pay for OpenF1 on this evidence.
Ship the live win-prob as a **calibrated race-companion overlay** (engagement feature, the
"anti-AWS" — it matches the market without claiming to beat it), and redirect modeling effort
to the **props/sub-markets** lane (brief 10) and the **hazard DNF model**, which improve
finishing-position props regardless of the in-play null.

_Artifacts: `app/etl/inplay_backtest.py`, `data/inplay_backtest.json`._
