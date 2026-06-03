"""Season championship simulator (task #25) — Monte Carlo the rest of the season.

Aggregates the per-race model into a championship forecast: take the current standings, then for
every REMAINING race sample a finishing order from the model (pre-quali pace + Gumbel + hazard
DNF), award points, and repeat thousands of times -> title probability, expected points and the
final-standings distribution for every driver and constructor. Low overfit by construction — it
only aggregates predictions we already validated per race.

Interactive: `overrides` lets a user nudge a driver's pace or reliability (e.g. "give VER 3 more
DNFs", "make a rookie 0.3 z slower") and see the championship re-shake — the season-sim sandbox.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from . import hazard

# F1 race points (top 10). Sprints / fastest-lap omitted in v1 (documented).
POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
SEASON_TEMPERATURE = 0.6   # pre-quali races are less certain than post-quali -> a touch flatter


def _points_table(d: int) -> np.ndarray:
    t = np.zeros(d)
    t[: min(10, d)] = POINTS[: min(10, d)]
    return t


def _current_standings(year: int, roster) -> tuple[dict[str, float], list[str]]:
    """Points so far this season (from actual classified results) + list of done circuits."""
    from pathlib import Path

    rp = Path(__file__).resolve().parents[2] / "data" / "results.parquet"
    if not rp.exists():
        return {}, []
    res = pl.read_parquet(rp).filter((pl.col("year") == year) & ~pl.col("dns"))
    pts: dict[str, float] = {}
    for r in res.to_dicts():
        pos = r.get("classified_pos")
        try:
            p = int(pos)
        except (TypeError, ValueError):
            continue
        if 1 <= p <= 10:
            pts[r["driver"]] = pts.get(r["driver"], 0.0) + POINTS[p - 1]
    done = res.select("circuit").unique()["circuit"].to_list()
    return pts, done


def _remaining_count(year: int, done: list[str]) -> int:
    """Races left on the calendar (schedule minus done); falls back to a 24-race season."""
    try:
        from app.etl.fastf1_client import _ensure_cache
        _ensure_cache()
        import fastf1
        sched = fastf1.get_event_schedule(year, include_testing=False)
        circuits = {str(r["EventName"]).replace(" Grand Prix", "").strip()
                    for _, r in sched.iterrows() if int(r["RoundNumber"]) > 0}
        return max(0, len(circuits) - len(set(done)))
    except Exception:
        return max(0, 24 - len(set(done)))


def simulate_season(year: int | None = None, *, n_sims: int = 20000,
                    overrides: dict | None = None, seed: int = 7) -> dict:
    """Returns championship title probabilities + expected points for drivers and constructors.

    overrides: {driver: {"pace_delta": float (z, +ve=faster), "dnf_prob": float (0..1 per race,
    overrides the hazard), "extra_dnfs": int (added retirements over the rest of the season)}}.
    """
    from .predict_kalman import _fitted
    from .predict_quali import _pre_quali_strength

    overrides = overrides or {}
    model, roster, latest = _fitted()
    year = year or latest
    drivers = roster["driver"].to_list()
    team_of = {r["driver"]: r["team"] for r in roster.to_dicts()}
    d = len(drivers)

    strengths = _pre_quali_strength(model, drivers, team_of)
    sv = np.array([strengths[d_] + float(overrides.get(d_, {}).get("pace_delta", 0.0)) for d_ in drivers])

    cur_pts, done = _current_standings(year, roster)
    current = np.array([cur_pts.get(d_, 0.0) for d_ in drivers])
    n_remaining = _remaining_count(year, done)

    clf, prior = hazard._cached_model()
    grid_rank = {d_: i + 1 for i, d_ in enumerate(sorted(drivers, key=lambda x: -strengths[x]))}
    dnf_probs = np.array([
        float(overrides.get(d_, {}).get(
            "dnf_prob",
            hazard.race_dnf_prob(clf, prior, grid=grid_rank[d_], team=team_of[d_], year=year, total_laps=57)))
        for d_ in drivers
    ])
    # "extra_dnfs over the season" -> per-race bump
    if n_remaining > 0:
        for i, d_ in enumerate(drivers):
            extra = int(overrides.get(d_, {}).get("extra_dnfs", 0))
            if extra:
                dnf_probs[i] = min(0.95, dnf_probs[i] + extra / n_remaining)

    pts_table = _points_table(d)
    rng = np.random.default_rng(seed)
    season = np.tile(current[:, None], (1, n_sims)).astype(float)
    for _ in range(n_remaining):
        g = rng.gumbel(0.0, 1.0, (d, n_sims))
        dnf = rng.random((d, n_sims)) < dnf_probs[:, None]
        score = np.where(dnf, -1e9, sv[:, None] / SEASON_TEMPERATURE + g)
        order = np.argsort(-score, axis=0)
        ranks = np.argsort(order, axis=0)              # position of each driver per sim
        season += pts_table[ranks]

    # Driver title probabilities + expected points + final-position distribution.
    champ = season.argmax(axis=0)
    driver_title = np.bincount(champ, minlength=d) / n_sims
    final_rank = np.argsort(np.argsort(-season, axis=0), axis=0) + 1   # championship position per sim
    drv_rows = []
    for i, d_ in enumerate(drivers):
        drv_rows.append({
            "driver": d_, "team": team_of[d_],
            "title_pct": round(float(driver_title[i]), 4),
            "current_points": int(current[i]),
            "exp_points": round(float(season[i].mean()), 1),
            "p_top3": round(float(np.mean(final_rank[i] <= 3)), 3),
        })
    drv_rows.sort(key=lambda r: -r["title_pct"])

    # Constructors: sum each team's drivers' points per sim.
    teams = sorted(set(team_of.values()))
    tmap = {t: i for i, t in enumerate(teams)}
    team_season = np.zeros((len(teams), n_sims))
    for i, d_ in enumerate(drivers):
        team_season[tmap[team_of[d_]]] += season[i]
    tchamp = team_season.argmax(axis=0)
    team_title = np.bincount(tchamp, minlength=len(teams)) / n_sims
    con_rows = [{"team": t, "title_pct": round(float(team_title[tmap[t]]), 4),
                 "exp_points": round(float(team_season[tmap[t]].mean()), 1)} for t in teams]
    con_rows.sort(key=lambda r: -r["title_pct"])

    return {
        "year": year, "n_done": len(set(done)), "n_remaining": n_remaining, "n_sims": n_sims,
        "drivers": drv_rows, "constructors": con_rows,
    }


if __name__ == "__main__":
    r = simulate_season(n_sims=20000)
    print(f"Season {r['year']} — {r['n_done']} done, {r['n_remaining']} remaining ({r['n_sims']} sims)\n")
    print("Drivers' title odds:")
    for x in r["drivers"][:8]:
        print(f"  {x['driver']:4s} {x['title_pct']*100:5.1f}%  (now {x['current_points']:3d} pts, exp {x['exp_points']:.0f})")
    print("\nConstructors:")
    for x in r["constructors"][:6]:
        print(f"  {x['team']:16s} {x['title_pct']*100:5.1f}%  (exp {x['exp_points']:.0f})")
