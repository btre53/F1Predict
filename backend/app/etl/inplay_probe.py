"""In-play step 2: does Polymarket actually MOVE during an F1 race?

Pre-race step (`market_backtest.py`) only used the last price before lights-out. Here we
pull the full CLOB `prices-history` curve at 1-minute fidelity across the whole race
window and measure intra-race movement per driver: how many points exist after lights
out, how far the price travels, how many real moves happen, and whether the eventual
winner's probability visibly climbs toward 1. If the curves are flat lines that only
jump at settlement, there are no mid-race trades to score against and the in-play backtest
(step 3) has no benchmark. Liquidity is expected to be thin -- this quantifies how thin.

Race start times come from FastF1's cached schedule (offline; Jolpica is flaky). Raw
curves are cached to data/inplay_probe.json so re-analysis is free.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

import httpx
import polars as pl

from app.etl.polymarket import CLOB, GAMMA, MARKETS_2024, SURNAME_TO_CODE, season_winner_markets

warnings.filterwarnings("ignore")
logging.getLogger("fastf1").setLevel(logging.ERROR)

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
OUT = DATA_DIR / "inplay_probe.json"

PRE = 1800       # window opens 30 min before scheduled lights-out
POST = 6 * 3600  # ... and runs 6h after, to absorb rain delays / long races
MOVE = 0.005     # |Δprice| above this counts as a real move (not quantisation noise)


def _race_start_ts_offline() -> dict[int, int]:
    """{round -> unix ts} scheduled race start (UTC) from the cached FastF1 schedule."""
    import fastf1

    from app.config import get_settings

    fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)
    sched = fastf1.get_event_schedule(2024, include_testing=False)
    out: dict[int, int] = {}
    for _, row in sched.iterrows():
        ts = row.get("Session5DateUtc")
        if ts is not None and not pl.Series([ts]).is_null().any():
            out[int(row["RoundNumber"])] = int(ts.timestamp())
    return out


def _winner_by_circuit() -> dict[str, str]:
    """Eventual race winner (3-letter code) per 2024 circuit, from laps.parquet."""
    from app.etl import backtest as bt

    full = pl.read_parquet(LAPS_PARQUET).filter(
        (pl.col("session_name") == "R") & (pl.col("year") == 2024)
    )
    out: dict[str, str] = {}
    for m in MARKETS_2024:
        race = full.filter(pl.col("circuit") == m["circuit"])
        if race.height == 0:
            continue
        actual = bt._actual_finish(race)
        if actual:
            out[m["circuit"]] = min(actual, key=actual.get)
    return out


def fetch(force: bool = False) -> dict:
    if OUT.exists() and not force:
        return json.loads(OUT.read_text())

    starts = _race_start_ts_offline()
    races: list[dict] = []
    with httpx.Client(timeout=30) as c:
        for m in MARKETS_2024:
            rts = starts.get(m["round"])
            if not rts:
                continue
            try:
                ev = c.get(f"{GAMMA}/events", params={"slug": m["slug"]}).json()
                ev = ev[0] if isinstance(ev, list) and ev else ev
            except Exception as e:  # noqa: BLE001
                print(f"  skip {m['circuit']}: {e}")
                continue
            curves: dict[str, list[list[float]]] = {}
            for mk in (ev or {}).get("markets", []):
                label = (mk.get("groupItemTitle") or "").strip()
                code = SURNAME_TO_CODE.get(label.split()[-1]) if label else None
                if not code:
                    continue
                toks = mk.get("clobTokenIds")
                toks = json.loads(toks) if isinstance(toks, str) else toks
                if not toks:
                    continue
                try:
                    h = c.get(
                        f"{CLOB}/prices-history",
                        params={"market": toks[0], "startTs": rts - PRE,
                                "endTs": rts + POST, "fidelity": 1},
                    ).json().get("history", [])
                except Exception:
                    h = []
                if h:
                    curves[code] = [[int(p["t"]), float(p["p"])] for p in h]
            races.append({"circuit": m["circuit"], "round": m["round"],
                          "race_ts": rts, "curves": curves})
            print(f"  {m['circuit']:14s} drivers={len(curves)} "
                  f"pts={sum(len(v) for v in curves.values())}")

    out = {"races": races, "winners": _winner_by_circuit()}
    OUT.write_text(json.dumps(out))
    print(f"\nwrote {OUT}")
    return out


def _winner_code(year: int, circuit: str) -> str | None:
    """Eventual race winner (3-letter code) for a single race, from laps.parquet."""
    from app.etl import backtest as bt

    race = pl.read_parquet(LAPS_PARQUET).filter(
        (pl.col("session_name") == "R")
        & (pl.col("year") == year)
        & (pl.col("circuit") == circuit)
    )
    if race.height == 0:
        return None
    actual = bt._actual_finish(race)
    return min(actual, key=actual.get) if actual else None


def _curves_for_event(c: httpx.Client, slug: str, race_ts: int) -> dict[str, list[list[float]]]:
    """Per-driver in-play winner-price curve from CLOB prices-history for one event."""
    try:
        ev = c.get(f"{GAMMA}/events", params={"slug": slug}).json()
        ev = ev[0] if isinstance(ev, list) and ev else ev
    except Exception:
        return {}
    curves: dict[str, list[list[float]]] = {}
    for mk in (ev or {}).get("markets", []):
        label = (mk.get("groupItemTitle") or "").strip()
        code = SURNAME_TO_CODE.get(label.split()[-1]) if label else None
        if not code:
            continue
        toks = mk.get("clobTokenIds")
        toks = json.loads(toks) if isinstance(toks, str) else toks
        if not toks:
            continue
        try:
            h = c.get(
                f"{CLOB}/prices-history",
                params={"market": toks[0], "startTs": race_ts - PRE,
                        "endTs": race_ts + POST, "fidelity": 1},
            ).json().get("history", [])
        except Exception:
            h = []
        if h:
            curves[code] = [[int(p["t"]), float(p["p"])] for p in h]
    return curves


def fetch_year(year: int, only: set[str] | None = None, force: bool = False) -> dict:
    """Merge in-play winner-market curves for `year`'s completed races into the probe file.

    Year-aware and incremental: reuses `season_winner_markets` (slug-drift-robust + race
    timestamps from the cached FastF1 schedule), skips races already captured (unless
    `force`), and never clobbers the legacy 2024 entries. `only` restricts to a set of
    circuit names (e.g. just the race(s) a refresh ingested). Best-effort -- a race whose
    market/curve can't be resolved is simply skipped. Returns the updated probe dict.
    """
    data = json.loads(OUT.read_text()) if OUT.exists() else {"races": [], "winners": {}}
    have = {(r.get("year", 2024), r["circuit"]) for r in data["races"]}
    added = 0
    with httpx.Client(timeout=30) as c:
        for m in season_winner_markets(year):
            circuit = m["circuit"]
            if only is not None and circuit not in only:
                continue
            key = (year, circuit)
            if key in have and not force:
                continue
            curves = _curves_for_event(c, m["slug"], m["race_ts"])
            if not curves:
                continue
            data["races"] = [
                r for r in data["races"] if (r.get("year", 2024), r["circuit"]) != key
            ]
            data["races"].append({
                "circuit": circuit, "year": year, "round": m["round"],
                "race_ts": m["race_ts"], "winner": _winner_code(year, circuit),
                "curves": curves,
            })
            added += 1
            print(f"  {year} {circuit:14s} drivers={len(curves)} "
                  f"pts={sum(len(v) for v in curves.values())}")
    OUT.write_text(json.dumps(data))
    print(f"fetch_year({year}): +{added} race(s) -> {OUT}")
    return data


def analyse() -> None:
    data = fetch()
    winners = data["winners"]
    print(f"\n{'circuit':15s} {'drv':>3s} {'inplay':>6s} {'moves':>5s} "
          f"{'range':>6s} {'maxjmp':>6s}   winner-price climb")
    race_rows: list[dict] = []
    for r in data["races"]:
        rts = r["race_ts"]
        win = winners.get(r["circuit"])
        race_inplay_pts = 0
        race_moves = 0
        win_climb = None
        for code, curve in r["curves"].items():
            inplay = [(t, p) for t, p in curve if t > rts]
            if not inplay:
                continue
            ps = [p for _, p in inplay]
            moves = sum(1 for a, b in zip(ps, ps[1:]) if abs(b - a) > MOVE)
            rng = max(ps) - min(ps)
            maxjmp = max((abs(b - a) for a, b in zip(ps, ps[1:])), default=0.0)
            race_inplay_pts += len(inplay)
            race_moves += moves
            if code == win:
                # how much did the winner's in-play price rise from its opening?
                win_climb = max(ps) - ps[0]
                print(f"{r['circuit']:15s} {code:>3s} {len(inplay):6d} {moves:5d} "
                      f"{rng:6.3f} {maxjmp:6.3f}   first {ps[0]:.3f} -> max {max(ps):.3f}  *WINNER")
        race_rows.append({
            "circuit": r["circuit"], "winner": win,
            "inplay_pts": race_inplay_pts, "moves": race_moves,
            "win_climb": round(win_climb, 3) if win_climb is not None else None,
        })

    print("\nPer-race summary (across all priced drivers):")
    print(f"{'circuit':15s} {'inplay_pts':>10s} {'moves':>6s} {'winner_climb':>12s}")
    live = 0
    for rr in race_rows:
        wc = f"{rr['win_climb']:+.3f}" if rr["win_climb"] is not None else "   n/a"
        flag = ""
        if rr["moves"] >= 10:
            live += 1
            flag = "  <- live"
        print(f"{rr['circuit']:15s} {rr['inplay_pts']:10d} {rr['moves']:6d} {wc:>12s}{flag}")
    n = len(race_rows)
    print(f"\nVERDICT: {live}/{n} races show in-play movement (>=10 price moves across drivers).")
    tot_moves = sum(rr["moves"] for rr in race_rows)
    tot_pts = sum(rr["inplay_pts"] for rr in race_rows)
    print(f"  total in-play points {tot_pts}, total moves {tot_moves} "
          f"({tot_moves/max(tot_pts,1)*100:.1f}% of steps were a real move)")
    climbs = [rr["win_climb"] for rr in race_rows if rr["win_climb"] is not None]
    if climbs:
        good = sum(1 for c in climbs if c > 0.1)
        print(f"  winner's price climbed >0.10 in {good}/{len(climbs)} races "
              f"(median climb {sorted(climbs)[len(climbs)//2]:+.3f}) -- proxy for genuine repricing")


if __name__ == "__main__":
    analyse()
