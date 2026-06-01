"""Smoke tests for the deterministic engine and strategy layer."""

import numpy as np

from app.engine.noise import sample_execution_noise
from app.engine.params import CircuitParams, Compound, NoiseParams, TrackStatus
from app.engine.physics import baseline_lap_time_s, fuel_mass
from app.engine.strategy import (
    Stint,
    Strategy,
    cover_or_extend,
    evaluate_strategy,
    evaluate_undercut,
    optimize_strategy,
    safety_car_decision,
)
from app.engine.tyres import degradation_penalty, seed_for


def test_fuel_mass_decreases():
    assert fuel_mass(1, CircuitParams().fuel) > fuel_mass(30, CircuitParams().fuel)


def test_degradation_monotone_after_warmup():
    p = seed_for(Compound.MEDIUM)
    d = degradation_penalty(np.arange(5, 30), p)
    assert np.all(np.diff(d) > 0)  # wearing out after warm-up


def test_baseline_lap_time_reasonable():
    t = baseline_lap_time_s(
        1, tyre_age=0, compound=Compound.MEDIUM, circuit=CircuitParams()
    )
    assert 80.0 < t < 95.0  # base 85s + fuel + tyre offset


def test_pit_loss_scaling():
    c = CircuitParams()
    green = c.pit_loss.total_loss(TrackStatus.GREEN)
    sc = c.pit_loss.total_loss(TrackStatus.SAFETY_CAR)
    assert sc < green  # safety car makes pitting cheaper
    assert green > 18.0  # realistic green pit loss


def test_safety_car_decision_pits_when_tyres_due():
    """SC + worn tyres (a stop due soon) -> take the cheap stop now."""
    c = CircuitParams(total_laps=57)
    d = safety_car_decision(
        current_lap=26, total_laps=57, current_compound=Compound.SOFT,
        current_tyre_age=24, fresh_compound=Compound.HARD, circuit=c,
    )
    assert d.recommendation == "PIT"
    assert d.sc_pit_saving_s > 0  # boxing under SC is cheaper than a green stop
    assert d.delta_s > 0


def test_safety_car_decision_stays_on_fresh_tyres():
    """SC + fresh tyres -> don't throw away a good set for a stop you don't need."""
    c = CircuitParams(total_laps=57)
    d = safety_car_decision(
        current_lap=10, total_laps=57, current_compound=Compound.HARD,
        current_tyre_age=6, fresh_compound=Compound.HARD, circuit=c,
    )
    assert d.recommendation == "STAY"


def test_evaluate_strategy_valid_one_stop():
    c = CircuitParams(total_laps=57)
    strat = Strategy([Stint(Compound.MEDIUM, 25), Stint(Compound.HARD, 32)])
    r = evaluate_strategy(strat, c)
    assert r.valid
    assert r.n_stops == 1
    assert r.pit_laps == [25]
    assert len(r.lap_times_s) == 57


def test_optimizer_returns_sorted_valid():
    c = CircuitParams(total_laps=57)
    results = optimize_strategy(c, max_stops=2, top_k=5)
    assert len(results) >= 1
    times = [r.total_time_s for r in results]
    assert times == sorted(times)
    assert all(r.valid for r in results)


def test_undercut_small_gap_works():
    c = CircuitParams()
    r = evaluate_undercut(
        gap_s=1.0,
        attacker_compound=Compound.SOFT,
        attacker_tyre_age=0,
        defender_compound=Compound.HARD,
        defender_tyre_age=20,
        pit_lap=20,
        circuit=c,
    )
    assert r.fresh_tyre_gain_s > 0


def test_cover_or_extend_small_gap_covers():
    c = CircuitParams()
    d = cover_or_extend(
        gap_to_follower_s=0.8,
        laps_remaining=20,
        leader_tyre_age=22,
        leader_compound=Compound.MEDIUM,
        circuit=c,
    )
    assert d.recommendation in {"COVER", "EXTEND"}


def test_noise_is_positively_skewed():
    rng = np.random.default_rng(42)
    noise = sample_execution_noise((20, 5000), NoiseParams(), rng=rng)
    from scipy.stats import skew

    assert skew(noise.ravel()) > 0.2  # long slow tail
