"""Strengths -> probabilities, shared by every bake-off model.

Each model emits a per-driver latent "strength" (higher = faster). This module turns
strengths into calibrated win/podium/points probabilities via a Plackett-Luce Monte
Carlo (Gumbel-max sampling = exact PL), with:
  * a TEMPERATURE that flattens/sharpens the field — the single highest-ROI
    calibration knob (the agents' consensus; also the practical form of the
    Henery/Stern "discount favourites at lower placings" correction), and
  * optional per-driver DNF censoring.

Plus the Benter market-blend: combine model and market log-probabilities so we only
deviate from a sharp market where we have real signal.
"""

from __future__ import annotations

import numpy as np

_EPS = 1e-12


def strengths_to_probs(
    drivers: list[str],
    strengths: np.ndarray,
    *,
    temperature: float = 1.0,
    dnf_prob: np.ndarray | None = None,
    n_sims: int = 20_000,
    seed: int = 0,
) -> dict[str, dict[str, float]]:
    """Plackett-Luce Monte Carlo -> {driver: {win, podium, points}}.

    Gumbel-max trick: argsort(strength/T + Gumbel) is an exact draw from the
    Plackett-Luce order. Temperature T>1 spreads the field (less overconfident).
    """
    s = np.asarray(strengths, dtype=np.float64) / max(temperature, 1e-6)
    n = len(drivers)
    rng = np.random.default_rng(seed)
    wins = np.zeros(n)
    pod = np.zeros(n)
    pts = np.zeros(n)
    dnf_prob = (
        np.zeros(n) if dnf_prob is None else np.clip(np.asarray(dnf_prob), 0, 0.95)
    )
    for _ in range(n_sims):
        g = rng.gumbel(0.0, 1.0, n)
        score = s + g
        dnf = rng.random(n) < dnf_prob
        score = np.where(dnf, -1e9, score)
        order = np.argsort(-score)
        wins[order[0]] += 1
        pod[order[:3]] += 1
        pts[order[:10]] += 1
    return {
        d: {"win": wins[i] / n_sims, "podium": pod[i] / n_sims, "points": pts[i] / n_sims}
        for i, d in enumerate(drivers)
    }


def softmax(strengths: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    """Closed-form Plackett-Luce win probabilities (fast; for CLV checks)."""
    s = np.asarray(strengths, dtype=np.float64) / max(temperature, 1e-6)
    s = s - s.max()
    e = np.exp(s)
    return e / e.sum()


def benter_blend(
    p_model: np.ndarray,
    p_market: np.ndarray,
    alpha: float = 1.0,
    beta: float = 1.0,
) -> np.ndarray:
    """Benter market-blend: c_i ∝ exp(α·log p_model + β·log p_market), renormalized.

    α=1,β=0 -> pure model; α=0,β=1 -> pure market. Fit (α,β) on holdout to only
    deviate from the market where the model adds signal. Returns a probability vector.
    """
    lm = np.log(np.clip(p_model, _EPS, 1.0))
    lk = np.log(np.clip(p_market, _EPS, 1.0))
    z = alpha * lm + beta * lk
    z = z - z.max()
    e = np.exp(z)
    return e / e.sum()
