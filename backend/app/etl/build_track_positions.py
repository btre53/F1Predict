"""Precompute per-frame car positions from FastF1 position telemetry.

For each replayable race, samples every car's X/Y on a coarse common time grid (one
frame every FRAME_S seconds), projects onto the SAME 360x180 viewBox as the track
outline (so dots sit on the traced line), and caches to data/track_positions.json.

Telemetry is heavy, so we downsample hard and cache per (year, circuit). We draw only the
20 race cars (which keep their GPS feed even while circulating behind the safety car), so
the f1-race-replay trick of placing a GPS-less SC dot ahead of the leader isn't needed.

    uv run python -m app.etl.build_track_positions --circuit Bahrain --year 2024
    uv run python -m app.etl.build_track_positions --year 2024
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from app.engine.replay import available_races
from app.etl.build_track_outlines import fit_box, project
from app.etl.fastf1_client import _ensure_cache

OUT = Path(__file__).resolve().parents[2] / "data" / "track_positions.json"
FRAME_S = 2.0  # one frame every 2s of session time


def _resample(t_s: np.ndarray, vals: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Linear-interp a value series onto the common time grid (NaN outside range)."""
    order = np.argsort(t_s)
    t_s, vals = t_s[order], vals[order]
    out = np.interp(grid, t_s, vals, left=np.nan, right=np.nan)
    return out


def _build_one(fastf1, year: int, circuit: str) -> dict | None:
    """Return a positions payload for one race, or None if telemetry is unavailable."""
    s = fastf1.get_session(year, circuit, "R")
    s.load(telemetry=True, laps=True, weather=False, messages=False)

    fastest = s.laps.pick_fastest().get_telemetry()
    box = fit_box(fastest["X"].to_numpy(), fastest["Y"].to_numpy())

    # Clamp the frame grid to the racing window (lights-out -> chequered) so we don't
    # waste frames on the standing grid + slow-down lap.
    race_t0 = float(s.laps["LapStartTime"].min().total_seconds())
    race_t1 = float(s.laps["Time"].max().total_seconds())

    drivers = list(s.drivers)
    t0, t1 = None, None
    per_driver: dict[str, tuple] = {}
    for drv in drivers:
        try:
            pos = s.pos_data[drv]
        except Exception:  # noqa: BLE001
            continue
        if pos is None or len(pos) == 0 or "SessionTime" not in pos:
            continue
        sec = pos["SessionTime"].dt.total_seconds().to_numpy()
        if "Status" in pos:
            on = pos["Status"].to_numpy() == "OnTrack"
        else:
            on = np.ones(len(sec), bool)
        x = pos["X"].to_numpy(dtype=float)
        y = pos["Y"].to_numpy(dtype=float)
        x = np.where(on, x, np.nan)
        y = np.where(on, y, np.nan)
        code = s.get_driver(drv)["Abbreviation"]
        per_driver[code] = (sec, x, y)
        lo, hi = float(np.nanmin(sec)), float(np.nanmax(sec))
        t0 = lo if t0 is None else min(t0, lo)
        t1 = hi if t1 is None else max(t1, hi)

    if not per_driver or t0 is None:
        return None

    lo = max(t0, race_t0)
    hi = min(t1, race_t1) if race_t1 > race_t0 else t1
    grid = np.arange(lo, hi, FRAME_S)

    cars: dict[str, list] = {}
    for code, (sec, x, y) in per_driver.items():
        gx = _resample(sec, x, grid)
        gy = _resample(sec, y, grid)
        px, py = project(gx, gy, box)
        pts = []
        for a, b in zip(px, py):
            pts.append(None if (np.isnan(a) or np.isnan(b)) else [round(float(a), 1), round(float(b), 1)])
        cars[code] = pts

    return {
        "view": [360, 180],
        "frame_s": FRAME_S,
        "n_frames": len(grid),
        "cars": cars,
    }


def _select(races: list[dict], year: int | None, circuit: str | None) -> list[dict]:
    out = races
    if year is not None:
        out = [r for r in out if r["year"] == year]
    if circuit is not None:
        out = [r for r in out if r["circuit"] == circuit]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--circuit", type=str, default=None)
    args = ap.parse_args()

    _ensure_cache()
    import fastf1

    out: dict = json.loads(OUT.read_text()) if OUT.exists() else {}
    for r in _select(available_races(), args.year, args.circuit):
        circ, yr = r["circuit"], r["year"]
        try:
            payload = _build_one(fastf1, yr, circ)
            if payload is None:
                print("skip", yr, circ, "no position telemetry")
                continue
            out[f"{yr}:{circ}"] = payload
            print("ok  ", yr, circ, payload["n_frames"], "frames", len(payload["cars"]), "cars")
        except Exception as e:  # noqa: BLE001
            print("skip", yr, circ, e)
    OUT.write_text(json.dumps(out))
    print(f"wrote {OUT} ({len(out)} keys)")


if __name__ == "__main__":
    main()
