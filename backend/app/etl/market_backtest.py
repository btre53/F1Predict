"""Real model-vs-market backtest: our win probabilities vs Polymarket's.

For every race with a Polymarket winner market — the 2024 set (coverage began at the
2024 British GP) plus the 2025/26 markets derived from the schedule — we compare the
**market's** de-vigged pre-race win probabilities against **our model's**, and who each
favoured, vs the actual result. The market is a strong, well-calibrated opponent, so
this is the honest "do we have edge?" test.

The model is the **production Kalman** (`KalmanOTModel`), run **forward-chained** so each
race is predicted using only strictly-prior races (leak-free) — with that race's real
qualifying fused (post-quali), matching what the market's pre-race price already knows.
This is the same engine that powers the Predictor, not the old pooled mechanistic sim.

Writes data/market_backtest.json. Network-dependent (Gamma + CLOB), run offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from app.etl import backtest as bt
from app.etl.polymarket import (
    MARKETS_2024,
    prerace_devig,
    race_start_ts,
    season_winner_markets,
)
from app.models.features import build_feature_table
from app.models.kalman import KalmanOTModel
from app.models.probability import benter_blend, strengths_to_probs

# Fixed conservative blend weight — the in-sample optimum (brief 23). NOT re-fit per request
# (the (alpha,beta) fit is too noisy at n~23 to bank, so we hard-code the documented value).
BENTER_ALPHA = BENTER_BETA = 0.75

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
MARKET_BACKTEST_JSON = DATA_DIR / "market_backtest.json"


def load_market_backtest() -> dict | None:
    if MARKET_BACKTEST_JSON.exists():
        return json.loads(MARKET_BACKTEST_JSON.read_text())
    return None


def _all_markets() -> list[dict]:
    """Every Polymarket winner market we can score: the 2024 set (legacy slugs) + the
    2025/26 seasons derived from the schedule (new f1-...-winner-<date> slugs)."""
    markets = [{**m, "year": 2024, "race_ts": None} for m in MARKETS_2024]
    for y in (2025, 2026):
        markets += [{**m, "year": y} for m in season_winner_markets(y)]
    return markets


def run_market_backtest(n_sims: int = 6000, temperature: float = 0.5) -> dict:
    table = build_feature_table()
    # (year, circuit) -> resolved market (slug + race_ts) for every priced race.
    markets = {(m["year"], m["circuit"]): m for m in _all_markets()}
    # Cache the market de-vig once per race (network), reused as we reach it forward-chained.
    devig_cache: dict[tuple, dict] = {}

    model = KalmanOTModel(w0=0.8)
    model.reset()
    model_pairs: list[tuple[float, int]] = []
    market_pairs: list[tuple[float, int]] = []
    blend_pairs: list[tuple[float, int]] = []   # Benter model·market blend (calibration aid, brief 23)
    per_race: list[dict] = []

    for s in sorted(table["seq"].unique().to_list()):
        race = table.filter(pl.col("seq") == s)
        year, circuit = int(race["year"][0]), str(race["circuit"][0])
        key = (year, circuit)
        if key in markets and race.height >= 4:
            m = markets[key]
            if key not in devig_cache:
                rts = m.get("race_ts") or race_start_ts(year, m["round"])
                devig_cache[key] = prerace_devig(m["slug"], rts) if rts else {}
            market = devig_cache[key]
            winner_row = race.filter(pl.col("finish_pos") == 1)
            if market and winner_row.height:
                winner = winner_row["driver"][0]
                # Post-quali Kalman (the feature table carries this race's quali + grid),
                # forward-chained: predict BEFORE folding the result in below.
                strengths = model.predict(race)
                drivers = [d for d in race["driver"].to_list() if d in strengths]
                probs = strengths_to_probs(
                    drivers, np.array([strengths[d] for d in drivers]),
                    temperature=temperature, n_sims=n_sims,
                )
                model_p = {d: probs[d]["win"] for d in drivers}
                # Benter blend over the drivers BOTH price (renormalised within that field).
                common = [d for d in market if d in model_p]
                blend_p: dict[str, float] = {}
                if len(common) >= 2:
                    bp = benter_blend(
                        np.array([model_p[d] for d in common]),
                        np.array([market[d] for d in common]),
                        alpha=BENTER_ALPHA, beta=BENTER_BETA,
                    )
                    blend_p = {d: float(bp[i]) for i, d in enumerate(common)}
                for drv, mkt_p in market.items():
                    o = int(drv == winner)
                    market_pairs.append((mkt_p, o))
                    model_pairs.append((model_p.get(drv, 0.0), o))
                    if drv in blend_p:
                        blend_pairs.append((blend_p[drv], o))
                mkt_fav = max(market, key=market.get)
                mdl_fav = max(model_p, key=model_p.get) if model_p else None
                per_race.append({
                    "year": year, "circuit": circuit, "winner": winner,
                    "market_fav": mkt_fav, "market_fav_p": round(market[mkt_fav], 3),
                    "market_p_winner": round(market.get(winner, 0.0), 3),
                    "model_fav": mdl_fav,
                    "model_fav_p": round(model_p.get(mdl_fav, 0.0), 3) if mdl_fav else None,
                    "model_p_winner": round(model_p.get(winner, 0.0), 3),
                    "market_hit": mkt_fav == winner, "model_hit": mdl_fav == winner,
                })
        model.update(race)

    out = {
        "n_races": len(per_race),
        "n_sims": n_sims,
        "model_win": bt._score(model_pairs),
        "market_win": bt._score(market_pairs),
        "blend_win": bt._score(blend_pairs),
        "blend_alpha": BENTER_ALPHA,
        "blend_beta": BENTER_BETA,
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
    print(f"Model vs Market — {r['n_races']} races (2024-2026 Polymarket overlap, Kalman)")
    print(
        f"  win Brier:  model {r['model_win']['brier']}  vs  market {r['market_win']['brier']}"
        f"  vs  blend {r['blend_win']['brier']} (α=β={r['blend_alpha']})"
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
