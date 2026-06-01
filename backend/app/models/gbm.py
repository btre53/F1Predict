"""LightGBM learning-to-rank model (the discriminative-ML corner of the bake-off).

A LambdaRank GBDT that optimizes the finishing ORDER directly (grouped by race) from
pre-race features (grid, quali gap, FP long-run pace). Forward-chained: each race it
refits on all prior races, so it's leak-free, and heavily regularized because the
effective sample is ~tens of races (the overfitting trap the prior-art survey flagged).

Falls back to a grid prior until there's enough history to train.
"""

from __future__ import annotations

import numpy as np
import polars as pl


def _features(rows: list[dict]) -> np.ndarray:
    gaps = [r["quali_gap_pct"] for r in rows if r["quali_gap_pct"] is not None]
    gfill = (max(gaps) * 1.5) if gaps else 0.03
    fps = [r["fp_pace_pct"] for r in rows if r["fp_pace_pct"] is not None]
    ffill = (max(fps) * 1.5) if fps else 0.05
    return np.array(
        [
            [
                float(r["grid"]) if r["grid"] is not None else 20.0,
                float(r["quali_gap_pct"]) if r["quali_gap_pct"] is not None else gfill,
                float(r["fp_pace_pct"]) if r["fp_pace_pct"] is not None else ffill,
            ]
            for r in rows
        ]
    )


class GBMModel:
    def __init__(self, min_train_races: int = 8, num_boost_round: int = 80):
        self.name = "lightgbm"
        self.min_train_races = min_train_races
        self.num_boost_round = num_boost_round
        self.reset()

    def reset(self) -> None:
        self.history: list[list[dict]] = []  # one entry per race

    def update(self, race: pl.DataFrame) -> None:
        self.history.append(race.to_dicts())

    def predict(self, race: pl.DataFrame) -> dict[str, float]:
        rows = race.to_dicts()
        if len(self.history) < self.min_train_races:
            # Cold start: lean on the grid until there's data to learn from.
            return {
                r["driver"]: -(float(r["grid"]) if r["grid"] is not None else 20.0)
                for r in rows
            }
        import lightgbm as lgb

        X_parts, y, group = [], [], []
        for hr in self.history:
            X_parts.append(_features(hr))
            maxpos = max(r["finish_pos"] for r in hr)
            y.extend(int(maxpos - r["finish_pos"]) for r in hr)  # higher = better
            group.append(len(hr))
        ds = lgb.Dataset(np.vstack(X_parts), label=np.array(y), group=group)
        params = {
            "objective": "lambdarank",
            "metric": "ndcg",
            "num_leaves": 15,
            "min_data_in_leaf": 20,
            "max_depth": 4,
            "learning_rate": 0.05,
            "lambda_l2": 1.0,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "verbose": -1,
        }
        model = lgb.train(params, ds, num_boost_round=self.num_boost_round)
        scores = model.predict(_features(rows))
        return {r["driver"]: float(s) for r, s in zip(rows, scores)}
