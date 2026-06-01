"""Build the shared per-(race, driver) feature table for the model bake-off.

One row per driver per race, chronologically ordered, with only PRE-RACE signals
(grid, qualifying pace, FP long-run pace) plus the realized outcome for scoring.
Everything downstream is forward-chained on this table, so it must never leak
post-race information into the feature columns.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import polars as pl

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
PRACTICE_PARQUET = DATA_DIR / "practice.parquet"

DRY = ("SOFT", "MEDIUM", "HARD")


@lru_cache
def _race_seq() -> dict[tuple[int, str], int]:
    """Chronological index per (year, circuit) from the FastF1 schedules."""
    from app.etl.fastf1_client import _ensure_cache

    _ensure_cache()
    import fastf1

    ordered: list[tuple[int, int, str]] = []
    for year in range(2018, 2027):
        try:
            sched = fastf1.get_event_schedule(year, include_testing=False)
        except Exception:
            continue
        for _, row in sched.iterrows():
            rnd = int(row["RoundNumber"])
            if rnd == 0:
                continue
            circuit = str(row["EventName"]).replace(" Grand Prix", "").strip()
            ordered.append((year, rnd, circuit))
    ordered.sort(key=lambda t: (t[0], t[1]))
    return {(y, c): i for i, (y, r, c) in enumerate(ordered)}


def _finish_table(race: pl.DataFrame) -> pl.DataFrame:
    """Per-driver finishing position (laps completed desc, last position asc)."""
    last = (
        race.with_columns(pl.col("lap_number").max().over("driver").alias("mx"))
        .filter(pl.col("lap_number") == pl.col("mx"))
        .unique(subset=["driver"], keep="first")
        .select(["driver", "lap_number", "position"])
        .with_columns(pl.col("position").fill_null(99))
        .sort(["lap_number", "position"], descending=[True, False])
    )
    rows = last.to_dicts()
    total = int(race["lap_number"].max())
    out = []
    for i, r in enumerate(rows):
        out.append(
            {
                "driver": r["driver"],
                "finish_pos": i + 1,
                "dnf": r["lap_number"] < total - 1,  # ran fewer than ~all laps
            }
        )
    return pl.DataFrame(out)


def _quali_pace(qlaps: pl.DataFrame) -> pl.DataFrame:
    """Best clean Q lap per driver -> % gap to pole (a one-lap pace signal)."""
    q = qlaps.filter(pl.col("lap_time_s").is_not_null())
    if q.height == 0:
        return pl.DataFrame(schema={"driver": pl.Utf8, "quali_gap_pct": pl.Float64})
    best = q.group_by("driver").agg(pl.col("lap_time_s").min().alias("q_best"))
    pole = float(best["q_best"].min())
    return best.with_columns(
        ((pl.col("q_best") / pole) - 1.0).alias("quali_gap_pct")
    ).select(["driver", "quali_gap_pct"])


def _grid(race: pl.DataFrame) -> pl.DataFrame:
    """Starting grid = lap-1 race positions."""
    g1 = (
        race.filter(pl.col("lap_number") == 1)
        .filter(pl.col("position").is_not_null())
        .select(["driver", pl.col("position").alias("grid")])
    )
    return g1


@lru_cache
def _practice() -> pl.DataFrame:
    if PRACTICE_PARQUET.exists():
        return pl.read_parquet(PRACTICE_PARQUET)
    return pl.DataFrame()


def _fp_longrun(circuit: str, year: int) -> pl.DataFrame:
    """Fuel-corrected FP long-run pace per driver -> % gap to fastest (or empty)."""
    fp = _practice()
    if fp.height == 0:
        return pl.DataFrame(schema={"driver": pl.Utf8, "fp_pace_pct": pl.Float64})
    sub = fp.filter(
        (pl.col("circuit") == circuit)
        & (pl.col("year") == year)
        & (pl.col("track_status") == "1")
        & pl.col("is_accurate")
        & ~pl.col("is_pit_out")
        & ~pl.col("is_pit_in")
        & pl.col("lap_time_s").is_not_null()
        & pl.col("compound").is_in(DRY)
    )
    if sub.height == 0:
        return pl.DataFrame(schema={"driver": pl.Utf8, "fp_pace_pct": pl.Float64})
    # Within-stint fuel correction (relative): add back burned-fuel time by lap-in-stint.
    sub = sub.sort(["driver", "stint", "lap_number"]).with_columns(
        pl.col("lap_number")
        .rank("ordinal")
        .over(["driver", "stint"])
        .alias("lap_in_stint")
    )
    sub = sub.with_columns(
        (pl.col("lap_time_s") + 0.033 * 1.8 * pl.col("lap_in_stint")).alias("corr")
    )
    # Keep drivers with a real long run; take their median corrected pace.
    agg = sub.group_by("driver").agg(
        pl.col("corr").median().alias("med"), pl.len().alias("n")
    ).filter(pl.col("n") >= 6)
    if agg.height == 0:
        return pl.DataFrame(schema={"driver": pl.Utf8, "fp_pace_pct": pl.Float64})
    fastest = float(agg["med"].min())
    return agg.with_columns(
        ((pl.col("med") / fastest) - 1.0).alias("fp_pace_pct")
    ).select(["driver", "fp_pace_pct"])


def build_feature_table() -> pl.DataFrame:
    """One row per (year, circuit, driver) with pre-race features + outcome."""
    df = pl.read_parquet(LAPS_PARQUET)
    seq = _race_seq()
    races = (
        df.filter(pl.col("session_name") == "R")
        .select(["year", "circuit"])
        .unique()
        .to_dicts()
    )
    frames: list[pl.DataFrame] = []
    for rk in races:
        circuit, year = rk["circuit"], rk["year"]
        race = df.filter(
            (pl.col("session_name") == "R")
            & (pl.col("circuit") == circuit)
            & (pl.col("year") == year)
        )
        qlaps = df.filter(
            (pl.col("session_name") == "Q")
            & (pl.col("circuit") == circuit)
            & (pl.col("year") == year)
        )
        if race.height == 0:
            continue
        teams = (
            race.group_by("driver").agg(pl.col("team").last()).select(["driver", "team"])
        )
        t = (
            _finish_table(race)
            .join(_grid(race), on="driver", how="left")
            .join(_quali_pace(qlaps), on="driver", how="left")
            .join(_fp_longrun(circuit, year), on="driver", how="left")
            .join(teams, on="driver", how="left")
            .with_columns(
                pl.lit(year).alias("year"),
                pl.lit(circuit).alias("circuit"),
                pl.lit(seq.get((year, circuit), 9999)).alias("seq"),
                (pl.col("finish_pos") == 1).alias("won"),
                (pl.col("finish_pos") <= 3).alias("podium"),
                (pl.col("finish_pos") <= 10).alias("points"),
            )
        )
        frames.append(t)
    out = pl.concat(frames, how="vertical_relaxed").sort(["seq", "finish_pos"])
    return out


if __name__ == "__main__":
    t = build_feature_table()
    print(f"feature table: {t.height} driver-races, {t['seq'].n_unique()} races")
    print("columns:", t.columns)
    print("quali coverage:", t.filter(pl.col("quali_gap_pct").is_not_null()).height)
    print("FP coverage:", t.filter(pl.col("fp_pace_pct").is_not_null()).height)
    print(t.filter((pl.col("circuit") == "Bahrain") & (pl.col("year") == 2024)).select(
        ["driver", "grid", "quali_gap_pct", "fp_pace_pct", "finish_pos", "won"]
    ).head(5))
