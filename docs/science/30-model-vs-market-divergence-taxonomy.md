# 30 — Why our model diverges from the market: a taxonomy (and what to do about it)

_Brief 29 concluded we're at the free-data ceiling on the AVERAGE gap. This brief is the
complement: a structured account of WHERE and WHY our probability diverges sharply from Polymarket
on individual outcomes — the cases an honest model should be able to explain about itself. It also
maps the divergence onto the ranking-model literature (Harville / Henery / Lo–Bacon-Shone) and
reports a validated fix._

## The motivating experiment: a fast car starting last

We forced the model's favourite to start P20 and measured its win probability:

| Track | Favourite (normal grid) | Forced to P20 |
|---|---|---|
| Monaco | 24% | **0.0%** |
| Bahrain | 15% | **8.9%** |

Two things fall out immediately. (1) The model is **already circuit-aware** — it crushes a P20 car
at Monaco but gives a fast P20 car at Bahrain a real 8.9%, because the overtaking-difficulty index
tells it Monaco is a track-position lock. (2) The Monaco **0.0% is too absolute** — nothing is truly
0%; Monaco's high safety-car rate + strategy offset gives a recovering car a small but real chaos
tail the Monte Carlo under-samples. (And the popular intuition that "a P20 star is still 15-20% at
Monaco" is itself wrong — that holds at *overtaking* tracks, not Monaco.)

## The taxonomy

Our model is a **pace + grid engine with roughly symmetric noise**. The market is a **pace engine
+ a fat chaos tail + soft priors**. We diverge exactly where the extra ingredients dominate.

**We read LOWER than the market (under-price a contender):**
1. **Fast car starting low** (grid penalty / Q1-out) at an overtaking track — recovery is real; we
   may under-give it.
2. **The fat tail** — a star car/driver is never truly out (safety car, rain, others' DNFs, a
   strategy offset). Our MC applies field-average noise and has no explicit "recovery via chaos"
   path, so it thins this tail; the market keeps stars "in the mix."
3. **Carve-through over-penalty** — a much-faster car stuck behind a backmarker is penalised as if
   the backmarker defends to the death (it doesn't — see the fix below).

**We read HIGHER than the market (over-price):**
4. **Hot-streak extrapolation** — we over-extrapolate a dominant run (the championship case: model
   87% vs market 51% on the leader); the market regresses to the mean over a season.
5. **A known problem we can't see** — engine derate, damage, a binned setup. Rare in a thin
   casual-bettor market, but real when it happens.

**Symmetric / structural:**
6. **Wet conditions** — we widen only the POINTS market in the wet (brief 21); we have no win-prob
   wet-pace term and no per-driver wet skill. The market bumps known wet-masters; we don't.
7. **Track specialism / car-track fit** — we tested affinity and REJECTED it (overfit); the market
   prices it. Divergence at "character" tracks (Monaco specialists, power-track cars).
8. **Distribution sharpness (temperature)** — our Plackett-Luce temperature sets how peaked the
   favourite is. If it's mis-set we diverge on the favourite's absolute number even when we agree on
   the ORDER. This is the deepest one — see the methods note.

The unifying line: **we agree with the market on a normal dry race at a normal track (pace + grid is
the whole story) and diverge precisely where chaos, recovery, conditions, or specialism dominate.**

## Methods note: what distribution are we even using?

The ranking-from-strengths literature gives three classical models, and it's worth being exact
because it governs the tails:

- **Harville (1973)** — finishing-order probability by sequential conditional normalisation of the
  win probabilities. This **is Plackett-Luce**, and it's the model implied when each competitor's
  latent performance = strength + i.i.d. **Gumbel** noise (the Gumbel-max ⟺ softmax identity).
  Closed-form and cheap, but **over-states the favourite** in the lower placings (favourite-longshot
  bias).
- **Henery (1981)** — performance = strength + **Normal** noise (Thurstone–Mosteller order
  statistics). No closed form; better-behaved place/show, more expensive.
- **Lo & Bacon-Shone** — a cheap correction to Harville: raise the strengths to a power **λ_r ≤ 1**
  when computing the r-th finishing position, discounting strong competitors in lower placings.
  Fixes the favourite-longshot bias while keeping Harville's closed form.

**What we use:** the Kalman gives Gaussian *beliefs* about strengths, but the finishing-order
sampling is `score = strength / T + Gumbel`, argmax over the field — i.e. **Harville / Plackett-Luce
with a temperature T** (the Gumbel scale). So we're Harville with a learned, time-varying strength
model underneath.

This corrects a tempting-but-backwards intuition: switching to a **Normal** (Henery) performance
distribution would make the tails *thinner*, not fatter — **Gumbel is the heavier-tailed,
right-skewed choice, and we already use it.** The levers for MORE upset potential (keeping longshots
alive) are therefore (a) a higher temperature T, (b) a heavier-than-Gumbel performance law
(Student-t / a chaos mixture), or (c) the **Lo–Bacon-Shone λ** discount — which is the most elegant
because it targets the favourite-longshot bias directly and stays closed-form.

## Three improvement levers (and one validated, kept)

1. **Temperature from the market** (calibration, not edge). T is a nuisance parameter we have no
   independent way to set well. Fitting T so our dispersion matches the market's anchors only the
   *scale* — not the ranking or the relative probabilities — so it keeps our signal (who's favoured)
   while borrowing the market's well-calibrated sharpness. Defensible precisely because it does NOT
   anchor the probability itself, only how peaked it is. Honest caveat: improves calibration where a
   market exists; for unpriced races, a globally-fit T. (Not yet wired.)
2. **Lo–Bacon-Shone λ** — test whether a per-position discount beats our flat temperature for the
   favourite-longshot structure. The principled version of "the favourite is too peaked." (Not yet
   tested.)
3. **Held-up asymmetry — BUILT + VALIDATED, KEPT (opt-in).** A backmarker yields to a much-faster
   car rather than wreck its tyres in a battle it can't win, so the per-lap held-up penalty shrinks
   with the pace mismatch (`yield_factor = 1 − σ(k·(surplus − τ))`). Forward-chained over 45 races
   (leak-free): **win log-loss 0.178 → 0.160, top-pick 35.6% → 37.8%**, and the targeted metric —
   "fast car from the back" (started P8+, top-6 on pace) podium log-loss — **0.321 → 0.299**. It
   costs a little on podium/points calibration (an accuracy↔calibration trade), but it directly
   improves the exact scenario the taxonomy flagged: a fast car recovering from the back. The most
   positive mechanistic result in the project so far on win/top-pick. `position_sim.run_position_
   simulation(held_up_asymmetry=True)`.

## Honest framing

These target the **tails** — the drastic divergences — not the average gap (which brief 29 showed is
structural). Two of the three levers are *calibration* tools, not edges: anchoring temperature or
applying a λ-discount makes our numbers better-behaved, it doesn't beat an efficient market. The
held-up asymmetry is a genuine *accuracy* gain for the ordering/props engine. The value of this
brief is the same as the project's: knowing precisely where and why the model and the market part
company — humility with a paper trail.
