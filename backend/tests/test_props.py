"""Prop-market scoring infrastructure (task #14): per-sim orders -> joint props."""

import numpy as np

from app.models.validate_props import _props, _rank_model_ranks


def test_rank_model_ranks_shape_and_validity():
    drivers = ["A", "B", "C", "D"]
    strengths = {"A": 1.0, "B": 0.3, "C": -0.2, "D": -1.0}
    ranks, ds = _rank_model_ranks(drivers, strengths, [0.0] * 4,
                                  temperature=0.5, n_sims=500, seed=1)
    assert ranks.shape == (4, 500)
    # every sim is a permutation 1..4
    assert set(np.unique(ranks)) <= {1, 2, 3, 4}
    # the strongest driver wins more often than the weakest
    assert (ranks[0] == 1).mean() > (ranks[3] == 1).mean()


def test_props_pairwise_and_podium_without_fav():
    drivers = ["A", "B", "C", "D"]
    # deterministic ranks: A always 1, B always 2, ...
    ranks = np.array([[1] * 10, [2] * 10, [3] * 10, [4] * 10])
    actual = {"A": 1, "B": 2, "C": 3, "D": 4}
    pairs, pwf = _props(ranks, drivers, actual, fav="A")
    # A ahead of B with prob 1, outcome 1 -> perfect
    assert all(p == 1.0 and o == 1 for p, o in pairs)
    # favourite A always finishes 1st -> P(podium-less) = 0, outcome 0
    assert pwf == (0.0, 0)
