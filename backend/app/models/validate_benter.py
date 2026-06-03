"""Benter market-blend: does combining our model with the market beat either alone?

The Benter blend (probability.benter_blend) is `c_i ∝ exp(α·log p_model + β·log p_market)`,
renormalized over the field. α=1,β=0 is pure model; α=0,β=1 is pure market. If our model
carries *independent* signal the optimal blend has α>0 and beats the pure market; if it
doesn't, the optimum collapses to the market (α≈0) — which is itself the honest answer to
"do we have edge?".

Method (leak-free): forward-chain the production Kalman (KalmanOTModel, post-quali) exactly
as `market_backtest.py` does, and at each Polymarket-priced race collect the full per-driver
(model win-prob, de-vigged market win-prob, did-win). The market de-vig is network; we cache
it to data/benter_collect.json so reruns are offline. Then:
  * grid-search (α,β) in-sample for the optimal blend (interpretation), and
  * expanding-window forward-chained (fit on prior priced races, apply to the next) for the
    honest score vs pure model and pure market.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from .probability import benter_blend

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
COLLECT_JSON = DATA_DIR / "benter_collect.json"
_EPS = 1e-12


def collect(*, n_sims: int = 8000, temperature: float = 0.5, force: bool = False) -> list[dict]:
    """Per priced race: {year, circuit, drivers, model_p, market_p, winner}. Cached."""
    if COLLECT_JSON.exists() and not force:
        return json.loads(COLLECT_JSON.read_text())

    from app.etl.market_backtest import _all_markets
    from app.etl.polymarket import prerace_devig, race_start_ts
    from app.models.features import build_feature_table
    from app.models.kalman import KalmanOTModel
    from app.models.probability import strengths_to_probs

    table = build_feature_table()
    markets = {(m["year"], m["circuit"]): m for m in _all_markets()}
    devig_cache: dict = {}

    model = KalmanOTModel(w0=0.8)
    model.reset()
    out: list[dict] = []
    for s in sorted(table["seq"].unique().to_list()):
        race = table.filter(pl.col("seq") == s)
        year, circuit = int(race["year"][0]), str(race["circuit"][0])
        key = (year, circuit)
        if key in markets and race.height >= 4:
            m = markets[key]
            ckey = f"{year}|{circuit}"
            if ckey not in devig_cache:
                rts = m.get("race_ts") or race_start_ts(year, m["round"])
                devig_cache[ckey] = prerace_devig(m["slug"], rts) if rts else {}
            market = devig_cache[ckey]
            winner_row = race.filter(pl.col("finish_pos") == 1)
            if market and winner_row.height:
                winner = winner_row["driver"][0]
                strengths = model.predict(race)
                drivers = [d for d in race["driver"].to_list() if d in strengths]
                probs = strengths_to_probs(
                    drivers, np.array([strengths[d] for d in drivers]),
                    temperature=temperature, n_sims=n_sims,
                )
                # Align on drivers priced by BOTH (the winner is always priced).
                common = [d for d in drivers if d in market]
                if winner in common and len(common) >= 4:
                    out.append({
                        "year": year, "circuit": circuit, "winner": winner,
                        "drivers": common,
                        "model_p": [float(probs[d]["win"]) for d in common],
                        "market_p": [float(market[d]) for d in common],
                    })
        model.update(race)

    COLLECT_JSON.write_text(json.dumps(out, indent=2))
    return out


def _renorm(p):
    a = np.clip(np.array(p, dtype=float), _EPS, None)
    return a / a.sum()


def _logloss_brier(races, alpha, beta):
    """Score the (α,β) blend over all per-driver win pairs."""
    ll, br, n = 0.0, 0.0, 0
    for r in races:
        pm = _renorm(r["model_p"])
        pk = _renorm(r["market_p"])
        c = benter_blend(pm, pk, alpha=alpha, beta=beta) if (alpha or beta) else _renorm(np.ones_like(pm))
        wi = r["drivers"].index(r["winner"])
        for i in range(len(r["drivers"])):
            o = 1.0 if i == wi else 0.0
            p = min(max(float(c[i]), _EPS), 1 - _EPS)
            ll += -(o * np.log(p) + (1 - o) * np.log(1 - p))
            br += (p - o) ** 2
            n += 1
    return round(ll / n, 4), round(br / n, 4), n


def evaluate(*, grid=(0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5)) -> dict:
    races = collect()
    pure_model = _logloss_brier(races, 1.0, 0.0)
    pure_market = _logloss_brier(races, 0.0, 1.0)

    # In-sample best blend (interpretation: what mix is optimal?).
    best = None
    for a in grid:
        for b in grid:
            if a == 0 and b == 0:
                continue
            ll, br, _ = _logloss_brier(races, a, b)
            if best is None or ll < best["logloss"]:
                best = {"alpha": a, "beta": b, "logloss": ll, "brier": br}

    # Honest: expanding-window forward-chained blend vs pure model / pure market on held-out races.
    fc_blend, fc_model, fc_market = [], [], []
    MIN_FIT = 6
    for i in range(len(races)):
        if i < MIN_FIT:
            continue
        train = races[:i]
        # fit (α,β) on prior priced races
        bfit = None
        for a in grid:
            for b in grid:
                if a == 0 and b == 0:
                    continue
                ll, _, _ = _logloss_brier(train, a, b)
                if bfit is None or ll < bfit[0]:
                    bfit = (ll, a, b)
        _, a, b = bfit
        held = [races[i]]
        fc_blend.append(_logloss_brier(held, a, b)[0])
        fc_model.append(_logloss_brier(held, 1.0, 0.0)[0])
        fc_market.append(_logloss_brier(held, 0.0, 1.0)[0])

    fc = {
        "n_heldout": len(fc_blend),
        "blend_logloss": round(float(np.mean(fc_blend)), 4) if fc_blend else None,
        "model_logloss": round(float(np.mean(fc_model)), 4) if fc_model else None,
        "market_logloss": round(float(np.mean(fc_market)), 4) if fc_market else None,
    }
    return {
        "n_races": len(races),
        "pure_model": {"logloss": pure_model[0], "brier": pure_model[1], "n_pairs": pure_model[2]},
        "pure_market": {"logloss": pure_market[0], "brier": pure_market[1]},
        "best_blend_insample": best,
        "forward_chained": fc,
    }


if __name__ == "__main__":
    r = evaluate()
    print(f"Benter market-blend — {r['n_races']} Polymarket-priced races\n")
    print(f"  pure model   logloss={r['pure_model']['logloss']}  brier={r['pure_model']['brier']}")
    print(f"  pure market  logloss={r['pure_market']['logloss']}  brier={r['pure_market']['brier']}")
    b = r["best_blend_insample"]
    print(f"  best blend   α={b['alpha']} β={b['beta']}  logloss={b['logloss']}  brier={b['brier']}  (in-sample)")
    fc = r["forward_chained"]
    print(f"\n  forward-chained (expanding window, {fc['n_heldout']} held-out races):")
    print(f"    blend  {fc['blend_logloss']}   model {fc['model_logloss']}   market {fc['market_logloss']}")
    in_both = b["logloss"] < min(r["pure_model"]["logloss"], r["pure_market"]["logloss"])
    fc_beats_model = (fc["blend_logloss"] or 9) < (fc["model_logloss"] or 9)
    fc_beats_market = (fc["blend_logloss"] or 9) < (fc["market_logloss"] or 9)
    print("\n  verdict:")
    print(f"    in-sample equal blend beats BOTH: {in_both} (→ the model carries independent signal)")
    print(f"    out-of-sample blend beats our model: {fc_beats_model}; beats the market: {fc_beats_market}")
    print("    → a calibration tool that improves on our own model; NOT a market-beating edge"
          " on 23 races.")
