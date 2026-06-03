"""Forward-chained validation of weather-as-variance (roadmap open-Q #4, brief 16 §4).

Hypotheses (mechanistic, brand-agnostic; weather is an exogenous race-day shock):
  H1 (spread)  rain makes the FRONT of the order volatile -> the favourite is less safe,
               so widening the PL temperature on wet races should improve win/podium
               calibration *on wet races* without hurting dry races.
  H2 (DNF)     rain raises retirements -> a wet DNF multiplier should improve DNF
               calibration. (Descriptively this signal is ~absent in 2018-2026 -- modern
               reliability + wet running behind the SC -- so we test it but expect ~nil.)

Method: forward-chain the Kalman ONCE over the feature table, cache each scored race's
strengths + realized finish + this-race rain (exogenous, known pre-race -> leak-free).
Then re-score win/podium/points under temperature policies T(seq)=T0*(1+k*rain) for a
sweep of k, splitting metrics into WET / DRY / ALL. Pure spread test (matches the bake-off
harness: no DNF censoring), so it isolates the calibration effect of the weather widening.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from .features import build_feature_table
from .kalman import KalmanModel
from .probability import strengths_to_probs

_EPS = 1e-12

DEFAULT_T0 = 0.5            # the production PL temperature (predict_kalman.DEFAULT_TEMPERATURE)
PRECIP_SCALE = 3.0         # mm of race-window precip -> intensity 1.0 (continuous policy)


def _rain_intensity(row: dict, mode: str) -> float:
    """Pre-race rain intensity in [0,1] from the race-window precip features."""
    if mode == "binary":
        return 1.0 if row.get("wet") else 0.0
    if mode == "window":
        return float(min(1.0, (row.get("precip_mm_window") or 0.0) / PRECIP_SCALE))
    if mode == "max":
        return float(min(1.0, (row.get("precip_mm_max") or 0.0) / 1.0))
    raise ValueError(mode)


def _collect(min_history: int = 5, n_sims: int = 6000, seed: int = 0):
    """Forward-chain the Kalman; return scored-race records with strengths + rain."""
    table = build_feature_table()
    w = pl.read_parquet("data/weather.parquet").select(
        ["seq", "wet", "precip_mm_window", "precip_mm_max"]
    )
    wmap = {int(r["seq"]): r for r in w.to_dicts()}

    model = KalmanModel()
    model.reset()
    seqs = sorted(table["seq"].unique().to_list())
    seen = 0
    records = []
    for s in seqs:
        race = table.filter(pl.col("seq") == s)
        if seen >= min_history and race.height >= 4:
            strengths = model.predict(race)
            drivers = [d for d in race["driver"].to_list() if d in strengths]
            if len(drivers) >= 4:
                rmap = {r["driver"]: r for r in race.to_dicts()}
                records.append({
                    "seq": int(s),
                    "drivers": drivers,
                    "sv": np.array([strengths[d] for d in drivers]),
                    "finish": np.array([rmap[d]["finish_pos"] for d in drivers]),
                    "rain": wmap.get(int(s), {}),
                })
        model.update(race)
        seen += 1
    return records, n_sims, seed


def _score(pairs):
    if not pairs:
        return {"brier": None, "logloss": None, "n": 0}
    p = np.clip(np.array([x[0] for x in pairs]), _EPS, 1 - _EPS)
    o = np.array([x[1] for x in pairs], dtype=float)
    return {
        "brier": round(float(np.mean((p - o) ** 2)), 4),
        "logloss": round(float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p))), 4),
        "n": len(pairs),
    }


def evaluate(mode: str = "binary", ks=(0.0, 0.5, 1.0, 1.5, 2.0), t0: float = DEFAULT_T0) -> dict:
    """Sweep the weather-widening strength k; report win/podium/points split wet/dry."""
    records, n_sims, seed = _collect()
    # Precompute rain intensity + wet flag per record.
    for r in records:
        r["intensity"] = _rain_intensity(r["rain"], mode)
        r["is_wet"] = bool(r["rain"].get("wet"))

    results = []
    for k in ks:
        buckets = {seg: {"win": [], "podium": [], "points": []} for seg in ("all", "wet", "dry")}
        for r in records:
            T = t0 * (1.0 + k * r["intensity"])
            probs = strengths_to_probs(r["drivers"], r["sv"], temperature=T, n_sims=n_sims, seed=seed)
            seg = "wet" if r["is_wet"] else "dry"
            for i, d in enumerate(r["drivers"]):
                fin = int(r["finish"][i])
                for key, hit in (("win", fin == 1), ("podium", fin <= 3), ("points", fin <= 10)):
                    pair = (probs[d][key], int(hit))
                    buckets["all"][key].append(pair)
                    buckets[seg][key].append(pair)
        results.append({
            "k": k,
            "T0": t0,
            "all": {m: _score(buckets["all"][m]) for m in ("win", "podium", "points")},
            "wet": {m: _score(buckets["wet"][m]) for m in ("win", "podium", "points")},
            "dry": {m: _score(buckets["dry"][m]) for m in ("win", "podium", "points")},
        })
    n_wet = sum(1 for r in records if r["is_wet"])
    return {"mode": mode, "n_races": len(records), "n_wet": n_wet, "sweep": results}


def dnf_signal() -> dict:
    """H2 descriptive: DNF rate wet vs dry (per-car-race), to confirm/deny a wet DNF lift."""
    res = pl.read_parquet("data/results.parquet")
    w = pl.read_parquet("data/weather.parquet").select(["year", "circuit", "wet", "precip_mm_max"])
    r = res.join(w, on=["year", "circuit"], how="inner").filter(~pl.col("dns"))
    by = r.group_by("wet").agg(pl.col("dnf").mean().round(4).alias("dnf"), pl.len().alias("n")).sort("wet")
    return {row["wet"]: {"dnf_rate": row["dnf"], "n": row["n"]} for row in by.to_dicts()}


def _fmt(seg):
    return (f"win ll={seg['win']['logloss']} pod ll={seg['podium']['logloss']} "
            f"pts ll={seg['points']['logloss']}")


if __name__ == "__main__":
    print("=== H2: DNF rate wet vs dry ===")
    for wet, d in dnf_signal().items():
        print(f"  {'WET' if wet else 'DRY'}: dnf={d['dnf_rate']} (n={d['n']})")

    for mode in ("binary", "window"):
        out = evaluate(mode=mode)
        print(f"\n=== H1: weather spread, intensity='{mode}'  "
              f"({out['n_races']} races, {out['n_wet']} wet) ===")
        for r in out["sweep"]:
            print(f"  k={r['k']}:")
            print(f"     WET  {_fmt(r['wet'])}  (n_win={r['wet']['win']['n']})")
            print(f"     DRY  {_fmt(r['dry'])}")
            print(f"     ALL  {_fmt(r['all'])}")
