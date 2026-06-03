"""Qualifying-prediction model (predict the grid from one-lap pace)."""

import numpy as np

from app.models.predict_quali import grid_distribution, sample_grid


def test_grid_distribution_normalized_and_ordered():
    drivers = ["A", "B", "C", "D", "E"]
    strn = {"A": 1.2, "B": 0.5, "C": 0.0, "D": -0.5, "E": -1.1}
    dist, pole = grid_distribution(drivers, strn, n_sims=4000, seed=1)
    for d in drivers:
        assert abs(float(dist[d].sum()) - 1.0) < 1e-9
    assert pole["A"] > pole["E"]            # fastest car most likely on pole
    assert abs(sum(pole.values()) - 1.0) < 0.02


def test_sample_grid_is_a_permutation():
    drivers = ["A", "B", "C", "D", "E"]
    strn = {d: s for d, s in zip(drivers, [1.0, 0.3, 0.0, -0.4, -1.0])}
    g = sample_grid(drivers, strn, rng=np.random.default_rng(0))
    assert sorted(g) == sorted(drivers)     # every car placed exactly once
