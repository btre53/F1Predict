"""Normalized circuit outlines (from FastF1 fastest-lap telemetry) for the Explorer map.

Served from a precomputed cache (data/track_outlines.json) built by
app.etl.build_track_outlines — the API never calls FastF1 at request time.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

OUTLINES = Path(__file__).resolve().parents[2] / "data" / "track_outlines.json"


@lru_cache
def _cache() -> dict:
    return json.loads(OUTLINES.read_text()) if OUTLINES.exists() else {}


def outline_for(circuit: str, year: int) -> dict | None:
    """Return {'path': '<svg d>'} for a circuit, preferring the exact year."""
    c = _cache()
    return c.get(f"{year}:{circuit}") or c.get(circuit)
