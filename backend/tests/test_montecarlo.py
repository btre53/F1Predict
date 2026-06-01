"""Tests for the vectorized Monte Carlo race engine."""

import numpy as np

from app.engine.montecarlo import GridEntry, run_race_simulation
from app.engine.params import CircuitParams, Compound
from app.engine.strategy import Stint, Strategy


def _grid(circuit):
    half = circuit.total_laps // 2
    strat = Strategy([Stint(Compound.MEDIUM, half), Stint(Compound.HARD, circuit.total_laps - half)])
    # Three drivers with realistic, overlapping pace gaps (~0.12 s/lap apart).
    return [
        GridEntry("FAST", strat, pace_offset_s=-0.12, grid_pos=1, dnf_prob=0.0),
        GridEntry("MID", strat, pace_offset_s=0.0, grid_pos=2, dnf_prob=0.0),
        GridEntry("SLOW", strat, pace_offset_s=0.12, grid_pos=3, dnf_prob=0.0),
    ]


def test_probabilities_normalize():
    c = CircuitParams(total_laps=50)
    res = run_race_simulation(c, _grid(c), n_sims=3000)
    assert abs(sum(o.win_pct for o in res.outcomes) - 1.0) < 1e-9
    for o in res.outcomes:
        assert abs(sum(o.finish_distribution) - 1.0) < 1e-6


def test_faster_car_wins_more():
    c = CircuitParams(total_laps=50)
    res = run_race_simulation(c, _grid(c), n_sims=4000)
    by = {o.driver: o for o in res.outcomes}
    assert by["FAST"].win_pct > by["MID"].win_pct > by["SLOW"].win_pct
    assert by["FAST"].win_pct > 0.5


def test_safety_car_probability_reasonable():
    c = CircuitParams(total_laps=57)
    res = run_race_simulation(c, _grid(c), n_sims=5000)
    # TUM count model -> ~55% of races see >=1 SC.
    assert 0.45 < res.sc_probability < 0.65


def test_dnf_knocks_out_sims():
    c = CircuitParams(total_laps=40)
    half = 20
    strat = Strategy([Stint(Compound.MEDIUM, half), Stint(Compound.HARD, 20)])
    grid = [
        GridEntry("A", strat, pace_offset_s=0.0, grid_pos=1, dnf_prob=0.2),
        GridEntry("B", strat, pace_offset_s=0.0, grid_pos=2, dnf_prob=0.0),
    ]
    res = run_race_simulation(c, grid, n_sims=4000)
    by = {o.driver: o for o in res.outcomes}
    assert 0.15 < by["A"].dnf_pct < 0.25
