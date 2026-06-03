"""Per-car tyre degradation from its OWN stint slopes — measured, not a team label (task #11).

The sim used to scale deg by a season-long per-team `deg_multiplier` (0.6-1.6) — a generic
"Team X is good on tyres" claim, and the source of the double-count bug. The principled version:
measure each car's deg from the slope of its own fuel-corrected lap time vs tyre age, within each
stint, traceable to specific stints, and express it as EXCESS over the compound's expected deg
(so soft-vs-hard is netted out). A per-(year, circuit, driver) excess-deg in s/lap/lap.

HONEST GATE first: is per-car deg a reproducible property or just stint noise? We forward-chain a
per-team EWMA of excess-deg and test whether it predicts the team's NEXT race's excess-deg. If the
autocorrelation is weak, per-car deg isn't reliably separable on free data (consistent with brief
08A: per-lap residuals are swamped by ~2.9s traffic noise) -> keep the per-compound curve, note v2.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import spearmanr

from app.engine import calibration_store as store
from app.engine.physics import fuel_penalty
from app.engine.params import Compound
from app.engine.tyres import degradation_penalty, seed_for

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
CAR_DEG_PARQUET = DATA_DIR / "tyre_deg_car.parquet"

DRY = ("SOFT", "MEDIUM", "HARD")
WARMUP_LAPS = 2        # ignore the first laps of a stint (out-lap, warm-up)
MIN_STINT = 8          # laps needed to fit a slope
MIN_AGE_PTS = 5        # distinct tyre ages needed


def _tp(circuit: str, comp: Compound):
    return store.tyre_overrides_for(circuit).get(comp) or seed_for(comp)


def _expected_slope(circuit: str, comp: Compound, ages: np.ndarray) -> float:
    """The compound's expected deg slope (s/lap/lap) over this stint's age range."""
    tp = _tp(circuit, comp)
    d = np.asarray(degradation_penalty(ages, tp), dtype=float)
    if len(ages) < 2 or np.ptp(ages) < 1e-6:
        return 0.0
    return float(np.polyfit(ages, d, 1)[0])


def build_car_deg(*, force: bool = False) -> pl.DataFrame:
    """Per (year, circuit, driver): EXCESS deg (s/lap/lap) over the compound expectation."""
    if CAR_DEG_PARQUET.exists() and not force:
        return pl.read_parquet(CAR_DEG_PARQUET)

    from .features import _race_seq

    laps = pl.read_parquet(LAPS_PARQUET).filter(
        (pl.col("session_name") == "R")
        & (pl.col("track_status").cast(pl.Utf8) == "1")
        & pl.col("is_accurate") & ~pl.col("is_pit_out") & ~pl.col("is_pit_in")
        & pl.col("lap_time_s").is_not_null() & pl.col("compound").is_in(DRY)
        & pl.col("tyre_life").is_not_null()
    )
    seq = _race_seq()
    rows: list[dict] = []
    for key, race in laps.group_by(["year", "circuit"]):
        year, circuit = int(key[0]), str(key[1])
        cp = store.circuit_params_for(circuit)
        for (driver,), dl in race.group_by(["driver"]):
            excesses, weights = [], []
            for (_stint,), st in dl.group_by(["stint"]):
                st = st.filter(pl.col("tyre_life") >= WARMUP_LAPS)
                if st.height < MIN_STINT:
                    continue
                ages = st["tyre_life"].to_numpy().astype(float)
                if len(np.unique(ages)) < MIN_AGE_PTS:
                    continue
                lapn = st["lap_number"].to_numpy().astype(float)
                corrected = st["lap_time_s"].to_numpy().astype(float) - np.asarray(
                    fuel_penalty(lapn, cp.fuel), dtype=float)
                if not np.all(np.isfinite(corrected)):
                    m = np.isfinite(corrected)
                    ages, corrected = ages[m], corrected[m]
                    if len(ages) < MIN_STINT:
                        continue
                slope = float(np.polyfit(ages, corrected, 1)[0])          # measured deg s/lap/lap
                comp = Compound(st["compound"][0])
                excess = slope - _expected_slope(circuit, comp, ages)     # vs compound expectation
                # robustness: stint-relative slopes can be wild; clip absurd values
                if abs(excess) > 0.5:
                    continue
                excesses.append(excess); weights.append(st.height)
            if excesses:
                w = np.array(weights, dtype=float)
                rows.append({
                    "year": year, "circuit": circuit, "driver": driver,
                    "team": dl["team"].drop_nulls().to_list()[-1] if dl["team"].drop_nulls().len() else "",
                    "excess_deg_s_per_lap2": round(float(np.average(excesses, weights=w)), 4),
                    "n_stints": len(excesses), "seq": seq.get((year, circuit), 9999),
                })
    out = pl.DataFrame(rows).sort("seq")
    out.write_parquet(CAR_DEG_PARQUET)
    return out


def stability_gate(alpha: float = 0.4) -> dict:
    """Forward-chained: does a team's prior EWMA excess-deg predict its NEXT race's excess-deg?"""
    t = build_car_deg().sort("seq")
    belief: dict[str, float] = {}
    pairs = []  # (prior_belief, actual)
    for r in t.to_dicts():
        team = r["team"]; v = r["excess_deg_s_per_lap2"]
        if team in belief:
            pairs.append((belief[team], v))
        belief[team] = v if team not in belief else alpha * v + (1 - alpha) * belief[team]
    if len(pairs) < 30:
        return {"n": len(pairs), "spearman": None}
    a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
    return {
        "n": len(pairs),
        "spearman_prior_vs_next": round(float(spearmanr(a, b).correlation), 3),
        "field_sd_s_per_lap2": round(float(t["excess_deg_s_per_lap2"].std()), 4),
    }


if __name__ == "__main__":
    t = build_car_deg(force=True)
    print(f"per-car deg: {t.height} car-races over {t['seq'].n_unique()} races")
    g = stability_gate()
    print(f"\nSTABILITY GATE (is per-car deg reproducible, or stint noise?):")
    print(f"  prior-EWMA vs next-race excess-deg Spearman: {g.get('spearman_prior_vs_next')}  (n={g['n']})")
    print(f"  field spread of excess-deg: {g.get('field_sd_s_per_lap2')} s/lap/lap")
    # face validity: most-/least-degrading cars in the latest season
    yr = int(t["year"].max())
    agg = (t.filter(pl.col("year") == yr).group_by("team")
           .agg(pl.col("excess_deg_s_per_lap2").mean().round(4).alias("excess"), pl.len())
           .sort("excess"))
    print(f"\n{yr} team mean excess-deg (lower = gentler than the compound expectation):")
    for r in agg.to_dicts():
        print(f"  {r['team']:18s} {r['excess']:+.4f}  (n={r['len']})")
