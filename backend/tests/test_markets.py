"""Tests for vig removal / Kelly (pure math) and the backtest loader."""

from app.etl.backtest import load_backtest
from app.etl.polymarket import _book_price, devig, kelly_fraction, overround


def _book(bids, asks, last=None):
    return {
        "bids": [{"price": str(p), "size": "100"} for p in bids],
        "asks": [{"price": str(p), "size": "100"} for p in asks],
        "last_trade_price": str(last) if last is not None else None,
    }


def test_book_price_mids_a_tight_two_sided_book():
    """Healthy book (best bid 0.32, best ask 0.33) -> midpoint, matches Polymarket."""
    price, bid, ask, spread, src = _book_price(_book([0.30, 0.32], [0.35, 0.33]), 0.40)
    assert src == "book_mid"
    assert abs(price - 0.325) < 1e-9 and bid == 0.32 and ask == 0.33 and spread == 0.01


def test_book_price_falls_back_when_one_sided():
    """No bids -> no trustworthy mid -> use the last executed trade, not a fake mid."""
    price, bid, ask, spread, src = _book_price(_book([], [0.002], last=0.01), 0.05)
    assert src == "last_trade" and price == 0.01 and bid is None


def test_book_price_falls_back_when_spread_too_wide():
    """Bid 0.10 / ask 0.50 -> mid 0.30 is meaningless -> last trade instead."""
    price, _, _, spread, src = _book_price(_book([0.10], [0.50], last=0.22), 0.25)
    assert src == "last_trade" and price == 0.22 and spread == 0.40


def test_book_price_uses_gamma_when_no_book_and_no_trade():
    price, _, _, _, src = _book_price(_book([], []), 0.18)
    assert src == "gamma" and price == 0.18


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
