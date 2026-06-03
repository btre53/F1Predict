"""Per-car tyre deg from own stints (task #11): is it a reproducible measured property?"""

import polars as pl

from app.models.tyre_deg_car import CAR_DEG_PARQUET, build_car_deg, stability_gate


def test_artifact_shape():
    build_car_deg()
    assert CAR_DEG_PARQUET.exists()
    t = pl.read_parquet(CAR_DEG_PARQUET)
    assert t.height > 1000
    for col in ("year", "circuit", "driver", "team", "excess_deg_s_per_lap2", "n_stints", "seq"):
        assert col in t.columns
    # clipped to a sane physical range (s/lap/lap)
    assert t["excess_deg_s_per_lap2"].abs().max() <= 0.5


def test_per_car_deg_is_reproducible_not_noise():
    """The gate that justifies using per-car deg at all: prior deg must predict next deg."""
    g = stability_gate()
    assert g["n"] > 100
    # a real, persistent property shows positive forward autocorrelation
    assert g["spearman_prior_vs_next"] is not None and g["spearman_prior_vs_next"] > 0.15
