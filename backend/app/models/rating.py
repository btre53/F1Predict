"""Plackett-Luce rating model: hierarchical car + driver strength, updated online.

Each entry's strength = car/constructor rating + (regularized) driver offset. One
Plackett-Luce gradient step per race updates both, with Glicko-style rating-deviation
(RD) controlling step size and uncertainty. The car carries the rating mass (~88% of
finishing-order variance is the constructor); the driver is a small offset isolated
by teammate deltas (same car -> car term cancels in the gradient).

Fully incremental: update(race) folds in one race in O(drivers) — exactly what a
post-race cronjob calls. Optionally fuses this weekend's qualifying gap as a
pre-race prior shift (the strongest single signal the pure rating misses).
"""

from __future__ import annotations

import numpy as np
import polars as pl


class _R:
    __slots__ = ("mu", "rd")

    def __init__(self, mu: float, rd: float):
        self.mu = mu
        self.rd = rd


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


class RatingModel:
    def __init__(
        self,
        *,
        lr_car: float = 0.15,
        lr_drv: float = 0.08,
        car_rd0: float = 0.80,
        drv_rd0: float = 0.30,
        car_rd_floor: float = 0.30,
        drv_rd_floor: float = 0.12,
        quali_weight: float = 0.0,
        grid_weight: float = 0.0,
        season_inflate: float = 1.25,
    ):
        self.lr_car, self.lr_drv = lr_car, lr_drv
        self.car_rd0, self.drv_rd0 = car_rd0, drv_rd0
        self.car_rd_floor, self.drv_rd_floor = car_rd_floor, drv_rd_floor
        self.quali_weight = quali_weight
        self.grid_weight = grid_weight
        self.season_inflate = season_inflate
        self.name = f"rating(q={quali_weight},g={grid_weight})"
        self.reset()

    def reset(self) -> None:
        self.car: dict[str, _R] = {}
        self.drv: dict[str, _R] = {}
        self._last_year: int | None = None

    def _seed(self, driver: str, team: str) -> None:
        self.car.setdefault(team, _R(0.0, self.car_rd0))
        self.drv.setdefault(driver, _R(0.0, self.drv_rd0))

    def _season_boundary(self, race: pl.DataFrame) -> None:
        """At a new season, inflate RD (more uncertain) + mild mean-reversion."""
        year = int(race["year"][0])
        if self._last_year is not None and year != self._last_year:
            for r in list(self.car.values()) + list(self.drv.values()):
                r.rd = min(self.car_rd0, r.rd * self.season_inflate)
                r.mu *= 0.9
        self._last_year = year

    def predict(self, race: pl.DataFrame) -> dict[str, float]:
        rows = race.to_dicts()
        out: dict[str, float] = {}
        for r in rows:
            self._seed(r["driver"], r["team"])
            out[r["driver"]] = self.car[r["team"]].mu + self.drv[r["driver"]].mu
        if self.quali_weight:
            gaps = [r["quali_gap_pct"] for r in rows if r["quali_gap_pct"] is not None]
            fill = (max(gaps) * 1.5) if gaps else 0.03
            g = np.array(
                [r["quali_gap_pct"] if r["quali_gap_pct"] is not None else fill for r in rows]
            )
            sd = g.std()
            z = (g - g.mean()) / sd if sd > 1e-9 else np.zeros_like(g)
            for r, zi in zip(rows, z):
                out[r["driver"]] += self.quali_weight * (-zi)
        if self.grid_weight:
            # Track position — the dominant signal for the rest-of-field order
            # (overtaking is hard). Lower grid -> higher strength.
            gr = np.array([float(r["grid"]) if r["grid"] is not None else 20.0 for r in rows])
            sd = gr.std()
            zg = (gr - gr.mean()) / sd if sd > 1e-9 else np.zeros_like(gr)
            for r, zi in zip(rows, zg):
                out[r["driver"]] += self.grid_weight * (-zi)
        return out

    def update(self, race: pl.DataFrame) -> None:
        self._season_boundary(race)
        rows = sorted(race.to_dicts(), key=lambda r: r["finish_pos"])
        drivers = [r["driver"] for r in rows]
        teams = {r["driver"]: r["team"] for r in rows}
        for d in drivers:
            self._seed(d, teams[d])
        mu = np.array([self.car[teams[d]].mu + self.drv[d].mu for d in drivers])

        # Plackett-Luce gradient: at each position the actual finisher gets +1,
        # the remaining field is discounted by its softmax weight.
        grad = np.zeros(len(drivers))
        for i in range(len(drivers) - 1):
            rem = slice(i, len(drivers))
            w = _softmax(mu[rem])
            grad[rem] -= w
            grad[i] += 1.0

        for d, g in zip(drivers, grad):
            cr, dr = self.car[teams[d]], self.drv[d]
            cr.mu += self.lr_car * (cr.rd**2) * g
            dr.mu += self.lr_drv * (dr.rd**2) * g
            cr.rd = max(self.car_rd_floor, cr.rd * 0.985)
            dr.rd = max(self.drv_rd_floor, dr.rd * 0.985)
