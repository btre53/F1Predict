"""net_dnf decoupling: a retirement must not depress the car's PACE strength (task #10)."""

import polars as pl

from app.models.kalman import KalmanModel


def _race(dnf_a: bool) -> pl.DataFrame:
    # A qualifies fastest but finishes last; B/C finish ahead. dnf_a marks A's last place a DNF.
    return pl.DataFrame({
        "year": [2024, 2024, 2024],
        "team": ["TA", "TB", "TC"],
        "driver": ["A", "B", "C"],
        "quali_gap_pct": [0.0, 0.010, 0.020],   # A is the quali pacesetter
        "finish_pos": [3.0, 1.0, 2.0],          # A classified last
        "dnf": [dnf_a, False, False],
    })


def _strength(model: KalmanModel, drv: str, team: str) -> float:
    return model.car[team][0] + model.drv[drv][0]


def test_net_dnf_protects_pace_strength_on_a_retirement():
    std = KalmanModel(net_dnf=False); std.reset()
    net = KalmanModel(net_dnf=True); net.reset()
    std.update(_race(dnf_a=True))
    net.update(_race(dnf_a=True))
    # With net_dnf, A's last-place finish (a DNF) is ignored, so its strength stays higher.
    assert _strength(net, "A", "TA") > _strength(std, "A", "TA")


def test_net_dnf_is_a_noop_when_the_car_finished():
    std = KalmanModel(net_dnf=False); std.reset()
    net = KalmanModel(net_dnf=True); net.reset()
    std.update(_race(dnf_a=False))   # A's last place is a real (classified) finish
    net.update(_race(dnf_a=False))
    assert abs(_strength(net, "A", "TA") - _strength(std, "A", "TA")) < 1e-9
