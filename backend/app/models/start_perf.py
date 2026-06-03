"""Start performance per driver = official grid − lap-1 position (task #22).

Now that we have BOTH the official starting grid (Jolpica) and the lap-1 timing-line position, the
difference IS the start/first-lap component the lap-1-as-grid proxy used to hide: places gained
(or lost) off the line + through T1. Positive = gained places.

HONEST GATE: is start performance a reproducible DRIVER skill, or race-day noise? We forward-chain
a per-driver EWMA and test whether it predicts the driver's NEXT race start. If weak, it's mostly
noise (chaos, grid side, clutch) and shouldn't be a per-driver term — keep it as variance only.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import spearmanr

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"


def start_deltas() -> pl.DataFrame:
    """Per (year, circuit, driver): official_grid − lap1_position (positive = gained places)."""
    from app.etl.jolpica import official_grid_map
    from app.models.features import _race_seq

    gm = official_grid_map()
    lap1 = (
        pl.read_parquet(LAPS_PARQUET, columns=["year", "circuit", "driver", "session_name",
                                               "lap_number", "position"])
        .filter((pl.col("session_name") == "R") & (pl.col("lap_number") == 1)
                & pl.col("position").is_not_null())
        .select(["year", "circuit", "driver", pl.col("position").alias("lap1")])
    )
    seq = _race_seq()
    rows = []
    for r in lap1.to_dicts():
        g = gm.get((int(r["year"]), r["circuit"], r["driver"]))
        if g is None:
            continue
        rows.append({
            "year": int(r["year"]), "circuit": r["circuit"], "driver": r["driver"],
            "start_delta": float(g - r["lap1"]),   # +ve = gained places off the line / T1
            "seq": seq.get((int(r["year"]), r["circuit"]), 9999),
        })
    return pl.DataFrame(rows).sort("seq")


def stability_gate(alpha: float = 0.35) -> dict:
    """Forward-chained: does a driver's prior-EWMA start_delta predict the next race's?"""
    t = start_deltas()
    belief: dict[str, float] = {}
    pairs = []
    for r in t.to_dicts():
        d = r["driver"]; v = r["start_delta"]
        if d in belief:
            pairs.append((belief[d], v))
        belief[d] = v if d not in belief else alpha * v + (1 - alpha) * belief[d]
    if len(pairs) < 50:
        return {"n": len(pairs), "spearman": None}
    a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
    return {
        "n": len(pairs),
        "spearman_prior_vs_next": round(float(spearmanr(a, b).correlation), 3),
        "field_sd_places": round(float(t["start_delta"].std()), 3),
    }


if __name__ == "__main__":
    t = start_deltas()
    g = stability_gate()
    print(f"start performance: {t.height} car-races\n")
    print(f"STABILITY GATE (reproducible driver skill, or noise?):")
    print(f"  prior-EWMA vs next-race start_delta Spearman: {g.get('spearman_prior_vs_next')} (n={g['n']})")
    print(f"  field spread: {g.get('field_sd_places')} places")
    best = (t.group_by("driver").agg(pl.col("start_delta").mean().round(2).alias("avg"), pl.len())
            .filter(pl.col("len") >= 20).sort("avg", descending=True))
    print("\nbest average starters (>=20 races):")
    for r in best.head(6).to_dicts():
        print(f"  {r['driver']:4s} {r['avg']:+.2f} places  (n={r['len']})")
    print("worst:")
    for r in best.tail(4).to_dicts():
        print(f"  {r['driver']:4s} {r['avg']:+.2f} places  (n={r['len']})")
