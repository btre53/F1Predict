"""Pole-market backtest (#28): our pre-quali grid model vs Polymarket's pole price.

Qualifying is the most deterministic part of an F1 weekend (the pole sitter is far more
predictable than the winner), so if there is any market gap to find, the pole market is the best
candidate. We test it honestly.

For every race with a Polymarket DRIVER pole market we compare:
- MODEL: the pre-quali Kalman pole probability (car μ + driver μ, NO this-weekend quali fused),
  Plackett-Luce sampled at the qualifying temperature -- exactly `predict_quali`. Forward-chained,
  so each race uses only strictly-prior races (leak-free).
- MARKET: the de-vigged Polymarket pole price snapshotted just BEFORE qualifying starts (the
  leak-free cutoff -- the market hasn't seen the session either).
...vs who actually took pole (official grid == 1).

HONEST CAVEAT: Polymarket only began per-race pole markets in late 2025, so the sample is small
(~late-2025 + early-2026). This is a "we checked what exists" probe, not a large-n verdict.

Writes data/quali_market_backtest.json. Network-dependent (Gamma + CLOB); run offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from app.etl import backtest as bt
from app.etl.polymarket import prerace_devig, season_pole_markets
from app.models.features import build_feature_table
from app.models.kalman import KalmanModel
from app.models.predict_quali import (
    QUALI_TEMPERATURE,
    _pre_quali_strength,
    grid_distribution,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
QUALI_MARKET_JSON = DATA_DIR / "quali_market_backtest.json"


def load_quali_market_backtest() -> dict | None:
    if QUALI_MARKET_JSON.exists():
        return json.loads(QUALI_MARKET_JSON.read_text())
    return None


def _pole_markets() -> list[dict]:
    out: list[dict] = []
    for y in (2025, 2026):
        out += [{**m, "year": y} for m in season_pole_markets(y)]
    return out


def run_quali_market_backtest(temperature: float = QUALI_TEMPERATURE,
                              n_sims: int = 6000, min_history: int = 20) -> dict:
    table = build_feature_table()
    markets = {(m["year"], m["circuit"]): m for m in _pole_markets()}
    devig_cache: dict[tuple, dict] = {}

    model = KalmanModel(net_dnf=True)
    model.reset()
    seen = 0
    model_pairs: list[tuple[float, int]] = []
    market_pairs: list[tuple[float, int]] = []
    per_race: list[dict] = []

    for s in sorted(table["seq"].unique().to_list()):
        race = table.filter(pl.col("seq") == s)
        year, circuit = int(race["year"][0]), str(race["circuit"][0])
        key = (year, circuit)
        rows = race.to_dicts()
        drivers = [r["driver"] for r in rows if r.get("grid") is not None]
        if (key in markets and seen >= min_history and len(drivers) >= 6):
            m = markets[key]
            if key not in devig_cache:
                devig_cache[key] = prerace_devig(m["slug"], m["quali_ts"])
            market = devig_cache[key]
            rmap = {r["driver"]: r for r in rows}
            actual_pole = min(drivers, key=lambda d: rmap[d]["grid"])
            if market:
                team_of = {r["driver"]: (r["team"] or "") for r in rows}
                strn = _pre_quali_strength(model, drivers, team_of)
                _dist, pole = grid_distribution(drivers, strn, temperature=temperature,
                                                n_sims=n_sims, seed=1)
                # Restrict to drivers the market priced, so both score the same field.
                for drv, mkt_p in market.items():
                    if drv not in pole:
                        continue
                    o = int(drv == actual_pole)
                    market_pairs.append((mkt_p, o))
                    model_pairs.append((pole.get(drv, 0.0), o))
                mkt_fav = max(market, key=market.get)
                mdl_fav = max(pole, key=pole.get)
                per_race.append({
                    "year": year, "circuit": circuit, "pole": actual_pole,
                    "market_fav": mkt_fav, "market_fav_p": round(market[mkt_fav], 3),
                    "market_p_pole": round(market.get(actual_pole, 0.0), 3),
                    "model_fav": mdl_fav, "model_fav_p": round(pole[mdl_fav], 3),
                    "model_p_pole": round(pole.get(actual_pole, 0.0), 3),
                    "market_hit": mkt_fav == actual_pole, "model_hit": mdl_fav == actual_pole,
                })
        model.update(race)
        seen += 1

    out = {
        "n_races": len(per_race),
        "temperature": temperature,
        "model_pole": bt._score(model_pairs),
        "market_pole": bt._score(market_pairs),
        "model_top_pick_accuracy": round(_hit_rate(per_race, "model_hit"), 3),
        "market_top_pick_accuracy": round(_hit_rate(per_race, "market_hit"), 3),
        "agree_on_favourite": round(
            (sum(1 for p in per_race if p["model_fav"] == p["market_fav"]) / len(per_race))
            if per_race else 0.0, 3),
        "per_race": per_race,
    }
    QUALI_MARKET_JSON.write_text(json.dumps(out, indent=2))
    return out


def _hit_rate(per_race: list[dict], key: str) -> float:
    return (sum(1 for p in per_race if p[key]) / len(per_race)) if per_race else 0.0


if __name__ == "__main__":
    r = run_quali_market_backtest()
    print(f"Pole model vs Polymarket — {r['n_races']} races (late-2025 + 2026 overlap)")
    if r["n_races"]:
        print(f"  pole Brier:  model {r['model_pole']['brier']}  vs  market {r['market_pole']['brier']}")
        print(f"  top-pick:    model {r['model_top_pick_accuracy']:.0%}  vs  market {r['market_top_pick_accuracy']:.0%}")
        print(f"  agree on favourite: {r['agree_on_favourite']:.0%}")
        for p in r["per_race"]:
            print(f"  {p['year']} {p['circuit']:12s} pole {p['pole']:3s} | "
                  f"mkt {p['market_fav']:3s} {p['market_fav_p']:.0%} | "
                  f"model {p['model_fav']:3s} {p['model_fav_p']:.0%}")
    print(f"  -> wrote {QUALI_MARKET_JSON}")
