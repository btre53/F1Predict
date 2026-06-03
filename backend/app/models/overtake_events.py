"""Overtake-event detection — do STRONG cars CLEAR traffic faster? (task #24, the brief-25 probe).

Brief 25 (`docs/science/25-strength-dependent-dirty-air.md`) found the OPPOSITE of the naive
"strong cars shrug off dirty air" hypothesis at the PER-LAP grain: a stronger car loses MORE per
lap stuck in traffic (~1.3 s/lap vs ~0.5 s for a slow car), because a fast car behind a slow one is
being HELD UP — the pace-mismatch loss dwarfs any aero-wake benefit. Brief 25 left the honest open
question this module answers:

    Do strong cars nonetheless CLEAR traffic FASTER — lose less TOTAL time over a stint — because
    of DRS / top-speed / overtaking ability? (Fewer laps stuck, even at a steeper per-lap cost.)

This is an OUTCOME-level (not per-lap) measurement. It needs overtake-event detection from lap-to-lap
position, which the per-lap penalty curve cannot give. Method:

  * "Stuck-behind" EPISODE: a car within CLOSE_S (~1.5 s) of the car ahead (OpenF1 `gap_ahead_s`)
    for >= MIN_EPISODE_LAPS consecutive green laps.
  * The episode RESOLVES with a PASS if the following car's `position` improves by the end of /
    during the close run AND the gap then jumps (it cleared the car); otherwise the episode just
    ENDS (gap opened without a pass, pit, SC, or end of data) — not credited as a pass.
  * Bucket every episode by the FOLLOWING car's strength = its clean-air pace gap tercile
    (STRONG < 0.5 %, MID 0.5-1.5 %, SLOW > 1.5 %), the same split as brief 25.

Reports per bucket: episodes, pass rate, mean/median laps-stuck-per-episode, and (laps-stuck x the
measured per-lap dirty-air penalty for that bucket, from `dirty_air`) an estimate of TOTAL time lost
to traffic per episode. Honest caveats printed at the end — position-change detection from lap data
is noisy and SC/pit cycles confound "gap jumped".

Self-contained read-only analysis: reads laps.parquet, openf1_clean_laps.parquet, clean_air_pace.parquet
and the dirty_air per-lap penalties. Writes nothing, modifies no shared module.

Run:  uv run python -X utf8 -m app.models.overtake_events
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
OPENF1_CLEAN_PARQUET = DATA_DIR / "openf1_clean_laps.parquet"
CLEAN_AIR_PARQUET = DATA_DIR / "clean_air_pace.parquet"

CLOSE_S = 1.5          # within this gap-to-car-ahead = "stuck behind" (matches openf1 GAP_CLEAN_S)
MIN_EPISODE_LAPS = 2   # need at least this many consecutive close laps to count as an episode
GAP_JUMP_S = 1.0       # gap must open by at least this much after a pass to confirm "cleared"

# Strength buckets on clean-air pace gap (same split as brief 25 / dirty_air.py).
STRONG_MAX = 0.005
MID_MAX = 0.015

# Per-lap in-traffic penalty by bucket, MEASURED in brief 25 (close-gap <1s median, s/lap).
# Used only to translate laps-stuck -> an order-of-magnitude TOTAL time-lost estimate.
PERLAP_PENALTY = {"strong": 1.31, "mid": 0.76, "slow": 0.46}


def _strength(gap_pct: float) -> str:
    if gap_pct < STRONG_MAX:
        return "strong"
    if gap_pct < MID_MAX:
        return "mid"
    return "slow"


def _load() -> pl.DataFrame:
    """Per (year, circuit, driver, lap): green flag, position, gap_ahead_s, following-car strength.

    Joins lap position (laps.parquet) to the OpenF1 gap and the car's clean-air strength. Restricted
    to 2023+ R laps that OpenF1 covers. Keeps pit-out laps flagged so an episode can be broken there.
    """
    laps = (
        pl.read_parquet(
            LAPS_PARQUET,
            columns=["year", "circuit", "driver", "lap_number", "session_name",
                     "track_status", "position", "is_pit_out", "is_pit_in"],
        )
        .filter((pl.col("session_name") == "R") & (pl.col("year") >= 2023))
        .with_columns((pl.col("track_status").cast(pl.Utf8) == "1").alias("green"))
        .drop("session_name", "track_status")
    )
    gaps = pl.read_parquet(
        OPENF1_CLEAN_PARQUET,
        columns=["year", "circuit", "driver", "lap_number", "gap_ahead_s"],
    )
    strength = (
        pl.read_parquet(CLEAN_AIR_PARQUET, columns=["year", "circuit", "driver", "clean_air_gap_pct"])
    )
    return (
        laps.join(gaps, on=["year", "circuit", "driver", "lap_number"], how="inner")
        .join(strength, on=["year", "circuit", "driver"], how="inner")
        .filter(pl.col("position").is_not_null())
        .sort(["year", "circuit", "driver", "lap_number"])
    )


def _episodes(df: pl.DataFrame) -> list[dict]:
    """Walk each car's lap sequence and emit one record per stuck-behind episode.

    An episode = a maximal run of consecutive laps (lap_number contiguous, green, not pit) with
    gap_ahead_s <= CLOSE_S. It is credited a PASS if the car's position at the lap AFTER the run is
    BETTER (lower) than at the lap the run started, and the gap-ahead on that exit lap opened by
    >= GAP_JUMP_S (it cleared into the next car's wake / clean air). Otherwise it just ENDED.
    """
    episodes: list[dict] = []
    for (year, circuit, driver), car in df.group_by(
        ["year", "circuit", "driver"], maintain_order=True
    ):
        rows = car.to_dicts()
        n = len(rows)
        i = 0
        while i < n:
            r = rows[i]
            close = (
                r["gap_ahead_s"] is not None
                and r["gap_ahead_s"] <= CLOSE_S
                and r["green"]
                and not r["is_pit_in"]
                and not r["is_pit_out"]
            )
            if not close:
                i += 1
                continue
            # Extend the run while laps are contiguous, green, non-pit, and still close.
            start = i
            j = i
            while j + 1 < n:
                nxt = rows[j + 1]
                contiguous = nxt["lap_number"] == rows[j]["lap_number"] + 1
                still = (
                    contiguous
                    and nxt["gap_ahead_s"] is not None
                    and nxt["gap_ahead_s"] <= CLOSE_S
                    and nxt["green"]
                    and not nxt["is_pit_in"]
                    and not nxt["is_pit_out"]
                )
                if not still:
                    break
                j += 1
            laps_stuck = j - start + 1
            if laps_stuck >= MIN_EPISODE_LAPS:
                start_pos = rows[start]["position"]
                start_str = _strength(rows[start]["clean_air_gap_pct"])
                # Resolution: look at the lap immediately after the run (if any, contiguous).
                passed = False
                resolved_in_data = False
                if j + 1 < n and rows[j + 1]["lap_number"] == rows[j]["lap_number"] + 1:
                    resolved_in_data = True
                    exit_row = rows[j + 1]
                    pos_improved = (
                        exit_row["position"] is not None
                        and start_pos is not None
                        and exit_row["position"] < start_pos
                    )
                    gap_opened = (
                        exit_row["gap_ahead_s"] is not None
                        and exit_row["gap_ahead_s"] >= GAP_JUMP_S
                    )
                    passed = bool(pos_improved and gap_opened)
                episodes.append({
                    "year": year, "circuit": circuit, "driver": driver,
                    "strength": start_str,
                    "laps_stuck": laps_stuck,
                    "passed": passed,
                    "resolved_in_data": resolved_in_data,
                    "start_lap": rows[start]["lap_number"],
                    "start_pos": start_pos,
                })
            i = j + 1
    return episodes


def analyse() -> dict:
    df = _load()
    eps = _episodes(df)
    if not eps:
        return {"n_episodes": 0, "buckets": {}}
    e = pl.DataFrame(eps)

    out: dict = {"n_episodes": e.height, "buckets": {}}
    for bucket in ("strong", "mid", "slow"):
        sub = e.filter(pl.col("strength") == bucket)
        if sub.height == 0:
            out["buckets"][bucket] = None
            continue
        # Pass rate only over episodes whose resolution we can actually see in the data.
        resolved = sub.filter(pl.col("resolved_in_data"))
        laps = sub["laps_stuck"].to_numpy().astype(float)
        perlap = PERLAP_PENALTY[bucket]
        out["buckets"][bucket] = {
            "n_episodes": sub.height,
            "n_resolved": resolved.height,
            "pass_rate": round(float(resolved["passed"].mean()), 3) if resolved.height else None,
            "mean_laps_stuck": round(float(np.mean(laps)), 2),
            "median_laps_stuck": int(np.median(laps)),
            "perlap_penalty_s": perlap,
            "mean_total_time_lost_s": round(float(np.mean(laps)) * perlap, 2),
            "median_total_time_lost_s": round(float(np.median(laps)) * perlap, 2),
        }
    return out


def _fmt(b: dict | None) -> str:
    if b is None:
        return "  (no episodes)"
    pr = "n/a" if b["pass_rate"] is None else f"{b['pass_rate']*100:4.1f}%"
    return (
        f"  episodes {b['n_episodes']:4d} | pass-rate {pr} ({b['n_resolved']} resolved)\n"
        f"  laps-stuck/episode  mean {b['mean_laps_stuck']:.2f}  median {b['median_laps_stuck']}\n"
        f"  per-lap penalty {b['perlap_penalty_s']:.2f}s -> total time lost/episode "
        f"mean {b['mean_total_time_lost_s']:.1f}s  median {b['median_total_time_lost_s']:.1f}s"
    )


if __name__ == "__main__":
    r = analyse()
    print("Overtake-event detection — do STRONG cars CLEAR traffic faster? (task #24)\n")
    print(f"Total stuck-behind episodes (>= {MIN_EPISODE_LAPS} consecutive laps within "
          f"{CLOSE_S}s): {r['n_episodes']}\n")
    for bucket in ("strong", "mid", "slow"):
        print(f"[{bucket.upper()}]  (clean-air pace gap "
              f"{'<0.5%' if bucket=='strong' else '0.5-1.5%' if bucket=='mid' else '>1.5%'})")
        print(_fmt(r["buckets"].get(bucket)))
        print()
    print("Hypothesis: STRONG cars clear traffic in FEWER laps / higher pass rate (even though")
    print("they lose MORE per lap, brief 25). Read pass-rate + laps-stuck across buckets above.")
