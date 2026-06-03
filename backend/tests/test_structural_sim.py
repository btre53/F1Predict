"""Tests for the anchored+ensembled structural sim (brief 22).

The headline property is the ENSEMBLE GUARANTEE: the blend at w=0 is exactly the anchor, so
the structural sim can never make the rank model worse. These tests lock that in (the
forward-chained skill comparison lives in app/models/validate_structural_sim.py)."""

import numpy as np

from app.models.structural_sim import (
    blend_distributions,
    dist_to_markets,
    simulate_field,
    strengths_to_pace_offsets,
)


def test_faster_strength_gets_negative_pace_offset():
    """Higher Kalman strength (faster) -> lower (negative) per-lap pace offset."""
    off = strengths_to_pace_offsets({"FAST": 1.0, "MID": 0.0, "SLOW": -1.0})
    assert off["FAST"] < off["MID"] < off["SLOW"]


def test_blend_w0_is_anchor_w1_is_sim():
    a = {"A": np.array([0.6, 0.3, 0.1]), "B": np.array([0.4, 0.4, 0.2])}
    b = {"A": np.array([0.1, 0.2, 0.7]), "B": np.array([0.2, 0.3, 0.5])}
    at0 = blend_distributions(a, b, 0.0)
    at1 = blend_distributions(a, b, 1.0)
    for d in a:
        assert np.allclose(at0[d], a[d])      # w=0 -> pure anchor (the can't-be-worse floor)
        assert np.allclose(at1[d], b[d])      # w=1 -> pure sim


def test_blend_stays_a_normalized_distribution():
    a = {"A": np.array([0.6, 0.3, 0.1])}
    b = {"A": np.array([0.1, 0.2, 0.7])}
    mid = blend_distributions(a, b, 0.5)
    assert abs(float(mid["A"].sum()) - 1.0) < 1e-9
    assert np.all(mid["A"] >= 0)


def test_simulate_field_returns_valid_distributions():
    drivers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    strengths = {d: s for d, s in zip(drivers, [1.2, 0.6, 0.1, -0.2, -0.6, -1.1])}
    team_of = {d: t for d, t in zip(drivers, ["T1", "T1", "T2", "T2", "T3", "T3"])}
    dist = simulate_field(
        "Bahrain", strengths, grid_order=drivers, team_of=team_of,
        dnf_of={d: 0.05 for d in drivers}, n_sims=1500,
    )
    assert set(dist) == set(drivers)
    for v in dist.values():
        assert abs(float(v.sum()) - 1.0) < 0.02   # ~normalized (DNF leaks a little mass)
    # The fastest car should win more often than the slowest.
    mk = dist_to_markets(dist)
    assert mk["AAA"]["win"] > mk["FFF"]["win"]
