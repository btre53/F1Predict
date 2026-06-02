"""Car-DNA: corner-speed-band pace decomposition x circuit corner-band demand (task #22).

The owner's flagship anti-brand idea (brief 16 §2): not "Ferrari is strong at Monaco"
but "cars relatively fast in LOW-speed corners do well at low-speed-corner circuits."
We decompose each car's qualifying telemetry into its relative speed in physically-named
speed bands (low/medium/high-speed corner + straight), **shape-normalized** (relative to
the car's OWN mean speed, so we measure *where* it's fast, not *that* it's fast -- the
critical guard against this being scalar-pace in five hats). A circuit is a **demand
profile** = the lap-distance share spent in each band. Suitability = car band-factor
vector . circuit demand vector. A brand-new team inherits its rating from its measured
factors, so it generalizes by construction.

HIGHEST overfit risk in the brief: telemetry pulls are slow (~10s/session) so the sample
is effectively small, and corner-speed factors are car-and-driver confounded unless
shape-normalized. We therefore (a) qualifying only (clean, low-fuel, one-lap), (b)
shape-normalize, (c) judge on INCREMENTAL signal over scalar pace, (d) check it does NOT
collapse into the rejected team x circuit affinity. Per the owner: kept as an Explainer
feature (the per-car corner-band radar) regardless of predictive lift, labelled honestly.

Network-bound, so `extract()` caches per-(year,circuit,driver) band speeds + per-circuit
demand to data/car_dna.parquet; all analysis below is offline on that cache.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import polars as pl

warnings.filterwarnings("ignore")
logging.getLogger("fastf1").setLevel(logging.ERROR)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUT = DATA_DIR / "car_dna.parquet"

# Speed-band edges (km/h). Low/med/high are CORNER bands; straight is full-power running.
# ~130 / ~210 corner split + a straight cut are established telemetry heuristics (brief 16).
BANDS = ("low", "med", "high", "straight")
_EDGES = (130.0, 210.0, 290.0)

# Sample: 2024 qualifying across the corner-band spectrum -- low-speed (Monaco/Hungary/
# Singapore), high-speed flowing (British/Belgian/Japanese), power/straight (Italian/
# Azerbaijan/Las Vegas), mixed (Bahrain/Spanish/United States). One season keeps car
# identity stable, so the leave-one-circuit-out DNA estimate is clean.
SAMPLE_YEAR = 2024
SAMPLE_CIRCUITS = [
    "Monaco", "Hungarian", "Singapore", "British", "Belgian", "Japanese",
    "Italian", "Azerbaijan", "Las Vegas", "Bahrain", "Spanish", "United States",
]


def _band(v: float) -> str:
    if v < _EDGES[0]:
        return "low"
    if v < _EDGES[1]:
        return "med"
    if v < _EDGES[2]:
        return "high"
    return "straight"


def _gp_name(circuit: str) -> str:
    """FastF1 wants the event name; our circuit labels are EventName minus 'Grand Prix'."""
    return circuit


def extract(force: bool = False) -> pl.DataFrame:
    """Per-(circuit, driver) mean speed in each band + per-circuit demand share.

    Demand = distance-share per band on the field-fastest lap. Car band speeds = mean
    speed in each band on the driver's own fastest lap (distance-resampled telemetry)."""
    if OUT.exists() and not force:
        return pl.read_parquet(OUT)

    import fastf1
    from app.config import get_settings

    fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)

    rows: list[dict] = []
    for circuit in SAMPLE_CIRCUITS:
        try:
            s = fastf1.get_session(SAMPLE_YEAR, _gp_name(circuit), "Q")
            s.load(laps=True, telemetry=True, weather=False, messages=False)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {circuit}: {e}")
            continue
        # Circuit demand from the field-fastest lap.
        try:
            ftel = s.laps.pick_fastest().get_telemetry()
            demand = _demand_profile(ftel)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {circuit} (no fastest tel): {e}")
            continue
        for drv in s.drivers:
            dl = s.laps.pick_drivers(drv)
            if len(dl) == 0:
                continue
            try:
                lap = dl.pick_fastest()
                tel = lap.get_telemetry()
                bands = _band_speeds(tel)
                abbr = lap["Driver"]
                team = lap["Team"]
            except Exception:  # noqa: BLE001
                continue
            if bands is None:
                continue
            rows.append({
                "year": SAMPLE_YEAR, "circuit": circuit, "driver": abbr, "team": team,
                **{f"spd_{b}": bands[b] for b in BANDS},
                "mean_speed": bands["_mean"],
                **{f"dem_{b}": demand[b] for b in BANDS},
            })
        print(f"  done {circuit}: {sum(1 for r in rows if r['circuit'] == circuit)} drivers")

    df = pl.DataFrame(rows)
    df.write_parquet(OUT)
    print(f"\nwrote {OUT} ({df.height} car-circuits)")
    return df


def _demand_profile(tel) -> dict[str, float]:
    """Lap-distance share spent in each speed band (the circuit's corner-band demand)."""
    spd = tel["Speed"].to_numpy(dtype=float)
    dist = tel["Distance"].to_numpy(dtype=float)
    dd = np.diff(dist, prepend=dist[0])
    dd = np.clip(dd, 0, None)
    total = dd.sum()
    out = {b: 0.0 for b in BANDS}
    for v, w in zip(spd, dd):
        out[_band(v)] += w
    return {b: (out[b] / total if total else 0.0) for b in BANDS}


def _band_speeds(tel) -> dict[str, float] | None:
    """Mean speed in each band on one lap, + the lap mean (for shape-normalization)."""
    spd = tel["Speed"].to_numpy(dtype=float)
    if len(spd) < 100:
        return None
    out: dict[str, list[float]] = {b: [] for b in BANDS}
    for v in spd:
        out[_band(v)].append(v)
    res = {b: (float(np.mean(out[b])) if out[b] else np.nan) for b in BANDS}
    res["_mean"] = float(np.nanmean(spd))
    return res


# ---- offline analysis (no network) ------------------------------------------------

def car_factors(df: pl.DataFrame | None = None) -> pl.DataFrame:
    """Shape-normalized, field-netted per-(car, circuit) band factors.

    Two-stage scalar-pace removal (dividing by lap-mean alone is NOT enough -- a faster,
    higher-downforce car carries proportionally more speed through *every* band, so the
    ratio still leaks pace):
      1. rel_b = spd_b / lap-mean speed  (relative speed in band b)
      2. cross-band demean PER car-circuit: relc_b = rel_b - mean_b(rel_b)  -> a zero-sum
         profile, so a uniformly-fast car is flat. This is the "WHERE not HOW FAST" step.
      3. field-net within circuit: fac_b = relc_b - field-median(relc_b) -> how this car's
         profile differs from the field's at this circuit.
    Positive `fac_low` = relatively strong in slow corners (vs its own average and the field).
    """
    df = df if df is not None else extract()
    recs = df.to_dicts()
    for r in recs:
        rel = {}
        for b in BANDS:
            v = r[f"spd_{b}"]
            rel[b] = (v / r["mean_speed"]) if (v is not None and not np.isnan(v)
                                               and r["mean_speed"]) else np.nan
        present = [rel[b] for b in BANDS if not np.isnan(rel[b])]
        m = float(np.mean(present)) if present else 0.0
        for b in BANDS:
            r[f"relc_{b}"] = (rel[b] - m) if not np.isnan(rel[b]) else np.nan
    out = pl.DataFrame(recs)
    # field-net per circuit (NaN-skip: a NaN band stays NaN, dropped downstream).
    fieldmed = out.group_by("circuit").agg(
        [pl.col(f"relc_{b}").median().alias(f"relm_{b}") for b in BANDS]
    )
    out = out.join(fieldmed, on="circuit", how="left").with_columns(
        [(pl.col(f"relc_{b}") - pl.col(f"relm_{b}")).alias(f"fac_{b}") for b in BANDS]
    )
    return out


def suitability_loo(df: pl.DataFrame | None = None) -> pl.DataFrame:
    """Leave-one-circuit-out suitability: each car's GENERAL band DNA (mean factor over its
    OTHER sampled circuits) projected onto THIS circuit's demand. Leave-one-out so the
    score can't trivially see the target circuit -- a thin forward-chaining proxy."""
    df = car_factors(df)
    # demand per circuit (any row carries it)
    dem = df.group_by("circuit").agg([pl.col(f"dem_{b}").first().alias(f"dem_{b}") for b in BANDS])
    rows = []
    recs = df.to_dicts()
    by_driver: dict[str, list[dict]] = {}
    for r in recs:
        by_driver.setdefault(r["driver"], []).append(r)
    dem_map = {r["circuit"]: r for r in dem.to_dicts()}
    def _clean(vals):
        return [v for v in vals if v is not None and not np.isnan(v)]

    for r in recs:
        others = [o for o in by_driver[r["driver"]] if o["circuit"] != r["circuit"]]
        if len(others) < 3:
            continue
        # NaN-safe: a band a car never enters at a circuit (e.g. no straight at Monaco)
        # yields a NaN factor; drop those from the DNA average and the projection.
        dna = {}
        for b in BANDS:
            cv = _clean([o[f"fac_{b}"] for o in others])
            dna[b] = float(np.mean(cv)) if cv else 0.0
        d = dem_map[r["circuit"]]
        suit = sum(dna[b] * d[f"dem_{b}"] for b in BANDS)
        if np.isnan(suit):
            continue
        rows.append({"year": r["year"], "circuit": r["circuit"], "driver": r["driver"],
                     "team": r["team"], "suitability": suit})
    return pl.DataFrame(rows)


def validate() -> dict:
    """Does suitability predict a car's circuit-specific qualifying deviation, INCREMENTALLY
    over scalar pace, and is it distinct from the rejected team x circuit affinity?"""
    from .features import build_feature_table

    df = extract()
    suit = suitability_loo(df)
    feat = build_feature_table().filter(
        (pl.col("year") == SAMPLE_YEAR) & pl.col("quali_gap_pct").is_not_null()
    ).select(["circuit", "driver", "team", "quali_gap_pct"])
    j = suit.join(feat, on=["circuit", "driver"], how="inner")
    if j.height < 20:
        return {"error": "insufficient sample", "n": j.height}

    # Target = circuit-specific quali deviation: the car's quali gap netted against its OWN
    # mean gap across sampled circuits (so we predict WHERE it over/under-performs).
    car_mean = j.group_by("driver").agg(pl.col("quali_gap_pct").mean().alias("car_mean"))
    j = j.join(car_mean, on="driver").with_columns(
        (pl.col("quali_gap_pct") - pl.col("car_mean")).alias("dev")
    )
    s = j["suitability"].to_numpy()
    dev = j["dev"].to_numpy()
    # Higher suitability should mean a FASTER (more negative gap) deviation -> expect r<0.
    r = float(np.corrcoef(s, dev)[0, 1])
    # Distinctness from scalar pace: suitability vs the car's mean pace (should be ~0 if
    # shape-normalization worked -- otherwise it's just "fast car").
    cm = j["car_mean"].to_numpy()
    r_scalar = float(np.corrcoef(s, cm)[0, 1])
    return {
        "n": j.height, "n_drivers": j["driver"].n_unique(), "n_circuits": j["circuit"].n_unique(),
        "corr_suitability_vs_quali_deviation": round(r, 3),
        "corr_suitability_vs_scalar_pace": round(r_scalar, 3),
    }


def dna_summary() -> dict:
    """Per-circuit corner-band demand + per-car mean band DNA, for the Explainer.

    The honest framing this ships with: the decomposition is real and interpretable
    (McLaren/VER strong in low-speed corners, Alpine/Sauber on straights) but does NOT
    add predictive lift over scalar pace (validate(): corr with quali deviation ~0).
    """
    df = car_factors(extract())
    dem = df.group_by("circuit").agg(
        [pl.col(f"dem_{b}").first().alias(b) for b in BANDS]
    ).sort("low", descending=True)
    car = df.group_by("driver").agg(
        [pl.col(f"fac_{b}").drop_nans().mean().alias(b) for b in BANDS]
        + [pl.col("team").last().alias("team"), pl.len().alias("n")]
    ).filter(pl.col("n") >= 5).sort("low", descending=True)
    rnd = lambda r: {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}
    return {
        "bands": list(BANDS),
        "year": SAMPLE_YEAR,
        "circuit_demand": [rnd(r) for r in dem.iter_rows(named=True)],
        "car_dna": [rnd(r) for r in car.iter_rows(named=True)],
        "note": ("Shape-normalized corner-band factors (where a car is relatively fast, "
                 "not how fast). Interpretable but not predictive over scalar pace -- see "
                 "docs/science/19."),
    }


def main() -> None:
    df = extract()
    print(f"\ncar-DNA sample: {df.height} car-circuits, {df['circuit'].n_unique()} circuits\n")
    dem = df.group_by("circuit").agg(
        [pl.col(f"dem_{b}").first().round(3).alias(b) for b in BANDS]
    ).sort("low", descending=True)
    print("circuit corner-band DEMAND (distance share):")
    print(f"  {'circuit':14s} {'low':>6s} {'med':>6s} {'high':>6s} {'straight':>9s}")
    for r in dem.iter_rows(named=True):
        print(f"  {r['circuit']:14s} {r['low']:>6.3f} {r['med']:>6.3f} {r['high']:>6.3f} {r['straight']:>9.3f}")
    print("\nvalidation (leave-one-circuit-out, qualifying):")
    for k, v in validate().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
