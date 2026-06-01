"""In-play step 3: WPA live win-probability backtest vs Polymarket (brief 10 §1).

Steps 1-2 established: racecraft isn't a telemetry edge (brief 12), but the Polymarket
winner market *does* reprice live (inplay_probe). This module tests the actual edge
thesis: can a fair-price engine fed from reconstructed race state produce a live win
probability that **leads** the thin/slow market around on-track events?

Pipeline (all free, offline replay):
  1. State reconstruction from laps.parquet: per lap, each car's running position,
     time gap, recent green pace, laps remaining, track status.
  2. Live win-prob: a fast vectorized Monte Carlo over the REMAINING laps, seeded from
     that state (current gaps + recent pace + flat DNF hazard). Not the mechanistic sim
     (known miscalibration, awkward to re-seed mid-race) -- a purpose-built live engine
     in the same spirit. DNF/regime hooks are where brief 10 §2/§3 plug in later.
  3. Wall-clock alignment: race start = schedule lights-out (Session5DateUtc), each lap
     stamped by cumulative leader lap-time. Rain-delayed races (e.g. São Paulo) are
     flagged -- scheduled start is wrong for them.
  4. Score vs Polymarket (data/inplay_probe.json curves): live-prob calibration (Brier
     vs eventual winner) for us AND the market, plus the lead-lag/CLV test -- do our
     prob increments lead the market's, and does (our_prob - market) predict the
     market's next move (Δ=5 min, pre-registered)?

Writes data/inplay_backtest.json. Network-free if inplay_probe.json + the FastF1 lap
cache exist.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

import numpy as np
import polars as pl

from app.etl import backtest as bt

warnings.filterwarnings("ignore")
logging.getLogger("fastf1").setLevel(logging.ERROR)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
PROBE_JSON = DATA_DIR / "inplay_probe.json"
OUT = DATA_DIR / "inplay_backtest.json"

# Rain-delayed 2024 races where scheduled lights-out != actual; alignment unreliable.
DELAYED = {"São Paulo"}

# Live-MC parameters (tuned for calibration in __main__; see report()).
SIGMA_FORM = 0.08   # s/lap systematic pace uncertainty per car (applied to all rem laps)
SIGMA_LAP = 0.45    # s/lap independent execution noise
H_DNF = 0.0016      # per-lap DNF hazard (flat for now; hazard model is step 3b)
N_SIMS = 6000
LAGS = [-300, -180, -120, -60, 0, 60, 120, 180, 300]  # seconds; +lag = market follows us


def _race_start_ts() -> dict[str, int]:
    """{2024 circuit -> scheduled lights-out unix} from the cached FastF1 schedule."""
    import fastf1

    from app.config import get_settings

    fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)
    sched = fastf1.get_event_schedule(2024, include_testing=False)
    out: dict[str, int] = {}
    for _, row in sched.iterrows():
        ts = row.get("Session5DateUtc")
        name = str(row["EventName"]).replace(" Grand Prix", "").strip()
        if ts is not None and not pl.Series([ts]).is_null().any():
            out[name] = int(ts.timestamp())
    return out


def _prep_race(race: pl.DataFrame) -> pl.DataFrame:
    """Clean per-lap frame: fill null lap times with the driver's green median."""
    med = (
        race.filter((pl.col("track_status") == "1") & pl.col("is_accurate")
                    & pl.col("lap_time_s").is_not_null())
        .group_by("driver").agg(pl.col("lap_time_s").median().alias("dmed"))
    )
    gmed = float(race.filter(pl.col("lap_time_s").is_not_null())["lap_time_s"].median() or 90.0)
    return (
        race.join(med, on="driver", how="left")
        .with_columns(
            pl.col("lap_time_s").fill_null(pl.col("dmed")).fill_null(gmed).alias("lt"),
            pl.col("dmed").fill_null(gmed).alias("dmed"),
        )
        .sort(["driver", "lap_number"])
        .with_columns(pl.col("lt").cum_sum().over("driver").alias("cum_t"))
    )


def _live_winprob(snap: list[dict], rem: int, rng: np.random.Generator) -> dict[str, float]:
    """Vectorized live win-prob MC from a per-car snapshot {driver, cum_t, pace}."""
    if rem <= 0 or not snap:
        # Race over: leader (min cum_t) wins with prob 1.
        lead = min(snap, key=lambda d: d["cum_t"])["driver"] if snap else None
        return {d["driver"]: float(d["driver"] == lead) for d in snap}
    drivers = [d["driver"] for d in snap]
    cum = np.array([d["cum_t"] for d in snap])
    pace = np.array([d["pace"] for d in snap])
    n = len(drivers)
    form = rng.normal(0, SIGMA_FORM, (N_SIMS, n)) * rem
    noise = rng.normal(0, SIGMA_LAP * np.sqrt(rem), (N_SIMS, n))
    total = cum[None, :] + pace[None, :] * rem + form + noise
    p_dnf = 1.0 - (1.0 - H_DNF) ** rem
    total[rng.random((N_SIMS, n)) < p_dnf] = np.inf
    winners = total.argmin(axis=1)
    counts = np.bincount(winners, minlength=n)
    return {drivers[i]: counts[i] / N_SIMS for i in range(n)}


def _race_winprob_series(race: pl.DataFrame, *, every: int = 1) -> tuple[list[int], dict[str, list[float]]]:
    """Per-lap elapsed-seconds and a per-driver live win-prob series for one race."""
    r = _prep_race(race)
    total_laps = int(r["lap_number"].max())
    rng = np.random.default_rng(0)
    elapsed: list[int] = []
    series: dict[str, list[float]] = {}
    for L in range(1, total_laps + 1):
        if L % every and L != total_laps:
            continue
        upto = r.filter(pl.col("lap_number") <= L)
        atL = r.filter(pl.col("lap_number") == L).filter(pl.col("position").is_not_null())
        if atL.height == 0:
            continue
        cumL = {row["driver"]: row["cum_t"] for row in upto.group_by("driver")
                .agg(pl.col("cum_t").max()).to_dicts()}
        # recent pace = mean of last 5 green accurate laps (fallback: driver median).
        recent = (
            upto.filter(pl.col("lap_number") > L - 5)
            .filter((pl.col("track_status") == "1") & pl.col("is_accurate"))
            .group_by("driver").agg(pl.col("lt").mean().alias("rp"))
        )
        rp = {row["driver"]: row["rp"] for row in recent.to_dicts()}
        dmed = {row["driver"]: row["dmed"] for row in atL.select(["driver", "dmed"]).to_dicts()}
        snap = []
        for row in atL.to_dicts():
            d = row["driver"]
            snap.append({"driver": d, "cum_t": cumL.get(d, 1e9),
                         "pace": rp.get(d) or dmed.get(d, 90.0)})
        # elapsed wall-clock at end of lap L = leader's cum time.
        elapsed_s = int(min(s["cum_t"] for s in snap))
        wp = _live_winprob(snap, total_laps - L, rng)
        elapsed.append(elapsed_s)
        for d, p in wp.items():
            series.setdefault(d, []).append((len(elapsed) - 1, p))
    # densify: each driver -> list aligned to elapsed indices (missing = 0.0)
    dense: dict[str, list[float]] = {}
    for d, pairs in series.items():
        arr = [0.0] * len(elapsed)
        for idx, p in pairs:
            arr[idx] = p
        dense[d] = arr
    return elapsed, dense


def _market_at(curve: list[list[float]], ts: int) -> float | None:
    """Last Polymarket price at or before unix ts (None if before coverage)."""
    pre = [p for t, p in curve if t <= ts]
    return pre[-1] if pre else None


def run(every: int = 1, time_offset: int = 0) -> dict:
    """time_offset (s) shifts OUR stamps vs the market -- used for a lead-lag placebo:
    a genuine lead survives small shifts; a pure clock-misalignment artefact does not."""
    probe = json.loads(PROBE_JSON.read_text())
    winners = probe["winners"]
    starts = _race_start_ts()
    full = pl.read_parquet(LAPS_PARQUET).filter(
        (pl.col("session_name") == "R") & (pl.col("year") == 2024)
    )

    races_out: list[dict] = []
    # Pooled calibration pairs (our vs market), sampled across all laps/drivers.
    our_pairs: list[tuple[float, int]] = []
    mkt_pairs: list[tuple[float, int]] = []
    xcorr_pts: dict[int, list[tuple[float, float]]] = {lag: [] for lag in LAGS}

    for pr in probe["races"]:
        circuit = pr["circuit"]
        race = full.filter(pl.col("circuit") == circuit)
        if race.height == 0 or circuit not in starts:
            continue
        winner = winners.get(circuit)
        start_ts = starts[circuit]
        elapsed, series = _race_winprob_series(race, every=every)
        if not elapsed:
            continue
        curves = pr["curves"]
        delayed = circuit in DELAYED
        ts_arr = np.array([start_ts + el + time_offset for el in elapsed], dtype=float)

        # Forward CLV (does our edge predict the market's next move) and the reverse
        # placebo (does the market's edge predict OUR next move) -- pooled over ALL
        # priced drivers, so it covers probs that FALL (fading contenders) not just rise.
        race_fwd: list[tuple[float, float]] = []
        race_rev: list[tuple[float, float]] = []
        for d, arr in series.items():
            if d not in curves:
                continue
            our = np.array(arr, dtype=float)
            for i, ts in enumerate(ts_arr):
                mkt = _market_at(curves[d], ts)
                if mkt is None:
                    continue
                if not delayed:
                    our_pairs.append((our[i], int(d == winner)))
                    mkt_pairs.append((mkt, int(d == winner)))
                if delayed:
                    continue
                mkt_fut = _market_at(curves[d], ts + 300)        # market 5 min later
                our_fut = float(np.interp(ts + 300, ts_arr, our))  # our prob 5 min later
                if mkt_fut is not None:
                    race_fwd.append((our[i] - mkt, mkt_fut - mkt))
                    race_rev.append((mkt - our[i], our_fut - our[i]))

        # Increment cross-correlation (detrended): on a 60s grid, corr(Δour[t], Δmkt[t+lag]).
        # First differences remove the shared convergence trend, isolating WHO MOVES FIRST.
        # A genuine lead => peak correlation at POSITIVE lag (market follows us).
        if not delayed and len(ts_arr) >= 3:
            grid = np.arange(ts_arr[0], ts_arr[-1], 60.0)
            for d, arr in series.items():
                if d not in curves or len(grid) < 6:
                    continue
                our_g = np.interp(grid, ts_arr, np.array(arr, dtype=float))
                mkt_g = np.array([_market_at(curves[d], int(t)) for t in grid], dtype=object)
                if any(v is None for v in mkt_g):
                    mkt_g = np.array([v if v is not None else np.nan for v in mkt_g])
                mkt_g = mkt_g.astype(float)
                dou, dmk = np.diff(our_g), np.diff(mkt_g)
                for lag in LAGS:
                    k = lag // 60
                    if k >= 0:
                        a, b = dou[:len(dou) - k], dmk[k:]
                    else:
                        a, b = dou[-k:], dmk[:len(dmk) + k]
                    m = ~(np.isnan(a) | np.isnan(b))
                    xcorr_pts[lag].extend(zip(a[m].tolist(), b[m].tolist()))

        races_out.append({
            "circuit": circuit, "winner": winner, "delayed": delayed,
            "n_laps": len(elapsed),
            "our_winner_final": round(series.get(winner, [0])[-1], 3) if winner in series else None,
            "clv_fwd": _safe_corr(race_fwd),
            "clv_rev": _safe_corr(race_rev),
        })

    out = {
        "params": {"sigma_form": SIGMA_FORM, "sigma_lap": SIGMA_LAP, "h_dnf": H_DNF,
                   "n_sims": N_SIMS, "every": every},
        "calibration": {
            "our": bt._score(our_pairs),
            "market": bt._score(mkt_pairs),
            "our_curve": bt._calibration(our_pairs),
            "market_curve": bt._calibration(mkt_pairs),
        },
        "lead_lag": {
            "note": "clv_fwd = corr(our-mkt(t), mkt(t+5min)-mkt(t)): does our edge predict "
                    "the MARKET's move. clv_rev = corr(mkt-our(t), our(t+5min)-our(t)): the "
                    "placebo -- does the market's edge predict OUR move. fwd>>rev => we lead.",
            "mean_clv_fwd": _mean([r["clv_fwd"] for r in races_out]),
            "mean_clv_rev": _mean([r["clv_rev"] for r in races_out]),
        },
        "increment_xcorr": {
            "note": "corr(Δour[t], Δmkt[t+lag]) on a 60s grid, detrended. Peak at +lag => "
                    "market follows us by that many seconds (a genuine lead).",
            "by_lag_s": {str(lag): _safe_corr(xcorr_pts[lag]) for lag in LAGS},
            "n": len(xcorr_pts[0]),
        },
        "per_race": races_out,
    }
    OUT.write_text(json.dumps(out, indent=2))
    return out


def _safe_corr(pts: list[tuple[float, float]]) -> float | None:
    if len(pts) < 8:
        return None
    x = np.array([a for a, _ in pts]); y = np.array([b for _, b in pts])
    if x.std() < 1e-9 or y.std() < 1e-9:
        return None
    return round(float(np.corrcoef(x, y)[0, 1]), 3)


def _mean(vals: list) -> float | None:
    v = [x for x in vals if x is not None]
    return round(float(np.mean(v)), 4) if v else None


if __name__ == "__main__":
    r = run(every=1)
    c = r["calibration"]
    print(f"In-play WPA backtest ({c['our']['n']} lap-driver obs across "
          f"{len(r['per_race'])} races; params {r['params']})")
    print(f"  WIN-PROB CALIBRATION (live, pooled over all laps):")
    print(f"    our    Brier={c['our']['brier']}  logloss={c['our']['logloss']}")
    print(f"    market Brier={c['market']['brier']}  logloss={c['market']['logloss']}")
    print(f"  LEAD-LAG / CLV (all priced drivers, non-delayed races):")
    print(f"    mean clv_fwd (our edge -> market's next 5-min move): {r['lead_lag']['mean_clv_fwd']}")
    print(f"    mean clv_rev (PLACEBO: market edge -> our next move): {r['lead_lag']['mean_clv_rev']}")
    xc = r["increment_xcorr"]["by_lag_s"]
    print(f"  INCREMENT CROSS-CORR (detrended; +lag=market follows us), n={r['increment_xcorr']['n']}:")
    print("    " + "  ".join(f"{lag:>+4}s:{xc[str(lag)]}" for lag in LAGS))
    print(f"  per-race (winner's final live prob | clv_fwd | clv_rev placebo):")
    for p in r["per_race"]:
        d = " [delayed]" if p["delayed"] else ""
        print(f"    {p['circuit']:14s} {p['winner']:3s}  final={p['our_winner_final']}  "
              f"fwd={p['clv_fwd']}  rev={p['clv_rev']}{d}")
    print(f"  -> wrote {OUT}")
