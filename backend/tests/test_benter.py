"""Tests for the Benter market-blend primitive (brief 23) + the brief-30 calibration primitives."""

import numpy as np

from app.models.probability import (
    benter_blend, fit_market_gamma, strengths_to_probs_lbs, temper,
)


def test_temper_sharpens_and_flattens():
    p = np.array([0.5, 0.3, 0.2])
    assert abs(temper(p, 1.0).sum() - 1.0) < 1e-9
    assert np.allclose(temper(p, 1.0), p)             # gamma=1 is identity
    assert temper(p, 2.0)[0] > p[0]                   # sharpen -> favourite grows
    assert temper(p, 0.5)[0] < p[0]                   # flatten -> favourite shrinks


def test_fit_market_gamma_recovers_a_known_sharpening():
    # If the "market" is exactly our probs sharpened by gamma*, the fit should recover ~gamma*.
    base = [np.array([0.4, 0.35, 0.25]), np.array([0.5, 0.3, 0.2])]
    market = [temper(p, 1.6) for p in base]
    g = fit_market_gamma(base, market)
    assert 1.4 <= g <= 1.8


def test_lbs_is_plackett_luce_at_lambda_one():
    drivers = ["A", "B", "C", "D", "E", "F"]
    s = np.array([2.0, 1.0, 0.5, 0.0, -0.5, -1.0])
    pl = strengths_to_probs_lbs(drivers, s, temperature=0.6, lam=1.0, n_sims=40000, seed=1)
    # win probs are a valid distribution; the strong car leads win + podium
    assert abs(sum(pl[d]["win"] for d in drivers) - 1.0) < 0.02
    assert pl["A"]["win"] > pl["F"]["win"] and pl["A"]["podium"] > pl["A"]["win"]


def test_lbs_lambda_below_one_flattens_podium():
    """A per-placing discount (lam<1) pulls podium share toward the longshots (the LBS correction)."""
    drivers = ["A", "B", "C", "D", "E", "F"]
    s = np.array([2.0, 1.0, 0.5, 0.0, -0.5, -1.0])
    full = strengths_to_probs_lbs(drivers, s, temperature=0.6, lam=1.0, n_sims=40000, seed=2)
    disc = strengths_to_probs_lbs(drivers, s, temperature=0.6, lam=0.5, n_sims=40000, seed=2)
    assert full["A"]["win"] == __import__("pytest").approx(disc["A"]["win"], abs=0.02)  # win unchanged
    assert disc["A"]["podium"] < full["A"]["podium"]   # strong car's podium share discounted


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
