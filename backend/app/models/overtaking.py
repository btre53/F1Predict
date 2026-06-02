"""Circuit overtaking-difficulty index (mechanistic, brand-agnostic).

ONE number per circuit summarizing how locked track position is, from three
forward-chainable proxies on our own data (no team/driver identity anywhere):

  1. grid->finish rank lock  -- Spearman rho(grid, finish_pos) per running
     (grid = qualifying-pace order). High rho => qualifying dominates.
  2. green on-track passing rate -- position gains / car / racing lap on green
     laps, excluding a driver's own pit-cycle laps. Low rate => hard to pass.
  3. lap-1 churn -- mean |grid - position after lap 1|. Low churn => the start
     conserves grid order.

High index => hard to pass => qualifying should dominate the prediction and the
finishing-order distribution is tight. Low index => pace overcomes grid, so the
distribution is wide. The index is empirical-Bayes shrunk toward the calendar
mean by visit count, so thin-sample circuits fall back to "average difficulty".

This is the mechanistic, generalizing replacement for the REJECTED team x circuit
affinity (`KalmanTrackModel`): it modulates *confidence* (a track-physics number
shared by every team), never *who we favour by name*. A brand-new circuit is
scored by its measured passing rate; a brand-new team is unaffected because the
index multiplies everyone's grid weight equally. See docs/science/16 (section 1).

Two uses (both validated forward-chained, killed if they don't beat the flat
baseline): (a) scale the Kalman `grid_weight` per circuit; (b) set the spread of
the pre-quali finishing-order distribution.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import polars as pl

from .features import LAPS_PARQUET, _race_seq, build_feature_table

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
PROXIES_PARQUET = DATA_DIR / "overtaking_proxies.parquet"

# Wet races are excluded from the index (they break the qualifying lock for a
# weather reason, not a track-geometry one). A running is "wet" if this share of
# its racing laps ran on intermediate/wet rubber.
_WET_COMPOUNDS = ("INTERMEDIATE", "WET")
_WET_FRACTION = 0.30
# Empirical-Bayes shrinkage strength (visits needed to half-trust a circuit's
# own estimate). Matches the rejected affinity's form, on a track-stable number.
_SHRINK_K = 6.0


def _spearman(a: list[float], b: list[float]) -> float | None:
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if len(x) < 4:
        return None
    rx = x.argsort().argsort().astype(float)
    ry = y.argsort().argsort().astype(float)
    if rx.std() < 1e-9 or ry.std() < 1e-9:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def _passing_rate(race: pl.DataFrame) -> float | None:
    """Green on-track position gains per car per racing lap.

    A clean gain = a driver's position improving on a green lap that is neither a
    pit-out for them nor the lap after a pit-in (their own pit cycle removed). We
    cannot attribute who was passed, so position changes caused by *others*
    pitting remain as symmetric noise -- acceptable for a per-circuit median.
    """
    n_cars = race["driver"].n_unique()
    racing_laps = race["lap_number"].max()
    if not n_cars or not racing_laps:
        return None
    g = race.sort(["driver", "lap_number"]).with_columns(
        pl.col("position").shift(1).over("driver").alias("_prev"),
        pl.col("is_pit_in").shift(1).over("driver").alias("_prev_in"),
    )
    gains = (
        g.filter(
            (pl.col("track_status") == "1")
            & pl.col("position").is_not_null()
            & pl.col("_prev").is_not_null()
            & ~pl.col("is_pit_out")
            & ~pl.col("is_pit_in")
            & ~pl.col("_prev_in").fill_null(False)
        )
        .select(
            (pl.col("_prev") - pl.col("position")).clip(lower_bound=0).sum().alias("g")
        )
        .item()
    )
    return float(gains) / (n_cars * int(racing_laps))


def _wet_fraction(race: pl.DataFrame) -> float:
    total = race.height
    if not total:
        return 0.0
    wet = race.filter(pl.col("compound").is_in(_WET_COMPOUNDS)).height
    return wet / total


def build_running_proxies() -> pl.DataFrame:
    """Per-running (year, circuit) overtaking proxies -- the raw, unshrunk inputs.

    Combines the feature table (grid via qualifying-pace order, finish_pos) with
    per-lap positions from laps.parquet (passing rate, lap-1 churn). One row per
    race, tagged with `seq` (chronological) and `era` for forward-chaining.
    """
    feat = build_feature_table()
    laps = pl.read_parquet(
        LAPS_PARQUET,
        columns=[
            "year", "circuit", "session_name", "driver", "lap_number",
            "position", "track_status", "is_pit_in", "is_pit_out", "compound",
        ],
    ).filter(pl.col("session_name") == "R")
    parts: dict[tuple[int, str], pl.DataFrame] = {}
    for df in laps.partition_by(["year", "circuit"]):
        parts[(df["year"][0], df["circuit"][0])] = df

    rows: list[dict] = []
    for (year, circuit), fr in feat.group_by(["year", "circuit"]):
        race = parts.get((year, circuit))
        if race is None or fr.height < 6:
            continue
        seq = int(fr["seq"][0])
        # grid = qualifying-pace rank (true pre-race order); fall back to lap-1
        # position where qualifying is missing for that driver.
        f = fr.with_columns(
            pl.col("quali_gap_pct").rank("ordinal").alias("_qrank"),
        )
        f = f.with_columns(
            pl.coalesce([pl.col("_qrank"), pl.col("grid")]).alias("_grid")
        ).filter(pl.col("_grid").is_not_null() & pl.col("finish_pos").is_not_null())
        rho = _spearman(f["_grid"].to_list(), f["finish_pos"].to_list())
        # lap-1 churn: |grid - lap-1 position|. features `grid` IS the lap-1 end
        # position, so churn = grid(quali) vs that.
        churn_df = f.filter(pl.col("grid").is_not_null())
        lap1_churn = (
            float((churn_df["_grid"] - churn_df["grid"]).abs().mean())
            if churn_df.height >= 4
            else None
        )
        rows.append(
            {
                "year": int(year),
                "circuit": str(circuit),
                "seq": seq,
                "era": "pre2022" if int(year) < 2022 else "modern",
                "n_cars": int(race["driver"].n_unique()),
                "racing_laps": int(race["lap_number"].max()),
                "wet_frac": _wet_fraction(race),
                "grid_finish_rho": rho,
                "pass_rate": _passing_rate(race),
                "lap1_churn": lap1_churn,
            }
        )
    return pl.DataFrame(rows).sort("seq")


@lru_cache(maxsize=1)
def _proxy_table() -> pl.DataFrame:
    if PROXIES_PARQUET.exists():
        return pl.read_parquet(PROXIES_PARQUET)
    t = build_running_proxies()
    return t


class OvertakingIndex:
    """Forward-chained per-circuit overtaking-difficulty from the proxy table.

    `index(circuit, before_seq=s)` uses only runnings with seq < s, so it is
    leak-free by construction. Each circuit's median proxies are z-scored across
    circuits (using the cross-circuit distribution available *at that time*),
    combined as z(rho) - z(pass_rate) - z(lap1_churn), then empirical-Bayes shrunk
    toward 0 (the calendar mean) by visit count. Returns 0 for unseen circuits.
    """

    def __init__(self, *, shrink_k: float = _SHRINK_K, era_split: bool = False,
                 table: pl.DataFrame | None = None):
        self.k = shrink_k
        self.era_split = era_split
        self._t = table if table is not None else _proxy_table()
        # Drop wet runnings and rows missing a proxy up front.
        self._t = self._t.filter(
            (pl.col("wet_frac") < _WET_FRACTION)
            & pl.col("grid_finish_rho").is_not_null()
            & pl.col("pass_rate").is_not_null()
            & pl.col("lap1_churn").is_not_null()
        )
        self._cache: dict[tuple, float] = {}

    def reset(self) -> None:
        self._cache.clear()

    def _eligible(self, before_seq: int | None, era: str | None) -> pl.DataFrame:
        t = self._t
        if before_seq is not None:
            t = t.filter(pl.col("seq") < before_seq)
        if self.era_split and era is not None:
            t = t.filter(pl.col("era") == era)
        return t

    def index(self, circuit: str, *, before_seq: int | None = None,
              era: str | None = None) -> float:
        key = (circuit, before_seq, era if self.era_split else None)
        if key in self._cache:
            return self._cache[key]
        t = self._eligible(before_seq, era)
        if t.height == 0:
            self._cache[key] = 0.0
            return 0.0
        med = t.group_by("circuit").agg(
            pl.col("grid_finish_rho").median().alias("rho"),
            pl.col("pass_rate").median().alias("pr"),
            pl.col("lap1_churn").median().alias("churn"),
            pl.len().alias("n"),
        )
        if circuit not in med["circuit"].to_list() or med.height < 2:
            self._cache[key] = 0.0
            return 0.0

        def _z(col: str, val: float) -> float:
            a = med[col].to_numpy()
            mu, sd = float(np.nanmean(a)), float(np.nanstd(a))
            return (val - mu) / sd if sd > 1e-9 else 0.0

        row = med.filter(pl.col("circuit") == circuit).to_dicts()[0]
        raw = _z("rho", row["rho"]) - _z("pr", row["pr"]) - _z("churn", row["churn"])
        n = float(row["n"])
        ot = raw * n / (n + self.k)
        self._cache[key] = ot
        return ot

    def grid_weight(self, circuit: str, w0: float, *, before_seq: int | None = None,
                    era: str | None = None) -> float:
        """w0 * sigmoid(index): hard tracks lean on grid, easy tracks on pace."""
        ot = self.index(circuit, before_seq=before_seq, era=era)
        return w0 * float(1.0 / (1.0 + np.exp(-ot)))

    def spread(self, circuit: str, t0: float, *, gamma: float = 0.25,
               before_seq: int | None = None, era: str | None = None) -> float:
        """Pre-quali finishing-order temperature: wider (hotter) at easy-to-pass
        tracks, tighter (cooler) at locked tracks. T = t0 * exp(-gamma * index)."""
        ot = self.index(circuit, before_seq=before_seq, era=era)
        return t0 * float(np.exp(-gamma * ot))


def main() -> None:
    t = build_running_proxies()
    PROXIES_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    t.write_parquet(PROXIES_PARQUET)
    print(f"wrote {PROXIES_PARQUET} ({t.height} runnings)")

    idx = OvertakingIndex(table=t)
    circuits = sorted(set(t["circuit"].to_list()))
    scored = sorted(
        ((c, idx.index(c)) for c in circuits), key=lambda x: -x[1]
    )
    print("\novertaking-difficulty index (high = hard to pass, qualifying-locked):")
    for c, v in scored:
        n = t.filter(pl.col("circuit") == c).height
        print(f"  {v:+6.2f}  gw={idx.grid_weight(c, 0.6):.3f}  ({n:>2d} runs)  {c}")


if __name__ == "__main__":
    main()
