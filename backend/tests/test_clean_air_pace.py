"""Tests for the clean-air race-pace observable (brief 22 decoupling / brief 24)."""

import polars as pl

from app.models.clean_air_pace import CLEAN_AIR_PARQUET, build_clean_air_pace


def test_clean_air_artifact_shape():
    assert CLEAN_AIR_PARQUET.exists(), "run `python -m app.models.clean_air_pace` to build it"
    t = pl.read_parquet(CLEAN_AIR_PARQUET)
    assert t.height > 1000
    for col in ("year", "circuit", "driver", "clean_air_pace_s", "clean_air_gap_pct", "n_clean_laps"):
        assert col in t.columns
    # gap is a non-negative %; each row keeps at least one measured clean lap (the fast
    # quantile of the >=6 green laps required per car)
    assert t["clean_air_gap_pct"].min() >= 0.0
    assert t["n_clean_laps"].min() >= 1


def test_each_race_has_a_zero_gap_reference():
    """Per race, the fastest clean-air car defines the 0% reference."""
    t = build_clean_air_pace()
    per_race_min = t.group_by(["year", "circuit"]).agg(pl.col("clean_air_gap_pct").min().alias("m"))
    assert per_race_min["m"].max() < 1e-6   # every race's best car is ~0.0


def test_gap_is_a_small_realistic_spread():
    """Clean-air gaps should be a sane race-pace spread (cars within a few % of the leader)."""
    t = build_clean_air_pace()
    assert t["clean_air_gap_pct"].quantile(0.9) < 0.10   # 90th pct under ~10% off the pace
