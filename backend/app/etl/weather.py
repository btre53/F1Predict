"""Weather-as-variance ETL (free, leak-free): per-race race-window precipitation.

Weather is an *exogenous* race-day shock: rain reshuffles the order (lower grid->finish
lock, more upsets) and raises retirements. We don't try to predict *who* wins from it
(brief 16 §4) -- we use it to widen the finishing distribution and multiply the DNF
hazard. The model lever, not a who-wins term.

Signal: realized race-window precipitation (mm) from the Open-Meteo ERA5 **archive**
(`archive-api.open-meteo.com`). Two honesty notes:
  * Open-Meteo's archived *forecast* (`historical-forecast-api`) does NOT populate
    `precipitation_probability` for past dates, and only covers ~2022+. The ERA5
    archive's realized precipitation is the one signal consistent across 2018-2026.
  * Realized precipitation is mildly optimistic vs a pure ex-ante forecast, but weather
    is exogenous (not caused by the race outcome) and conditions are broadly known at
    lights-out, so it's a defensible leak-free stand-in. For a *future* race the
    deploy path swaps in the live forecast (same column). Documented in docs/science/21.

Ground truth for the wet label is cross-checked against FastF1's own session weather
(`session.weather_data.Rainfall`) on a sample -- see `crosscheck_fastf1()`.

Writes data/weather.parquet (one row per R race) + a fetch cache (data/weather_cache.json).
"""

from __future__ import annotations

import json
import logging
import warnings
from functools import lru_cache
from pathlib import Path

import polars as pl

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
WEATHER_PARQUET = DATA_DIR / "weather.parquet"
FETCH_CACHE = DATA_DIR / "weather_cache.json"

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

# Race-window precipitation classification (mm/h, ERA5 hourly).
WET_MM_THRESHOLD = 0.10   # max hourly precip over the race window to call a race "wet"
RACE_WINDOW_H = 3         # race start hour .. start + this many hours (covers ~2h race + buffer)

# Circuit -> (lat, lon), keyed by the circuit name as it appears in laps.parquet
# (FastF1 EventName minus " Grand Prix"). Covers every R-race circuit 2018-2026,
# including one-off / renamed venues (70th Anniversary=Silverstone, Eifel=Nurburgring,
# Styrian=Red Bull Ring, Sakhir=Bahrain outer, Sao Paulo=Interlagos, ...).
CIRCUIT_COORDS: dict[str, tuple[float, float]] = {
    "70th Anniversary": (52.0786, -1.0169),   # Silverstone
    "Abu Dhabi": (24.4672, 54.6031),          # Yas Marina
    "Australian": (-37.8497, 144.9680),       # Albert Park
    "Austrian": (47.2197, 14.7647),           # Red Bull Ring
    "Azerbaijan": (40.3725, 49.8533),         # Baku City
    "Bahrain": (26.0325, 50.5106),            # Sakhir
    "Belgian": (50.4372, 5.9714),             # Spa-Francorchamps
    "Brazilian": (-23.7036, -46.6997),        # Interlagos
    "British": (52.0786, -1.0169),            # Silverstone
    "Canadian": (45.5000, -73.5228),          # Circuit Gilles Villeneuve
    "Chinese": (31.3389, 121.2200),           # Shanghai
    "Dutch": (52.3888, 4.5409),               # Zandvoort
    "Eifel": (50.3356, 6.9475),               # Nurburgring
    "Emilia Romagna": (44.3439, 11.7167),     # Imola
    "French": (43.2506, 5.7916),              # Paul Ricard
    "German": (49.3278, 8.5656),              # Hockenheim
    "Hungarian": (47.5789, 19.2486),          # Hungaroring
    "Italian": (45.6156, 9.2811),             # Monza
    "Japanese": (34.8431, 136.5410),          # Suzuka
    "Las Vegas": (36.1147, -115.1730),        # Las Vegas Strip
    "Mexican": (19.4042, -99.0907),           # Autodromo Hermanos Rodriguez
    "Mexico City": (19.4042, -99.0907),
    "Miami": (25.9581, -80.2389),             # Miami International Autodrome
    "Monaco": (43.7347, 7.4206),
    "Portuguese": (37.2270, -8.6267),         # Portimao
    "Qatar": (25.4900, 51.4542),              # Lusail
    "Russian": (43.4057, 39.9578),            # Sochi
    "Sakhir": (26.0325, 50.5106),             # Bahrain outer
    "Saudi Arabian": (21.6319, 39.1044),      # Jeddah Corniche
    "Singapore": (1.2914, 103.8640),          # Marina Bay
    "Spanish": (41.5700, 2.2611),             # Barcelona-Catalunya
    "Styrian": (47.2197, 14.7647),            # Red Bull Ring
    "São Paulo": (-23.7036, -46.6997),        # Interlagos
    "Turkish": (40.9517, 29.4050),            # Istanbul Park
    "Tuscan": (43.9975, 11.3719),             # Mugello
    "United States": (30.1328, -97.6411),     # COTA, Austin
}


def _load_cache() -> dict:
    if FETCH_CACHE.exists():
        try:
            return json.loads(FETCH_CACHE.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    FETCH_CACHE.write_text(json.dumps(cache, indent=0))


@lru_cache(maxsize=1)
def _race_datetimes() -> dict[tuple[int, str], tuple[str, int]]:
    """(year, circuit) -> (race_date 'YYYY-MM-DD', local_start_hour) from the schedule.

    Reads the FastF1 event schedule (cached). Finds the session named 'Race' and uses
    its LOCAL datetime (the schedule's Session*Date carries the venue tz offset), so the
    precip window lines up with the actual race hours (Open-Meteo timezone=auto is local).
    """
    warnings.filterwarnings("ignore")
    logging.getLogger("fastf1").setLevel(logging.ERROR)
    from app.etl.fastf1_client import _ensure_cache

    _ensure_cache()
    import fastf1

    out: dict[tuple[int, str], tuple[str, int]] = {}
    for year in range(2018, 2027):
        try:
            sched = fastf1.get_event_schedule(year, include_testing=False)
        except Exception:
            continue
        for _, row in sched.iterrows():
            if int(row["RoundNumber"]) == 0:
                continue
            circuit = str(row["EventName"]).replace(" Grand Prix", "").strip()
            # The race is the session named 'Race' (last session on conventional and
            # sprint weekends alike).
            dt = None
            for i in range(1, 6):
                if str(row.get(f"Session{i}")) == "Race":
                    dt = row.get(f"Session{i}Date")
                    break
            if dt is None:
                dt = row.get("Session5Date")
            try:
                date_str = dt.strftime("%Y-%m-%d")
                hour = int(dt.hour)
            except Exception:
                continue
            out[(year, circuit)] = (date_str, hour)
    return out


def _fetch_precip(lat: float, lon: float, date: str, cache: dict) -> dict | None:
    """Hourly precip/temperature for one venue-day from the ERA5 archive (cached)."""
    key = f"{lat:.4f},{lon:.4f},{date}"
    if key in cache:
        return cache[key]
    import requests

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date,
        "end_date": date,
        "hourly": "precipitation,rain,temperature_2m",
        "timezone": "auto",
    }
    try:
        r = requests.get(ARCHIVE_URL, params=params, timeout=30)
        r.raise_for_status()
        h = r.json().get("hourly", {})
    except Exception:
        return None
    payload = {
        "precip": h.get("precipitation") or [],
        "rain": h.get("rain") or [],
        "temp": h.get("temperature_2m") or [],
    }
    cache[key] = payload
    _save_cache(cache)
    return payload


def _window_stats(payload: dict, start_hour: int) -> dict:
    """Reduce hourly arrays to race-window precip + temperature features."""
    n = len(payload.get("precip", []))
    lo = max(0, min(start_hour, max(n - 1, 0)))
    hi = min(n, lo + RACE_WINDOW_H)

    def clean(seq):
        return [float(x) for x in seq[lo:hi] if x is not None]

    p = clean(payload.get("precip", []))
    t = clean(payload.get("temp", []))
    precip_sum = round(sum(p), 3)
    precip_max = round(max(p), 3) if p else 0.0
    return {
        "precip_mm_window": precip_sum,   # total rainfall over the race window (mm)
        "precip_mm_max": precip_max,      # peak hourly intensity (mm/h)
        "wet": bool(precip_max >= WET_MM_THRESHOLD),
        "temp_c": round(sum(t) / len(t), 1) if t else None,
        "window": f"{lo:02d}:00-{hi:02d}:00",
    }


def build_weather_table(*, force: bool = False) -> pl.DataFrame:
    """One row per R race with race-window precipitation features. Caches to parquet."""
    if WEATHER_PARQUET.exists() and not force:
        return pl.read_parquet(WEATHER_PARQUET)

    from app.models.features import _race_seq

    laps = pl.read_parquet(LAPS_PARQUET, columns=["year", "circuit", "session_name"])
    races = (
        laps.filter(pl.col("session_name") == "R")
        .select(["year", "circuit"])
        .unique()
        .to_dicts()
    )
    seq = _race_seq()
    dts = _race_datetimes()
    cache = _load_cache()

    rows: list[dict] = []
    missing_coords: set[str] = set()
    for rk in races:
        year, circuit = int(rk["year"]), rk["circuit"]
        coords = CIRCUIT_COORDS.get(circuit)
        if coords is None:
            missing_coords.add(circuit)
            continue
        dt = dts.get((year, circuit))
        if dt is None:
            continue
        date, hour = dt
        payload = _fetch_precip(coords[0], coords[1], date, cache)
        if payload is None:
            continue
        stats = _window_stats(payload, hour)
        rows.append({
            "year": year,
            "circuit": circuit,
            "seq": seq.get((year, circuit), 9999),
            "race_date": date,
            **stats,
            "source": "open-meteo-archive",
        })

    if missing_coords:
        logging.getLogger(__name__).warning("weather: no coords for %s", sorted(missing_coords))
    out = pl.DataFrame(rows).sort(["seq"])
    out.write_parquet(WEATHER_PARQUET)
    return out


@lru_cache(maxsize=1)
def weather_map() -> dict[tuple[int, str], dict]:
    """(year, circuit) -> weather row, for the predictor/validator to look up rain."""
    if not WEATHER_PARQUET.exists():
        return {}
    return {(int(r["year"]), r["circuit"]): r for r in pl.read_parquet(WEATHER_PARQUET).to_dicts()}


def crosscheck_fastf1(samples: list[tuple[int, str]]) -> list[dict]:
    """Validate the Open-Meteo wet flag against FastF1's own session weather (Rainfall).

    FastF1 weather is the actual trackside measurement, perfectly windowed to the race;
    if our archive-derived wet flag agrees with it on known races we trust the artifact.
    Slow (loads each session) -- call on a handful of races only.
    """
    warnings.filterwarnings("ignore")
    logging.getLogger("fastf1").setLevel(logging.ERROR)
    from app.etl.fastf1_client import _ensure_cache

    _ensure_cache()
    import fastf1

    wm = weather_map()
    out: list[dict] = []
    for year, circuit in samples:
        ff1_wet = None
        try:
            s = fastf1.get_session(year, circuit, "R")
            s.load(laps=False, telemetry=False, weather=True, messages=False)
            wd = s.weather_data
            ff1_wet = bool(wd["Rainfall"].any()) if wd is not None and len(wd) else None
        except Exception:
            ff1_wet = None
        ours = wm.get((year, circuit))
        out.append({
            "year": year, "circuit": circuit,
            "om_wet": ours["wet"] if ours else None,
            "om_precip_max": ours["precip_mm_max"] if ours else None,
            "fastf1_rain": ff1_wet,
            "agree": (ours is not None and ff1_wet is not None and ours["wet"] == ff1_wet),
        })
    return out


if __name__ == "__main__":
    t = build_weather_table(force=True)
    print(f"weather table: {t.height} races; wet={t.filter(pl.col('wet')).height}")
    print(t.filter(pl.col("wet")).select(
        ["year", "circuit", "precip_mm_window", "precip_mm_max", "temp_c", "window"]
    ).sort(["precip_mm_max"], descending=True).head(20))
