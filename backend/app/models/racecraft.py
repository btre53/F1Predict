"""Positions-gained-above-expectation (PGAE) + a car-netted 'racecraft' rating.

The F1 analog of golf strokes-gained / football xG: baseline each driver-race against
the expected finish for its grid slot, so the dominant grid signal is removed and the
residual is race-day performance (overtaking, race pace, strategy, tyre management).

    PGAE = E[finish | grid] - finish          (+ve = beat the grid)
    racecraft(driver) = shrink( mean over races of (PGAE - team's PGAE that race) )

This is an eval/analytics lens, not a new prediction target (predicting PGAE with a
grid-aware model is a reparameterization, per docs/science strokes-gained research).
Its value is interpretability + a defensible "good drive" signal.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from .features import build_feature_table


def expected_finish_by_grid(table: pl.DataFrame) -> dict[int, float]:
    """Empirical E[finish | grid], monotone-smoothed. DNFs sit at the back already
    (finish_pos ranks them last), so attrition opportunity is baked into the curve."""
    g = (
        table.filter(pl.col("grid").is_not_null())
        .group_by("grid")
        .agg(pl.col("finish_pos").mean().alias("exp"))
        .sort("grid")
    )
    grids = g["grid"].to_list()
    exps = g["exp"].to_list()
    # Isotonic (monotone non-decreasing) smoothing via pool-adjacent-violators.
    iso = _pava(np.array(exps, dtype=float))
    return {int(gr): float(e) for gr, e in zip(grids, iso)}


def _pava(y: np.ndarray) -> np.ndarray:
    """Pool-adjacent-violators: nearest monotone-increasing fit (least squares)."""
    y = y.copy()
    w = np.ones_like(y)
    i = 0
    while i < len(y) - 1:
        if y[i] > y[i + 1]:
            new = (w[i] * y[i] + w[i + 1] * y[i + 1]) / (w[i] + w[i + 1])
            y[i] = new
            w[i] += w[i + 1]
            y = np.delete(y, i + 1)
            w = np.delete(w, i + 1)
            i = max(i - 1, 0)
        else:
            i += 1
    # Re-expand to original length.
    out, idx = [], 0
    counts = w.astype(int)
    for val, c in zip(y, counts):
        out.extend([val] * c)
    return np.array(out[: len(out)])


def compute_pgae(table: pl.DataFrame) -> pl.DataFrame:
    base = expected_finish_by_grid(table)
    default = float(np.mean(list(base.values())))
    return table.with_columns(
        pl.col("grid")
        .map_elements(lambda g: base.get(int(g), default) if g is not None else default,
                      return_dtype=pl.Float64)
        .alias("exp_finish")
    ).with_columns((pl.col("exp_finish") - pl.col("finish_pos")).alias("pgae"))


def racecraft_ratings(table: pl.DataFrame | None = None, *, prior_races: int = 6) -> pl.DataFrame:
    """Per-driver racecraft = car-netted mean PGAE, empirical-Bayes shrunk to 0."""
    t = compute_pgae(table if table is not None else build_feature_table())
    # Net out the car: subtract the team's mean PGAE in each race (teammate-shared).
    team_race = t.group_by(["seq", "team"]).agg(pl.col("pgae").mean().alias("team_pgae"))
    t = t.join(team_race, on=["seq", "team"]).with_columns(
        (pl.col("pgae") - pl.col("team_pgae")).alias("driver_pgae")
    )
    agg = t.group_by("driver").agg(
        pl.col("driver_pgae").mean().alias("raw"),
        pl.len().alias("n"),
    )
    # Shrink toward 0 by sample size (drivers with few races -> near 0).
    return agg.with_columns(
        (pl.col("raw") * pl.col("n") / (pl.col("n") + prior_races)).alias("racecraft")
    ).sort("racecraft", descending=True).select(["driver", "racecraft", "raw", "n"])


if __name__ == "__main__":
    r = racecraft_ratings()
    print("Racecraft (car-netted positions-gained-above-expectation), top & bottom:")
    rows = r.filter(pl.col("n") >= 15).to_dicts()
    for d in rows[:8]:
        print(f"  +{d['racecraft']:+.2f}  {d['driver']}  (n={d['n']})")
    print("  ...")
    for d in rows[-5:]:
        print(f"  {d['racecraft']:+.2f}  {d['driver']}  (n={d['n']})")
