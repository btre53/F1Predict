# 29 — Have we exhausted the market gap? An honest audit + open problems

_The recurring result is "competitive, no edge": pre-race winner Brier 0.054 (us) vs 0.049 (market);
pole 0.045 vs 0.039. This brief asks the question directly — is the residual gap closable on free
data, or is it structural? — and frames what's left as an open, collaborate-on-it problem._

## What the model actually uses (and what it ignores)

The production predictor (`kalman.KalmanModel.predict`) is built from exactly two inputs:
`quali_gap_pct` (this weekend's qualifying pace) and `grid` (the real starting grid). That's it.
Forward-chained prior-race pace lives in the Kalman state; this weekend it conditions on qualifying.

It does **not** use this-weekend **practice (FP1/FP2/FP3) pace** — the one piece of fresh
information the market has on Friday/Saturday that we don't fold in. So the obvious question:
would fusing practice pace close the gap?

## Why practice pace doesn't close it (on free data)

Two independent pieces of evidence say no — not because practice is uninformative in principle, but
because **the version of it we can compute from free public laps is noise**:

1. **It barely correlates with the session it should predict.** Our `fp_pace_pct` (fuel-corrected FP
   long-run % gap) correlates **0.06 with the qualifying result** and 0.05 with the grid on 2025
   races. Real fuel-corrected practice pace tracks qualifying at ~0.5–0.7; ~0 means our free-data
   long-run extraction is swamped by what we *can't* see — **fuel load, engine mode, tyre prep, and
   run program** all differ car-to-car in practice and we have none of them. Teams fuel-correct with
   telemetry; we can't.
2. **It was already in the bake-off and didn't help.** The LightGBM model (`gbm.py`) *does* take
   `fp_pace_pct` as a feature, and the bake-off verdict was "≈ the grid+quali baseline." Extra
   features, practice included, didn't beat the two-line model.

Add the coverage problem — practice is ingested for only ~45% of 2025 and 0% of 2026 races so far —
and practice pace is, today, neither clean enough nor complete enough to move the number.

## Decomposing the residual gap

Where the market's ~0.005 Brier edge actually comes from, best estimate:

| Source | Can we get it on free data? |
|---|---|
| Prior-race pace (car + driver form) | **Yes — we have it** (the Kalman) |
| The real qualifying grid | **Yes — we fuse it** (post-quali) |
| Announced grid penalties (PU components) | **Yes — already in the official starting grid** |
| **Fuel-corrected practice pace** | **No** — needs fuel loads / engine modes / tyre state we lack |
| Setup direction, car upgrades' true step | **No** — paddock/telemetry intel |
| Soft information (sentiment, sharp money) | **No** — the crowd prices it; we structurally can't |

The top three we already extract. The bottom three are the market's edge — and they all require data
we **don't have access to**, not cleverer modelling of data we do have.

## The two cases the owner asked about

- **Pre-race winner (post-quali).** Largely **exhausted on free data.** Once the real qualifying grid
  is fused, this-weekend practice is redundant (qualifying is a cleaner, later read of the same pace),
  and penalties are already in the grid. The residual is structural — soft info. We're near the floor.
- **Pre-qualifying / pole.** This is where a lever *could* exist — there's no qualifying yet, so
  this-weekend practice (especially FP3, run right before quali) is the only fresh pace signal, and
  we currently ignore it. But it's exactly the signal that's too noisy/sparse for us to clean up
  (the 0.06 correlation is measured on this regime). So it's the **most promising open problem and
  also the hardest** — gated on data we can't fuel-correct without telemetry.

## Honest verdict

On free, public data we have extracted essentially all the reliable pre-race signal. The market's
remaining edge is **structural** — it prices information (fuel-corrected internal pace, setup/upgrade
intel, crowd sentiment) that no amount of re-modelling our inputs can recover. We did not find a
free lever that closes the gap, and the two we could test (practice pace, the GBM feature set) come
back null. The realistic ceiling is the one we've hit: well-calibrated, transparent, competitive,
no edge.

## Open problems — collaborate

This is the frontier, posted as an invitation rather than a conclusion. If you can crack any of these,
the gap might narrow:

1. **Clean practice pace from public laps.** A robust fuel-/tyre-age-corrected long-run extraction
   that actually correlates with qualifying (>0.4) — the single highest-value unlock, and the one
   gating the pole market. Needs a better stint/fuel model and far better practice-ingest coverage.
   **NB: today this is not even testable on the priced races** — FP is ingested for ~45% of 2025 and
   0% of 2026, so we have almost no practice data for the races that carry market prices. Step one is
   coverage (ingest FP1–FP3 reliably), only then can the signal be validated. Until then, FP closing
   the gap is an assertion we *cannot* test, not a lever we've ruled in.
1b. **Practice as a *driver-skill* read, not a pace read** (owner's idea). On representative laps a
   driver takes a consistent preferred line, so practice telemetry might isolate driver skill from
   car. Tempering evidence: brief 12 (telemetry→racecraft) came back amber and brief 19 (car-DNA
   corner-bands) showed no lift over scalar pace, both on cleaner race/quali telemetry. Practice adds
   confounds — non-push laps, race-start practice, setup/fuel changes between runs — so expect the
   same amber unless those can be filtered out (push-lap detection + line-consistency on matched
   corners). A real but uphill open problem.
2. **A race-weather *pace* model** (not just the points-widening we ship): condition pace + DNF on an
   ex-ante forecast. Few wet races → hard to validate without overfitting.
3. **Recency / upgrade-step adaptation.** The Kalman's process noise is fixed; a mid-season upgrade
   isn't seen until results arrive, but the market reads it from practice. A principled
   time-varying / change-point process noise, without overfitting recency.
4. **Alternative free data.** Anything public the market prices that we don't ingest — official
   penalty/stewards feeds, tyre allocations, FP3-specific reads.

If you have a model that beats `market_backtest.py` out-of-sample on the priced races, open a PR — the
harness is built to score it honestly.
