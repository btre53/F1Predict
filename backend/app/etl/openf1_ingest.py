"""FastF1-free lap ingest from OpenF1 (+ Jolpica for the calendar).

Reproduces the SAME normalized lap schema as `fastf1_client.load_session_laps`, but sourced
entirely from OpenF1 (api.openf1.org) and Jolpica (api.jolpi.ca). Neither is datacenter-IP
blocked, so this runs on the VPS where FastF1's livetiming endpoint 403s (see the
`f1-datacenter-ip-block` finding in docs/CURRENT_STATE.md). FastF1 stays available as a
fallback for telemetry/GPS work; this is the production ingest path going forward.

Per session_key we pull OpenF1 `drivers` (code+team), `laps` (times/sectors/speed-trap/pit-out),
`stints` (compound/tyre age), `pit` (pit-in laps), `position` (per-lap order), and `race_control`
(safety-car / VSC / red laps -> track_status). Jolpica gives each race's date so we can match the
right OpenF1 session, plus the completed-race calendar (replacing FastF1's schedule).

Two columns have no direct OpenF1 equivalent and are approximated (documented in-line):
  - track_status: derived from race_control SC/VSC/red windows; transient yellows default to green.
  - is_accurate: a clean-lap heuristic (timed, all sectors, not in/out, green track).
"""

from __future__ import annotations

import bisect
import datetime as dt
from functools import lru_cache

import polars as pl

from app.etl import jolpica as jol
from app.etl import openf1 as of1
from app.etl.fastf1_client import LAP_COLUMNS, era_for_year

# our session_name -> OpenF1 `session_name`
_OF1_SESSION = {
    "R": "Race", "Q": "Qualifying", "S": "Sprint", "SQ": "Sprint Qualifying",
    "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
}


def _circuit(race_name: str) -> str:
    return race_name.replace(" Grand Prix", "").strip()


@lru_cache(maxsize=8)
def year_schedule(year: int) -> tuple[tuple[str, str, int], ...]:
    """((circuit, race_date_YYYY-MM-DD, round), ...) for a season, from Jolpica. Cached."""
    j = jol._get(f"{year}.json")
    if not j:
        return ()
    races = j["MRData"]["RaceTable"]["Races"]
    return tuple(
        (_circuit(r["raceName"]), r["date"], int(r["round"]))
        for r in races if r.get("date")
    )


def _race_date(year: int, circuit: str) -> str | None:
    for c, d, _ in year_schedule(year):
        if c == circuit:
            return d
    return None


def _resolve_session_key(year: int, circuit: str, session_name: str) -> int | None:
    """The OpenF1 session_key for (year, circuit, session), matched by date to Jolpica.

    OpenF1 keys sessions by country/circuit names that don't match our circuit convention,
    so we pick the session of the right TYPE whose date is closest to the race date (race
    weekends are weeks apart, so the nearest same-type session is unambiguous)."""
    of1_name = _OF1_SESSION.get(session_name)
    rdate = _race_date(year, circuit)
    if of1_name is None or rdate is None:
        return None
    sessions = of1._get("sessions", year=year, session_name=of1_name)
    if not sessions:
        return None
    target = dt.date.fromisoformat(rdate)
    best, best_gap = None, 99
    for s in sessions:
        ds = s.get("date_start")
        sk = s.get("session_key")
        if not ds or sk is None:
            continue
        gap = abs((dt.date.fromisoformat(ds[:10]) - target).days)
        if gap < best_gap:
            best, best_gap = int(sk), gap
    return best if best_gap <= 4 else None


def _track_status_by_lap(rc: list[dict]) -> dict[int, str]:
    """{lap_number -> FastF1-style track_status code} from race_control messages.

    Codes: '1' clear, '4' safety car, '5' red, '6' virtual safety car. Transient sector
    yellows are left as '1' (the model keys clean-air pace off SC/green, not sector yellows)."""
    events = sorted(
        [e for e in rc if e.get("lap_number") is not None and e.get("date")],
        key=lambda e: e["date"],
    )
    status: dict[int, str] = {}
    sc = vsc = red = None  # open-window start laps
    last_lap = 0
    for e in events:
        lap = int(e["lap_number"])
        last_lap = max(last_lap, lap)
        msg = (e.get("message") or "").upper()
        flag = (e.get("flag") or "").upper()
        cat = (e.get("category") or "")
        if "VIRTUAL SAFETY CAR" in msg or cat == "VirtualSafetyCar":
            if "DEPLOY" in msg:
                vsc = lap
            elif ("ENDING" in msg or "IN THIS LAP" in msg) and vsc is not None:
                for L in range(vsc, lap + 1):
                    status[L] = "6"
                vsc = None
        elif "SAFETY CAR" in msg or cat == "SafetyCar":
            if "DEPLOY" in msg:
                sc = lap
            elif ("IN THIS LAP" in msg or "ENDING" in msg) and sc is not None:
                for L in range(sc, lap + 1):
                    status[L] = "4"
                sc = None
        elif flag == "RED":
            red = lap
        elif flag == "GREEN" and red is not None:
            for L in range(red, lap + 1):
                status.setdefault(L, "5")
            red = None
    # close any window left open at the chequered flag
    for start, code in ((sc, "4"), (vsc, "6"), (red, "5")):
        if start is not None:
            for L in range(start, last_lap + 1):
                status.setdefault(L, code)
    return status


def _positions_by_lap(positions: list[dict], lap_end: dict[tuple[int, int], float]) -> dict:
    """{(driver_number, lap_number) -> position} = the order in effect at each lap's end."""
    timeline: dict[int, tuple[list[float], list[int]]] = {}
    for p in sorted(positions, key=lambda r: r.get("date") or ""):
        dn, pos, d = p.get("driver_number"), p.get("position"), p.get("date")
        if dn is None or pos is None or d is None:
            continue
        ts, ps = timeline.setdefault(int(dn), ([], []))
        ts.append(of1._ts(d))
        ps.append(int(pos))
    out: dict[tuple[int, int], int] = {}
    for (dn, lap), end_ts in lap_end.items():
        tl = timeline.get(dn)
        if not tl:
            continue
        ts, ps = tl
        i = bisect.bisect_right(ts, end_ts) - 1
        if i >= 0:
            out[(dn, lap)] = ps[i]
    return out


def load_session_laps_openf1(year: int, circuit: str, session_name: str) -> pl.DataFrame:
    """One session's laps as the normalized Polars frame (empty frame if unavailable)."""
    empty = pl.DataFrame(schema={c: pl.Utf8 for c in LAP_COLUMNS})
    sk = _resolve_session_key(year, circuit, session_name)
    if sk is None:
        return empty
    drivers = of1._get("drivers", session_key=sk)
    laps = of1._get("laps", session_key=sk)
    if not drivers or not laps:
        return empty

    num2code = {int(d["driver_number"]): d.get("name_acronym") for d in drivers}
    num2team = {int(d["driver_number"]): d.get("team_name") for d in drivers}

    # From OpenF1 `stints`: per-lap COMPOUND and native tyre age. OpenF1's tyre_age_at_start is
    # its own best guess at the real tyre set (we lack F1's set IDs); it has the lowest mean
    # error vs FastF1, so we trust it for tyre_life/fresh. Its occasional red-flag-split (age
    # reset mid-tyre on one car) is a documented source limitation -- a ~1-2 lap mean age error
    # the degradation model (which bins by age) absorbs.
    stints = of1._get("stints", session_key=sk)
    compound_at: dict[tuple[int, int], str | None] = {}
    life_at: dict[tuple[int, int], tuple[int, bool]] = {}
    for s in stints:
        dn = s.get("driver_number")
        l0, l1 = s.get("lap_start"), s.get("lap_end")
        if dn is None or l0 is None or l1 is None:
            continue
        dn, l0, l1 = int(dn), int(l0), int(l1)
        age0 = int(s.get("tyre_age_at_start") or 0)
        for L in range(l0, l1 + 1):
            compound_at[(dn, L)] = s.get("compound")
            life_at[(dn, L)] = (age0 + (L - l0) + 1, age0 == 0)  # FastF1 TyreLife counts the lap

    pit_laps = {(int(p["driver_number"]), int(p["lap_number"]))
                for p in of1._get("pit", session_key=sk)
                if p.get("driver_number") is not None and p.get("lap_number") is not None}

    # stint NUMBER from the pit-out flag: increments at every out-lap incl. red-flag restarts,
    # matching FastF1's stint splits (it's a clean integer counter, unlike OpenF1's age).
    stint_no: dict[tuple[int, int], int] = {}
    by_drv_laps: dict[int, list[tuple[int, bool]]] = {}
    for lp in laps:
        dn, ln = lp.get("driver_number"), lp.get("lap_number")
        if dn is not None and ln is not None:
            by_drv_laps.setdefault(int(dn), []).append((int(ln), bool(lp.get("is_pit_out_lap"))))
    for dn, lst in by_drv_laps.items():
        lst.sort()
        stint = 1
        for i, (ln, pout) in enumerate(lst):
            if i > 0 and pout:
                stint += 1
            stint_no[(dn, ln)] = stint

    ts_by_lap = _track_status_by_lap(of1._get("race_control", session_key=sk))

    lap_end: dict[tuple[int, int], float] = {}
    for lp in laps:
        dn, ln, dstart, dur = (lp.get("driver_number"), lp.get("lap_number"),
                               lp.get("date_start"), lp.get("lap_duration"))
        if dn is not None and ln is not None and dstart and isinstance(dur, (int, float)):
            lap_end[(int(dn), int(ln))] = of1._ts(dstart) + float(dur)
    pos_at = _positions_by_lap(of1._get("position", session_key=sk), lap_end)

    rows: list[dict] = []
    for lp in laps:
        dn = lp.get("driver_number")
        ln = lp.get("lap_number")
        if dn is None or ln is None:
            continue
        dn, ln = int(dn), int(ln)
        code = num2code.get(dn)
        if not code:
            continue
        comp = compound_at.get((dn, ln))
        life = life_at.get((dn, ln))
        ts_code = ts_by_lap.get(ln, "1")
        s1, s2, s3 = (lp.get("duration_sector_1"), lp.get("duration_sector_2"),
                      lp.get("duration_sector_3"))
        ltime = lp.get("lap_duration")
        is_pit_out = bool(lp.get("is_pit_out_lap"))
        is_pit_in = (dn, ln) in pit_laps
        accurate = (
            isinstance(ltime, (int, float)) and None not in (s1, s2, s3)
            and not is_pit_out and not is_pit_in and ts_code == "1"
        )
        rows.append({
            "year": year, "circuit": circuit, "session_name": session_name,
            "regulation_era": era_for_year(year).value,
            "driver": code, "driver_number": dn, "team": num2team.get(dn),
            "lap_number": ln,
            "stint": stint_no.get((dn, ln)),
            "compound": comp.upper() if comp else None,
            "tyre_life": life[0] if life else None,
            "fresh_tyre": life[1] if life else None,
            "lap_time_s": float(ltime) if isinstance(ltime, (int, float)) else None,
            "sector1_s": float(s1) if isinstance(s1, (int, float)) else None,
            "sector2_s": float(s2) if isinstance(s2, (int, float)) else None,
            "sector3_s": float(s3) if isinstance(s3, (int, float)) else None,
            "speed_st": float(lp["st_speed"]) if isinstance(lp.get("st_speed"), (int, float)) else None,
            "track_status": ts_code,
            "position": pos_at.get((dn, ln)),
            "is_pit_out": is_pit_out,
            "is_pit_in": is_pit_in,
            "is_accurate": bool(accurate),
        })

    if not rows:
        return empty
    return pl.DataFrame(rows).with_columns(
        pl.col("driver_number").cast(pl.Int32),
        pl.col("lap_number").cast(pl.Int32),
        pl.col("stint").cast(pl.Int32),
        pl.col("tyre_life").cast(pl.Int32),
        pl.col("position").cast(pl.Int32),
    ).select(LAP_COLUMNS)


def ingest_events_openf1(
    events: list[tuple[int, str]], sessions: tuple[str, ...] = ("Q", "R")
) -> pl.DataFrame:
    """Batch OpenF1 ingest mirroring ingest.ingest_events, but FastF1-free.

    `events` is [(year, gp_or_circuit)]; the GP may carry the ' Grand Prix' suffix (it's
    stripped to our circuit key). Bad sessions are skipped, never fatal."""
    frames: list[pl.DataFrame] = []
    for year, gp in events:
        circuit = _circuit(str(gp))
        for sess in sessions:
            try:
                df = load_session_laps_openf1(year, circuit, sess)
                if df.height:
                    frames.append(df)
                print(f"  [{year} {circuit} {sess}] {df.height} laps (openf1)", flush=True)
            except Exception as e:  # noqa: BLE001 — keep going on a bad session
                print(f"  [{year} {circuit} {sess}] SKIP: {type(e).__name__}: {e}", flush=True)
    return pl.concat(frames, how="vertical_relaxed") if frames else pl.DataFrame()


if __name__ == "__main__":
    import sys

    y, c, s = int(sys.argv[1]), sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "R")
    df = load_session_laps_openf1(y, c, s)
    print(f"{y} {c} {s}: {df.height} laps")
    if df.height:
        print(df.head(5))
