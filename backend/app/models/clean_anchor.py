"""Clean-air pace anchor for the structural sim (task #24 prerequisite, briefs 22/26).

The sim used to seed pace from the LUMPED Kalman strength (which already contains tyre deg,
reliability, traffic) — so adding physical terms (deg, dirty-air, position resolution) double-counts
(cf. brief 15). This builds a DECOUPLED pace anchor from measured, leak-free observables:

    clean strength = w_quali · z(quali pace this race) + w_ca · z(prior clean-air race pace)

- quali pace: this weekend's `quali_gap_pct` (one flying lap — no deg/reliability/traffic).
- prior clean-air race pace: a forward-chained per-TEAM EWMA of `clean_air_gap_pct` from strictly
  earlier races (a car property; a driver inherits it on a move). Leak-free.

`pace_surplus` computed from this anchor is pure pace, so the dirty-air penalty and the per-lap
overtake/pass-probability model (brief 26) add on top without re-counting what's already baked in.
Returns {seq: {driver: strength}} (higher = faster), the unit the sim seeds from.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import polars as pl

from .clean_air_pace import build_clean_air_pace
from .features import build_feature_table

W_QUALI = 0.7      # quali is the stronger single signal (brief: Spearman 0.57 vs 0.36)
W_CA = 0.3
EWMA_ALPHA = 0.45
SEASON_REVERT = 0.5


def _z(vals: np.ndarray) -> np.ndarray:
    sd = vals.std()
    return (vals - vals.mean()) / sd if sd > 1e-9 else np.zeros_like(vals)


@lru_cache(maxsize=1)
def forward_clean_anchor() -> dict[int, dict[str, float]]:
    """seq -> {driver: clean-pace strength} (higher = faster), forward-chained / leak-free."""
    feat = build_feature_table()
    ca = build_clean_air_pace()
    ca_map = {(int(r["year"]), r["circuit"], r["driver"]): r["clean_air_gap_pct"]
              for r in ca.to_dicts()}
    field_mean = float(ca["clean_air_gap_pct"].mean())

    out: dict[int, dict[str, float]] = {}
    belief: dict[str, float] = {}     # team -> EWMA clean-air gap (lower = faster)
    last_year: int | None = None

    for s in sorted(feat["seq"].unique().to_list()):
        rows = feat.filter(pl.col("seq") == s).to_dicts()
        if not rows:
            continue
        year = int(rows[0]["year"])
        if last_year is not None and year != last_year:
            for t in belief:
                belief[t] *= SEASON_REVERT      # winter reset toward the field
        last_year = year

        # Build clean strengths from THIS race's quali + the PRIOR clean-air belief (leak-free).
        drv = [r["driver"] for r in rows if r.get("quali_gap_pct") is not None]
        if len(drv) >= 4:
            rmap = {r["driver"]: r for r in rows}
            qz = -_z(np.array([float(rmap[d]["quali_gap_pct"]) for d in drv]))
            cb = np.array([belief.get(rmap[d].get("team") or "", field_mean) for d in drv])
            caz = -_z(cb)
            out[int(s)] = {d: float(W_QUALI * qz[i] + W_CA * caz[i]) for i, d in enumerate(drv)}

        # Fold THIS race's measured clean-air gap into the belief (for future races).
        for r in rows:
            g = ca_map.get((year, r["circuit"], r["driver"]))
            if g is None:
                continue
            t = r.get("team") or ""
            belief[t] = g if t not in belief else EWMA_ALPHA * g + (1 - EWMA_ALPHA) * belief[t]

    return out


if __name__ == "__main__":
    a = forward_clean_anchor()
    print(f"clean anchor: {len(a)} races with a clean-pace strength")
    # spot-check a recent race
    last = max(a)
    top = sorted(a[last].items(), key=lambda kv: -kv[1])[:6]
    print(f"  seq {last} fastest by clean anchor: " + ", ".join(f"{d} {v:+.2f}" for d, v in top))
