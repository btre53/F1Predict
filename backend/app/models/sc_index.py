"""Structural safety-car / caution likelihood index (task #21, brief 16 §3).

A **race-level SC prior** estimated from *measurable track structure*, not circuit
identity: street-ness / wall-proximity (low on-track passing + high lap-1 churn =
narrow, walled, little run-off), plus a weather flag, plus an empirical-Bayes
shrunk per-circuit history term. The mechanistic, generalizing version of
"Singapore always has a safety car": a new street circuit gets a high prior from
its *structure* (once raced) rather than its name, and the model is shared across
all teams (no identity features).

We estimate a **prior intensity**, NOT "SC in the next N laps" (that is near-Poisson
noise, doc 10 — a trap). P(any SC) per race, forward-chained and leak-free; scored
against (a) the calendar base rate and (b) the per-circuit historical rate (the
brand-proxy baseline). It feeds the hazard model's SC-restart pathway and the sim's
SC count, and improves chaos-driven props (podium-without-favourite, midfield points).

SC label = any lap with track_status containing 4/6/7 (SC or VSC), via
`hazard._sc_active_laps`. Structural features reuse `overtaking_proxies.parquet`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.linear_model import LogisticRegression

from .features import LAPS_PARQUET, _race_seq
from .hazard import _sc_active_laps
from .overtaking import _proxy_table

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SC_TABLE_PARQUET = DATA_DIR / "sc_table.parquet"

# Pre-registered, tiny feature set (overfitting is the enemy at 168 races):
#   circ_pass   median green on-track passing rate over the circuit's prior runnings
#   circ_churn  median lap-1 churn over prior runnings   (low pass + high churn = walls)
#   circ_rate   empirical-Bayes shrunk per-circuit historical P(any SC)
#   wet         this race ran >30% laps on wet/inter rubber (a contemporaneous flag;
#               a true pre-race prior would use a rain *forecast* -- see v2)
STRUCT = ["circ_pass", "circ_churn", "wet"]   # generalizes from structure alone
FULL = ["circ_pass", "circ_churn", "circ_rate", "wet"]
WET_FRACTION = 0.30
CIRC_RATE_PRIOR = 6.0       # EB shrinkage strength for the per-circuit SC rate
GLOBAL_SC_RATE = 0.72       # fallback before any history


def _sc_periods(race: pl.DataFrame) -> int:
    """Number of distinct SC/VSC periods (gaps of >1 lap start a new period)."""
    laps = sorted(_sc_active_laps(race))
    n, prev = 0, -10
    for L in laps:
        if L - prev > 1:
            n += 1
        prev = L
    return n


def build_sc_table() -> pl.DataFrame:
    """Per-race SC labels joined with structural proxies (one row per running)."""
    laps = pl.read_parquet(
        LAPS_PARQUET, columns=["year", "circuit", "session_name", "lap_number", "track_status"]
    ).filter(pl.col("session_name") == "R")
    seq = _race_seq()
    rows: list[dict] = []
    for df in laps.partition_by(["year", "circuit"]):
        year, circuit = int(df["year"][0]), str(df["circuit"][0])
        if int(df["lap_number"].max()) < 5:
            continue
        periods = _sc_periods(df)
        rows.append({
            "year": year, "circuit": circuit,
            "seq": int(seq.get((year, circuit), 9999)),
            "any_sc": int(periods > 0), "n_periods": periods,
        })
    labels = pl.DataFrame(rows)
    prox = _proxy_table().select(["year", "circuit", "pass_rate", "lap1_churn", "wet_frac"])
    out = labels.join(prox, on=["year", "circuit"], how="left").with_columns(
        (pl.col("wet_frac") > WET_FRACTION).cast(pl.Float64).fill_null(0.0).alias("wet")
    )
    return out.sort("seq")


def _circuit_features(train: pl.DataFrame, circuit: str) -> dict:
    """Forward-chained per-circuit structural features from prior runnings only.

    Falls back to the global median (unseen circuit) so a thin circuit borrows the
    calendar mean rather than a noisy single-race estimate."""
    g_pass = float(train["pass_rate"].median() or 0.1)
    g_churn = float(train["lap1_churn"].median() or 2.0)
    g_rate = float(train["any_sc"].mean()) if train.height else GLOBAL_SC_RATE
    c = train.filter(pl.col("circuit") == circuit)
    n = c.height
    if n == 0:
        return {"circ_pass": g_pass, "circ_churn": g_churn, "circ_rate": g_rate}
    rate = float(c["any_sc"].mean())
    return {
        "circ_pass": float(c["pass_rate"].median() or g_pass),
        "circ_churn": float(c["lap1_churn"].median() or g_churn),
        # EB shrink the per-circuit rate toward the calendar mean by visit count.
        "circ_rate": (rate * n + g_rate * CIRC_RATE_PRIOR) / (n + CIRC_RATE_PRIOR),
    }


def _design(table: pl.DataFrame, train: pl.DataFrame, feats: list[str]) -> np.ndarray:
    cols = [_circuit_features(train, c) for c in table["circuit"].to_list()]
    base = {"wet": table["wet"].to_list()}
    arr = []
    for f in feats:
        if f == "wet":
            arr.append(np.array(base["wet"], dtype=float))
        else:
            arr.append(np.array([d[f] for d in cols], dtype=float))
    return np.column_stack(arr)


def forward_chain_eval(min_history: int = 25) -> dict:
    """Leak-free forward-chained P(any SC): structural models vs the two baselines."""
    t = build_sc_table()
    seqs = sorted(t["seq"].unique().to_list())
    cutoff = seqs[min_history]

    pairs = {"base": [], "circ_rate": [], "structure": [], "full": []}
    for s in seqs:
        if s < cutoff:
            continue
        train = t.filter(pl.col("seq") < s)
        test = t.filter(pl.col("seq") == s)
        if train.height < 20 or test.height == 0:
            continue
        y = test["any_sc"].to_numpy()
        ytr = train["any_sc"].to_numpy()

        base = float(ytr.mean())
        # (b) per-circuit shrunk rate baseline (the brand proxy).
        cr = _design(test, train, ["circ_rate"]).ravel()
        # structural logistic models
        def _fit_predict(feats):
            Xtr = _design(train, train, feats)
            clf = LogisticRegression(C=1.0, max_iter=400)
            clf.fit(Xtr, ytr)
            return clf.predict_proba(_design(test, train, feats))[:, 1]
        ps = _fit_predict(STRUCT)
        pf = _fit_predict(FULL)
        for i, e in enumerate(y):
            pairs["base"].append((base, int(e)))
            pairs["circ_rate"].append((float(cr[i]), int(e)))
            pairs["structure"].append((float(ps[i]), int(e)))
            pairs["full"].append((float(pf[i]), int(e)))

    def score(pr):
        p = np.clip(np.array([x[0] for x in pr]), 1e-6, 1 - 1e-6)
        o = np.array([x[1] for x in pr], dtype=float)
        return {
            "brier": round(float(np.mean((p - o) ** 2)), 4),
            "logloss": round(float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p))), 4),
            "n": len(pr),
        }

    # Coefficients from a full fit (interpretation only).
    full = build_sc_table()
    cf = LogisticRegression(C=1.0, max_iter=400).fit(
        _design(full, full, FULL), full["any_sc"].to_numpy()
    )
    coefs = {f: round(float(c), 3) for f, c in zip(FULL, cf.coef_[0])}
    return {m: score(p) for m, p in pairs.items()} | {"coefficients": coefs}


@lru_cache(maxsize=1)
def _fitted() -> tuple[LogisticRegression, pl.DataFrame]:
    """Fit the full structural model on all data; cache for the process."""
    t = build_sc_table()
    clf = LogisticRegression(C=1.0, max_iter=400)
    clf.fit(_design(t, t, FULL), t["any_sc"].to_numpy())
    return clf, t


def sc_probability(circuit: str, *, wet: bool = False) -> float:
    """Pre-race P(any SC) for a circuit from structure (the production entry point)."""
    clf, t = _fitted()
    feat = _circuit_features(t, circuit)
    X = np.array([[feat["circ_pass"], feat["circ_churn"], feat["circ_rate"], float(wet)]])
    return float(clf.predict_proba(X)[:, 1][0])


def main() -> None:
    build_sc_table().write_parquet(SC_TABLE_PARQUET)
    r = forward_chain_eval()
    print("Structural SC index — forward-chained P(any SC)\n")
    print(f"  {'model':12s} {'brier':>7s} {'logloss':>8s}  (n={r['base']['n']})")
    for m in ("base", "circ_rate", "structure", "full"):
        print(f"  {m:12s} {r[m]['brier']:>7.4f} {r[m]['logloss']:>8.4f}")
    print("\ncoefficients (log-odds):")
    for f, c in r["coefficients"].items():
        print(f"  {f:12s} {c:+.3f}")
    clf, t = _fitted()
    circuits = sorted(set(t["circuit"].to_list()))
    scored = sorted(((c, sc_probability(c)) for c in circuits), key=lambda x: -x[1])
    print("\nstructural dry-race SC prior (high = chaos-prone):")
    for c, v in scored[:6] + scored[-6:]:
        print(f"  {v:5.2f}  {c}")


if __name__ == "__main__":
    main()
