"""Pull FastF1 *car telemetry* for a race sample and test the live-telemetry premise.

The lap-level test (`racecraft_signatures.py`) found that car-netted racecraft barely
shows up in lap aggregates -- only race pace carries it. This goes one level deeper:
does sub-lap driving STYLE (full-throttle share, braking, coasting, top speed, throttle
smoothness), teammate-netted, track the racecraft rating? If even rich telemetry can't
separate racecraft from the car, a live telemetry feed won't either.

Costly (FastF1 telemetry ~30s/session), so it runs on a small fixed sample and caches
the per-driver-race signatures to data/telemetry_sig.parquet. Re-run is free after that.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import numpy as np
import polars as pl

warnings.filterwarnings("ignore")
logging.getLogger("fastf1").setLevel(logging.ERROR)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
OUT = DATA_DIR / "telemetry_sig.parquet"

# Sample chosen for strong within-team racecraft contrast (HAM/RUS, ALB/SAR, BOT/ZHO,
# PER/VER, ...), spread across circuit types and both 2023 & 2024.
SAMPLE: list[tuple[int, str]] = [
    (2024, "Bahrain"), (2024, "Spain"), (2024, "Austria"), (2024, "Italy"),
    (2024, "Mexico City"), (2023, "Bahrain"), (2023, "Hungary"), (2023, "Brazil"),
]


def _lap_features(car) -> dict[str, float] | None:
    """Driving-style summary of one lap's car telemetry."""
    if car is None or len(car) < 50:
        return None
    thr = car["Throttle"].to_numpy(dtype=float)
    brk = car["Brake"].to_numpy().astype(float)  # bool -> 0/1
    spd = car["Speed"].to_numpy(dtype=float)
    return {
        "full_throttle_pct": float(np.mean(thr >= 98) * 100),
        "brake_pct": float(np.mean(brk > 0.5) * 100),
        "coast_pct": float(np.mean((thr < 5) & (brk <= 0.5)) * 100),
        "top_speed": float(np.nanmax(spd)),
        "avg_speed": float(np.nanmean(spd)),
        # Throttle smoothness: mean |delta throttle| between samples (lower = smoother).
        "throttle_jerk": float(np.mean(np.abs(np.diff(thr)))),
    }


def extract(force: bool = False) -> pl.DataFrame:
    if OUT.exists() and not force:
        return pl.read_parquet(OUT)

    import fastf1
    from app.config import get_settings

    fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)

    rows: list[dict] = []
    for year, gp in SAMPLE:
        try:
            s = fastf1.get_session(year, gp, "R")
            s.load(laps=True, telemetry=True, weather=False, messages=False)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {year} {gp}: {e}")
            continue
        circuit = str(s.event["EventName"]).replace(" Grand Prix", "").strip()
        for drv in s.drivers:
            dl = s.laps.pick_drivers(drv).pick_quicklaps()  # clean racing laps
            if len(dl) < 6:
                continue
            abbr = dl["Driver"].iloc[0]
            team = dl["Team"].iloc[0]
            dl = dl.iloc[:25]  # cap laps/driver to bound telemetry-slice time
            per_lap: list[dict] = []
            for _, lap in dl.iterrows():
                try:
                    f = _lap_features(lap.get_car_data())
                except Exception:  # noqa: BLE001
                    f = None
                if f is not None:
                    per_lap.append(f)
            if len(per_lap) < 6:
                continue
            agg = {k: float(np.median([d[k] for d in per_lap])) for k in per_lap[0]}
            agg |= {"year": year, "circuit": circuit, "driver": abbr,
                    "team": team, "n_laps": len(per_lap)}
            rows.append(agg)
        print(f"  done {year} {gp}: "
              f"{len([r for r in rows if r['year']==year and r['circuit']==circuit])} drivers")

    df = pl.DataFrame(rows)
    df.write_parquet(OUT)
    print(f"\nwrote {OUT} ({df.height} driver-races)")
    return df


METRICS = ["full_throttle_pct", "brake_pct", "coast_pct", "top_speed",
           "avg_speed", "throttle_jerk"]


def _corr(a, b) -> tuple[float, int]:
    d = pl.DataFrame({"a": a, "b": b}).drop_nulls()
    if d.height < 8:
        return float("nan"), d.height
    x, y = d["a"].to_numpy(), d["b"].to_numpy()
    if np.std(x) < 1e-9 or np.std(y) < 1e-9:
        return float("nan"), d.height
    return float(np.corrcoef(x, y)[0, 1]), d.height


def report() -> None:
    from .features import _race_seq, build_feature_table
    from .racecraft import compute_pgae, racecraft_ratings

    df = extract()
    seq = _race_seq()
    df = df.with_columns(
        pl.struct(["year", "circuit"])
        .map_elements(lambda s: seq.get((s["year"], s["circuit"]), 9999), return_dtype=pl.Int64)
        .alias("seq")
    )
    # Teammate-net each style metric (subtract the team mean that race).
    team = df.group_by(["seq", "team"]).agg([pl.col(m).mean().alias(f"{m}__t") for m in METRICS])
    df = df.join(team, on=["seq", "team"], how="left").with_columns(
        [(pl.col(m) - pl.col(f"{m}__t")).alias(f"{m}_net") for m in METRICS]
    )

    # Attach teammate-netted PGAE (per driver-race outcome).
    feat = compute_pgae(build_feature_table()).select(["seq", "driver", "team", "pgae"])
    tpg = feat.group_by(["seq", "team"]).agg(pl.col("pgae").mean().alias("pgae__t"))
    feat = feat.join(tpg, on=["seq", "team"]).with_columns(
        (pl.col("pgae") - pl.col("pgae__t")).alias("pgae_net")
    )
    df = df.join(feat.select(["seq", "driver", "pgae_net"]), on=["seq", "driver"], how="left")

    print(f"\nTelemetry sample: {df.height} driver-races, {df['seq'].n_unique()} races\n")
    print("Per-DRIVER-RACE: teammate-netted STYLE metric vs teammate-netted PGAE:")
    for m in METRICS:
        r, n = _corr(df[f"{m}_net"], df["pgae_net"])
        print(f"  {m:18s} r={r:+.3f}  n={n:3d}")

    # Per-driver: mean netted style vs racecraft rating.
    rc = racecraft_ratings().select(["driver", "racecraft", "n"])
    agg = df.group_by("driver").agg(
        [pl.col(f"{m}_net").mean().alias(m) for m in METRICS] + [pl.len().alias("races")]
    ).filter(pl.col("races") >= 3).join(rc, on="driver", how="inner")
    print(f"\nPer-DRIVER ({agg.height} drivers, >=3 sampled races): netted style vs racecraft:")
    for m in METRICS:
        r, n = _corr(agg[m], agg["racecraft"])
        print(f"  {m:18s} r={r:+.3f}  n={n:3d}")


if __name__ == "__main__":
    report()
