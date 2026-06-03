"""Tests for the OpenF1 clean-air gap artifact (brief 24). Offline: reads the built parquet."""

import polars as pl

from app.etl.openf1 import OPENF1_CLEAN_PARQUET, clean_lap_set, covered_races


def test_artifact_built_and_shaped():
    assert OPENF1_CLEAN_PARQUET.exists(), "run `python -m app.etl.openf1` to build it"
    t = pl.read_parquet(OPENF1_CLEAN_PARQUET)
    assert t.height > 10000
    for col in ("year", "circuit", "driver", "lap_number", "gap_ahead_s", "clean"):
        assert col in t.columns
    # clean is a sensible majority-ish fraction (most laps are in clearish air)
    assert 0.4 < t["clean"].mean() < 0.85


def test_coverage_is_2023_plus():
    races = covered_races()
    assert races and all(yr >= 2023 for (yr, _) in races)
    assert (2024, "Bahrain") in races


def test_clean_set_has_the_leader_laps():
    """The Bahrain-2024 winner (VER) led in clear air — his laps must be flagged clean."""
    cl = clean_lap_set()
    assert cl
    ver = [k for k in cl if k[0] == 2024 and k[1] == "Bahrain" and k[2] == "VER"]
    assert len(ver) > 30   # led most of the race in clean air
