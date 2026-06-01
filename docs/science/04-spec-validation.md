# 04 — Validating the Original Research Doc

This cross-checks the project's original spec — `F1Predict_ Stochastic Race
Simulation Engine.md` — against **independent web research** (academic papers,
FastF1/TUM source code, FIA regs, industry analysis). Each research agent was given
the doc's specific numbers and asked to corroborate or refute them.

**Verdict in one line:** the doc's *structure and most of its numbers are sound and
faithful to the published state of the art*. A handful of items are wrong or
oversimplified — listed under **Corrections**. Nothing fundamental is broken.

Legend: ✅ corroborated · ⚠️ corrected/refined · ❌ wrong

---

## A. Corroborated by independent research

| # | Original doc claim (section) | Independent finding | Verdict |
|---|---|---|---|
| 1 | Additive model `t_lap = physics + ML residual + ε` (§0, §1) | Canonical backbone of every published F1 sim (Heilmeier/TUM); residual-learning is a legitimate gray-box pattern | ✅ |
| 2 | Linear fuel penalty ~0.03 s/kg (§1, `t_lap_sens_mass`) | Industry rule of thumb "0.3 s per 10 kg"; TUM Catalunya uses 0.033 | ✅ |
| 3 | Fuel burn ~1.6 kg/lap (§4) | ~100–110 kg over 50–70 laps ⇒ 1.5–2.2 kg/lap; 1.6 fine for avg circuit | ✅ |
| 4 | Base lap ~85 s (§4) | Plausible generic ≈1:25 (but should be per-circuit — see Corrections) | ✅* |
| 5 | Three-phase tyre curve: warm-up → linear → cliff (§2) | Consensus in engineering + academic models; functional form is reasonable | ✅ |
| 6 | `θ1·exp(−θ2·age) + θ3·age + θ4/(1+exp(−θ5(age−θ6)))` (§2) | One basis function per regime — sound modeling instinct | ✅ (see ⚠️ #C2) |
| 7 | Vectorized lap-wise Monte Carlo, ~10k iterations (§4) | Matches Heilmeier reference architecture; iteration count appropriate | ✅ |
| 8 | Pit loss higher under green, lower under SC; ~0.45× under SC (§2) | TUM real data: SC drive portion 8.35/16.0 ≈ 0.52, ~0.45 overall | ✅ |
| 9 | VSC pit-loss between green and SC (§2) | TUM: VSC ≈ 0.55–0.70× green, SC ≈ 0.40–0.50× | ✅ |
| 10 | SC probability varies by circuit / hazard map (§2, §4) | Correct practice (Singapore ≫ Paul Ricard); AWS/teams do this | ✅ (extend — see ⚠️ #C4) |
| 11 | Dirty-air pace loss as a function of gap, era-specific (§2) | Standard; 2022+ ground-effect wake ~20% intended → ~35% actual | ✅ |
| 12 | MINLP for joint compound + energy; DP alternatives (§3) | Both are the established formulations; recent papers use MINLP+RL | ✅ |
| 13 | "3-lap-block" decision-space reduction (§3) | Acceptable coarse heuristic — cost surface near optimum is flat | ✅ (refine — see ⚠️ #C5) |
| 14 | 2026: MGU-H removed, MGU-K → 350 kW, ~50/50 split (§0) | Confirmed FIA regs | ✅ |
| 15 | 2026: DRS replaced by override/overtake mode within ~1 s (§0, §2) | Confirmed; follower gets MGU-K boost, +~0.5 MJ | ✅ |
| 16 | 2026: active aero (low-drag straight / high-downforce corner) (§0) | Confirmed (X-mode / Z-mode) | ✅ |
| 17 | 2026: narrower tyres, shorter wheelbase, lighter car (§0) | Confirmed: 768 kg, 3400 mm, front −25 mm / rear −30 mm | ✅ |
| 18 | Polymarket: midpoint + vig removal → clean probability (§4) | Correct; normalize `p_i = mid_i / Σ mid_j` for multi-outcome | ✅ |
| 19 | Fractional Kelly sizing for allocation (§4) | Standard risk-managed sizing | ✅ |
| 20 | Run on a single Hetzner VPS CPU, in-memory NumPy (§4) | Feasible; 10k×20×70 float32 vectorized is fine | ✅ |

\* base lap is realistic as a placeholder but must be circuit-specific.

---

## B. The doc actively flagged its own uncertainty (good practice — confirmed right)

- **2026 dirty-air coefficient "low-confidence until 2026 data exists" (§0):** correct
  — the *strategic consequences* of 2026 are genuinely unverified projections.
- **`BREAKING_ASSUMPTION` era-guarding (§0):** the instinct to prevent mixing
  era-dependent parameters is sound; 2022–2025 data must be excluded from 2026
  tyre/aero calibration because geometry changes wear and wake.

---

## C. Corrections (where the doc is wrong or oversimplified)

| # | Original doc claim | Problem | Fix |
|---|---|---|---|
| C1 | Execution error sampled as **symmetric** noise (`np.random.normal`, σ≈350 ms) (§4) | Drivers can lose far more time than they can gain — the residual is **positively skewed**; a symmetric draw overstates freakishly-fast laps | Use a **skewed-t** (positive skew, df≈2); clean-lap σ ≈ 0.2–0.35 s, inflate in traffic/wet. Validated: skewed-t beats symmetric (CRPS 0.202 vs 0.324) |
| C2 | 6-parameter tyre curve fit freely from FP data (§2) | **Over-parameterized** — clean long-runs rarely reach the cliff, so θ4–θ6 are weakly identified | Fit with **priors / bounds (Bayesian or bounded SLSQP)**; fall back to **linear/log** when data is sparse (Heilmeier's own guidance) |
| C3 | Undercut/overcut via **Nash equilibrium** / `nashpy` mixed strategies (§3) | **Mislabeled.** Pit moves are observed in real time → simultaneous-move/mixed-Nash assumption is weak; the leader genuinely moves first | Use **Stackelberg cover-vs-extend** backward-induction DP (Aguad & Thraves). Reserve mixed strategies for the rare no-clear-track-position case |
| C4 | Safety car as a single per-lap **hazard rate** → SC probability (§4) | A flat hazard misses the **lap-1 spike** and duration | Model **three parts**: count `[0.455,0.413,0.099,0.033]`, **front-loaded** start timing `[0.364,…]`, and duration (peak 2–4 laps) — TUM `pars_mcs.ini` |
| C5 | 3-lap blocks for the *whole* remaining race (§3) | Can miss the exact optimal lap near **hard constraints** (undercut window, tyre-rule deadline, SC window) where 1 lap is decisive | Coarse blocks for global search **+ fine ±2-lap refinement**; never quantize across a known SC window or the rival's pit lap |
| C6 | Global constant `base_lap`, `fuel_burn`, `k_fuel` (§1, §4) | Realistic as averages but **circuit-dependent** (Spa ≫ Red Bull Ring on base lap and burn) | Make all three **circuit-specific** |
| C7 | Pit loss treated as a single value scaled by status (§2) | The fixed **standstill** (tyre change ~2 s) does **not** scale with track status — only the drive portion does | **Decompose** pit loss (standstill + in-lap + out-lap); apply green/VSC/SC scaling only to the drive portion |
| C8 | Apply 0.45× SC multiplier to the whole pit loss (§2 table) | Slightly **over-discounts** because it scales the standstill too | Same as C7 — scale drive portion only |

---

## D. Factual / data errors in the doc

| # | Original doc claim | Reality | Source |
|---|---|---|---|
| D1 | Battery "harvest up to **9.0 MJ** per lap" **and** state arrays init to "**4 MJ Max**" (§0, §4) | **Two different quantities conflated:** ~8.5–9 MJ = per-lap **harvest throughput**; ~4 MJ = instantaneous **battery store cap**. Neither is "the battery size = 9 MJ" nor "deploy budget = 4 MJ" | FIA 2026 PU Technical Regs |
| D2 | OpenF1 **WebSocket** listener for free live ingestion (§4, §6) | **No free websocket.** Live/streaming (MQTT/WSS) is **paywalled** (~€9.90/mo); free tier is REST + historical (2023+) only | openf1.org/docs |
| D3 | Postgres write latency **"under 10 ms"** as a validation target (§5) | Not a guarantee on a small VPS with fsync on; durable single-row commits are low-single to tens of ms | — (engineering) |
| D4 | DRS logic present in the model for 2022–2025, disabled for 2026 (§0) | Correct — but ensure the **2026** path uses Override + active aero, **not** DRS zones (the doc does handle this, just verify in code) | FIA 2026 regs |
| D5 | Ergast/OpenF1 as historical sources (§1) | **Ergast is deprecated**; use **Jolpica** (`api.jolpi.ca`) — FastF1 already does | jolpica-f1 |

---

## E. Net effect on the build

Nothing here changes the **architecture** — the doc's pipeline (era-aware schema →
deterministic physics → ML residual → vectorized Monte Carlo → strategy
optimization → markets) is validated and we are building exactly that. The
corrections are **parameter- and module-level** and are already folded into
[ROADMAP.md](../ROADMAP.md) and the engine design:

1. Skewed-t noise sampler (not Gaussian).
2. Bounded/Bayesian tyre fit with linear fallback.
3. Strategy game relabeled and re-derived as Stackelberg.
4. Three-part SC model.
5. Coarse-block + refine optimizer.
6. Circuit-specific constants.
7. Decomposed, status-scaled pit loss.
8. Correct 2026 energy semantics (harvest vs store).
9. Data layer = FastF1 + Jolpica + OpenF1-REST, ETL→DB→web; live via polling/backfill.

**Bottom line:** the original doc is a strong, largely-accurate spec written by
someone who knew the domain; independent research confirms it and sharpens roughly
a dozen details. We build on it with confidence.
