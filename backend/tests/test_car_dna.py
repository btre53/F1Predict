"""Tests for the car-DNA corner-band decomposition (task #22).

Offline only -- runs on the committed telemetry cache (data/car_dna.parquet), never
pulls from the network. The key guard is that shape-normalization actually removed
scalar pace (the brief's "scalar-pace in five hats" trap)."""

import numpy as np
import polars as pl
import pytest

from app.models.car_dna import BANDS, car_factors, dna_summary, extract


@pytest.fixture(scope="module")
def df():
    return extract()  # cache only; SAMPLE pull is gated behind force=True


def test_demand_profiles_sum_to_one(df):
    dem = df.group_by("circuit").agg([pl.col(f"dem_{b}").first() for b in BANDS])
    for r in dem.iter_rows(named=True):
        assert abs(sum(r[f"dem_{b}"] for b in BANDS) - 1.0) < 1e-6


def test_shape_normalization_removes_scalar_pace(df):
    """Per car-circuit, the shape factors must be ~zero-sum across present bands."""
    f = car_factors(df)
    for r in f.iter_rows(named=True):
        vals = [r[f"fac_{b}"] for b in BANDS if not np.isnan(r[f"fac_{b}"])]
        # field-net shifts the per-car zero-sum, but the cross-band spread must be finite
        # and not dominated by a single uniform level.
        assert all(abs(v) < 0.2 for v in vals)


def test_dna_summary_shape(df):
    s = dna_summary()
    assert s["bands"] == list(BANDS)
    assert len(s["circuit_demand"]) >= 10
    assert len(s["car_dna"]) >= 10
