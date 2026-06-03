# 28 — Per-car straight-line defence + the 2026 era gate

_Tasks #24 (cont.) and #26/#29. Two threads on the position-resolution sim's overtake threshold:
(1) a MEASURED per-car straight-line term — the "Abu Dhabi straight" defence; (2) an era gate for
2026's no-DRS, active-aero + energy-override rules, informed by a Formula E research scan._

## 1. Per-car straight-line speed — the "Abu Dhabi" defence

The position sim (brief 26) resolves a pass when pace surplus beats one global per-circuit
threshold. But two cars at equal race pace don't pass each other equally: a car with a straight-line
advantage clears traffic more easily and defends better. We measured it, traceably.

**Measurement (`straightline.py`).** Each car's median speed-trap reading (`speed_st`, full
coverage all years), **z-scored within each race** (absolute top speed is circuit-dependent — Monza
fast, Monaco slow — so only the within-race ranking is a car trait). Decoupled: it ties only to
observed data, is not a brand label, and adjusts only HOW a pass resolves, never the pace itself.

**It's a real, stable trait.** Team straight-line z correlates **0.82** from 2024→2025 (Williams,
Mercedes high; Sauber, Alpine low) — a persistent car characteristic, not race noise.

**It predicts clearing traffic (validated).** Joining the index to the 3,480 resolved
stuck-behind episodes from the overtake-event probe (brief 26): a logistic `pass ~ sl_z + pace
strength` gives **sl_z coef +0.094 (se 0.039, z = 2.4)** — a fast-straight car passes ~5pp more
often than a slow-straight one *at equal pace* (fast-SL 49% vs slow-SL 44%). The "Abu Dhabi
straight defence" is real and measurable.

**Wired (opt-in) into the position sim.** A per-pair term: the follower's straight-line z-advantage
over the car directly ahead lowers the pass threshold (`thr − s_per_z·(sl_follower − sl_leader)`),
swapped through track-position space alongside pace. Default **off** (`straightline_s_per_z=0`).

**Forward-chained result — neutral (honest).** Over 45 recent races, leak-free (Kalman on prior
races, each car's straight-line tendency from its PRIOR readings only), the term at s_per_z=0.15 is
a wash: top-pick 0.356→0.333, podium-ll 0.382→0.402 (worse), **points-ll 0.774→0.750 (better)**,
best-of-rest tied. The mechanism is real but feeding it into the sim doesn't improve order accuracy
at the tested magnitude. **Kept opt-in, not on by default** — consistent with the project's rule
(a validated mechanistic feature stays in the conversation as an explainer + a hook for v2, even
when it doesn't beat the baseline). v2: use the *actual car-ahead's* top speed at each gap (we
approximate with the field-relative z), and a per-circuit straight-length weight.

## 2. The 2026 era gate (no DRS → active aero + energy override)

2026 is a regulation reset: DRS is replaced by **active aero** (X/Z-mode wings, available to every
car every lap) plus an **override** — a proximity-gated (+0.5 MJ within 1 s) electrical boost, with
the chaser keeping full power to a higher speed than the leader — and a manual **Boost** usable to
attack *or* defend. Energy becomes a state variable, the way tyre deg already is.

**Formula E research scan (background subagent).** Honest verdicts:
- **FE prior data is NOT usable** for F1-2026 prediction (different cars, street circuits, far
  harsher energy limit) — and, decisively, **there is no free FE timing/telemetry API** (only
  Alkamel live timing + FIA result PDFs; no OpenF1 equivalent). Don't plan to train on FE.
- **FE methods ARE transferable.** The right abstraction (from the optimal-control / energy-
  management literature — Limebeer/Tremlett ERS power-split, the Applied-Energy convex FE
  formulation, TUM min-time control) is a **finite energy reservoir that is spent and recharged**,
  where deployment trades closing speed in the pass window against vulnerability elsewhere
  ("you can't attack and defend on the same joule").

**What we wired now (minimal, era-appropriate).** Active aero is available to *everyone every lap*,
so it creates no relative advantage — the correct, smallest change is a **global threshold
reduction** (cars follow closer → easier passing baseline), NOT a per-car term:
`ERA_THRESHOLD_MULT = {"drs": 1.0, "2026": 0.85}`. The magnitude is a shrunk prior — with only 5
2026 races we can't fit it yet, so it's deliberately conservative.

**Designed, deferred (waiting for data).** The override/Boost energy model — a per-car reservoir
`E` with spend/recharge dynamics, a straight-length-scaled boost term `b_eff`, and a chaser
asymmetry bonus — is specced from the published regs (sketch below) but **not built**: at n=5 races
any magnitude fit is noise. Build it once a season of 2026 racing exists.

```
P(pass) = sigmoid( k·( Δpace + b_eff − τ_2026 ) )
b_eff   = c · min(E_attacker, e_lap) · (L_straight / L_ref)   + a_chase   # chaser-only bonus
E_{t+1} = clamp(E_t − spend_t + r·harvest_t, 0, E_max)        # spent to attack OR defend
τ_2026  = τ_DRS · 0.85                                         # active-aero baseline (wired)
```

## Verdict

Two honest, decoupled additions to the (opt-in, research) position sim: a measured straight-line
defence term (real mechanism, neutral on order accuracy → kept opt-in + as the per-pair v2 hook)
and a conservative 2026 active-aero threshold gate, with the energy-override model designed and
deferred until 2026 data can fit it. No production probabilities change.
