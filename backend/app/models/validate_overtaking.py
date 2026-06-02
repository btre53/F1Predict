"""Forward-chained validation of the overtaking-difficulty index (task #20).

The decisive gate from docs/science/16 (section 1): does scaling the Kalman
grid_weight per circuit by the mechanistic overtaking index beat the best FLAT
grid_weight, and does it (as required) beat the REJECTED team x circuit affinity?

We sweep each configuration over a small temperature grid and report its best by
win log-loss, plus podium/points log-loss (the grid mechanism mainly helps the
rest-of-field, since the winner is grid-dominated) and top-pick / best-of-rest.
Pre-committed bar: keep the index only if circuit-scaling lowers finishing-order
log-loss vs the best flat baseline AND beats the affinity. Otherwise document as
another honest negative and do not wire it in.
"""

from __future__ import annotations

from .features import build_feature_table
from .harness import run_model
from .kalman import KalmanModel, KalmanOTModel, KalmanTrackModel
from .overtaking import OvertakingIndex

TEMPS = (0.5, 0.75, 1.0, 1.5)
N_SIMS = 2500


def _agg_ll(r: dict) -> float:
    return r["win"]["logloss"] + r["podium"]["logloss"] + r["points"]["logloss"]


def validate_spread(table) -> None:
    """Does a per-circuit finishing-order SPREAD (T = t0*exp(-gamma*index)) beat
    the best single global temperature? This is the pre-quali production lever
    (grid_weight=0): tight field at locked tracks, wide at easy-to-pass tracks."""
    ot = OvertakingIndex()
    print("\n--- per-circuit spread (plain Kalman, grid_weight=0) ---")
    print(f"  {'config':22s} {'top':>5s} {'win_ll':>7s} {'pod_ll':>7s} "
          f"{'pts_ll':>7s} {'sum_ll':>7s}")
    rows = []
    for T in (0.4, 0.5, 0.6, 0.75, 1.0):
        r = run_model(KalmanModel(grid_weight=0.0), table=table,
                      temperature=T, n_sims=N_SIMS)
        r["label"] = f"flat T={T}"
        rows.append(r)
    for t0 in (0.5, 0.6, 0.75):
        for gamma in (0.15, 0.25, 0.4):
            def temp_fn(circuit, seq, _t0=t0, _g=gamma):
                return ot.spread(circuit, _t0, gamma=_g, before_seq=seq)
            r = run_model(KalmanModel(grid_weight=0.0), table=table,
                          temp_fn=temp_fn, n_sims=N_SIMS)
            r["label"] = f"OT-spread t0={t0} g={gamma}"
            rows.append(r)
    best_flat = min((r for r in rows if r["label"].startswith("flat")), key=_agg_ll)
    for r in rows:
        flag = "  <-- best flat" if r is best_flat else ""
        print(f"  {r['label']:22s} {r['top_pick_accuracy']:>5.3f} "
              f"{r['win']['logloss']:>7.4f} {r['podium']['logloss']:>7.4f} "
              f"{r['points']['logloss']:>7.4f} {_agg_ll(r):>7.4f}{flag}")


def _best(model_factory, label: str, table) -> dict:
    best = None
    for T in TEMPS:
        r = run_model(model_factory(), table=table, temperature=T, n_sims=N_SIMS)
        if best is None or r["win"]["logloss"] < best["win"]["logloss"]:
            best = r
    best["label"] = label
    return best


def main() -> None:
    t = build_feature_table()
    configs = [
        (lambda: KalmanModel(grid_weight=0.0), "flat gw=0.0"),
        (lambda: KalmanModel(grid_weight=0.2), "flat gw=0.2"),
        (lambda: KalmanModel(grid_weight=0.4), "flat gw=0.4"),
        (lambda: KalmanModel(grid_weight=0.6), "flat gw=0.6"),
        (lambda: KalmanOTModel(w0=0.4), "OT w0=0.4"),
        (lambda: KalmanOTModel(w0=0.8), "OT w0=0.8"),
        (lambda: KalmanOTModel(w0=1.2), "OT w0=1.2"),
        (lambda: KalmanOTModel(w0=0.8, era_split=True), "OT w0=0.8 era-split"),
        (lambda: KalmanTrackModel(track_weight=1.0), "affinity (REJECTED)"),
    ]
    rows = [_best(f, lbl, t) for f, lbl in configs]

    print(f"\nforward-chained, best of T in {TEMPS}, n_sims={N_SIMS}, "
          f"{rows[0]['n_races']} scored races\n")
    print(f"  {'config':22s} {'T':>4s} {'top':>5s} {'bor':>5s} "
          f"{'win_ll':>7s} {'pod_ll':>7s} {'pts_ll':>7s}")
    for r in rows:
        print(f"  {r['label']:22s} {r['temperature']:>4.2f} "
              f"{r['top_pick_accuracy']:>5.3f} {r['best_of_rest_accuracy']:>5.3f} "
              f"{r['win']['logloss']:>7.4f} {r['podium']['logloss']:>7.4f} "
              f"{r['points']['logloss']:>7.4f}")

    validate_spread(t)


if __name__ == "__main__":
    main()
