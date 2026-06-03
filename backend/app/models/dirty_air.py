"""Measured dirty-air penalty curve — per circuit, from OpenF1 gaps + lap times (brief 24).

NOT a flat linear loss (owner's spec). Dirty air is:
  * non-linear in gap — worse the closer you are (aero wash grows as you approach);
  * track-dependent — it HURTS most where grip is aero-dependent (high-speed corners) and
    HELPS on straight-heavy tracks (slipstream tow can outweigh the corner loss → net GAIN),
    and hurts least on low-speed/mechanical-grip tracks.

So we MEASURE it per circuit and let the sign/shape fall out of the data. For each 2023+ race
lap we know the real gap-to-car-ahead (OpenF1, `clean_air_pace`/`openf1`) and the car's clean-air
baseline pace; the fuel- and tyre-age-corrected lap-time EXCESS over that baseline, binned by
gap, is the dirty-air penalty curve (can be negative = slipstream). Then we check the per-circuit
penalty against absolute track speed to confirm the physics (faster tracks → more slipstream /
the aero effect). Writes data/dirty_air.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from app.engine import calibration_store as store
from app.engine.physics import fuel_penalty
from app.engine.tyres import degradation_penalty, seed_for
from app.engine.params import Compound

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
CLEAN_AIR_PARQUET = DATA_DIR / "clean_air_pace.parquet"
OPENF1_CLEAN_PARQUET = DATA_DIR / "openf1_clean_laps.parquet"
DIRTY_AIR_JSON = DATA_DIR / "dirty_air.json"

DRY = ("SOFT", "MEDIUM", "HARD")
# Gap bins (s): closest first. The curve is the mean lap-time excess in each bin.
GAP_EDGES = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
GAP_LABELS = ["0-0.5", "0.5-1", "1-1.5", "1.5-2", "2-3", "3-4"]
MIN_LAPS_PER_BIN = 8       # per-circuit bin needs this many laps to be reported
MIN_LAPS_PER_CIRCUIT = 60  # total in-traffic laps for a per-circuit curve


def _tp(circuit: str, comp: Compound):
    return store.tyre_overrides_for(circuit).get(comp) or seed_for(comp)


def _corrected_laps() -> pl.DataFrame:
    """Per (year, circuit, driver, lap): fuel+tyre-corrected lap time, for 2023+ R laps."""
    laps = pl.read_parquet(LAPS_PARQUET).filter(
        (pl.col("session_name") == "R") & (pl.col("year") >= 2023)
        & (pl.col("track_status").cast(pl.Utf8) == "1")
        & pl.col("is_accurate") & ~pl.col("is_pit_out") & ~pl.col("is_pit_in")
        & pl.col("lap_time_s").is_not_null() & pl.col("compound").is_in(DRY)
    )
    out: list[pl.DataFrame] = []
    for (year, circuit), race in laps.group_by(["year", "circuit"]):
        year, circuit = int(year), str(circuit)
        cp = store.circuit_params_for(circuit)
        for comp in DRY:
            c = race.filter(pl.col("compound") == comp)
            if c.height == 0:
                continue
            tp = _tp(circuit, comp)
            ages = c["tyre_life"].to_numpy().astype(float)
            lapn = c["lap_number"].to_numpy().astype(float)
            corrected = (c["lap_time_s"].to_numpy().astype(float)
                         - np.asarray(degradation_penalty(ages, tp), dtype=float)
                         - np.asarray(fuel_penalty(lapn, cp.fuel), dtype=float))
            out.append(c.select(["year", "circuit", "driver", "lap_number"])
                       .with_columns(pl.Series("corrected", corrected)))
    return pl.concat(out).filter(pl.col("corrected").is_finite())


def _top_speed() -> dict[str, float]:
    """Per-circuit straight-line speed proxy: 95th-pct speed-trap (absolute, all circuits)."""
    s = pl.read_parquet(LAPS_PARQUET, columns=["circuit", "session_name", "speed_st"]).filter(
        (pl.col("session_name") == "R") & pl.col("speed_st").is_not_null()
    )
    g = s.group_by("circuit").agg(pl.col("speed_st").quantile(0.95).alias("v"))
    return {r["circuit"]: float(r["v"]) for r in g.to_dicts() if r["v"] is not None}


def _dirty_air_df() -> pl.DataFrame:
    """Per following-lap: corrected lap-time EXCESS over the car's clean-air baseline, the gap to
    the car ahead, the gap bin, and the car's own clean-air pace gap (a strength proxy: lower=faster)."""
    corrected = _corrected_laps()
    baseline = pl.read_parquet(CLEAN_AIR_PARQUET).select(
        ["year", "circuit", "driver", "clean_air_pace_s", "clean_air_gap_pct"]
    )
    gaps = pl.read_parquet(OPENF1_CLEAN_PARQUET).select(
        ["year", "circuit", "driver", "lap_number", "gap_ahead_s"]
    )
    return (
        corrected.join(baseline, on=["year", "circuit", "driver"], how="inner")
        .join(gaps, on=["year", "circuit", "driver", "lap_number"], how="inner")
        .with_columns((pl.col("corrected") - pl.col("clean_air_pace_s")).alias("excess"))
        .filter((pl.col("gap_ahead_s") > 0.0) & (pl.col("gap_ahead_s") <= GAP_EDGES[-1]))
        .with_columns(pl.col("gap_ahead_s").cut(GAP_EDGES[1:-1], labels=GAP_LABELS).alias("bin"))
    )


def strength_dependent_dirty_air() -> dict:
    """Does a STRONGER car lose less time stuck in traffic? (task #23, the win/podium-gap fix.)

    Split the following-lap penalty by the FOLLOWING car's strength (its own clean-air pace gap to
    the race's fastest: STRONG <0.5%, MID 0.5-1.5%, SLOW >1.5%) and report the close-gap (<1s)
    penalty per bucket. If stronger cars lose less, the sim's uniform dirty-air over-penalises the
    front -> scale the wake penalty by strength. Honest caveat: "following" mixes pure aero wake
    with being-held-up by a slower car; we report the combined in-traffic penalty (which is what
    the sim's track-position term needs) and flag the confound.
    """
    df = _dirty_air_df().with_columns(
        pl.when(pl.col("clean_air_gap_pct") < 0.005).then(pl.lit("strong"))
        .when(pl.col("clean_air_gap_pct") < 0.015).then(pl.lit("mid"))
        .otherwise(pl.lit("slow")).alias("strength")
    )
    out: dict[str, dict] = {}
    for bucket in ("strong", "mid", "slow"):
        sub = df.filter(pl.col("strength") == bucket)
        close = sub.filter(pl.col("gap_ahead_s") <= 1.0)
        out[bucket] = {
            "close_gap_penalty_s": round(float(close["excess"].median()), 3) if close.height else None,
            "n_close": close.height,
            "by_gap": {lab: round(float(sub.filter(pl.col("bin") == lab)["excess"].median()), 3)
                       for lab in GAP_LABELS
                       if sub.filter(pl.col("bin") == lab).height >= MIN_LAPS_PER_BIN},
        }
    return out


def build_dirty_air(*, force: bool = False) -> dict:
    if DIRTY_AIR_JSON.exists() and not force:
        return json.loads(DIRTY_AIR_JSON.read_text())

    df = _dirty_air_df()

    def curve(sub: pl.DataFrame) -> dict:
        out = {}
        for lab in GAP_LABELS:
            b = sub.filter(pl.col("bin") == lab)
            if b.height >= MIN_LAPS_PER_BIN:
                out[lab] = {"penalty_s": round(float(b["excess"].median()), 3), "n": b.height}
        return out

    overall = curve(df)
    per_circuit: dict[str, dict] = {}
    for (circuit,), sub in df.group_by(["circuit"]):
        if sub.height >= MIN_LAPS_PER_CIRCUIT:
            per_circuit[str(circuit)] = curve(sub)

    # Physics check: per-circuit close-gap penalty (<1s) vs absolute straight-line speed.
    vmax = _top_speed()
    close = []
    for circ, cv in per_circuit.items():
        near = [cv[k]["penalty_s"] for k in ("0-0.5", "0.5-1") if k in cv]
        if near and circ in vmax:
            close.append({"circuit": circ, "close_penalty_s": round(float(np.mean(near)), 3),
                          "top_speed_kmh": round(vmax[circ], 1)})
    close.sort(key=lambda r: r["close_penalty_s"])
    corr = None
    if len(close) >= 6:
        a = np.array([c["close_penalty_s"] for c in close])
        v = np.array([c["top_speed_kmh"] for c in close])
        corr = round(float(np.corrcoef(a, v)[0, 1]), 3)

    result = {
        "gap_labels": GAP_LABELS,
        "overall": overall,
        "per_circuit": per_circuit,
        "close_gap_penalty_vs_top_speed": {
            "rows": close,
            "corr_penalty_topspeed": corr,
            "note": "negative penalty = net slipstream gain; faster tracks should show "
                    "smaller/negative close-gap penalty (more tow) -> expect corr < 0",
        },
    }
    DIRTY_AIR_JSON.write_text(json.dumps(result, indent=2))
    return result


def penalty_curve(circuit: str | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(gap_midpoints, penalty_s) for a circuit, falling back to the overall curve.

    Used by the sim's dirty-air model: interpolate penalty at any gap (penalty can be negative
    = slipstream). Returns empty arrays if the artifact isn't built."""
    if not DIRTY_AIR_JSON.exists():
        return np.array([]), np.array([])
    d = json.loads(DIRTY_AIR_JSON.read_text())
    cv = d.get("per_circuit", {}).get(circuit) if circuit else None
    if not cv or len(cv) < 3:
        cv = d.get("overall", {})
    mids = {"0-0.5": 0.25, "0.5-1": 0.75, "1-1.5": 1.25, "1.5-2": 1.75, "2-3": 2.5, "3-4": 3.5}
    pts = sorted((mids[k], v["penalty_s"]) for k, v in cv.items() if k in mids)
    if not pts:
        return np.array([]), np.array([])
    return np.array([p[0] for p in pts]), np.array([p[1] for p in pts])


if __name__ == "__main__":
    r = build_dirty_air(force=True)
    print("Dirty-air penalty curve (median lap-time excess vs gap-to-car-ahead)\n")
    print("OVERALL (s, +=loss, -=slipstream gain):")
    for k in r["gap_labels"]:
        if k in r["overall"]:
            print(f"  gap {k:>6}s : {r['overall'][k]['penalty_s']:+.3f}  (n={r['overall'][k]['n']})")
    cz = r["close_gap_penalty_vs_top_speed"]
    print(f"\nPer-circuit close-gap (<1s) penalty vs top speed  (corr={cz['corr_penalty_topspeed']}):")
    for c in cz["rows"]:
        print(f"  {c['circuit'][:16]:16s} {c['close_penalty_s']:+.3f}s   vmax {c['top_speed_kmh']:.0f} km/h")
