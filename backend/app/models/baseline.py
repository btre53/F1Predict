"""Baseline models: 'is it just the grid (and qualifying)?'

These ignore history and use only this weekend's grid + qualifying pace, per-race
z-scored so a single global temperature is meaningful. If the rating/Kalman models
can't beat these, the signal is mostly the grid — the most important thing to learn
first (the panel's unanimous warning).
"""

from __future__ import annotations

import numpy as np
import polars as pl


def _zscore(vals: list[float]) -> list[float]:
    a = np.array(vals, dtype=float)
    sd = a.std()
    return list((a - a.mean()) / sd) if sd > 1e-9 else list(np.zeros_like(a))


class _Stateless:
    """Baselines carry no state: reset/update are no-ops."""

    def reset(self) -> None:
        pass

    def update(self, race: pl.DataFrame) -> None:
        pass


class GridBaseline(_Stateless):
    name = "baseline:grid"

    def predict(self, race: pl.DataFrame) -> dict[str, float]:
        rows = [r for r in race.to_dicts() if r["grid"] is not None]
        z = _zscore([float(r["grid"]) for r in rows])
        return {r["driver"]: -zi for r, zi in zip(rows, z)}  # lower grid = faster


class QualiBaseline(_Stateless):
    name = "baseline:quali"

    def predict(self, race: pl.DataFrame) -> dict[str, float]:
        rows = race.to_dicts()
        gaps = [r["quali_gap_pct"] for r in rows if r["quali_gap_pct"] is not None]
        fill = (max(gaps) * 1.5) if gaps else 0.03
        g = [float(r["quali_gap_pct"]) if r["quali_gap_pct"] is not None else fill for r in rows]
        z = _zscore(g)
        return {r["driver"]: -zi for r, zi in zip(rows, z)}  # smaller gap = faster


class GridQualiBaseline(_Stateless):
    name = "baseline:grid+quali"

    def __init__(self, w_grid: float = 1.0, w_quali: float = 1.0):
        self.w_grid, self.w_quali = w_grid, w_quali

    def predict(self, race: pl.DataFrame) -> dict[str, float]:
        rows = race.to_dicts()
        gaps = [r["quali_gap_pct"] for r in rows if r["quali_gap_pct"] is not None]
        fill = (max(gaps) * 1.5) if gaps else 0.03
        grid = [float(r["grid"]) if r["grid"] is not None else 20.0 for r in rows]
        gap = [float(r["quali_gap_pct"]) if r["quali_gap_pct"] is not None else fill for r in rows]
        zg, zq = _zscore(grid), _zscore(gap)
        return {
            r["driver"]: -(self.w_grid * zgi + self.w_quali * zqi)
            for r, zgi, zqi in zip(rows, zg, zq)
        }
