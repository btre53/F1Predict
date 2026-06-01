"""Strategy evaluation: the core of the Strategy Lab.

See docs/science/02-race-strategy.md.

A *strategy* is an ordered list of stints (compound + planned length). We evaluate
total race time deterministically as the sum of per-lap physics times plus a
decomposed, status-scaled pit loss per stop. The optimizer searches stop counts
and pit laps; undercut/overcut and Stackelberg cover-vs-extend reason about two
cars fighting on strategy.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .params import CircuitParams, Compound, TrackStatus, TyreParams
from .tyres import compound_lap_penalty, degradation_penalty, seed_for


@dataclass
class Stint:
    compound: Compound
    length: int  # laps on this stint
    start_tyre_age: int = 0  # >0 for a used/scrubbed set


@dataclass
class Strategy:
    stints: list[Stint]

    @property
    def n_stops(self) -> int:
        return max(0, len(self.stints) - 1)

    @property
    def total_laps(self) -> int:
        return sum(s.length for s in self.stints)

    @property
    def pit_laps(self) -> list[int]:
        laps, cum = [], 0
        for s in self.stints[:-1]:
            cum += s.length
            laps.append(cum)
        return laps

    @property
    def compounds_used(self) -> set[Compound]:
        return {s.compound for s in self.stints}


@dataclass
class StrategyResult:
    strategy: Strategy
    total_time_s: float
    lap_times_s: list[float]
    pit_laps: list[int]
    n_stops: int
    valid: bool
    notes: list[str]
    delta_to_best_s: float = 0.0  # gap to the optimal strategy (0 = fastest)
    avg_lap_s: float = 0.0


@dataclass
class RaceModel:
    """Precomputed race constants for fast strategy scoring.

    The base-lap + fuel contribution is identical for every strategy over the same
    N laps, so it is computed once. Only the per-stint tyre wear and the pit losses
    differ between strategies — which is exactly the *delta* that matters.
    """

    circuit: CircuitParams
    base_fuel_total_s: float
    deg_cum: dict[Compound, np.ndarray]   # cumulative *degradation* by age (no offset)
    offset_s: dict[Compound, float]       # per-compound pace offset
    fuel_frac_prefix: np.ndarray          # prefix sum of fuel fraction by lap
    pace_offset_s: float


def build_race_model(
    circuit: CircuitParams,
    *,
    pace_offset_s: float = 0.0,
    tyre_overrides: dict[Compound, TyreParams] | None = None,
) -> RaceModel:
    from .params import WEAR_FUEL_SENSITIVITY  # noqa: F401  (used in scorer)
    from .physics import fuel_mass, fuel_penalty

    n = circuit.total_laps
    laps = np.arange(1, n + 1, dtype=np.float64)
    base_s = circuit.base_lap_ms / 1000.0
    base_fuel_total = float(np.sum(base_s + fuel_penalty(laps, circuit.fuel)))
    base_fuel_total += pace_offset_s * n

    # Fuel fraction per lap (1.0 full -> ~0 empty); prefix sum for O(1) stint means.
    fuel_frac = np.asarray(
        fuel_mass(laps, circuit.fuel) / max(1e-6, circuit.fuel.start_fuel_kg)
    )
    fuel_frac_prefix = np.concatenate([[0.0], np.cumsum(fuel_frac)])

    max_age = n + 50
    ages = np.arange(0, max_age + 1, dtype=np.float64)
    deg_cum: dict[Compound, np.ndarray] = {}
    offset_s: dict[Compound, float] = {}
    for c in Compound:
        tp = _tyre_params_for(c, tyre_overrides)
        deg = np.asarray(degradation_penalty(ages, tp), dtype=np.float64)
        deg_cum[c] = np.concatenate([[0.0], np.cumsum(deg)])
        offset_s[c] = tp.pace_offset_s
    return RaceModel(
        circuit, base_fuel_total, deg_cum, offset_s, fuel_frac_prefix, pace_offset_s
    )


def score_strategy_fast(
    strategy: Strategy, model: RaceModel, *, sc_laps: set[int] | None = None
) -> float:
    """Total race time (s) in O(n_stints), with fuel-amplified tyre wear.

    Tyre wear is scaled by the stint's average fuel load, so a soft tyre run early
    (heavy car) costs more than the same tyre run late — the optimizer therefore
    prefers harder compounds on heavy fuel.
    """
    from .params import WEAR_FUEL_SENSITIVITY

    sc_laps = sc_laps or set()
    total = model.base_fuel_total_s
    prefix = model.fuel_frac_prefix
    lap = 0
    for stint in strategy.stints:
        a = stint.start_tyre_age
        deg = float(model.deg_cum[stint.compound][a + stint.length] - model.deg_cum[stint.compound][a])
        # average fuel fraction over this stint's lap window
        avg_frac = (prefix[lap + stint.length] - prefix[lap]) / stint.length
        mult = 1.0 + WEAR_FUEL_SENSITIVITY * avg_frac
        total += deg * mult + model.offset_s[stint.compound] * stint.length
        lap += stint.length
    for pit_lap in strategy.pit_laps:
        status = TrackStatus.SAFETY_CAR if pit_lap in sc_laps else TrackStatus.GREEN
        total += model.circuit.pit_loss.total_loss(status)
    return total


def _tyre_params_for(compound: Compound, overrides) -> TyreParams:
    if overrides and compound in overrides:
        return overrides[compound]
    return seed_for(compound)


def evaluate_strategy(
    strategy: Strategy,
    circuit: CircuitParams,
    *,
    pace_offset_s: float = 0.0,
    tyre_overrides: dict[Compound, TyreParams] | None = None,
    sc_laps: set[int] | None = None,
    require_two_compounds: bool = True,
) -> StrategyResult:
    """Deterministic total race time for a strategy (no stochastic events).

    ``sc_laps`` optionally marks laps run under safety car (pit loss discounted on
    those laps). The two-compound rule is enforced as a validity flag.
    """
    from .params import WEAR_FUEL_SENSITIVITY
    from .physics import fuel_mass, fuel_penalty

    sc_laps = sc_laps or set()
    notes: list[str] = []
    lap_times: list[float] = []
    lap = 0
    base_s = circuit.base_lap_ms / 1000.0
    start_fuel = max(1e-6, circuit.fuel.start_fuel_kg)

    for stint in strategy.stints:
        tp = _tyre_params_for(stint.compound, tyre_overrides)
        for k in range(stint.length):
            lap += 1
            age = stint.start_tyre_age + k
            fuel_frac = float(fuel_mass(lap, circuit.fuel)) / start_fuel
            mult = 1.0 + WEAR_FUEL_SENSITIVITY * fuel_frac
            tyre_s = float(degradation_penalty(age, tp)) * mult + tp.pace_offset_s
            lap_times.append(
                base_s
                + float(fuel_penalty(lap, circuit.fuel))
                + tyre_s
                + pace_offset_s
            )

    total = float(np.sum(lap_times))

    # Add pit loss per stop, status-scaled.
    for pit_lap in strategy.pit_laps:
        status = TrackStatus.SAFETY_CAR if pit_lap in sc_laps else TrackStatus.GREEN
        total += circuit.pit_loss.total_loss(status)

    valid = True
    if strategy.total_laps != circuit.total_laps:
        valid = False
        notes.append(
            f"stint lengths sum to {strategy.total_laps}, "
            f"expected {circuit.total_laps} laps"
        )
    if require_two_compounds and len(strategy.compounds_used) < 2:
        # Only enforced in dry races; wet races are exempt in the real rules.
        dry = {Compound.SOFT, Compound.MEDIUM, Compound.HARD}
        if strategy.compounds_used <= dry:
            valid = False
            notes.append("two-compound rule not satisfied")

    return StrategyResult(
        strategy=strategy,
        total_time_s=total,
        lap_times_s=lap_times,
        pit_laps=strategy.pit_laps,
        n_stops=strategy.n_stops,
        valid=valid,
        notes=notes,
        avg_lap_s=total / max(1, len(lap_times)),
    )


def enumerate_strategies(
    circuit: CircuitParams,
    *,
    compounds: list[Compound] | None = None,
    max_stops: int = 2,
    block: int = 3,
) -> list[Strategy]:
    """Generate candidate strategies on a coarse pit-lap grid (docs/science/02 §4).

    Uses ``block``-lap quantization for the global search; the optimizer refines
    the best candidates lap-by-lap afterwards.
    """
    compounds = compounds or [Compound.SOFT, Compound.MEDIUM, Compound.HARD]
    total = circuit.total_laps
    candidates: list[Strategy] = []

    # 1-stop
    if max_stops >= 1:
        for first in range(block, total, block):
            for c1 in compounds:
                for c2 in compounds:
                    if c1 == c2:
                        continue
                    candidates.append(
                        Strategy([Stint(c1, first), Stint(c2, total - first)])
                    )
    # 2-stop
    if max_stops >= 2:
        for p1 in range(block, total - block, block):
            for p2 in range(p1 + block, total, block):
                for c1 in compounds:
                    for c2 in compounds:
                        for c3 in compounds:
                            if len({c1, c2, c3}) < 2:
                                continue
                            candidates.append(
                                Strategy(
                                    [
                                        Stint(c1, p1),
                                        Stint(c2, p2 - p1),
                                        Stint(c3, total - p2),
                                    ]
                                )
                            )
    return candidates


def optimize_strategy(
    circuit: CircuitParams,
    *,
    compounds: list[Compound] | None = None,
    max_stops: int = 2,
    pace_offset_s: float = 0.0,
    tyre_overrides: dict[Compound, TyreParams] | None = None,
    top_k: int = 5,
    refine_window: int = 2,
) -> list[StrategyResult]:
    """Coarse-grid search + local ±refine_window refinement of pit laps.

    Uses the vectorized ``RaceModel`` scorer, so the whole search is sub-50ms even
    for long races. Returns the ``top_k`` strategies, best first, each annotated
    with its delta to the optimal strategy (the headline metric).
    """
    model = build_race_model(
        circuit, pace_offset_s=pace_offset_s, tyre_overrides=tyre_overrides
    )
    coarse = enumerate_strategies(circuit, compounds=compounds, max_stops=max_stops)

    # Score coarse grid fast, keep the best pool, then refine pit laps locally.
    scored = sorted(
        ((score_strategy_fast(s, model), s) for s in coarse), key=lambda t: t[0]
    )
    best_by_key: dict[tuple, tuple[float, Strategy]] = {}
    for time_s, strat in scored:
        best_by_key[_strategy_key(strat)] = (time_s, strat)

    for _, base in scored[: max(top_k * 3, 15)]:
        for cand in _refine_pit_laps(base, circuit, refine_window):
            t = score_strategy_fast(cand, model)
            key = _strategy_key(cand)
            if key not in best_by_key or t < best_by_key[key][0]:
                best_by_key[key] = (t, cand)

    ranked = sorted(best_by_key.values(), key=lambda t: t[0])[:top_k]
    if not ranked:
        return []
    best_time = ranked[0][0]
    n = circuit.total_laps
    return [
        StrategyResult(
            strategy=strat,
            total_time_s=time_s,
            lap_times_s=[],  # omitted in bulk optimize for speed; see /evaluate
            pit_laps=strat.pit_laps,
            n_stops=strat.n_stops,
            valid=True,
            notes=[],
            delta_to_best_s=time_s - best_time,
            avg_lap_s=time_s / n,
        )
        for time_s, strat in ranked
    ]


def _strategy_key(s: Strategy) -> tuple:
    return tuple((st.compound.value, st.length) for st in s.stints)


def _refine_pit_laps(
    strategy: Strategy, circuit: CircuitParams, window: int
) -> list[Strategy]:
    """Yield strategies with each pit lap shifted within +/- window."""
    if strategy.n_stops == 0:
        return [strategy]
    pit_laps = strategy.pit_laps
    compounds = [s.compound for s in strategy.stints]
    out: list[Strategy] = []
    offsets = range(-window, window + 1)

    if len(pit_laps) == 1:
        for d in offsets:
            p = pit_laps[0] + d
            if 1 <= p < circuit.total_laps:
                out.append(
                    Strategy(
                        [Stint(compounds[0], p),
                         Stint(compounds[1], circuit.total_laps - p)]
                    )
                )
    elif len(pit_laps) == 2:
        for d1 in offsets:
            for d2 in offsets:
                p1, p2 = pit_laps[0] + d1, pit_laps[1] + d2
                if 1 <= p1 < p2 < circuit.total_laps:
                    out.append(
                        Strategy(
                            [
                                Stint(compounds[0], p1),
                                Stint(compounds[1], p2 - p1),
                                Stint(compounds[2], circuit.total_laps - p2),
                            ]
                        )
                    )
    return out


# --------------------------------------------------------------------------- #
# Undercut / overcut  (docs/science/02 section 2)
# --------------------------------------------------------------------------- #
@dataclass
class UndercutResult:
    gap_s: float
    pit_lap: int
    projected_gap_after_s: float  # +ve = attacker ahead after the cycle
    undercut_works: bool
    fresh_tyre_gain_s: float
    notes: list[str]


def evaluate_undercut(
    *,
    gap_s: float,
    attacker_compound: Compound,
    attacker_tyre_age: int,
    defender_compound: Compound,
    defender_tyre_age: int,
    pit_lap: int,
    circuit: CircuitParams,
    window_laps: int = 3,
    tyre_overrides: dict[Compound, TyreParams] | None = None,
) -> UndercutResult:
    """Does pitting now (undercut) clear a rival ``gap_s`` ahead?

    The attacker pits, runs ``window_laps`` on fresh tyres while the defender stays
    out on worn tyres; we accumulate the per-lap pace delta and net out the pit
    loss differential (both pay it eventually, so it cancels for track position —
    what matters is the fresh-tyre advantage vs the initial gap).
    """
    notes: list[str] = []
    atk_tp = _tyre_params_for(attacker_compound, tyre_overrides)
    def_tp = _tyre_params_for(defender_compound, tyre_overrides)

    gain = 0.0
    for k in range(window_laps):
        atk_age = k  # fresh set
        def_age = defender_tyre_age + k
        atk_pace = float(compound_lap_penalty(atk_age, atk_tp))
        def_pace = float(compound_lap_penalty(def_age, def_tp))
        gain += def_pace - atk_pace  # +ve when attacker's fresh tyres are faster

    # Attacker loses the pit-lane time once; to leapfrog on track they must make up
    # the initial gap with the fresh-tyre advantage before the defender reacts.
    projected = gain - gap_s
    works = projected > 0.0
    if works:
        notes.append("fresh-tyre advantage clears the gap — undercut likely")
    else:
        notes.append("gap too large for the fresh-tyre window — consider overcut")

    return UndercutResult(
        gap_s=gap_s,
        pit_lap=pit_lap,
        projected_gap_after_s=projected,
        undercut_works=works,
        fresh_tyre_gain_s=gain,
        notes=notes,
    )


# --------------------------------------------------------------------------- #
# Stackelberg cover-vs-extend  (docs/science/02 section 3)
# --------------------------------------------------------------------------- #
@dataclass
class CoverDecision:
    recommendation: str  # "COVER" or "EXTEND"
    cover_value_s: float
    extend_value_s: float
    rationale: str


def cover_or_extend(
    *,
    gap_to_follower_s: float,
    laps_remaining: int,
    leader_tyre_age: int,
    leader_compound: Compound,
    circuit: CircuitParams,
    tyre_overrides: dict[Compound, TyreParams] | None = None,
) -> CoverDecision:
    """Leader's decision: cover the follower's undercut now, or extend the stint.

    A first-order backward-reasoning approximation of the Stackelberg game: compare
    the time cost of reacting immediately (cover) against the benefit of building a
    tyre-age offset by extending. The leader moves first having observed the
    follower's threat.
    """
    tp = _tyre_params_for(leader_compound, tyre_overrides)

    # Cover: pit now, concede track position risk but neutralize the undercut.
    # Cost ~ pit loss minus the undercut risk it removes.
    undercut_risk = max(0.0, 1.5 - gap_to_follower_s)  # bigger when gap is small
    cover_value = -circuit.pit_loss.total_loss() + undercut_risk * 2.0

    # Extend: keep running on aging tyres to build an offset for a later, fresher
    # final stint. Benefit grows with laps remaining, cost is current deg.
    current_deg = float(degradation_penalty(leader_tyre_age, tp))
    extend_value = (laps_remaining * 0.05) - current_deg * 2.0

    if gap_to_follower_s < 1.5 and cover_value >= extend_value:
        rec = "COVER"
        rationale = (
            f"follower within {gap_to_follower_s:.1f}s undercut range; "
            "react to protect track position"
        )
    else:
        rec = "EXTEND"
        rationale = (
            "gap large enough or tyre offset valuable enough to extend and "
            "execute a later overcut / fresher final stint"
        )
    return CoverDecision(rec, cover_value, extend_value, rationale)


# --------------------------------------------------------------------------- #
# Safety-car decision: pit now (cheap stop) vs stay out  (docs/science/02 §5)
# --------------------------------------------------------------------------- #
@dataclass
class SafetyCarDecision:
    recommendation: str       # "PIT" or "STAY"
    pit_now_cost_s: float     # relative time over the remaining laps if you pit now
    stay_out_cost_s: float    # ... if you stay out (best of pit-later / run-to-end)
    delta_s: float            # stay_out - pit_now  (+ve = pitting now is faster)
    sc_pit_saving_s: float    # green pit loss - SC pit loss (the discount for boxing now)
    stay_plan: str            # what the stay-out branch does
    rationale: str


def safety_car_decision(
    *,
    current_lap: int,
    total_laps: int,
    current_compound: Compound,
    current_tyre_age: int,
    fresh_compound: Compound,
    circuit: CircuitParams,
    tyre_overrides: dict[Compound, TyreParams] | None = None,
) -> SafetyCarDecision:
    """A safety car is out NOW — pit for a cheap stop, or stay out and keep position?

    Compares the relative time over the *remaining* laps of two branches (the shared
    base+fuel pace cancels, so only tyre wear and the status-scaled pit loss differ —
    the same primitives as the undercut/cover models):

      PIT NOW : pay the discounted SC pit loss, then run the rest on a fresh set.
      STAY OUT: keep track position, then either pit later under green (best lap) or
                run the current set to the flag — whichever is faster.

    The lever is the SC pit-loss discount (you lose far less time boxing while the field
    is bunched) traded against giving up track position now.
    """
    laps_remaining = max(0, total_laps - current_lap)
    cur_tp = _tyre_params_for(current_compound, tyre_overrides)
    fresh_tp = _tyre_params_for(fresh_compound, tyre_overrides)
    sc_loss = circuit.pit_loss.total_loss(TrackStatus.SAFETY_CAR)
    green_loss = circuit.pit_loss.total_loss(TrackStatus.GREEN)

    def fresh_sum(n: int) -> float:
        return float(sum(compound_lap_penalty(k, fresh_tp) for k in range(max(0, n))))

    def cur_sum(start_age: int, n: int) -> float:
        return float(sum(compound_lap_penalty(start_age + k, cur_tp) for k in range(max(0, n))))

    # PIT NOW: SC stop + fresh tyres to the flag.
    pit_now = sc_loss + fresh_sum(laps_remaining)

    # STAY OUT: best of running to the end on the current set, or pitting later (green).
    stay_to_end = cur_sum(current_tyre_age, laps_remaining)
    best_stay = stay_to_end
    stay_plan = "stay out and run the current set to the flag"
    for p in range(1, laps_remaining):
        c = cur_sum(current_tyre_age, p) + green_loss + fresh_sum(laps_remaining - p)
        if c < best_stay:
            best_stay = c
            stay_plan = f"stay out, then pit under green on lap {current_lap + p}"

    delta = best_stay - pit_now  # +ve => pitting now is faster
    rec = "PIT" if delta > 0 else "STAY"
    saving = green_loss - sc_loss
    if rec == "PIT":
        rationale = (
            f"boxing under the SC costs {saving:.1f}s less than a green stop and the "
            f"fresh {fresh_compound.value.lower()} pace wins back {delta:.1f}s over the "
            f"remaining {laps_remaining} laps — take the cheap stop."
        )
    else:
        rationale = (
            f"the SC stop saves {saving:.1f}s, but giving up track position isn't worth "
            f"it: {stay_plan} is {-delta:.1f}s faster over the remaining {laps_remaining} laps."
        )
    return SafetyCarDecision(
        recommendation=rec,
        pit_now_cost_s=pit_now,
        stay_out_cost_s=best_stay,
        delta_s=delta,
        sc_pit_saving_s=saving,
        stay_plan=stay_plan,
        rationale=rationale,
    )
