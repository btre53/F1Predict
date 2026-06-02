"""Predictor engine: time-local Kalman car+driver pace -> finishing-position probs.

Replaces the old mechanistic-sim path (which used `drivers.json`, a flat all-time
pooled average — the wrong way: it had Perez at Red Bull and Verstappen winning Monaco).
This:
  1. forward-chains the Kalman pace-filter (app/models/kalman.py) over ALL races so the
     car+driver beliefs are time-local and current (between-race + season-boundary
     variance inflation already handles upgrades / season changes);
  2. takes the roster from the LATEST season in the data, so it's the real current grid
     and a moved driver inherits the new car (strength = car_team.mu + driver.mu);
  3. samples finishing orders (Plackett-Luce / Gumbel-max) with per-driver DNF from the
     survival/hazard model, yielding the full finishing-position distribution.

The car/driver split is the whole point: HAM in a 2026 Ferrari gets Ferrari's current car
pace + Hamilton's driver skill — not his Mercedes-era pooled average.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import polars as pl

from app.engine import calibration_store as store
from app.engine.montecarlo import DriverOutcome, RaceSimResult
from app.engine.predict import TEAM_COLOURS

from . import hazard
from .features import LAPS_PARQUET, build_feature_table
from .kalman import KalmanModel
from .overtaking import OvertakingIndex

# PL temperature = the forward-chained calibrated value (best win log-loss in the bake-off
# harness). Pre-qualifying this yields an honestly-tight field (no single ~90% favourite);
# it sharpens automatically once a real quali grid is fused (model.predict with quali_gap).
DEFAULT_TEMPERATURE = 0.5
# Per-circuit finishing-order spread: the overtaking-difficulty index narrows the field at
# qualifying-locked tracks (Monaco) and widens it at easy-to-pass tracks (Spa). Gentle gamma
# -- forward-chained validation showed the spread is calibration-neutral in aggregate, so we
# use it for mechanistically-correct *per-circuit* variance, not an aggregate logloss gain.
# See app/models/overtaking.py + docs/science/16.
SPREAD_GAMMA = 0.2


@lru_cache(maxsize=1)
def _ot_index() -> OvertakingIndex:
    return OvertakingIndex()


@lru_cache(maxsize=1)
def _fitted():
    """Forward-chain the Kalman over all races; return (model, roster, latest_year).

    roster: one row per current-grid driver -> {driver, team, number} from the latest
    season (most-frequent team handles mid-season swaps; top-20 by laps drops reserves).
    """
    table = build_feature_table()
    model = KalmanModel()
    model.reset()
    for s in sorted(table["seq"].unique().to_list()):
        model.update(table.filter(pl.col("seq") == s))

    latest = int(table["year"].max())
    laps = pl.read_parquet(
        LAPS_PARQUET, columns=["year", "session_name", "driver", "driver_number", "team"]
    ).filter((pl.col("year") == latest) & (pl.col("session_name") == "R"))
    roster = (
        laps.group_by("driver").agg(
            pl.col("team").mode().first().alias("team"),
            pl.col("driver_number").mode().first().alias("number"),
            pl.len().alias("laps"),
        )
        # Tie-break by driver code so the roster order is deterministic run-to-run
        # (polars group_by hash order is not stable, and lap counts tie at season end).
        .sort(["laps", "driver"], descending=[True, False])
        .head(20)  # regulars only — drop one-off reserves
    )
    return model, roster, latest


# Post-quali grid-weight base (the OT index scales it per circuit -> Monaco leans hard on
# grid, Spa less). Activates feature #20's validated grid-vs-pace blend once a grid exists.
GRID_W0 = 0.8


def predict_race_kalman(
    circuit_name: str,
    *,
    n_sims: int = 10_000,
    grid_order: list[str] | None = None,
    quali_gap: dict[str, float] | None = None,
    use_quali: bool = False,
    temperature: float = DEFAULT_TEMPERATURE,
    circuit_spread: bool = True,
    seed: int = 12345,
) -> RaceSimResult:
    """Kalman pace -> Plackett-Luce finishing distribution + hazard DNF.

    PRE-QUALI (default): strength = car.mu + driver.mu, an honestly-tight field.
    POST-QUALI: pass `quali_gap` ({driver: % gap to pole}) and/or `grid_order` to fuse the
    real session -- the Kalman folds quali pace into each prior (gain k=var/(var+r_quali))
    and adds the circuit-scaled grid signal, sharpening toward the grid exactly as the
    bake-off validated. Hazard DNF then uses the real grid (pole ~2% vs P20 ~16%).
    """
    model, roster, latest = _fitted()
    cp = store.circuit_params_for(circuit_name)
    n_laps = cp.total_laps

    # Auto-fuse the real qualifying grid when asked (and not explicitly supplied). Best-effort:
    # returns {} if the Q session hasn't happened yet -> stays pre-quali.
    if use_quali and quali_gap is None and grid_order is None:
        quali_gap = fetch_quali_gaps(circuit_name, latest) or None

    # Track-aware spread: tighten the field where qualifying locks the order, widen it
    # where pace overcomes grid. Brand-agnostic (one track-physics number, all teams equal).
    if circuit_spread:
        temperature = _ot_index().spread(circuit_name, temperature, gamma=SPREAD_GAMMA)

    drivers = roster["driver"].to_list()
    team_of = {r["driver"]: r["team"] for r in roster.to_dicts()}
    num_of = {r["driver"]: r["number"] for r in roster.to_dicts()}

    # Derive the grid: explicit order > qualifying-pace ranking > (pre-quali) none.
    qg = {d: g for d, g in (quali_gap or {}).items() if d in team_of and g is not None}
    if grid_order is None and qg:
        grid_order = sorted(qg, key=lambda d: qg[d])
    post_quali = grid_order is not None or bool(qg)
    gpos = {d: i + 1 for i, d in enumerate(grid_order)} if grid_order else {}

    # Track-scaled grid weight only once a real grid exists (else the grid signal is just
    # the pace order -> circular). This is feature #20's validated production use.
    model.grid_weight = _ot_index().grid_weight(circuit_name, GRID_W0) if post_quali else 0.0

    race = pl.DataFrame({
        "driver": drivers,
        "team": [team_of[d] for d in drivers],
        "quali_gap_pct": [qg.get(d) for d in drivers],
        "grid": [float(gpos[d]) if d in gpos else None for d in drivers],
    })
    strengths = model.predict(race)

    # Grid order for DNF/display: the real grid post-quali, else predicted pace order.
    order = grid_order or sorted(drivers, key=lambda d: -strengths[d])
    grid_pos = {d: i + 1 for i, d in enumerate([d for d in order if d in strengths])}
    for d in drivers:
        grid_pos.setdefault(d, len(grid_pos) + 1)

    # Per-driver DNF from the survival/hazard model (time-local attrition by grid/era).
    clf, prior = hazard._cached_model()
    dnf = np.array([
        hazard.race_dnf_prob(clf, prior, grid=grid_pos[d], team=team_of[d],
                             year=latest, total_laps=n_laps)
        for d in drivers
    ])

    # Plackett-Luce Monte Carlo with DNF censoring -> full finishing distribution.
    n = len(drivers)
    sv = np.array([strengths[d] for d in drivers]) / max(temperature, 1e-6)
    rng = np.random.default_rng(seed)
    pos_counts = np.zeros((n, n))  # [driver, finish_pos-1]
    dnf_counts = np.zeros(n)
    for _ in range(n_sims):
        g = rng.gumbel(0.0, 1.0, n)
        retired = rng.random(n) < dnf
        score = np.where(retired, -1e9, sv + g)
        order_idx = np.argsort(-score)
        for finish, di in enumerate(order_idx):
            pos_counts[di, finish] += 1
        dnf_counts[retired] += 1

    outcomes: list[DriverOutcome] = []
    positions = np.arange(1, n + 1)
    for i, d in enumerate(drivers):
        dist = pos_counts[i] / n_sims
        cdf_win = dist[0]
        podium = dist[:3].sum()
        points = dist[:10].sum()
        mean_fin = float((positions * dist).sum())
        cum = np.cumsum(dist)
        p10 = int(np.searchsorted(cum, 0.10) + 1)
        p50 = int(np.searchsorted(cum, 0.50) + 1)
        p90 = int(np.searchsorted(cum, 0.90) + 1)
        outcomes.append(DriverOutcome(
            driver=d, number=int(num_of[d]) if num_of[d] is not None else None,
            team=team_of[d], colour=TEAM_COLOURS.get(team_of[d], "888888"),
            grid_pos=grid_pos[d],
            win_pct=float(cdf_win), podium_pct=float(podium), points_pct=float(points),
            mean_finish=mean_fin, p50_finish=p50, p10_finish=p10, p90_finish=p90,
            dnf_pct=float(dnf_counts[i] / n_sims),
            finish_distribution=[float(x) for x in dist],
        ))
    outcomes.sort(key=lambda o: o.win_pct, reverse=True)
    # Structural per-circuit SC prior (brand-agnostic; ordering-correct -- street/walled
    # circuits fire more cautions). Forward-chained it does NOT beat the base rate for
    # race-level prediction (SC is a near-Poisson shock), so this is a realism/Explainer
    # number, not a calibrated edge. Fail-safe to 0 if the model can't fit. See science/18.
    try:
        from . import sc_index
        sc_prob = sc_index.sc_probability(circuit_name)
    except Exception:
        sc_prob = 0.0
    return RaceSimResult(
        circuit=cp.name, total_laps=n_laps, n_sims=n_sims, outcomes=outcomes,
        sc_probability=sc_prob, post_quali=post_quali,
    )


def fetch_quali_gaps(circuit_name: str, year: int) -> dict[str, float]:
    """Real qualifying gaps ({driver_code: % gap to pole}) from FastF1, or {} if the Q
    session isn't available yet. Best-effort + cached; used to fuse a real grid post-quali."""
    import logging
    import warnings

    warnings.filterwarnings("ignore")
    logging.getLogger("fastf1").setLevel(logging.ERROR)
    try:
        import fastf1

        from app.config import get_settings

        fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)
        s = fastf1.get_session(year, circuit_name, "Q")
        s.load(laps=True, telemetry=False, weather=False, messages=False)
        laps = s.laps
        best: dict[str, float] = {}
        for drv in laps["Driver"].unique():
            t = laps.pick_drivers(drv)["LapTime"].min()
            if t is not None and t == t:  # not NaT
                best[str(drv)] = t.total_seconds()
        if len(best) < 4:
            return {}
        pole = min(best.values())
        return {d: round(sec / pole - 1.0, 5) for d, sec in best.items()}
    except Exception:
        return {}


if __name__ == "__main__":
    res = predict_race_kalman("Monaco", n_sims=8000)
    print(f"Kalman Predictor — {res.circuit} ({res.total_laps} laps)")
    print("  drv  team                 grid  win%   pod%   dnf%")
    for o in res.outcomes[:12]:
        print(f"  {o.driver:4s} {o.team:20s} P{o.grid_pos:<2d}  {o.win_pct*100:5.1f}  "
              f"{o.podium_pct*100:5.1f}  {o.dnf_pct*100:4.1f}")
