"""Calibrate per-circuit parameters from the ingested Parquet archive.

Produces, per (circuit, era):
  * base_lap_ms      — fastest fuel-corrected clean lap (dry, light-fuel reference)
  * total_laps       — race distance
  * fuel burn/lap    — start_fuel / total_laps (circuit-specific approximation)
  * tyre theta params per compound — three-phase curve fit to fuel-corrected,
    stint-relative degradation residuals (docs/science/01 section 3).

Output: data/calibration.json (consumed by app.engine.calibration_store).

Fuel correction and the stint-relative baseline isolate tyre degradation from the
two big confounders (fuel burn making the car faster, driver/car pace offsets).
See docs/science/01 sections 2-3.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from app.engine.params import FUEL_BY_ERA, RegulationEra
from app.engine.tyres import fit_tyre_parameters

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
CALIBRATION_JSON = DATA_DIR / "calibration.json"
DRIVERS_JSON = DATA_DIR / "drivers.json"
TEAM_TYRES_JSON = DATA_DIR / "team_tyres.json"

DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")
MIN_STINT_LAPS = 6          # need enough laps to see a degradation profile
MIN_LAPS_PER_COMPOUND = 25  # pooled across drivers/stints to fit 6 params


def _clean_race_laps(df: pl.DataFrame) -> pl.DataFrame:
    """Green-flag, accurate, non-pit racing laps (track_status '1' == all green)."""
    return df.filter(
        (pl.col("session_name") == "R")
        & (pl.col("track_status") == "1")
        & pl.col("is_accurate")
        & ~pl.col("is_pit_out")
        & ~pl.col("is_pit_in")
        & pl.col("lap_time_s").is_not_null()
        & pl.col("compound").is_in(DRY_COMPOUNDS)
    )


def _fuel_correct(df: pl.DataFrame, era: RegulationEra, total_laps: int) -> pl.DataFrame:
    """Add fuel-corrected lap time = raw - k_fuel * fuel_mass(lap)."""
    fm = FUEL_BY_ERA[era]
    burn = fm.start_fuel_kg / max(1, total_laps)  # circuit-specific avg burn
    return df.with_columns(
        (
            pl.col("lap_time_s")
            - fm.k_fuel_s_per_kg
            * (fm.start_fuel_kg - burn * (pl.col("lap_number") - 1)).clip(0.0, None)
        ).alias("fuel_corrected_s")
    )


def calibrate_circuit(df_circuit: pl.DataFrame) -> dict:
    """Calibrate one circuit (single era assumed within the group)."""
    era = RegulationEra(df_circuit["regulation_era"][0])
    total_laps = int(df_circuit["lap_number"].max())

    clean = _clean_race_laps(df_circuit)
    clean = _fuel_correct(clean, era, total_laps)

    # Base lap = fastest fuel-corrected clean lap (light-fuel dry reference).
    base_lap_s = float(clean["fuel_corrected_s"].min()) if clean.height else None

    # Per-stint degradation residuals: lap's fuel-corrected time minus the stint's
    # fastest fuel-corrected lap (removes per-driver/car pace offset).
    stint_min = clean.group_by(["driver", "stint"]).agg(
        pl.col("fuel_corrected_s").min().alias("stint_base"),
        pl.len().alias("stint_len"),
    )
    clean = clean.join(stint_min, on=["driver", "stint"]).filter(
        pl.col("stint_len") >= MIN_STINT_LAPS
    )
    clean = clean.with_columns(
        (pl.col("fuel_corrected_s") - pl.col("stint_base")).alias("deg_residual")
    )

    tyres: dict[str, dict] = {}
    for comp in DRY_COMPOUNDS:
        sub = clean.filter(pl.col("compound") == comp)
        if sub.height < MIN_LAPS_PER_COMPOUND:
            continue
        ages = sub["tyre_life"].to_numpy().astype(float)
        resid = sub["deg_residual"].to_numpy().astype(float)
        tp = fit_tyre_parameters(ages, resid)
        # Guard: a noisy/sparse fit (common on one-off or low-data circuits) can produce
        # degradation that DIPS after warm-up — physically wrong and bad for the optimizer.
        # Fall back to the generic seed curve for that compound when the fit isn't monotone.
        from app.engine.params import Compound
        from app.engine.tyres import degradation_penalty, seed_for

        curve = degradation_penalty(np.arange(5, 25), tp)
        if not np.all(np.diff(curve) > -1e-6):
            tp = seed_for(Compound(comp))
        tyres[comp] = {
            "theta1": tp.theta1, "theta2": tp.theta2, "theta3": tp.theta3,
            "theta4": tp.theta4, "theta5": tp.theta5, "theta6": tp.theta6,
            "n_laps": int(sub.height),
        }

    return {
        "era": era.value,
        "base_lap_ms": int(base_lap_s * 1000) if base_lap_s else None,
        "total_laps": total_laps,
        "clean_laps": int(clean.height),
        "tyres": tyres,
    }


def calibrate_drivers(df: pl.DataFrame) -> list[dict]:
    """Per-driver pace offset (s) vs the field, pooled across circuits.

    For each circuit we take each driver's 20th-percentile fuel-corrected lap (a
    robust 'true pace' estimate that discards traffic/degraded laps), reference it
    to the field median, then average each driver's deltas across circuits. This
    blends driver + car performance — i.e. the real competitive order.
    """
    rows: list[dict] = []
    for circuit in df["circuit"].unique().to_list():
        sub = df.filter(pl.col("circuit") == circuit)
        era = RegulationEra(sub["regulation_era"][0])
        total_laps = int(sub["lap_number"].max())
        clean = _fuel_correct(_clean_race_laps(sub), era, total_laps)
        if clean.height == 0:
            continue
        pace = clean.group_by(["driver", "driver_number", "team"]).agg(
            pl.col("fuel_corrected_s").quantile(0.2).alias("pace_s"),
            pl.len().alias("n"),
        ).filter(pl.col("n") >= 10)
        if pace.height == 0:
            continue
        field_ref = float(pace["pace_s"].median())
        rows.append(
            pace.with_columns(
                (pl.col("pace_s") - field_ref).alias("delta_s"),
                pl.lit(circuit).alias("circuit"),
            )
        )
    if not rows:
        return []
    allp = pl.concat(rows, how="vertical_relaxed")
    agg = (
        allp.group_by(["driver"])
        .agg(
            pl.col("delta_s").mean().alias("pace_offset_s"),
            pl.col("driver_number").last(),
            pl.col("team").last(),
            pl.col("n").sum().alias("n_laps"),
        )
        .sort("pace_offset_s")
    )
    return [
        {
            "driver": r["driver"],
            "driver_number": int(r["driver_number"]) if r["driver_number"] else None,
            "team": r["team"],
            "pace_offset_s": round(float(r["pace_offset_s"]), 3),
            "n_laps": int(r["n_laps"]),
        }
        for r in agg.to_dicts()
    ]


def _deg_residuals(df: pl.DataFrame) -> pl.DataFrame:
    """Per-lap, stint-relative, fuel-corrected degradation residuals (all circuits).

    Returns columns: team, tyre_life, deg_residual — comparable across circuits
    (each is a lap's loss vs. its own stint's best fuel-corrected lap).
    """
    frames: list[pl.DataFrame] = []
    for circuit in df["circuit"].unique().to_list():
        sub = df.filter(pl.col("circuit") == circuit)
        era = RegulationEra(sub["regulation_era"][0])
        total_laps = int(sub["lap_number"].max())
        clean = _fuel_correct(_clean_race_laps(sub), era, total_laps)
        if clean.height == 0:
            continue
        stint_min = clean.group_by(["driver", "stint"]).agg(
            pl.col("fuel_corrected_s").min().alias("base"),
            pl.len().alias("slen"),
        )
        clean = clean.join(stint_min, on=["driver", "stint"]).filter(
            pl.col("slen") >= MIN_STINT_LAPS
        )
        frames.append(
            clean.with_columns(
                (pl.col("fuel_corrected_s") - pl.col("base")).alias("deg_residual")
            ).select(["team", "tyre_life", "deg_residual"])
        )
    return pl.concat(frames, how="vertical_relaxed") if frames else pl.DataFrame()


def calibrate_team_tyres(df: pl.DataFrame) -> dict:
    """Per-team tyre-management multiplier on the linear degradation rate.

    Hierarchical idea: keep the generalized circuit×compound curve, but scale its
    wear rate (theta_3) per team. A multiplier > 1 means the team degrades tyres
    faster than the field; < 1 means gentler. Fit a linear slope of degradation vs.
    tyre age per team and divide by the field slope.
    """
    res = _deg_residuals(df)
    if res.height == 0:
        return {}

    def _slope(sub: pl.DataFrame) -> float | None:
        a = sub["tyre_life"].to_numpy().astype(float)
        y = sub["deg_residual"].to_numpy().astype(float)
        # Drop non-finite rows — new teams/circuits can yield NaN/inf residuals, which
        # make polyfit's SVD diverge (the crash that aborted the post-ingest recalibrate).
        m = np.isfinite(a) & np.isfinite(y)
        a, y = a[m], y[m]
        if a.size < 40 or a.std() < 1e-6:
            return None
        try:
            return float(np.polyfit(a, y, 1)[0])
        except np.linalg.LinAlgError:
            return None

    field_slope = _slope(res) or 0.05
    out: dict = {}
    for team in res["team"].unique().to_list():
        if not team:
            continue
        s = _slope(res.filter(pl.col("team") == team))
        if s is None:
            continue
        mult = float(np.clip(s / field_slope, 0.6, 1.6))
        out[team] = {
            "deg_multiplier": round(mult, 3),
            "wear_rate_s_per_lap": round(s, 4),
            "n_laps": int(res.filter(pl.col("team") == team).height),
        }
    return {
        "field_wear_rate_s_per_lap": round(field_slope, 4),
        "teams": dict(sorted(out.items(), key=lambda kv: kv[1]["deg_multiplier"])),
    }


def run() -> Path:
    if not LAPS_PARQUET.exists():
        raise FileNotFoundError(f"Run the ingest first: {LAPS_PARQUET} not found")
    df = pl.read_parquet(LAPS_PARQUET)

    team_tyres = calibrate_team_tyres(df)
    TEAM_TYRES_JSON.write_text(json.dumps(team_tyres, indent=2))
    print("Team tyre management (deg multiplier vs field):")
    for t, v in list(team_tyres.get("teams", {}).items()):
        print(f"  {t:24s} x{v['deg_multiplier']:.2f}  (n={v['n_laps']})")
    print(f"  -> wrote {TEAM_TYRES_JSON}\n")

    drivers = calibrate_drivers(df)
    DRIVERS_JSON.write_text(json.dumps(drivers, indent=2))
    print("Driver pace order (pooled, vs field median):")
    for d in drivers[:8]:
        print(f"  {d['driver']:4s} {d['team']:24s} {d['pace_offset_s']:+.3f}s")
    print(f"  ... wrote {len(drivers)} drivers -> {DRIVERS_JSON}\n")

    out: dict[str, dict] = {}
    for circuit in sorted(df["circuit"].unique().to_list()):
        sub = df.filter(pl.col("circuit") == circuit)
        cal = calibrate_circuit(sub)
        out[circuit] = cal
        comps = ", ".join(
            f"{c}(n={v['n_laps']})" for c, v in cal["tyres"].items()
        ) or "none"
        base = f"{cal['base_lap_ms'] / 1000:.2f}s" if cal["base_lap_ms"] else "n/a"
        print(
            f"{circuit:16s} base={base} laps={cal['total_laps']} "
            f"clean={cal['clean_laps']:4d}  tyres: {comps}"
        )

    CALIBRATION_JSON.write_text(json.dumps(out, indent=2))
    print(f"\nWrote calibration for {len(out)} circuits -> {CALIBRATION_JSON}")
    return CALIBRATION_JSON


if __name__ == "__main__":
    run()
