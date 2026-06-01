# 02 — Race Strategy & Race-Event Modeling

The science behind the Strategy Lab: pit stops, undercut/overcut, game theory,
optimization, safety cars, and dirty air. Backbone source throughout is the
**TUM Heilmeier simulator** (peer-reviewed + open source with real parameter
files), cross-checked against academic game-theory/DP papers and AWS F1 Insights.

---

## 1. Pit-stop fundamentals

Total race time = sum of per-lap times + a fixed time penalty per stop. Each stop
costs a **pit loss** (~18–25 s, circuit-dependent) but resets tyre degradation.

```
T_race = Σ_laps t_lap  +  Σ_stops (t_standstill + t_pitdrive_in + t_pitdrive_out)
```

⚠ **Correction:** pit loss is **not a single constant** — decompose it. TUM
Catalunya 2019 real values: standstill ≈ 1.9 s (+team add), in-lap drive ≈ 3.04 s,
out-lap drive ≈ 16.0 s ⇒ green pit loss ≈ **~21 s**. This decomposition is what
makes the green/VSC/SC scaling (§6) physically correct.

**One-stop vs two-stop:** an extra stop costs one pit loss (~20 s) but buys fresher
tyres. Worth it only when degradation time saved over the remaining laps exceeds
the pit loss. **Under linear degradation, total race time is quadratic in stint
lengths**, so the optimal split is a small, fast quadratic program (TUM
`opt_strategy_basic.py`).

| Parameter | Value | Units |
|---|---|---|
| Green pit loss (total) | 18–25 | s |
| Standstill tyre change | 1.9–2.5 (+team) | s |
| Fuel-mass sensitivity | 0.030–0.040 | s/kg |
| Lap-time noise σ (driver) | 0.46–0.86 (unknown 0.625) | s |

> **Explainer:** *Your total race time is just the sum of every lap plus a fixed
> ~20-second penalty each time you pit. Pitting more often means fresher, faster
> tyres — but each extra stop only pays off if the time saved beats that 20-second
> cost. We find the stop count and stint lengths that minimize total time.*

---

## 2. Undercut & overcut

- **Undercut:** pit *before* the rival; fresh tyres (~1–2 s/lap faster on the
  out-lap, decaying) bank enough time to emerge ahead after they pit.
- **Overcut:** stay out *longer*; the rival pits into cold tyres/traffic while
  your warm tyres still outpace their out-lap.

```
undercut works when:  Σ (per-lap fresh-tyre advantage)  >  gap_to_car_ahead
```

| Quantity | Value | Units |
|---|---|---|
| Fresh-tyre out-lap advantage | 1.0–2.0 (lap 1, decaying) | s/lap |
| Total undercut gain over window | ~1–3 | s |
| Required on-track overtake gap | ~1.5–2.5 | s |
| DRS benefit (pre-2026) | 0.3–0.8 | s/lap |

**Undercut dominates** on high-degradation tracks; **overcut wins** when deg is
low, warm-up is slow (cold/hard tyres), or the rival rejoins in traffic.

> **Explainer:** *An undercut means pitting a lap or two earlier than the car
> ahead: your fresh tyres are ~1–2 s/lap faster, so you bank time while they're on
> worn rubber and leapfrog them when they finally pit. An overcut is the opposite.
> Undercuts win on high-wear tracks; overcuts win when tyres last.*

---

## 3. Game theory — Stackelberg, not Nash

⚠ **Correction:** the original doc's "Nash equilibrium" framing is **mislabeled**.
The correct primitive is a **leader-follower (Stackelberg) game**: the leader
decides whether to **cover** (pit immediately to deny the chaser's undercut) or
**extend** (stay out for fresher tyres later). Solve by **backward-induction
dynamic programming** lap-by-lap to the finish (Aguad & Thraves, EJOR 2024).

**Why not Nash/mixed strategies?** Pit decisions are observed essentially in real
time — you *see* the rival enter the pit lane and react within a lap — so the
simultaneous-move assumption is weak. The leader genuinely moves first. Reserve
mixed strategies for the rare case where neither car has clear track position.

**Reported value of the strategic approach:** +>15% win probability, ~2.3 s
average race-time improvement, −17.8% probability of being undercut.

> **Explainer:** *When two cars fight on strategy it's a chess match: the leader
> must decide whether to "cover" by pitting the moment the chaser does, or gamble
> on staying out for fresher tyres later. We model this as a leader-follower game
> solved backwards from the finish — how real strategists think. Textbook "random
> mixed strategies" rarely apply, because in F1 you can see your rival pit and
> react.*

---

## 4. Optimization formulations

- **MINLP:** integer decisions (pit laps + compound per stint) + continuous state
  (tyre/energy/fuel). Objective: minimize total race time. Most general; recent
  work trains RL to approximate it for fast inference.
- **Dynamic programming:** discretize (lap, tyre age, compound, position), solve
  by backward recursion. Natural for adding stochastic SC/rain events.
- **Linear-deg special case:** the inner stint-length problem is a **convex QP** —
  solved in milliseconds.

```
V(lap, state) = min over action { stage_cost(action) + V(lap+1, next_state) }
```

**Tractability (single CPU):** linear-deg QP — ms; DP for 1–2 cars — seconds to
minutes; full multi-car MINLP with energy — minutes+ (pre-compute offline).

⚠ **On the doc's "group remaining laps into 3-lap blocks":** acceptable as a
*coarse* search (the cost surface around the optimum is flat), **but** add a fine
±2-lap local refinement and **never block-quantize across a known SC window, the
tyre-rule deadline, or the rival's pit lap** — there 1 lap is decisive.

> **Explainer:** *Finding the best strategy is an optimization problem: which laps
> to pit and which tyres to fit, to minimize total time. With simple (linear) tyre
> wear it has a fast exact solution; with realistic curves we search lap-by-lap.
> To stay fast we search in coarse lap-blocks, then fine-tune around the best
> window — but always check the exact lap near undercut windows or safety cars.*

---

## 5. Safety car / VSC modeling

⚠ **Correction:** a flat per-lap hazard is wrong. Model **three things** (TUM real
parameters, 2014–2019):

- **Number of SC phases per race** `p_sc_quant = [0.455, 0.413, 0.099, 0.033]` →
  **~54.5% of races have ≥1 SC.**
- **Start timing** `p_sc_start = [0.364, 0.136, 0.136, 0.08, 0.193, 0.091]` →
  **heavily front-loaded** (36% on lap 1).
- **Duration** peaks at **2–4 laps** SC; **1–2 laps** VSC.
- **VSC after a failure** = 0.227; retirements/accidents feed the event generator.

A **per-circuit hazard base rate** is good practice (Singapore/Baku/Monaco ≫ Paul
Ricard) — layer the start-timing + duration profiles on top of it.

> **Explainer:** *Safety cars are random but predictable in aggregate: about half
> of all races see at least one, they're most likely right after the start, and
> they usually last 2–4 laps (a Virtual Safety Car is shorter). Some tracks almost
> always throw one. We run thousands of simulated races drawing these events to see
> how robust each strategy is.*

---

## 6. Pit-loss under green vs VSC vs SC

The pit-lane speed limit is fixed, so time *in* the lane barely changes — what
changes is the **opportunity cost**, because under SC/VSC the on-track cars are
forced slow.

| Status | In-lap | Out-lap | Effective relative loss |
|---|---|---|---|
| **Green** | 3.04 s | 16.0 s | full ≈ ~21 s |
| **VSC** | 0.39 s | 9.64 s | ~0.55–0.70× green |
| **SC** | −0.47 s | 8.35 s | ~0.40–0.50× green |

⚠ The doc's **~0.45× under SC is well-supported** — but apply the discount **only
to the drive portion**, not the fixed standstill (the tyre change still takes
~2 s regardless of track status).

> **Explainer:** *Pitting always takes ~20 seconds in absolute terms, but under a
> Safety Car everyone else is slow too, so you "lose" far less — typically under
> half the normal cost. That's why a well-timed safety car is a free pit stop, and
> why strategists pray for one inside their pit window.*

---

## 7. Dirty air & overtaking

A following car loses downforce in the wake; the loss grows as the gap closes. You
can pass only when your pace advantage exceeds a track-specific threshold that
dirty air inflates.

```
pace_loss_dirty_air(gap) = L_max · exp(−gap / g0)     # g0 ≈ 1 s; vanishes beyond ~1.5–2 s
overtake when:  pace_advantage > t_gap_overtake  (Catalunya 2.31 s, −0.756 s with DRS)
```

| Quantity | Value | Units |
|---|---|---|
| Downforce loss following (2022+ ground effect) | ~20% intended, crept to ~35% | % |
| DRS top-speed gain (pre-2026) | 10–20 | km/h |
| Required overtake pace delta | ~0.8–2.3 (track) | s/lap |
| Min following gap | 0.5 (green) / 0.8 (SC) | s |

Overtaking is the **least physically-grounded part of any sim** — budget tuning
effort here, not on fuel/tyre physics which are well understood.

> **Explainer:** *Following closely ruins a car's aerodynamics — in turbulent
> "dirty air" it loses grip and slides, so you can't pass on pace alone. To
> overtake you need a pace advantage bigger than a track-specific threshold (often
> ~0.8–1.5 s/lap), which fresh tyres or DRS/overtake-mode can provide.*

---

## 8. 2026 strategy implications (projections — flag uncertainty)

Rule *inputs* are confirmed; strategic *consequences* are projections — label them
as such in the app.

- **DRS removed → "Manual Override" boost:** a car within ~1 s gets extra MGU-K
  energy (350 kW up to ~337 km/h, +~0.5 MJ). Overtaking becomes an **energy-budget
  decision**, not just track position.
- **Active aero (Z-mode high-downforce / X-mode low-drag)** replaces fixed DRS
  zones — overtakes spread out across the lap.
- **Bigger ERS (MGU-K 120→350 kW, ~8.5–9 MJ/lap harvest, ~50/50 split):** energy
  management becomes a **first-class strategic variable** alongside tyres. The
  optimization moves from "pit-laps + compounds" to **"pit-laps + compounds +
  per-lap energy allocation."**

> **Explainer:** *From 2026, DRS is gone — replaced by active wings that switch
> between low-drag and high-grip modes, plus an "override" electrical boost for a
> car chasing within a second. With far bigger hybrid systems, managing battery
> energy lap-by-lap becomes as strategic as managing tyres. These are early
> projections based on the published rules — real racing may differ.*

---

### Sources
- [TUMFTM/race-simulation](https://github.com/TUMFTM/race-simulation) (code + real parameter files)
- [Heilmeier et al. 2020, Applied Sciences](https://www.mdpi.com/2076-3417/10/12/4229)
- [Aguad & Thraves, Stackelberg pit-stop game (EJOR 2024)](https://www.sciencedirect.com/science/article/abs/pii/S0377221724005484)
- [Pit-stop optimization via DP (CEJOR 2022)](https://link.springer.com/article/10.1007/s10100-022-00806-4)
- [AWS F1 Insights](https://aws.amazon.com/sports/f1/)
