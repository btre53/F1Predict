"""Pre-compute the Predictor's instant first-paint snapshot.

The full 10k-sim race forecast can be a multi-second cold start on the first request after a
deploy (the Kalman model forward-chains the season and fits the hazard / safety-car / overtaking
models on first use). That left the flagship Predictor dashboard stuck on a loading spinner for a
recruiter's first screenshot.

To fix that we commit a *pre-computed* snapshot of the default-circuit forecast to
``data/predict_default.json``. The ``GET /predict/default`` endpoint serves it straight from disk
(no simulation, no cold start) so the dashboard paints a real result instantly; the frontend then
re-runs the live sim for the actually-selected circuit and swaps the sharper result in.

The snapshot circuit mirrors what the frontend lands on by default: the upcoming race when it's
calibrated, otherwise a sensible fallback. Re-run this whenever the calibration data changes:

    uv run python -m app.etl.predict_default
"""

from __future__ import annotations

import json
from pathlib import Path

from app.engine import calibration_store as store
from app.models.predict_kalman import predict_race_kalman

# Full fidelity so the instant snapshot is indistinguishable from a freshly-run forecast.
SNAPSHOT_SIMS = 10_000


def _default_circuit() -> str:
    """The circuit the Predictor opens on: the upcoming race if calibrated, else a fallback."""
    try:
        from app.etl.calendar import next_race

        nr = next_race()
        circ = nr.get("circuit") if isinstance(nr, dict) else None
        if circ and nr.get("calibrated") and circ in set(store.available_circuits()):
            return circ
    except Exception:  # noqa: BLE001 -- offline / no calendar: fall back below
        pass
    available = list(store.available_circuits())
    for pref in ("Bahrain", "Monaco", "British", "Spanish"):
        if pref in available:
            return pref
    return available[0] if available else "Bahrain"


def _serialize(res) -> dict:
    return {
        "circuit": res.circuit,
        "total_laps": res.total_laps,
        "n_sims": res.n_sims,
        "sc_probability": round(res.sc_probability, 4),
        "post_quali": res.post_quali,
        "rain_prob": round(res.rain_prob, 3),
        "wet": res.wet,
        "outcomes": [
            {
                "driver": o.driver,
                "number": o.number,
                "team": o.team,
                "colour": o.colour,
                "grid_pos": o.grid_pos,
                "win_pct": round(o.win_pct, 4),
                "podium_pct": round(o.podium_pct, 4),
                "points_pct": round(o.points_pct, 4),
                "mean_finish": round(o.mean_finish, 2),
                "p50_finish": o.p50_finish,
                "p10_finish": o.p10_finish,
                "p90_finish": o.p90_finish,
                "dnf_pct": round(o.dnf_pct, 4),
                "finish_distribution": [round(x, 4) for x in o.finish_distribution],
            }
            for o in res.outcomes
        ],
    }


def build_default_snapshot() -> dict:
    circuit = _default_circuit()
    res = predict_race_kalman(circuit, n_sims=SNAPSHOT_SIMS)
    payload = _serialize(res)
    out = Path(__file__).resolve().parents[2] / "data" / "predict_default.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    print(
        f"wrote {out} — {payload['circuit']} GP, "
        f"{payload['n_sims']:,} sims, {len(payload['outcomes'])} drivers"
    )
    return payload


if __name__ == "__main__":
    build_default_snapshot()
