"""FastF1-free track map (outline + per-frame car positions) from OpenF1 `location`.

Replaces build_track_outlines + build_track_positions (both FastF1, datacenter-blocked) with
OpenF1's `location` x/y feed, so the map auto-builds for every race on the VPS. Writes the SAME
two JSON files in the SAME shapes the front-end already reads (data/track_outlines.json keyed by
'<year>:<circuit>' + '<circuit>'; data/track_positions.json keyed by '<year>:<circuit>'), so
nothing downstream changes.

Outline and dots share ONE fit_box (fit from the fastest lap's extent), so the cars stay glued to
the traced line. OpenF1 x/y are a different coordinate system than FastF1's but that's irrelevant:
both layers use the same projection here.

    uv run python -m app.etl.build_map_openf1 2026 Monaco
"""

from __future__ import annotations

import json

import numpy as np

from app.etl import openf1 as of1
from app.etl.build_track_outlines import OUT as OUTLINES_OUT
from app.etl.build_track_outlines import STEP, fit_box, project
from app.etl.build_track_positions import OUT as POSITIONS_OUT
from app.etl.build_track_positions import FRAME_S, _resample
from app.etl.openf1_ingest import _resolve_session_key


def _driver_locations(sk: int) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """{driver_code -> (ts, x, y)} from OpenF1 location, per driver, sorted by time."""
    drivers = of1._get("drivers", session_key=sk)
    num2code = {int(d["driver_number"]): d.get("name_acronym") for d in drivers}
    out: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for dn, code in num2code.items():
        if not code:
            continue
        loc = of1._get("location", session_key=sk, driver_number=dn)
        pts = [
            (of1._ts(r["date"]), float(r["x"]), float(r["y"]))
            for r in loc
            if r.get("date") and r.get("x") is not None and r.get("y") is not None
            and not (r["x"] == 0 and r["y"] == 0)  # (0,0) = no signal / in garage
        ]
        if len(pts) < 10:
            continue
        pts.sort()
        out[code] = (
            np.array([p[0] for p in pts]),
            np.array([p[1] for p in pts]),
            np.array([p[2] for p in pts]),
        )
    return out


def build_map(year: int, circuit: str) -> bool:
    """Build + persist the outline and per-frame positions for one race. False if unavailable."""
    sk = _resolve_session_key(year, circuit, "R")
    if sk is None:
        return False
    laps = of1._get("laps", session_key=sk)
    valid = [lp for lp in laps
             if isinstance(lp.get("lap_duration"), (int, float))
             and lp.get("date_start") and not lp.get("is_pit_out_lap")]
    drv_loc = _driver_locations(sk)
    if not valid or not drv_loc:
        return False

    drivers = of1._get("drivers", session_key=sk)
    num2code = {int(d["driver_number"]): d.get("name_acronym") for d in drivers}

    # Outline = a single clean lap's x/y trace; its extent fixes the shared projection box.
    # Use the driver with the most location samples, and the FASTEST of their laps whose time
    # window is actually covered by location data -- recent races sometimes have a partial
    # location feed (e.g. it cuts out after a red flag), and the fastest lap overall may be
    # outside the covered window.
    out_code = max(drv_loc, key=lambda c: len(drv_loc[c][0]))
    out_dn = next((n for n, c in num2code.items() if c == out_code), None)
    ts, x, y = drv_loc[out_code]
    cand: list[tuple[float, float, float]] = []
    for lp in valid:
        if int(lp["driver_number"]) != out_dn:
            continue
        lo = of1._ts(lp["date_start"])
        hi = lo + float(lp["lap_duration"])
        if int(((ts >= lo) & (ts <= hi)).sum()) >= 20:
            cand.append((float(lp["lap_duration"]), lo, hi))
    if not cand:
        return False
    _, lo, hi = min(cand)  # fastest covered lap
    win = (ts >= lo) & (ts <= hi)
    lx, ly = x[win], y[win]
    # OpenF1's x/y orientation is arbitrary vs FastF1's; put the track's LONG axis horizontal so
    # it fills the 2:1 viewBox. Applied consistently to outline + dots so they stay glued.
    rot = (ly.max() - ly.min()) > (lx.max() - lx.min())
    ax, ay = (ly, lx) if rot else (lx, ly)
    box = fit_box(ax, ay)
    ox, oy = project(ax[::STEP], ay[::STEP], box)
    path = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(ox, oy)) + " Z"

    # Per-frame positions on a 2s grid over the covered race window, projected with the SAME
    # box. Clamp the end to the last location sample so a partial feed doesn't add a long tail
    # of empty frames.
    race_lo = min(of1._ts(lp["date_start"]) for lp in valid)
    loc_hi = max(t.max() for (t, _, _) in drv_loc.values())
    race_hi = min(max(of1._ts(lp["date_start"]) + float(lp["lap_duration"]) for lp in valid), loc_hi)
    grid = np.arange(race_lo, race_hi, FRAME_S)
    cars: dict[str, list] = {}
    for code, (t, cx, cy) in drv_loc.items():
        rx, ry = (cy, cx) if rot else (cx, cy)
        gx = _resample(t, rx, grid)
        gy = _resample(t, ry, grid)
        px, py = project(gx, gy, box)
        cars[code] = [
            None if (np.isnan(a) or np.isnan(b)) else [round(float(a), 1), round(float(b), 1)]
            for a, b in zip(px, py)
        ]

    key = f"{year}:{circuit}"
    outlines = json.loads(OUTLINES_OUT.read_text()) if OUTLINES_OUT.exists() else {}
    outlines[key] = {"path": path}
    outlines.setdefault(circuit, {"path": path})  # any-year fallback
    OUTLINES_OUT.write_text(json.dumps(outlines))

    positions = json.loads(POSITIONS_OUT.read_text()) if POSITIONS_OUT.exists() else {}
    positions[key] = {"view": [360, 180], "frame_s": FRAME_S, "n_frames": len(grid), "cars": cars}
    POSITIONS_OUT.write_text(json.dumps(positions))
    return True


if __name__ == "__main__":
    import sys

    y, c = int(sys.argv[1]), sys.argv[2]
    ok = build_map(y, c)
    print(f"{y} {c}: {'built' if ok else 'unavailable'}")
