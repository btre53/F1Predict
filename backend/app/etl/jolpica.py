"""Jolpica (Ergast successor) client: the OFFICIAL starting grid + retirement status (brief 24).

Ergast shut down early 2025; Jolpica (`api.jolpi.ca/ergast/f1`) is the free, backwards-compatible
replacement. Its race results carry `grid` (the official starting position, penalties applied —
NOT lap-1 position) and `status` (Finished / +1 Lap / Engine / Collision / ...). We use the grid
to replace the lap-1-position proxy (which conflates start performance into "grid"; task #19) and
expose status for reliability work.

Race names map to our circuit convention by stripping " Grand Prix" (Ergast "São Paulo Grand
Prix" -> "São Paulo", etc.). Free tier: 4 req/s, 500/hr -> we pace + retry on 429, cache to
data/grids.parquet.
"""

from __future__ import annotations

import time
from functools import lru_cache
from pathlib import Path

import polars as pl

BASE = "https://api.jolpi.ca/ergast/f1"
MIN_INTERVAL_S = 0.3
COVERAGE_YEARS = tuple(range(2018, 2027))

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
GRIDS_PARQUET = DATA_DIR / "grids.parquet"

_last = [0.0]


def _get(path: str, **params) -> dict | None:
    import requests

    for attempt in range(5):
        wait = MIN_INTERVAL_S - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        try:
            r = requests.get(f"{BASE}/{path}", params=params, timeout=40)
        except Exception:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 429:
            time.sleep(5 * (attempt + 1))
            continue
        if r.ok:
            return r.json()
        return None
    return None


def _circuit(race_name: str) -> str:
    return race_name.replace(" Grand Prix", "").strip()


def build_grids(years=COVERAGE_YEARS, *, force: bool = False) -> pl.DataFrame:
    """Official starting grid per (year, circuit, driver) from Jolpica. Cached."""
    if GRIDS_PARQUET.exists() and not force:
        return pl.read_parquet(GRIDS_PARQUET)

    rows: list[dict] = []
    for year in years:
        offset = 0
        while True:
            j = _get(f"{year}/results.json", limit=100, offset=offset)
            if not j:
                break
            races = j["MRData"]["RaceTable"]["Races"]
            if not races:
                break
            for race in races:
                circuit = _circuit(race["raceName"])
                for res in race.get("Results", []):
                    code = res["Driver"].get("code")
                    if not code:
                        continue
                    grid = int(res.get("grid", 0) or 0)
                    rows.append({
                        "year": year, "circuit": circuit, "driver": code,
                        "grid": grid if grid > 0 else 20,   # 0 = pit-lane start -> back
                        "status": res.get("status", ""),
                    })
            total = int(j["MRData"]["total"])
            offset += 100
            if offset >= total:
                break
    out = (
        pl.DataFrame(rows).unique(subset=["year", "circuit", "driver"], keep="first")
        if rows else pl.DataFrame(schema={"year": pl.Int64, "circuit": pl.Utf8,
                                          "driver": pl.Utf8, "grid": pl.Int64, "status": pl.Utf8})
    )
    out.write_parquet(GRIDS_PARQUET)
    return out


@lru_cache(maxsize=1)
def official_grid_map() -> dict[tuple[int, str, str], int]:
    """(year, circuit, driver) -> official starting grid position (empty if not built)."""
    if not GRIDS_PARQUET.exists():
        return {}
    return {(int(r["year"]), r["circuit"], r["driver"]): int(r["grid"])
            for r in pl.read_parquet(GRIDS_PARQUET).to_dicts()}


if __name__ == "__main__":
    t = build_grids(force=True)
    print(f"official grids: {t.height} car-races over {t.select(['year','circuit']).n_unique()} races")
    # coverage vs our laps
    laps = pl.read_parquet(DATA_DIR / "laps.parquet", columns=["year", "circuit", "session_name"]).filter(
        pl.col("session_name") == "R").select(["year", "circuit"]).unique()
    ours = {(int(r["year"]), r["circuit"]) for r in laps.to_dicts()}
    have = {(int(r["year"]), r["circuit"]) for r in t.select(["year", "circuit"]).unique().to_dicts()}
    print(f"  our R races: {len(ours)} | matched in Jolpica: {len(ours & have)} | unmatched: {sorted(ours - have)}")
