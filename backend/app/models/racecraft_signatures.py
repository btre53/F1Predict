"""Does the car-netted racecraft signal show up in *in-race process*, not just outcome?

Decisive, free (no API) test of the live-telemetry premise. Racecraft (`racecraft.py`)
is positions-gained-above-expectation, car-netted -- an OUTCOME. If that signal is real
driver skill (and therefore plausibly visible in a live telemetry feed), it should also
show up in *process* signatures we can measure lap-by-lap, netted against the teammate
(who shares the car):

    - tyre management  : within-stint green-flag degradation slope (s/lap). Flatter = better.
    - consistency      : detrended within-stint lap-time scatter (s). Lower = fewer mistakes.
    - race pace        : median green-flag lap gap to the race's best green lap.
    - traffic recovery : lap-time penalty while running in dirty air (close behind a car).
    - on-track moves   : net positions gained on track (pit-cycle-robust) -- a semi-outcome
                         cross-check, not a clean process feature.

We teammate-net every signature (subtract the teammate's value that race) so the car
cancels, exactly like racecraft does, then ask: do the netted process signatures track
the netted outcome (PGAE)? If yes, racecraft is a real, telemetry-visible skill signal.
If no, the live-telemetry premise is shaky -- learned for free, before any paid feed.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from .features import LAPS_PARQUET, _race_seq
from .racecraft import compute_pgae
from .features import build_feature_table

GREEN = "1"
DRY = ("SOFT", "MEDIUM", "HARD")


def _green_laps() -> pl.DataFrame:
    """All race laps usable for pace work: green-flag, accurate, non-pit, dry, timed."""
    df = pl.read_parquet(LAPS_PARQUET).filter(pl.col("session_name") == "R")
    seq = _race_seq()
    df = df.with_columns(
        pl.struct(["year", "circuit"])
        .map_elements(lambda s: seq.get((s["year"], s["circuit"]), 9999),
                      return_dtype=pl.Int64)
        .alias("seq")
    )
    return df.filter(
        (pl.col("track_status") == GREEN)
        & pl.col("is_accurate")
        & ~pl.col("is_pit_out")
        & ~pl.col("is_pit_in")
        & pl.col("lap_time_s").is_not_null()
        & pl.col("compound").is_in(DRY)
    )


def _stint_slope_and_scatter(g: pl.DataFrame) -> pl.DataFrame:
    """Per (seq, driver): median within-stint deg slope (s/lap) and detrended scatter (s).

    Fuel makes the car faster down a stint and tyres make it slower; the teammate shares
    the fuel effect, so the teammate-netted slope is a clean tyre-management delta.
    """
    # Lap index within stint (1..n) and per-stint sizes.
    g = g.sort(["seq", "driver", "stint", "lap_number"]).with_columns(
        pl.col("lap_number").rank("ordinal").over(["seq", "driver", "stint"]).alias("k"),
        pl.len().over(["seq", "driver", "stint"]).alias("stint_n"),
    ).filter(pl.col("stint_n") >= 5)  # need a real run to fit a slope

    # OLS slope of lap_time_s on k, per stint, via covariance / variance.
    stint = g.group_by(["seq", "driver", "stint"]).agg(
        pl.col("k").mean().alias("kbar"),
        pl.col("lap_time_s").mean().alias("ybar"),
        ((pl.col("k") - pl.col("k").mean()) * (pl.col("lap_time_s") - pl.col("lap_time_s").mean()))
        .sum().alias("sxy"),
        ((pl.col("k") - pl.col("k").mean()) ** 2).sum().alias("sxx"),
        pl.col("lap_time_s").alias("y"),
        pl.col("k").alias("kk"),
        pl.len().alias("n"),
    ).with_columns((pl.col("sxy") / pl.col("sxx")).alias("slope"))

    # Detrended residual std: std of (y - (ybar + slope*(k-kbar))).
    def _resid_std(row) -> float:
        y = np.array(row["y"], dtype=float)
        k = np.array(row["kk"], dtype=float)
        pred = row["ybar"] + row["slope"] * (k - row["kbar"])
        r = y - pred
        return float(np.std(r)) if len(r) >= 3 else float("nan")

    stint = stint.with_columns(
        pl.struct(["y", "kk", "ybar", "slope", "kbar"])
        .map_elements(_resid_std, return_dtype=pl.Float64)
        .alias("scatter")
    )
    return stint.group_by(["seq", "driver"]).agg(
        pl.col("slope").median().alias("deg_slope"),
        pl.col("scatter").median().alias("consistency"),
    )


def _race_pace(g: pl.DataFrame) -> pl.DataFrame:
    """Per (seq, driver): median green lap, then % gap to the race's best driver-median."""
    med = g.group_by(["seq", "driver"]).agg(
        pl.col("lap_time_s").median().alias("med_lap"),
        pl.len().alias("green_n"),
    ).filter(pl.col("green_n") >= 8)
    best = med.group_by("seq").agg(pl.col("med_lap").min().alias("best_med"))
    return med.join(best, on="seq").with_columns(
        ((pl.col("med_lap") / pl.col("best_med")) - 1.0).alias("race_pace_pct")
    ).select(["seq", "driver", "race_pace_pct", "green_n"])


def _traffic_penalty(g: pl.DataFrame) -> pl.DataFrame:
    """Per (seq, driver): dirty-air penalty = median(in-traffic lap) - median(clean lap).

    Reconstruct each lap's gap to the car ahead from cumulative race time, mark a lap as
    'traffic' when that gap < 1.5s. Crude (lap-resolution, ignores SC restarts) but the
    teammate-netting cancels most shared error. Positive = loses more time in traffic.
    """
    gg = g.sort(["seq", "driver", "lap_number"]).with_columns(
        pl.col("lap_time_s").cum_sum().over(["seq", "driver"]).alias("cum_t")
    )
    # Gap to the car ahead on the same lap: sort by cum_t within (seq, lap_number).
    gg = gg.sort(["seq", "lap_number", "cum_t"]).with_columns(
        (pl.col("cum_t") - pl.col("cum_t").shift(1)).over(["seq", "lap_number"]).alias("gap_ahead")
    )
    gg = gg.with_columns(
        (pl.col("gap_ahead").is_not_null() & (pl.col("gap_ahead") < 1.5)).alias("in_traffic")
    )
    agg = gg.group_by(["seq", "driver"]).agg(
        pl.col("lap_time_s").filter(pl.col("in_traffic")).median().alias("traf_lap"),
        pl.col("lap_time_s").filter(~pl.col("in_traffic")).median().alias("clean_lap"),
        pl.col("in_traffic").sum().alias("n_traffic"),
    )
    return agg.with_columns(
        (pl.col("traf_lap") - pl.col("clean_lap")).alias("traffic_penalty")
    ).select(["seq", "driver", "traffic_penalty", "n_traffic"])


def _ontrack_moves(g_all: pl.DataFrame) -> pl.DataFrame:
    """Per (seq, driver): net positions gained on track = lap1 pos - final-lap pos.

    Uses ALL race laps (positions exist under SC too). Semi-outcome cross-check only --
    it overlaps the PGAE target by construction, so a high correlation here is expected
    and not evidence of process signal.
    """
    first = g_all.filter(pl.col("lap_number") == 1).select(
        ["seq", "driver", pl.col("position").alias("p_start")]
    )
    last = (
        g_all.with_columns(pl.col("lap_number").max().over(["seq", "driver"]).alias("mx"))
        .filter(pl.col("lap_number") == pl.col("mx"))
        .unique(subset=["seq", "driver"], keep="first")
        .select(["seq", "driver", pl.col("position").alias("p_end")])
    )
    return first.join(last, on=["seq", "driver"], how="inner").with_columns(
        (pl.col("p_start") - pl.col("p_end")).alias("ontrack_gain")
    ).select(["seq", "driver", "ontrack_gain"])


def build_signature_table() -> pl.DataFrame:
    """Per driver-race process signatures + teammate-netted versions + PGAE target."""
    g = _green_laps()
    g_all = pl.read_parquet(LAPS_PARQUET).filter(pl.col("session_name") == "R")
    seq = _race_seq()
    g_all = g_all.with_columns(
        pl.struct(["year", "circuit"])
        .map_elements(lambda s: seq.get((s["year"], s["circuit"]), 9999), return_dtype=pl.Int64)
        .alias("seq")
    )

    sig = (
        _stint_slope_and_scatter(g)
        .join(_race_pace(g), on=["seq", "driver"], how="outer_coalesce")
        .join(_traffic_penalty(g), on=["seq", "driver"], how="outer_coalesce")
        .join(_ontrack_moves(g_all), on=["seq", "driver"], how="outer_coalesce")
    )

    # Attach team + PGAE (the car-netted outcome) from the feature table.
    feat = compute_pgae(build_feature_table()).select(
        ["seq", "driver", "team", "grid", "finish_pos", "pgae"]
    )
    sig = sig.join(feat, on=["seq", "driver"], how="inner")

    # Teammate-net every signature: subtract the team's mean that race.
    metrics = ["deg_slope", "consistency", "race_pace_pct", "traffic_penalty",
               "ontrack_gain", "pgae"]
    team_means = sig.group_by(["seq", "team"]).agg(
        [pl.col(m).mean().alias(f"{m}__team") for m in metrics]
    )
    sig = sig.join(team_means, on=["seq", "team"], how="left")
    sig = sig.with_columns(
        [(pl.col(m) - pl.col(f"{m}__team")).alias(f"{m}_net") for m in metrics]
    )
    return sig


def _corr(a: pl.Series, b: pl.Series) -> tuple[float, int]:
    df = pl.DataFrame({"a": a, "b": b}).drop_nulls()
    if df.height < 10:
        return float("nan"), df.height
    x, y = df["a"].to_numpy(), df["b"].to_numpy()
    if np.std(x) < 1e-12 or np.std(y) < 1e-12:
        return float("nan"), df.height
    return float(np.corrcoef(x, y)[0, 1]), df.height


def report() -> None:
    sig = build_signature_table()
    print(f"signature table: {sig.height} driver-races across {sig['seq'].n_unique()} races\n")

    # Expected sign of correlation with PGAE (beating the grid = +ve PGAE):
    #   deg_slope_net  : flatter (lower) slope is better -> NEGATIVE corr expected
    #   consistency_net: lower scatter is better         -> NEGATIVE
    #   race_pace_net  : lower % gap is faster           -> NEGATIVE
    #   traffic_net    : lower penalty is better         -> NEGATIVE
    #   ontrack_net    : more gains                       -> POSITIVE (semi-outcome)
    print("Per-DRIVER-RACE, teammate-netted signature vs teammate-netted PGAE:")
    print("  (sign in parens = direction that means 'better racecraft')")
    rows = [
        ("deg_slope_net", "lower=better tyre mgmt", "-"),
        ("consistency_net", "lower=fewer mistakes", "-"),
        ("race_pace_pct_net", "lower=faster race pace", "-"),
        ("traffic_penalty_net", "lower=better in traffic", "-"),
        ("ontrack_gain_net", "higher=more passes [semi-outcome]", "+"),
    ]
    for col, desc, want in rows:
        r, n = _corr(sig[col], sig["pgae_net"])
        print(f"  {col:22s} r={r:+.3f}  n={n:4d}   ({want}) {desc}")

    # Per-DRIVER: aggregate netted signatures, correlate with the racecraft rating.
    from .racecraft import racecraft_ratings
    rc = racecraft_ratings().filter(pl.col("n") >= 15)
    agg = sig.group_by("driver").agg(
        pl.col("deg_slope_net").mean(),
        pl.col("consistency_net").mean(),
        pl.col("race_pace_pct_net").mean(),
        pl.col("traffic_penalty_net").mean(),
        pl.col("ontrack_gain_net").mean(),
        pl.len().alias("nr"),
    ).filter(pl.col("nr") >= 15)
    agg = agg.join(rc.select(["driver", "racecraft"]), on="driver", how="inner")
    print(f"\nPer-DRIVER (n>=15 races, {agg.height} drivers), netted signature vs racecraft rating:")
    for col, desc, want in rows:
        r, n = _corr(agg[col], agg["racecraft"])
        print(f"  {col:22s} r={r:+.3f}  n={n:4d}   ({want}) {desc}")


if __name__ == "__main__":
    report()
