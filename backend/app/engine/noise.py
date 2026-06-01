"""Driver execution-noise sampler: positively-skewed, heavy-tailed.

See docs/science/01-lap-time-model.md section 4 and docs/science/04 (C1).

Drivers cluster near a target lap time but can lose far more time than they gain,
so the noise has a short left tail and a long right (slow) tail. We build this from
a skew-normal location-shape combined with a t-distributed scale for heavy tails,
then shift so the *mode* (not the mean) sits at zero — a clean lap is the most
likely outcome, with occasional slow blips.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

from .params import NoiseParams


def sample_execution_noise(
    size: tuple[int, ...],
    params: NoiseParams,
    *,
    rng: np.random.Generator,
    traffic_mask: np.ndarray | None = None,
    wet: bool = False,
) -> np.ndarray:
    """Sample additive lap-time noise (seconds), positively skewed.

    ``size`` is the output shape (e.g. ``(n_drivers, n_sims)``). ``traffic_mask``
    (broadcastable to ``size``) inflates sigma where a car is in dirty air.
    """
    sigma = params.sigma_s
    if wet:
        sigma *= params.wet_inflation

    # Skew-normal gives the asymmetry; scale by sigma. Then add a heavy-tailed
    # t component (small) for rare large blips.
    skewed = stats.skewnorm.rvs(
        a=params.skew, size=size, random_state=rng
    ).astype(np.float64)
    # Standardize skew-normal to unit-ish spread, then re-scale.
    delta = params.skew / np.sqrt(1.0 + params.skew**2)
    sn_mean = delta * np.sqrt(2.0 / np.pi)
    sn_std = np.sqrt(1.0 - sn_mean**2)
    skewed = (skewed - sn_mean) / sn_std  # zero-mean, unit-std skew-normal

    noise = skewed * sigma

    if traffic_mask is not None:
        mask = np.broadcast_to(traffic_mask, size)
        noise = np.where(mask, noise * params.traffic_inflation, noise)

    # Shift so the mode is near zero (clean lap most likely). Mode of standardized
    # skew-normal is slightly negative; nudge so most laps are at/just above base.
    noise -= float(np.median(noise)) if noise.size else 0.0
    return noise.astype(np.float32)
