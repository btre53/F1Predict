"""Discrete-time survival/hazard model for DNF (brief 10 §2).

The Monte Carlo sim currently samples retirement from a flat per-race rate
(`montecarlo.DriverParams.dnf_prob = 0.08`). That ignores that DNF risk is lap- and
context-dependent: first-lap contact, safety-car restarts, back-of-grid pack density,
and — dominantly — the constructor's reliability. This fits a discrete-time hazard

    P(DNF on lap k | survived to k) = sigmoid(beta . x_k)

on a TINY, pre-registered covariate set (overfitting is the enemy at ~105 races):
    lap_fraction      k / total_laps          (rising mechanical attrition)
    early_lap         k <= 2                   (first-lap collision spike)
    is_sc_restart     green lap after SC/VSC   (restart incidents)
    grid_norm         start position / 20      (midfield/back = more contact)
    team_prior        shrunk constructor DNF rate, forward-chained (the car-dominant term)
    era               (year-2018)/8            (modern cars finish far more often)

Validation is forward-chained (leak-free): for each race, fit on all prior person-laps,
predict that race's per-lap hazards, score vs the flat-rate baseline. The per-race
survival product 1 - prod(1 - h_k) is the drop-in replacement for the sim's flat dnf_prob.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import polars as pl
from sklearn.linear_model import LogisticRegression

from .features import _race_seq

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
RESULTS_PARQUET = DATA_DIR / "results.parquet"

FEATURES = ["lap_fraction", "early_lap", "is_sc_restart", "grid_norm", "team_prior", "era"]
PRIOR_RACES = 8          # empirical-Bayes shrinkage strength for the team DNF prior
GLOBAL_DNF_RATE = 0.12   # fallback team prior before any history


def _sc_active_laps(race: pl.DataFrame) -> set[int]:
    """Laps during which an SC or VSC was shown (track_status contains 4/6/7)."""
    g = (
        race.with_columns(
            pl.col("track_status").cast(pl.Utf8).fill_null("").str.contains("[467]").alias("sc_row")
        )
        .group_by("lap_number")
        .agg(pl.col("sc_row").any().alias("sc"))
    )
    return {int(r["lap_number"]) for r in g.filter(pl.col("sc")).to_dicts()}


def build_person_laps() -> pl.DataFrame:
    """One row per (car-race, lap-at-risk) with covariates + the DNF event flag."""
    laps = pl.read_parquet(LAPS_PARQUET).filter(pl.col("session_name") == "R")
    res = pl.read_parquet(RESULTS_PARQUET)
    seq = _race_seq()

    rows: list[dict] = []
    races = laps.select(["year", "circuit"]).unique().to_dicts()
    for rk in races:
        year, circuit = rk["year"], rk["circuit"]
        race = laps.filter((pl.col("year") == year) & (pl.col("circuit") == circuit))
        total_laps = int(race["lap_number"].max())
        if total_laps < 5:
            continue
        s = seq.get((year, circuit), 9999)
        sc_laps = _sc_active_laps(race)
        rres = res.filter((pl.col("year") == year) & (pl.col("circuit") == circuit))
        dnf_map = {r["driver"]: r["dnf"] for r in rres.to_dicts()}
        dns_map = {r["driver"]: r["dns"] for r in rres.to_dicts()}
        # grid = lap-1 position
        g1 = {r["driver"]: r["position"] for r in
              race.filter(pl.col("lap_number") == 1).to_dicts() if r["position"] is not None}

        for drv, dl in race.group_by("driver"):
            drv = drv[0] if isinstance(drv, tuple) else drv
            if dns_map.get(drv):  # never started -> not at risk
                continue
            last_lap = int(dl["lap_number"].max())
            did_dnf = bool(dnf_map.get(drv, False))
            team = dl["team"].drop_nulls().to_list()
            team = team[-1] if team else ""
            grid = g1.get(drv, 20)
            for k in range(1, last_lap + 1):
                event = int(did_dnf and k == last_lap)
                rows.append({
                    "seq": s, "year": year, "circuit": circuit, "driver": drv, "team": team,
                    "lap": k, "event": event,
                    "lap_fraction": k / total_laps,
                    "early_lap": 1.0 if k <= 2 else 0.0,
                    "is_sc_restart": 1.0 if (k not in sc_laps and (k - 1) in sc_laps) else 0.0,
                    "grid_norm": float(grid) / 20.0,
                    "era": (year - 2018) / 8.0,
                })
    return pl.DataFrame(rows).sort(["seq", "driver", "lap"])


def _team_prior(res_prior: pl.DataFrame) -> dict[str, float]:
    """Empirical-Bayes shrunk per-team DNF-per-car-race rate from prior races."""
    if res_prior.height == 0:
        return {}
    agg = res_prior.filter(~pl.col("dns")).group_by("team").agg(
        pl.col("dnf").mean().alias("rate"), pl.len().alias("n")
    )
    return {
        r["team"]: (r["rate"] * r["n"] + GLOBAL_DNF_RATE * PRIOR_RACES) / (r["n"] + PRIOR_RACES)
        for r in agg.to_dicts()
    }


def forward_chain_eval(min_history: int = 15) -> dict:
    """Leak-free forward-chained scoring of the hazard vs a flat-rate baseline."""
    pl_df = build_person_laps()
    # team lives in laps, not results -> attach it from the person-lap table.
    team_map = pl_df.select(["year", "circuit", "driver", "team"]).unique()
    res = (
        pl.read_parquet(RESULTS_PARQUET)
        .join(team_map, on=["year", "circuit", "driver"], how="left")
        .with_columns(pl.col("team").fill_null(""))
        .with_columns(
            pl.struct(["year", "circuit"]).map_elements(
                lambda s: _race_seq().get((s["year"], s["circuit"]), 9999), return_dtype=pl.Int64
            ).alias("seq")
        )
    )
    seqs = sorted(pl_df["seq"].unique().to_list())

    haz_pairs: list[tuple[float, int]] = []   # (per-lap hazard, event)
    flat_pairs: list[tuple[float, int]] = []
    race_haz: list[tuple[float, int]] = []     # (per-race P(DNF), did_dnf)
    race_flat: list[tuple[float, int]] = []

    for s in seqs:
        if s < seqs[min_history]:
            continue
        train = pl_df.filter(pl.col("seq") < s)
        test = pl_df.filter(pl.col("seq") == s)
        if train.height < 500 or test.height == 0:
            continue
        prior = _team_prior(res.filter(pl.col("seq") < s))
        Xtr = train.with_columns(
            pl.col("team").map_elements(lambda t: prior.get(t, GLOBAL_DNF_RATE),
                                        return_dtype=pl.Float64).alias("team_prior")
        )
        Xte = test.with_columns(
            pl.col("team").map_elements(lambda t: prior.get(t, GLOBAL_DNF_RATE),
                                        return_dtype=pl.Float64).alias("team_prior")
        )
        ytr = Xtr["event"].to_numpy()
        if ytr.sum() < 5:
            continue
        clf = LogisticRegression(C=1.0, max_iter=400, class_weight=None)
        clf.fit(Xtr.select(FEATURES).to_numpy(), ytr)
        ph = clf.predict_proba(Xte.select(FEATURES).to_numpy())[:, 1]
        flat = float(ytr.mean())
        for p, e in zip(ph, Xte["event"].to_numpy()):
            haz_pairs.append((float(p), int(e)))
            flat_pairs.append((flat, int(e)))
        # per-race: survival product per car -> P(DNF)
        te = Xte.with_columns(pl.Series("haz", ph))
        for (drv,), cl in te.group_by(["driver"]):
            h = cl["haz"].to_numpy()
            p_dnf = 1.0 - float(np.prod(1.0 - h))
            did = int(cl["event"].sum() > 0)
            race_haz.append((p_dnf, did))
            n_laps = len(h)
            race_flat.append((1.0 - (1.0 - flat) ** n_laps, did))

    def score(pairs):
        p = np.clip(np.array([x[0] for x in pairs]), 1e-6, 1 - 1e-6)
        o = np.array([x[1] for x in pairs], dtype=float)
        return {
            "brier": round(float(np.mean((p - o) ** 2)), 5),
            "logloss": round(float(-np.mean(o * np.log(p) + (1 - o) * np.log(1 - p))), 4),
            "n": len(pairs), "base_rate": round(float(o.mean()), 4),
        }

    # Coefficients from a final fit on everything (interpretation only).
    full = pl_df.with_columns(
        pl.col("team").map_elements(lambda t: _team_prior(res).get(t, GLOBAL_DNF_RATE),
                                    return_dtype=pl.Float64).alias("team_prior")
    )
    cf = LogisticRegression(C=1.0, max_iter=400).fit(
        full.select(FEATURES).to_numpy(), full["event"].to_numpy()
    )
    coefs = {f: round(float(c), 3) for f, c in zip(FEATURES, cf.coef_[0])}

    return {
        "per_lap": {"hazard": score(haz_pairs), "flat_baseline": score(flat_pairs)},
        "per_race_dnf": {"hazard": score(race_haz), "flat_baseline": score(race_flat)},
        "coefficients": coefs,
        "n_races_scored": len({s for s in seqs if s >= seqs[min_history]}),
    }


def fit_full_model() -> tuple[LogisticRegression, dict[str, float]]:
    """Fit the hazard on all data; return (classifier, team_prior map) for prediction."""
    pl_df = build_person_laps()
    res = pl.read_parquet(RESULTS_PARQUET).join(
        pl_df.select(["year", "circuit", "driver", "team"]).unique(),
        on=["year", "circuit", "driver"], how="left",
    ).with_columns(pl.col("team").fill_null(""))
    prior = _team_prior(res)
    full = pl_df.with_columns(
        pl.col("team").map_elements(lambda t: prior.get(t, GLOBAL_DNF_RATE),
                                    return_dtype=pl.Float64).alias("team_prior")
    )
    clf = LogisticRegression(C=1.0, max_iter=400).fit(
        full.select(FEATURES).to_numpy(), full["event"].to_numpy()
    )
    return clf, prior


def race_dnf_prob(clf: LogisticRegression, team_prior: dict[str, float], *,
                  grid: int, team: str, year: int, total_laps: int) -> float:
    """Pre-race P(DNF) for one car = 1 - prod over laps of (1 - per-lap hazard).

    The drop-in replacement for `montecarlo.DriverParams.dnf_prob`. Pre-race we don't
    know SC timing, so is_sc_restart=0 (a neutral baseline)."""
    k = np.arange(1, total_laps + 1)
    X = np.column_stack([
        k / total_laps,                                   # lap_fraction
        (k <= 2).astype(float),                           # early_lap
        np.zeros_like(k, dtype=float),                    # is_sc_restart
        np.full_like(k, grid / 20.0, dtype=float),        # grid_norm
        np.full_like(k, team_prior.get(team, GLOBAL_DNF_RATE), dtype=float),  # team_prior
        np.full_like(k, (year - 2018) / 8.0, dtype=float),  # era
    ])
    h = clf.predict_proba(X)[:, 1]
    return float(1.0 - np.prod(1.0 - h))


@lru_cache(maxsize=1)
def _cached_model() -> tuple[LogisticRegression, dict[str, float]]:
    """Fit once, cache for the process (the sim calls this on every prediction)."""
    return fit_full_model()


def apply_to_grid(grid, *, year: int, total_laps: int) -> None:
    """Populate each GridEntry's `dnf_prob` from the hazard model (in place).

    Duck-typed (reads `.grid_pos`/`.team`, sets `.dnf_prob`) so the engine never imports
    this module. Fails safe: any error leaves the entry's flat default untouched, so the
    deployed sim still runs if the parquet data or sklearn is unavailable.
    """
    try:
        clf, prior = _cached_model()
    except Exception:
        return
    for e in grid:
        try:
            e.dnf_prob = race_dnf_prob(
                clf, prior, grid=int(getattr(e, "grid_pos", 20)),
                team=getattr(e, "team", ""), year=year, total_laps=total_laps,
            )
        except Exception:
            continue


if __name__ == "__main__":
    r = forward_chain_eval()
    print(f"Hazard DNF model — forward-chained over {r['n_races_scored']} races\n")
    pl_ = r["per_lap"]
    print("PER-LAP hazard (does it beat a flat per-lap rate?):")
    print(f"  hazard   Brier={pl_['hazard']['brier']}  logloss={pl_['hazard']['logloss']}  (n={pl_['hazard']['n']})")
    print(f"  flat     Brier={pl_['flat_baseline']['brier']}  logloss={pl_['flat_baseline']['logloss']}")
    pr = r["per_race_dnf"]
    print("\nPER-RACE P(DNF) (the drop-in for the sim's flat 0.08):")
    print(f"  hazard   Brier={pr['hazard']['brier']}  logloss={pr['hazard']['logloss']}  (n={pr['hazard']['n']}, base={pr['hazard']['base_rate']})")
    print(f"  flat     Brier={pr['flat_baseline']['brier']}  logloss={pr['flat_baseline']['logloss']}")
    print("\ncoefficients (log-odds):")
    for f, c in r["coefficients"].items():
        print(f"  {f:14s} {c:+.3f}")
