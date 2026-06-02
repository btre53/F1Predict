"""Precompute normalized SVG track outlines from FastF1 telemetry.

Traces each replayable race's fastest-lap X/Y, downsamples, flips FastF1's Y axis, and
fits the path into the front-end's 360x180 viewBox. Run once (needs network + FastF1 cache):

    uv run python -m app.etl.build_track_outlines            # every replayable race
    uv run python -m app.etl.build_track_outlines --year 2024  # one season only
    uv run python -m app.etl.build_track_outlines --circuit Bahrain --year 2024
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from app.engine.replay import available_races
from app.etl.fastf1_client import _ensure_cache

OUT = Path(__file__).resolve().parents[2] / "data" / "track_outlines.json"
VIEW_W, VIEW_H, PAD, STEP = 360, 180, 20, 10  # STEP = telemetry downsample stride


def fit_box(X, Y) -> dict:
    """Map FastF1 X/Y (y-up) into the 360x180 viewBox; return the fit transform.

    Returns the scale + offsets so positional telemetry can be projected onto the
    exact same coordinate box as the outline path (cars stay glued to the track).
    """
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    xmin, xmax = float(X.min()), float(X.max())
    ymin, ymax = float(Y.min()), float(Y.max())
    s = min(
        (VIEW_W - 2 * PAD) / (xmax - xmin),
        (VIEW_H - 2 * PAD) / (ymax - ymin),
    )
    px_w = (xmax - xmin) * s
    py_h = (ymax - ymin) * s
    return {
        "xmin": xmin,
        "ymax": ymax,
        "scale": s,
        "dx": (VIEW_W - px_w) / 2,
        "dy": (VIEW_H - py_h) / 2,
    }


def project(X, Y, box: dict):
    """Project raw FastF1 X/Y arrays into viewBox px using a fit_box() transform."""
    X = np.asarray(X, float)
    Y = np.asarray(Y, float)
    px = (X - box["xmin"]) * box["scale"] + box["dx"]
    py = (box["ymax"] - Y) * box["scale"] + box["dy"]  # flip Y (FastF1 is y-up)
    return px, py


def _to_path(X, Y) -> str:
    X = np.asarray(X, float)[::STEP]
    Y = np.asarray(Y, float)[::STEP]
    box = fit_box(X, Y)
    px, py = project(X, Y, box)
    return "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in zip(px, py)) + " Z"


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
            s = fastf1.get_session(yr, circ, "R")
            s.load(telemetry=True, laps=True, weather=False, messages=False)
            tel = s.laps.pick_fastest().get_telemetry()
            d = _to_path(tel["X"].to_numpy(), tel["Y"].to_numpy())
            out[f"{yr}:{circ}"] = {"path": d}
            out.setdefault(circ, {"path": d})  # any-year fallback
            print("ok  ", yr, circ)
        except Exception as e:  # noqa: BLE001
            print("skip", yr, circ, e)
    OUT.write_text(json.dumps(out))
    print(f"wrote {OUT} ({len(out)} keys)")


if __name__ == "__main__":
    main()
