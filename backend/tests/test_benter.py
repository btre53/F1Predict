"""Tests for the Benter market-blend primitive (brief 23)."""

import numpy as np

from app.models.probability import benter_blend


def test_pure_model_and_pure_market():
    pm = np.array([0.6, 0.3, 0.1])
    pk = np.array([0.2, 0.3, 0.5])
    assert np.allclose(benter_blend(pm, pk, alpha=1.0, beta=0.0), pm, atol=1e-9)
    assert np.allclose(benter_blend(pm, pk, alpha=0.0, beta=1.0), pk, atol=1e-9)


def test_blend_is_a_normalized_distribution():
    pm = np.array([0.6, 0.3, 0.1])
    pk = np.array([0.2, 0.3, 0.5])
    c = benter_blend(pm, pk, alpha=0.75, beta=0.75)
    assert abs(float(c.sum()) - 1.0) < 1e-9
    assert np.all(c >= 0)


def test_equal_blend_sits_between_the_two_logspace():
    """An equal-weight blend is the renormalized geometric mean — between the inputs."""
    pm = np.array([0.7, 0.2, 0.1])
    pk = np.array([0.2, 0.3, 0.5])
    c = benter_blend(pm, pk, alpha=1.0, beta=1.0)
    # for the driver where model is high and market low, the blend lands in between
    assert pk[0] < c[0] < pm[0]
