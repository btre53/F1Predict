"""Bayesian sequential pace-filter: a scalar Kalman filter on car + driver pace.

Each car (team) and driver carries a Gaussian belief (mu, var) over pace in
per-race z-units (higher = faster). Between races the variance inflates (form drifts,
upgrades). predict() fuses THIS weekend's qualifying gap (a pre-race observation) into
the prior to return a post-quali strength. update() folds in the realized quali + race
result. Car and driver are jointly updated from each observation, so two teammates in
the same car both pull the car term while their driver terms separate — the principled
version of the rating model.

A simplification of docs/science/09's full state-space spec: scalar (not vector)
Kalman, quali + finishing-position observations (not full session sequence). Still
fully incremental and leak-free.
"""

from __future__ import annotations

import numpy as np
import polars as pl


def _z_faster(values: list[float | None], invert: bool) -> list[float | None]:
    """Per-race z-score; `invert` flips sign so smaller raw = faster (higher z)."""
    present = [v for v in values if v is not None]
    if not present:
        return [None] * len(values)
    a = np.array(present, dtype=float)
    mu, sd = a.mean(), a.std()
    out: list[float | None] = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            z = (v - mu) / sd if sd > 1e-9 else 0.0
            out.append(-z if invert else z)
    return out


class KalmanModel:
    def __init__(
        self,
        *,
        car_var0: float = 0.6,
        drv_var0: float = 0.2,
        proc_car: float = 0.03,
        proc_drv: float = 0.015,
        r_quali: float = 0.3,
        r_finish: float = 1.2,
        var_floor: float = 0.05,
        season_inflate: float = 1.5,
        grid_weight: float = 0.0,
    ):
        self.car_var0, self.drv_var0 = car_var0, drv_var0
        self.proc_car, self.proc_drv = proc_car, proc_drv
        self.r_quali, self.r_finish = r_quali, r_finish
        self.var_floor, self.season_inflate = var_floor, season_inflate
        self.grid_weight = grid_weight
        self.name = f"kalman(g={grid_weight})"
        self.reset()

    def reset(self) -> None:
        self.car: dict[str, list[float]] = {}     # team -> [mu, var]
        self.drv: dict[str, list[float]] = {}     # driver -> [mu, var]
        self._last_year: int | None = None

    def _seed(self, driver: str, team: str) -> None:
        self.car.setdefault(team, [0.0, self.car_var0])
        self.drv.setdefault(driver, [0.0, self.drv_var0])

    def predict(self, race: pl.DataFrame) -> dict[str, float]:
        rows = race.to_dicts()
        for r in rows:
            self._seed(r["driver"], r["team"])
        qz = _z_faster([r["quali_gap_pct"] for r in rows], invert=True)
        gz = _z_faster([float(r["grid"]) if r["grid"] is not None else None for r in rows], invert=True)
        out: dict[str, float] = {}
        for r, q, gr in zip(rows, qz, gz):
            mc, vc = self.car[r["team"]]
            md, vd = self.drv[r["driver"]]
            prior, var = mc + md, vc + vd
            if q is not None:
                k = var / (var + self.r_quali)
                s = prior + k * (q - prior)  # fuse this-weekend quali pace
            else:
                s = prior
            if self.grid_weight and gr is not None:
                s += self.grid_weight * gr  # track-position signal for rest-of-field
            out[r["driver"]] = s
        return out

    def update(self, race: pl.DataFrame) -> None:
        year = int(race["year"][0])
        rows = race.to_dicts()
        for r in rows:
            self._seed(r["driver"], r["team"])
        # Season boundary: inflate uncertainty + mild mean-reversion.
        if self._last_year is not None and year != self._last_year:
            for store in (self.car, self.drv):
                for e in store.values():
                    e[1] = min(self.car_var0, e[1] * self.season_inflate)
                    e[0] *= 0.9
        self._last_year = year

        # Process noise (between-race drift).
        for team in {r["team"] for r in rows}:
            self.car[team][1] += self.proc_car
        for d in (r["driver"] for r in rows):
            self.drv[d][1] += self.proc_drv

        # Observations, most-trusted first: qualifying pace, then finishing position.
        qz = _z_faster([r["quali_gap_pct"] for r in rows], invert=True)
        fz = _z_faster([float(r["finish_pos"]) for r in rows], invert=True)
        for r, q in zip(rows, qz):
            self._kupdate(r["team"], r["driver"], q, self.r_quali)
        for r, f in zip(rows, fz):
            self._kupdate(r["team"], r["driver"], f, self.r_finish)

    def _kupdate(self, team: str, driver: str, obs: float | None, r_obs: float) -> None:
        if obs is None:
            return
        mc, vc = self.car[team]
        md, vd = self.drv[driver]
        innov = obs - (mc + md)
        s = vc + vd + r_obs
        kc, kd = vc / s, vd / s  # higher-variance component absorbs more
        self.car[team][0] = mc + kc * innov
        self.drv[driver][0] = md + kd * innov
        self.car[team][1] = max(self.var_floor, vc * (1 - kc))
        self.drv[driver][1] = max(self.var_floor, vd * (1 - kd))


class KalmanTrackModel(KalmanModel):
    """Kalman + a regularized TEAM×CIRCUIT affinity (does this car suit this track?).

    Some cars over/under-perform their season pace at specific circuits (Ferrari at
    Monaco; low-downforce cars at Monza). We learn, forward-chained, the residual of a
    team's realized race strength minus the model's prior expectation at each circuit,
    empirical-Bayes shrunk toward 0, and add `track_weight × affinity` to the strength.
    Leak-free: predict() only sees affinities accumulated from strictly-prior races.

    VERDICT (2026-06-02): REJECTED, kept as a documented negative — NOT wired into the
    Predictor. Forward-chained over 168 races it made every metric worse, monotonically in
    track_weight (win log-loss 0.128 -> 0.130/0.134/0.139 at w=0.5/1.0/1.5; podium + top-pick
    likewise). At ~5-8 visits/circuit the team-circuit residual is dominated by race-day
    variance (SC/DNF/incidents), not stable car-track suitability, so it adds noise. The honest
    lever stays qualifying (post-quali the plain Kalman already converges toward the market).
    """

    def __init__(self, *, track_weight: float = 1.0, track_prior: float = 6.0, **kw):
        self.track_weight = track_weight
        self.track_prior = track_prior
        super().__init__(**kw)
        self.name = f"kalman+track(w={track_weight})"

    def reset(self) -> None:
        super().reset()
        self.track: dict[tuple[str, str], list[float]] = {}  # (team,circuit)->[sum,count]

    def _affinity(self, team: str, circuit: str) -> float:
        s, c = self.track.get((team, circuit), (0.0, 0.0))
        if c <= 0:
            return 0.0
        return (s / c) * (c / (c + self.track_prior))  # shrink toward 0 by sample size

    def predict(self, race: pl.DataFrame) -> dict[str, float]:
        base = super().predict(race)
        circ = race["circuit"][0] if "circuit" in race.columns else None
        if circ is None:
            return base
        rows = race.to_dicts()
        return {
            r["driver"]: base[r["driver"]]
            + self.track_weight * self._affinity(r["team"], circ)
            for r in rows
        }

    def update(self, race: pl.DataFrame) -> None:
        circ = race["circuit"][0] if "circuit" in race.columns else None
        if circ is not None:
            rows = race.to_dicts()
            for r in rows:
                self._seed(r["driver"], r["team"])
            # prior expectation (car+driver mu) vs realized finish, both z-scored.
            prior = [self.car[r["team"]][0] + self.drv[r["driver"]][0] for r in rows]
            pz = _z_faster(prior, invert=False)
            rz = _z_faster([float(r["finish_pos"]) for r in rows], invert=True)
            for r, p, rl in zip(rows, pz, rz):
                if p is None or rl is None:
                    continue
                key = (r["team"], circ)
                s, c = self.track.get(key, (0.0, 0.0))
                self.track[key] = [s + (rl - p), c + 1]  # residual = did better than expected
        super().update(race)
