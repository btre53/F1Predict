"""Tests for the telemetry lap-time/tyre physics work (brief 20)."""

import numpy as np

from app.engine.qss import curvature, fit_envelope, qss_profile
from app.etl.tyre_degradation import _fit_forms, _bin_medians


def test_degradation_fit_recovers_a_known_quadratic():
    """A clean quadratic age->loss must be best-fit by quadratic (or cubic), not linear."""
    age = np.repeat(np.arange(1, 31, dtype=float), 25)
    y = 0.02 * age + 0.001 * age**2 + np.random.default_rng(0).normal(0, 0.02, age.size)
    ba, bm, bw = _bin_medians(age, y)
    forms = _fit_forms(ba, bm, bw)
    best = min(forms, key=lambda f: forms[f]["aic"])
    assert best in ("quadratic", "cubic")
    assert forms["quadratic"]["aic"] <= forms["linear"]["aic"]


def test_bin_medians_kills_outliers():
    """A handful of huge traffic-lap residuals must not move the per-age median."""
    age = np.repeat(np.arange(1, 11, dtype=float), 30)
    y = 0.05 * age
    y[::30] += 8.0  # one giant outlier per age bin
    ba, bm, bw = _bin_medians(age, y)
    # median curve should still be ~0.05*age, not dragged up by the +8s laps
    assert np.all(bm < 0.05 * ba + 0.2)


def test_curvature_of_a_circle_is_one_over_radius():
    r, step = 50.0, 1.0
    theta = np.linspace(0, 2 * np.pi, 400)
    x, y = r * np.cos(theta), r * np.sin(theta)
    k = curvature(x, y, step_m=(2 * np.pi * r) / 400)
    # interior points (avoid finite-diff edge effects) should be ~1/r
    assert abs(np.median(k[5:-5]) - 1.0 / r) < 0.01


def test_qss_profile_slows_for_corners_and_respects_vmax():
    grid = np.arange(0, 500, 5.0)
    kappa = np.full_like(grid, 1e-6)   # straight...
    kappa[40:60] = 0.02                # ...with a tight corner in the middle
    env = {"a_lat_max": 25.0, "a_acc_max": 12.0, "a_brake_max": -40.0, "v_max": 90.0}
    v = qss_profile(grid, kappa, env)
    assert v.max() <= env["v_max"] + 1e-6
    assert v[50] < v[0]                # slows in the corner
    assert np.sqrt(env["a_lat_max"] / 0.02) - 1.0 <= v[50] <= np.sqrt(env["a_lat_max"] / 0.02) + 1.0
