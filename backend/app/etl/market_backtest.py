"""Real model-vs-market backtest: our win probabilities vs Polymarket's.

For each 2024 race that had a Polymarket winner market (coverage began at the 2024
British GP — 11 races overlap our data), we compare three things against the actual
result: the **market's** de-vigged pre-race win probabilities, **our model's** win
probabilities, and who each one favoured. This is the genuine "do we have edge?"
test — and an honest one, because the market is a strong, well-calibrated opponent.

Writes data/market_backtest.json. Network-dependent (Gamma + CLOB + Jolpica), run
offline like the other ETL steps.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from app.etl import backtest as bt
from app.etl.polymarket import MARKETS_2024, prerace_devig, race_start_ts

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
MARKET_BACKTEST_JSON = DATA_DIR / "market_backtest.json"


def load_market_backtest() -> dict | None:
    if MARKET_BACKTEST_JSON.exists():
        return json.loads(MARKET_BACKTEST_JSON.read_text())
    return None


def run_market_backtest(n_sims: int = 4000) -> dict:
    full = pl.read_parquet(LAPS_PARQUET).filter(pl.col("session_name") == "R")
    strat_cache: dict = {}
    model_pairs: list[tuple[float, int]] = []
    market_pairs: list[tuple[float, int]] = []
    per_race: list[dict] = []

    for m in MARKETS_2024:
        circuit, rnd = m["circuit"], m["round"]
        race = full.filter(
            (pl.col("circuit") == circuit) & (pl.col("year") == 2024)
        )
        if race.height == 0:
            continue
        actual = bt._actual_finish(race)
        if not actual:
            continue
        winner = min(actual, key=actual.get)

        rts = race_start_ts(2024, rnd)
        market = prerace_devig(m["slug"], rts) if rts else {}
        if not market:
            continue

        model_out = bt._predict_race(
            circuit, 2024, full, race, n_sims=n_sims, strat_cache=strat_cache
        )
        model = {d: o.win_pct for d, o in model_out.items()} if model_out else {}

        # Head-to-head on the drivers the market actually priced (the contenders).
        for drv, mkt_p in market.items():
            o = int(drv == winner)
            market_pairs.append((mkt_p, o))
            model_pairs.append((model.get(drv, 0.0), o))

        mkt_fav = max(market, key=market.get)
        mdl_fav = max(model, key=model.get) if model else None
        per_race.append(
            {
                "circuit": circuit,
                "winner": winner,
                "market_fav": mkt_fav,
                "market_fav_p": round(market[mkt_fav], 3),
                "market_p_winner": round(market.get(winner, 0.0), 3),
                "model_fav": mdl_fav,
                "model_fav_p": round(model.get(mdl_fav, 0.0), 3) if mdl_fav else None,
                "model_p_winner": round(model.get(winner, 0.0), 3),
                "market_hit": mkt_fav == winner,
                "model_hit": mdl_fav == winner,
            }
        )

    out = {
        "n_races": len(per_race),
        "n_sims": n_sims,
        "model_win": bt._score(model_pairs),
        "market_win": bt._score(market_pairs),
        "model_top_pick_accuracy": round(
            _hit_rate(per_race, "model_hit"), 3
        ),
        "market_top_pick_accuracy": round(
            _hit_rate(per_race, "market_hit"), 3
        ),
        "per_race": per_race,
    }
    MARKET_BACKTEST_JSON.write_text(json.dumps(out, indent=2))
    return out


def _hit_rate(per_race: list[dict], key: str) -> float:
    return (sum(1 for p in per_race if p[key]) / len(per_race)) if per_race else 0.0


if __name__ == "__main__":
    r = run_market_backtest()
    print(f"Model vs Market — {r['n_races']} races (2024 Polymarket overlap)")
    print(
        f"  win Brier:  model {r['model_win']['brier']}  vs  market {r['market_win']['brier']}"
    )
    print(
        f"  top-pick:   model {r['model_top_pick_accuracy']:.0%}  vs  market {r['market_top_pick_accuracy']:.0%}"
    )
    for p in r["per_race"]:
        print(
            f"  {p['circuit']:14s} won {p['winner']:3s} | "
            f"mkt {p['market_fav']:3s} {p['market_fav_p']:.0%} | "
            f"model {p['model_fav']:3s} {p['model_fav_p']:.0%}"
        )
    print(f"  -> wrote {MARKET_BACKTEST_JSON}")
