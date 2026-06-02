"""Quantify the pre-quali -> post-quali sharpening (the grid-fusion win).

Same forward-chained harness + same Kalman.predict the production Predictor uses. PRE nulls
quali_gap_pct + grid (car+driver prior only); POST fuses the real quali pace + the OT-scaled
grid weight (feature #20). Scored on best-of-rest / podium (the meaningful, high-variance
positions), not just win (VER 23/24 dominance makes win near-trivial)."""

from __future__ import annotations

import polars as pl

from .features import build_feature_table
from .harness import run_model
from .kalman import KalmanModel, KalmanOTModel

T = 0.5  # production temperature


def main() -> None:
    t = build_feature_table()
    pre_t = t.with_columns(
        pl.lit(None, dtype=pl.Float64).alias("quali_gap_pct"),
        pl.lit(None, dtype=t.schema["grid"]).alias("grid"),
    )
    pre = run_model(KalmanModel(grid_weight=0.0), table=pre_t, temperature=T, n_sims=3000)
    post = run_model(KalmanOTModel(w0=0.8), table=t, temperature=T, n_sims=3000)

    print(f"\nPre-quali vs post-quali fusion (forward-chained, T={T}, "
          f"{pre['n_races']} races)\n")
    print(f"  {'':10s} {'top':>6s} {'bor':>6s} {'win_ll':>7s} {'pod_ll':>7s} {'pts_ll':>7s}")
    for label, r in (("pre-quali", pre), ("post-quali", post)):
        print(f"  {label:10s} {r['top_pick_accuracy']:>6.3f} {r['best_of_rest_accuracy']:>6.3f} "
              f"{r['win']['logloss']:>7.4f} {r['podium']['logloss']:>7.4f} "
              f"{r['points']['logloss']:>7.4f}")


if __name__ == "__main__":
    main()
