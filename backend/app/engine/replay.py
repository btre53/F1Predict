"""Historical race replay: serve lap-by-lap state for the Explorer tab.

Reads the ingested Parquet archive (never the live APIs) and reshapes one race into
an animation-ready structure: per lap, every running driver's position, compound,
tyre age, pit flag, gap to leader, and the track status.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import polars as pl

from .predict import TEAM_COLOURS

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = _DATA_DIR / "laps.parquet"
INPLAY_OVERLAY = _DATA_DIR / "inplay_overlay.json"


@lru_cache(maxsize=1)
def _inplay_overlay_all() -> dict:
    if INPLAY_OVERLAY.exists():
        return json.loads(INPLAY_OVERLAY.read_text())
    return {}


def inplay_overlay(circuit: str, year: int) -> dict:
    """Per-lap model vs de-vigged Polymarket win-prob for a race (empty if none).

    Only 2024 races with an ingested in-play curve have an overlay (see
    app/etl/inplay_backtest.build_overlay). Win is the model's live MC win-prob; market
    is the de-vigged Polymarket winner price. Calibrated but does NOT lead the market
    (brief 13) -- a transparency/companion overlay, not a trading signal."""
    if int(year) != 2024:
        return {}
    return _inplay_overlay_all().get(circuit, {})


@lru_cache
def _laps() -> pl.DataFrame:
    return pl.read_parquet(LAPS_PARQUET)


def available_races() -> list[dict]:
    """List replayable races (race sessions in the archive)."""
    df = _laps().filter(pl.col("session_name") == "R")
    out = (
        df.group_by(["circuit", "year"])
        .agg(
            pl.col("lap_number").max().alias("total_laps"),
            pl.col("driver").n_unique().alias("n_drivers"),
        )
        .sort(["year", "circuit"], descending=[True, False])
    )
    return out.to_dicts()


def _track_status(code: str | None) -> str:
    """Map FastF1 concatenated status codes to the most severe state."""
    if not code:
        return "GREEN"
    if "5" in code:
        return "RED"
    if "4" in code:
        return "SC"
    if "6" in code or "7" in code:
        return "VSC"
    if "2" in code:
        return "YELLOW"
    return "GREEN"


def _f(x) -> float | None:
    return round(float(x), 3) if x is not None else None


@dataclass
class ReplayData:
    circuit: str
    year: int
    total_laps: int
    drivers: list[dict]
    laps: list[dict]


def load_replay(circuit: str, year: int) -> ReplayData:
    df = _laps().filter(
        (pl.col("session_name") == "R")
        & (pl.col("circuit") == circuit)
        & (pl.col("year") == year)
    )
    if df.height == 0:
        return ReplayData(circuit, year, 0, [], [])

    total_laps = int(df["lap_number"].max())

    # Fill missing lap times with each driver's median, for cumulative-gap estimates.
    df = df.with_columns(
        pl.col("lap_time_s")
        .fill_null(pl.col("lap_time_s").median().over("driver"))
        .fill_null(95.0)
        .alias("lt")
    ).sort(["driver", "lap_number"])
    df = df.with_columns(pl.col("lt").cum_sum().over("driver").alias("cum_s"))

    # Static driver metadata (latest team seen).
    drv = (
        df.group_by("driver")
        .agg(
            pl.col("driver_number").last().alias("number"),
            pl.col("team").last().alias("team"),
        )
        .sort("driver")
    )
    drivers = [
        {
            "driver": r["driver"],
            "number": int(r["number"]) if r["number"] is not None else None,
            "team": r["team"],
            "colour": TEAM_COLOURS.get(r["team"], "888888"),
        }
        for r in drv.to_dicts()
    ]

    laps: list[dict] = []
    for ln in range(1, total_laps + 1):
        lap_df = df.filter(pl.col("lap_number") == ln)
        if lap_df.height == 0:
            continue
        leader_cum = float(lap_df["cum_s"].min())
        status_codes = [c for c in lap_df["track_status"].to_list() if c]
        status = _track_status(max(status_codes, key=len) if status_codes else None)

        order = []
        rows = lap_df.sort("position", nulls_last=True).to_dicts()
        for rank, r in enumerate(rows, start=1):
            pos = int(r["position"]) if r["position"] is not None else rank
            order.append(
                {
                    "driver": r["driver"],
                    "position": pos,
                    "compound": r["compound"] or "UNKNOWN",
                    "tyre_life": int(r["tyre_life"]) if r["tyre_life"] is not None else 0,
                    "pitting": bool(r["is_pit_in"]) or bool(r["is_pit_out"]),
                    "gap_s": round(float(r["cum_s"]) - leader_cum, 1),
                    "sector1_s": _f(r["sector1_s"]),
                    "sector2_s": _f(r["sector2_s"]),
                    "sector3_s": _f(r["sector3_s"]),
                }
            )
        order.sort(key=lambda x: x["position"])
        laps.append({"lap": ln, "track_status": status, "order": order})

    return ReplayData(circuit, year, total_laps, drivers, laps)
