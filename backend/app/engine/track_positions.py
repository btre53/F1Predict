"""Per-frame car positions (from FastF1 position telemetry) for the Explorer map.

Served from a precomputed cache (data/track_positions.json) built by
app.etl.build_track_positions — the API never calls FastF1 at request time.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

POSITIONS = Path(__file__).resolve().parents[2] / "data" / "track_positions.json"


@lru_cache
def _cache() -> dict:
    return json.loads(POSITIONS.read_text()) if POSITIONS.exists() else {}


def positions_for(circuit: str, year: int) -> dict | None:
    """Return the cached positions payload for a race, or None if not built."""
    return _cache().get(f"{year}:{circuit}")
