"""Tests for vig removal / Kelly (pure math) and the backtest loader."""

from app.etl.backtest import load_backtest
from app.etl.polymarket import devig, kelly_fraction, overround


def test_devig_normalizes_to_one():
    prices = {"A": 0.62, "B": 0.28, "C": 0.18}  # sums to 1.08 (8% vig)
    clean = devig(prices)
    assert abs(sum(clean.values()) - 1.0) < 1e-9
    assert abs(overround(prices) - 0.08) < 1e-9
    # Ordering preserved, favourite still favourite.
    assert clean["A"] > clean["B"] > clean["C"]


def test_devig_handles_degenerate():
    assert devig({}) == {}
    assert devig({"A": 0.0, "B": 0.0}) == {}


def test_kelly_positive_only_with_edge():
    # Model above market price -> positive stake; below -> zero.
    assert kelly_fraction(0.70, 0.62) > 0
    assert kelly_fraction(0.50, 0.62) == 0.0
    # Fractional scaling keeps it well below full Kelly.
    assert kelly_fraction(0.90, 0.62) < 0.5


def test_backtest_loader_shape_when_present():
    bt = load_backtest()
    if bt is None:
        return  # not computed in this environment
    assert {"n_races", "metrics", "calibration_win", "per_race"} <= set(bt)
    assert bt["metrics"]["win"]["brier"] is not None
    assert 0.0 <= bt["top_pick_accuracy"] <= 1.0
