"""Temperature-from-market (brief 30): does borrowing the MARKET's sharpness improve our calibration?

Our Plackett-Luce temperature sets how peaked the favourite is — a nuisance calibration parameter
we set by hand (T=0.5). The market's de-vigged prices imply a dispersion. This fits the single
sharpness exponent gamma that makes our win distribution match the market's (anchoring only the
SCALE, not the ranking), forward-chained and leak-free, and asks whether that beats our hand-set T
against the ACTUAL winners. Calibration, not edge.

Offline: reuses the cached per-priced-race collection (data/benter_collect.json) from validate_benter
-- {drivers, model_p (our win-probs), market_p (de-vigged), winner}. We work within the priced
contender set (renormalised), which is exactly the dispersion temperature governs.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .probability import fit_market_gamma, temper

_EPS = 1e-12
DATA_DIR = Path(__file__).resolve().parents[2] / "data"
COLLECT_JSON = DATA_DIR / "benter_collect.json"
T0 = 0.5   # the temperature model_p was generated at


def _norm(p):
    p = np.clip(np.asarray(p, dtype=np.float64), _EPS, None)
    return p / p.sum()


def _ll_brier(prob_vecs, win_idx):
    """Multiclass win log-loss (-log p_winner) + per-field Brier, averaged over races."""
    ll = np.mean([-np.log(max(_EPS, p[w])) for p, w in zip(prob_vecs, win_idx)])
    brier = np.mean([float(np.mean((p - np.eye(len(p))[w]) ** 2)) for p, w in zip(prob_vecs, win_idx)])
    return round(float(ll), 4), round(float(brier), 4)


def evaluate() -> dict:
    if not COLLECT_JSON.exists():
        raise FileNotFoundError("run app.models.validate_benter.collect() first (needs network once)")
    data = json.loads(COLLECT_JSON.read_text())
    races = []
    for r in data:
        if r["winner"] not in r["drivers"]:
            continue
        pm = _norm(r["model_p"]); qm = _norm(r["market_p"])
        wi = r["drivers"].index(r["winner"])
        races.append({"pm": pm, "qm": qm, "wi": wi})

    pm_list = [r["pm"] for r in races]
    qm_list = [r["qm"] for r in races]
    g_global = fit_market_gamma(pm_list, qm_list)

    # Forward-chained (expanding window): fit gamma on strictly-prior races, apply to this one.
    model_vecs, mtemp_vecs, market_vecs, wis = [], [], [], []
    for k, r in enumerate(races):
        g = fit_market_gamma(pm_list[:k], qm_list[:k]) if k >= 3 else 1.0
        model_vecs.append(r["pm"])
        mtemp_vecs.append(temper(r["pm"], g))
        market_vecs.append(r["qm"])
        wis.append(r["wi"])

    mdl = _ll_brier(model_vecs, wis)
    mtp = _ll_brier(mtemp_vecs, wis)
    mkt = _ll_brier(market_vecs, wis)
    return {
        "n_races": len(races),
        "gamma_global": round(g_global, 3),
        "implied_T": round(T0 / max(g_global, 1e-6), 3),
        "model_default": {"win_ll": mdl[0], "win_brier": mdl[1]},
        "market_temperature": {"win_ll": mtp[0], "win_brier": mtp[1]},
        "market": {"win_ll": mkt[0], "win_brier": mkt[1]},
    }


if __name__ == "__main__":
    r = evaluate()
    print(f"Temperature-from-market — {r['n_races']} priced races (win, within contender set)\n")
    print(f"  market-implied sharpness: gamma {r['gamma_global']}  -> effective T {r['implied_T']} "
          f"(our default {T0}; gamma<1 = we were over-confident)\n")
    print(f"  {'variant':>20} {'win_ll':>8} {'win_brier':>10}")
    print(f"  {'model (T=0.5)':>20} {r['model_default']['win_ll']:>8} {r['model_default']['win_brier']:>10}")
    print(f"  {'market-temperature':>20} {r['market_temperature']['win_ll']:>8} {r['market_temperature']['win_brier']:>10}")
    print(f"  {'market':>20} {r['market']['win_ll']:>8} {r['market']['win_brier']:>10}")
