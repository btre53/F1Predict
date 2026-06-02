"""Quasi-steady-state (QSS) lap-time engine on a telemetry-derived line (brief 20, part B).

The implementable half of the optimal-control term structure (Perantoni-Limebeer / OpenLAP /
TUMFTM): reconstruct the track's curvature kappa(s) from a fastest lap's X/Y + distance, fit
the car's empirical g-g envelope (max lateral / forward / braking acceleration it actually
uses), then build a forward-backward velocity profile -- apex speed v = sqrt(a_lat_max/kappa)
at curvature peaks, integrated forward (traction/power limited) and backward (brake limited),
taking the min. Lap time = integral of ds/v, decomposed into corner / braking / straight time.

Everything here is on FREE FastF1 channels (Distance, Speed, X, Y at ~10 Hz); the g-g envelope
is *fit from the car's own telemetry* rather than assumed. This is the honest free-data version
of a QSS simulator: a reconstruction + decomposition tool (and Explainer content), validated by
how well the reconstructed velocity profile matches the actual speed trace. NOT wired into the
predictor unless it beats the lap-wise model (open question 2 in docs/science/20).

The minimum-curvature line ~ minimum-time line in corners (TUMFTM), so the driven line we read
from telemetry is already a good proxy for the optimal one.
"""

from __future__ import annotations

import json
import logging
import warnings
from functools import lru_cache
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
logging.getLogger("fastf1").setLevel(logging.ERROR)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
QSS_JSON = DATA_DIR / "qss_profiles.json"

# Empirical envelope percentile: the car's "limit" accel is the high-percentile of what it
# actually used (robust to noise/outliers in the finite-difference accelerations).
ENV_PCTL = 98.0
KAPPA_FLOOR = 1e-4  # 1/m; below this a segment is a straight (no corner speed limit)


def _fastest_trace(year: int, circuit: str) -> dict | None:
    """Distance(m)/Speed(m/s)/X/Y for the field-fastest lap (cached FastF1 telemetry)."""
    import fastf1
    from app.config import get_settings

    fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)
    try:
        s = fastf1.get_session(year, circuit, "Q")
        s.load(laps=True, telemetry=True, weather=False, messages=False)
        tel = s.laps.pick_fastest().get_telemetry()
    except Exception:
        return None
    d = tel["Distance"].to_numpy(dtype=float)
    v = tel["Speed"].to_numpy(dtype=float) / 3.6  # km/h -> m/s
    x = tel["X"].to_numpy(dtype=float)
    y = tel["Y"].to_numpy(dtype=float)
    m = np.isfinite(d) & np.isfinite(v) & np.isfinite(x) & np.isfinite(y)
    return {"dist": d[m], "speed": v[m], "x": x[m], "y": y[m]} if m.sum() > 200 else None


def _resample(trace: dict, step_m: float = 5.0) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Resample X/Y/Speed onto a uniform arc-length grid (FastF1 X/Y are in 1/10 m)."""
    d = trace["dist"]
    d = d - d[0]
    grid = np.arange(0, d[-1], step_m)
    x = np.interp(grid, d, trace["x"]) / 10.0  # 1/10 m -> m
    y = np.interp(grid, d, trace["y"]) / 10.0
    v = np.interp(grid, d, trace["speed"])
    return grid, x, y, v


def curvature(x: np.ndarray, y: np.ndarray, step_m: float) -> np.ndarray:
    """Path curvature kappa(s) = |x'y'' - y'x''| / (x'^2+y'^2)^1.5 (finite differences)."""
    dx = np.gradient(x, step_m)
    dy = np.gradient(y, step_m)
    ddx = np.gradient(dx, step_m)
    ddy = np.gradient(dy, step_m)
    num = np.abs(dx * ddy - dy * ddx)
    den = (dx * dx + dy * dy) ** 1.5 + 1e-9
    k = num / den
    # light smoothing (3-pt moving average) to tame 10 Hz position jitter
    return np.convolve(k, np.ones(3) / 3, mode="same")


def fit_envelope(grid: np.ndarray, v: np.ndarray, kappa: np.ndarray) -> dict:
    """Empirical g-g limits from the car's own telemetry: max lateral / forward / brake accel."""
    a_lat = v * v * kappa
    dv = np.gradient(v, grid)
    a_long = v * dv  # dv/dt = v dv/ds
    return {
        "a_lat_max": float(np.percentile(a_lat[np.isfinite(a_lat)], ENV_PCTL)),
        "a_acc_max": float(np.percentile(a_long[a_long > 0], ENV_PCTL)) if np.any(a_long > 0) else 5.0,
        "a_brake_max": float(-np.percentile(-a_long[a_long < 0], ENV_PCTL)) if np.any(a_long < 0) else -15.0,
        "v_max": float(np.percentile(v, 99.9)),
    }


def qss_profile(grid: np.ndarray, kappa: np.ndarray, env: dict) -> np.ndarray:
    """Forward-backward velocity profile over the g-g envelope (the QSS core)."""
    n = len(grid)
    step = grid[1] - grid[0]
    # corner-limited apex speed where there's real curvature; v_max on straights
    v_corner = np.where(kappa > KAPPA_FLOOR, np.sqrt(env["a_lat_max"] / np.maximum(kappa, KAPPA_FLOOR)), env["v_max"])
    v_corner = np.minimum(v_corner, env["v_max"])
    # forward pass: traction/power-limited acceleration out of corners
    vf = v_corner.copy()
    for i in range(1, n):
        vmax = np.sqrt(max(0.0, vf[i - 1] ** 2 + 2 * env["a_acc_max"] * step))
        vf[i] = min(v_corner[i], vmax)
    # backward pass: braking limit into corners
    vb = vf.copy()
    for i in range(n - 2, -1, -1):
        vmax = np.sqrt(max(0.0, vb[i + 1] ** 2 + 2 * abs(env["a_brake_max"]) * step))
        vb[i] = min(vf[i], vmax)
    return vb


def analyze(year: int, circuit: str, step_m: float = 5.0) -> dict | None:
    """Reconstruct the QSS profile for a circuit; validate it against the real speed trace."""
    trace = _fastest_trace(year, circuit)
    if trace is None:
        return None
    grid, x, y, v_act = _resample(trace, step_m)
    kappa = curvature(x, y, step_m)
    env = fit_envelope(grid, v_act, kappa)
    v_qss = qss_profile(grid, kappa, env)

    # validation: how well does the reconstructed profile match reality?
    corr = float(np.corrcoef(v_qss, v_act)[0, 1])
    rmse_kmh = float(np.sqrt(np.mean((v_qss - v_act) ** 2)) * 3.6)
    lap_qss = float(np.sum(step_m / np.maximum(v_qss, 1.0)))
    lap_act = float(np.sum(step_m / np.maximum(v_act, 1.0)))
    # decomposition by segment type (corner vs straight by curvature)
    corner = kappa > KAPPA_FLOOR
    t_seg = step_m / np.maximum(v_qss, 1.0)
    return {
        "circuit": circuit, "year": year, "lap_m": round(float(grid[-1])),
        "envelope": {k: round(val, 2) for k, val in env.items()},
        "validation": {"speed_corr": round(corr, 3), "speed_rmse_kmh": round(rmse_kmh, 1),
                       "lap_time_qss_s": round(lap_qss, 2), "lap_time_actual_s": round(lap_act, 2)},
        "decomposition": {
            "corner_time_pct": round(100 * float(t_seg[corner].sum() / t_seg.sum()), 1),
            "straight_time_pct": round(100 * float(t_seg[~corner].sum() / t_seg.sum()), 1),
            "n_corners": int(np.sum(np.diff(corner.astype(int)) == 1)),
        },
    }


@lru_cache(maxsize=1)
def _profiles() -> dict:
    if QSS_JSON.exists():
        return json.loads(QSS_JSON.read_text())
    return {}


def profile_for(circuit: str, year: int = 2024) -> dict:
    """Cached QSS profile for the Explainer ({} if not built)."""
    return _profiles().get(circuit, {})


# Circuits to precompute (spanning corner types); reuse the car-DNA sample.
SAMPLE = ["Monaco", "Hungarian", "Singapore", "British", "Belgian", "Japanese",
          "Italian", "Azerbaijan", "Bahrain", "Spanish"]


def build(year: int = 2024) -> dict:
    out: dict = {}
    for c in SAMPLE:
        r = analyze(year, c)
        if r:
            out[c] = r
            v = r["validation"]
            print(f"  {c:14s} corr={v['speed_corr']:.3f} rmse={v['speed_rmse_kmh']:4.1f}km/h "
                  f"lap qss={v['lap_time_qss_s']:.1f}s act={v['lap_time_actual_s']:.1f}s "
                  f"corner={r['decomposition']['corner_time_pct']:.0f}%")
    QSS_JSON.write_text(json.dumps(out, indent=2))
    print(f"\n  -> wrote {QSS_JSON} ({len(out)} circuits)")
    return out


if __name__ == "__main__":
    build()
