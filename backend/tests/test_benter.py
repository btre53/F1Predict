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


def test_market_backtest_artifact_has_blend():
    """The vs-market panel surfaces the blend (brief 23): the committed backtest must carry it,
    and the honest finding must hold — blend beats our model but not the market."""
    from app.etl.market_backtest import load_market_backtest

    d = load_market_backtest()
    assert d is not None and "blend_win" in d
    assert d["blend_alpha"] == 0.75 and d["blend_beta"] == 0.75
    # In the artifact: blend improves on the raw model, market still best (no edge).
    assert d["blend_win"]["brier"] <= d["model_win"]["brier"] + 1e-9
    assert d["market_win"]["brier"] <= d["blend_win"]["brier"] + 1e-9
