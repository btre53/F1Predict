"""Upstream schema-contract test: does FastF1 still return the shape our ETL expects?

FastF1 is an external dependency that can change its data schema between versions /
seasons — the classic silent-breakage source for a data app. This loads one real
session through our normalizer and asserts the normalized columns are intact, so schema
drift surfaces as a RED scheduled-ingest run (with an email) rather than a quiet failure
weeks later.

Network + FastF1 required, so it only runs when F1P_CONTRACT_TEST=1 (set in the ingest
workflow). It is skipped in the normal offline test run / main CI.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("F1P_CONTRACT_TEST") != "1",
    reason="network contract test; set F1P_CONTRACT_TEST=1 (ingest workflow only)",
)


def test_fastf1_lap_schema_intact():
    from app.etl.fastf1_client import LAP_COLUMNS, load_session_laps

    df = load_session_laps(2024, "Bahrain", "R")
    assert df.height > 0, "FastF1 returned no laps — upstream change or outage"
    missing = set(LAP_COLUMNS) - set(df.columns)
    assert not missing, f"FastF1 schema drift: normalized columns missing {missing}"
    # Spot-check the fields the engine actually relies on.
    assert df["lap_time_s"].dtype.is_numeric()
    assert df.filter(df["lap_time_s"].is_not_null()).height > 0
