"""Tests for weather-as-variance (brief 21): the ETL artifact + the points-only wet widening."""

import polars as pl

from app.etl.weather import CIRCUIT_COORDS, WEATHER_PARQUET, weather_map
from app.models.predict_kalman import predict_race_kalman


def test_weather_table_shape_and_labels():
    assert WEATHER_PARQUET.exists(), "run `python -m app.etl.weather` to build the artifact"
    t = pl.read_parquet(WEATHER_PARQUET)
    assert t.height > 100
    for col in ("year", "circuit", "wet", "precip_mm_window", "precip_mm_max", "seq"):
        assert col in t.columns
    # wet is a bool flag and a sensible minority of races
    assert set(t["wet"].unique().to_list()) <= {True, False}
    wet_rate = t["wet"].mean()
    assert 0.05 < wet_rate < 0.6


def test_every_raced_circuit_has_coords():
    """No R-race circuit should be silently dropped for a missing coordinate."""
    laps = pl.read_parquet(
        WEATHER_PARQUET.parent / "laps.parquet", columns=["circuit", "session_name"]
    )
    raced = set(laps.filter(pl.col("session_name") == "R")["circuit"].unique().to_list())
    missing = raced - set(CIRCUIT_COORDS)
    assert not missing, f"missing circuit coords: {missing}"


def test_weather_map_lookup():
    wm = weather_map()
    assert wm  # non-empty
    # 2024 Sao Paulo was a genuinely wet race (cross-checked vs FastF1 Rainfall)
    row = wm.get((2024, "São Paulo"))
    assert row is not None and row["wet"] is True


def test_wet_widening_touches_points_only():
    """The wet widening must leave win/podium/the distribution identical and only flatten points."""
    dry = predict_race_kalman("Monaco", n_sims=6000, rain=0.0)
    wet = predict_race_kalman("Monaco", n_sims=6000, rain=1.0)
    assert dry.wet is False and wet.wet is True
    assert wet.rain_prob == 1.0
    dd = {o.driver: o for o in dry.outcomes}
    ww = {o.driver: o for o in wet.outcomes}
    # win + podium come from the untouched base pass -> byte-identical
    assert all(abs(dd[k].win_pct - ww[k].win_pct) < 1e-9 for k in dd)
    assert all(abs(dd[k].podium_pct - ww[k].podium_pct) < 1e-9 for k in dd)
    # points come from the widened pass -> they move
    assert any(abs(dd[k].points_pct - ww[k].points_pct) > 1e-3 for k in dd)


def test_weather_spread_off_is_dry():
    res = predict_race_kalman("Monaco", n_sims=4000, weather_spread=False)
    assert res.wet is False and res.rain_prob == 0.0
