"""Tests for the measured dirty-air penalty curve (brief 24)."""

import json

import numpy as np

from app.models.dirty_air import DIRTY_AIR_JSON, build_dirty_air, penalty_curve


def test_curve_built_and_monotone_decreasing():
    build_dirty_air()
    assert DIRTY_AIR_JSON.exists()
    d = json.loads(DIRTY_AIR_JSON.read_text())
    ov = d["overall"]
    # closer = worse: the 0-0.5s penalty must exceed the 2-3s penalty, and the close-gap
    # penalty is a real, large loss (your spec: non-linear, worse when glued)
    assert ov["0-0.5"]["penalty_s"] > ov["2-3"]["penalty_s"]
    assert ov["0-0.5"]["penalty_s"] > 0.5
    # roughly monotone decreasing across the bins
    vals = [ov[k]["penalty_s"] for k in d["gap_labels"] if k in ov]
    assert all(vals[i] >= vals[i + 1] - 0.05 for i in range(len(vals) - 1))


def test_penalty_curve_interpolates_and_fades():
    mids, pen = penalty_curve("Bahrain")
    assert len(mids) >= 3 and len(pen) == len(mids)
    # close gap penalised much more than a 3s gap
    near = float(np.interp(0.3, mids, pen))
    far = float(np.interp(3.5, mids, pen))
    assert near > far
    assert far < 0.15   # ~clean air by 3s+


def test_per_circuit_spread_exists():
    """Track matters: high-speed/can't-pass circuits bite harder than slipstream tracks."""
    d = json.loads(DIRTY_AIR_JSON.read_text())
    pc = d["per_circuit"]
    assert len(pc) >= 10
    def close(c):
        cv = pc[c]
        xs = [cv[k]["penalty_s"] for k in ("0-0.5", "0.5-1") if k in cv]
        return np.mean(xs) if xs else None
    monaco, austria = close("Monaco"), close("Austrian")
    if monaco is not None and austria is not None:
        assert monaco > austria   # walled/can't-pass >> slipstream-heavy
