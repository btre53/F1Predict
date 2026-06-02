"""Tests for the circuit overtaking-difficulty index (task #20)."""

import polars as pl

from app.models.overtaking import OvertakingIndex, _proxy_table


def test_proxy_table_has_all_proxies():
    t = _proxy_table()
    assert t.height > 100  # ~168 runnings
    for col in ("grid_finish_rho", "pass_rate", "lap1_churn", "seq", "era"):
        assert col in t.columns


def test_monaco_is_harder_than_spa():
    """Face validity: Monaco (the strongest prior) must out-rank Spa/Bahrain."""
    idx = OvertakingIndex()
    assert idx.index("Monaco") > idx.index("Belgian")
    assert idx.index("Monaco") > idx.index("Bahrain")


def test_spread_is_tighter_at_locked_tracks():
    """Higher difficulty -> lower (tighter) temperature."""
    idx = OvertakingIndex()
    assert idx.spread("Monaco", 0.5) < idx.spread("Belgian", 0.5)


def test_index_is_leak_free():
    """`before_seq` must hide same-and-future runnings: an early cutoff that drops
    every Monaco running yields the unseen-circuit fallback (0.0)."""
    idx = OvertakingIndex()
    first_monaco = (
        _proxy_table().filter(pl.col("circuit") == "Monaco")["seq"].min()
    )
    assert idx.index("Monaco", before_seq=int(first_monaco)) == 0.0
    assert idx.index("Monaco", before_seq=None) != 0.0


def test_grid_weight_bounded():
    idx = OvertakingIndex()
    for c in ("Monaco", "Belgian", "Bahrain"):
        gw = idx.grid_weight(c, 0.6)
        assert 0.0 < gw < 0.6
