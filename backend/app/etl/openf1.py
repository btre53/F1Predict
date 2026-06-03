"""OpenF1 client: MEASURED gap-to-car-ahead per lap, to upgrade the clean-air proxy (brief 24).

OpenF1 (openf1.org) is FREE for historical data (anything >30 min after a session) — no auth.
Its `intervals` endpoint gives each car's gap to the car ahead over time, and `laps` gives each
lap's `date_start` + `lap_duration`, so we can window the gaps into laps and label each lap
**clean-air** (gap ahead > ~1.5 s) or **dirty-air** from real data — replacing the fast-quantile
proxy in `clean_air_pace.py`. Coverage is 2023+; older races keep the proxy.

Free-tier etiquette: 3 req/s, 30/min → we pace requests and retry on HTTP 429, and cache each
session's computed per-lap gaps to `data/openf1_clean_laps.parquet` so reruns are offline.
"""

from __future__ import annotations

import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import polars as pl

BASE = "https://api.openf1.org/v1"
MIN_INTERVAL_S = 2.1          # >= 1 request / 2.1s keeps us under the free 30/min limit
GAP_CLEAN_S = 1.5             # gap to car ahead above which a lap counts as clean air
COVERAGE_YEARS = (2023, 2024, 2025, 2026)   # OpenF1 history starts in 2023

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
OPENF1_CLEAN_PARQUET = DATA_DIR / "openf1_clean_laps.parquet"

_last_req = [0.0]


def _get(ep: str, **params) -> list[dict]:
    """Rate-limited GET against OpenF1 with 429 backoff. Returns [] on failure."""
    import requests

    for attempt in range(5):
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_req[0])
        if wait > 0:
            time.sleep(wait)
        _last_req[0] = time.monotonic()
        try:
            r = requests.get(f"{BASE}/{ep}", params=params, timeout=60)
        except Exception:
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 429:
            time.sleep(6 * (attempt + 1))
            continue
        if r.ok:
            return r.json()
        return []
    return []


def _ts(s: str) -> float:
    """OpenF1 ISO timestamp -> epoch seconds."""
    return datetime.fromisoformat(s).timestamp()


def _effective_gap(row: dict) -> float | None:
    """Gap to the car ahead in seconds; +inf for the leader; None if unknown."""
    g2l = row.get("gap_to_leader")
    if isinstance(g2l, (int, float)) and g2l < 0.05:
        return float("inf")          # this car is leading -> clear air
    iv = row.get("interval")
    return float(iv) if isinstance(iv, (int, float)) else None


def _session_clean_laps(session_key: int, num2code: dict[int, str]) -> list[dict]:
    """Per (driver, lap): median measured gap-to-car-ahead -> clean-air flag for one session."""
    laps = _get("laps", session_key=session_key)
    intervals = _get("intervals", session_key=session_key)
    if not laps or not intervals:
        return []

    # Group interval samples by driver_number, sorted by time.
    by_drv: dict[int, list[tuple[float, float | None]]] = {}
    for r in intervals:
        dn = r.get("driver_number")
        d = r.get("date")
        if dn is None or d is None:
            continue
        by_drv.setdefault(dn, []).append((_ts(d), _effective_gap(r)))
    for dn in by_drv:
        by_drv[dn].sort(key=lambda t: t[0])

    out: list[dict] = []
    for lp in laps:
        dn = lp.get("driver_number")
        code = num2code.get(dn)
        ds = lp.get("date_start")
        dur = lp.get("lap_duration")
        if code is None or ds is None or not isinstance(dur, (int, float)):
            continue
        lo = _ts(ds)
        hi = lo + float(dur)
        samples = [g for (t, g) in by_drv.get(dn, []) if lo <= t <= hi and g is not None]
        if not samples:
            continue
        samples.sort()
        med = samples[len(samples) // 2]
        out.append({
            "driver": code,
            "lap_number": int(lp["lap_number"]),
            "gap_ahead_s": round(float(med), 3) if med != float("inf") else 999.0,
            "clean": bool(med > GAP_CLEAN_S),
            "is_pit_out": bool(lp.get("is_pit_out_lap")),
        })
    return out


def build_openf1_clean_laps(years=COVERAGE_YEARS, *, force: bool = False) -> pl.DataFrame:
    """For every R race we hold in `years`, label each lap clean/dirty from OpenF1 gaps."""
    if OPENF1_CLEAN_PARQUET.exists() and not force:
        return pl.read_parquet(OPENF1_CLEAN_PARQUET)

    from app.etl.weather import _race_datetimes

    dts = _race_datetimes()
    laps_us = (
        pl.read_parquet(LAPS_PARQUET, columns=["year", "circuit", "driver", "driver_number", "session_name"])
        .filter(pl.col("session_name") == "R")
    )

    rows: list[dict] = []
    for year in years:
        sessions = _get("sessions", year=year, session_name="Race")
        by_date = {s["date_start"][:10]: s for s in sessions if s.get("date_start")}
        our_circuits = (
            laps_us.filter(pl.col("year") == year).select("circuit").unique()["circuit"].to_list()
        )
        for circuit in our_circuits:
            dt = dts.get((year, circuit))
            if dt is None:
                continue
            sess = by_date.get(dt[0])   # match by race date
            if not sess:
                continue                # no OpenF1 coverage for this race
            num2code = {
                int(r["driver_number"]): r["driver"]
                for r in laps_us.filter((pl.col("year") == year) & (pl.col("circuit") == circuit))
                .select(["driver", "driver_number"]).unique().to_dicts()
                if r["driver_number"] is not None
            }
            for r in _session_clean_laps(int(sess["session_key"]), num2code):
                r.update({"year": year, "circuit": circuit})
                rows.append(r)

    out = pl.DataFrame(rows) if rows else pl.DataFrame(
        schema={"driver": pl.Utf8, "lap_number": pl.Int64, "gap_ahead_s": pl.Float64,
                "clean": pl.Boolean, "is_pit_out": pl.Boolean, "year": pl.Int64, "circuit": pl.Utf8}
    )
    out.write_parquet(OPENF1_CLEAN_PARQUET)
    return out


@lru_cache(maxsize=1)
def clean_lap_set() -> set[tuple[int, str, str, int]]:
    """{(year, circuit, driver, lap_number)} flagged clean-air by OpenF1 (empty if not built)."""
    if not OPENF1_CLEAN_PARQUET.exists():
        return set()
    df = pl.read_parquet(OPENF1_CLEAN_PARQUET).filter(pl.col("clean"))
    return {(int(r["year"]), r["circuit"], r["driver"], int(r["lap_number"])) for r in df.to_dicts()}


@lru_cache(maxsize=1)
def covered_races() -> set[tuple[int, str]]:
    """{(year, circuit)} for which OpenF1 gap data was successfully built."""
    if not OPENF1_CLEAN_PARQUET.exists():
        return set()
    df = pl.read_parquet(OPENF1_CLEAN_PARQUET).select(["year", "circuit"]).unique()
    return {(int(r["year"]), r["circuit"]) for r in df.to_dicts()}


if __name__ == "__main__":
    t = build_openf1_clean_laps(force=True)
    print(f"OpenF1 clean-air laps: {t.height} laps across {t.select(['year','circuit']).n_unique()} races")
    if t.height:
        print(f"  clean fraction: {t['clean'].mean():.2f}")
        print(t.group_by("year").agg(pl.col("clean").mean().round(3), pl.len()).sort("year"))
