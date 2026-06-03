"""Polymarket read-only client + vig removal (docs/science/03 section 5).

We never place orders. This reads public prices, strips the vig (overround) to get
clean implied probabilities, and computes model-vs-market edge + fractional-Kelly
sizing for *display only*. The live-execution path stays off by design.

Network calls are best-effort: there may be no live F1 markets at a given time, so
every function degrades gracefully and the API surfaces a clear status.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
JOLPICA = "https://api.jolpi.ca/ergast/f1"

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
MARKETS_SNAPSHOT = DATA_DIR / "markets_snapshot.json"

# Surname (last token of the market label) -> 3-letter code, for joining markets to
# our data. Covers every named driver seen across 2024-2025 F1 winner markets.
SURNAME_TO_CODE: dict[str, str] = {
    "Verstappen": "VER", "Norris": "NOR", "Leclerc": "LEC", "Hamilton": "HAM",
    "Russell": "RUS", "Sainz": "SAI", "Piastri": "PIA", "Perez": "PER",
    "Alonso": "ALO", "Albon": "ALB", "Antonelli": "ANT", "Tsunoda": "TSU",
    "Lawson": "LAW", "Stroll": "STR", "Hadjar": "HAD", "Gasly": "GAS",
    "Bearman": "BEA", "Hulkenberg": "HUL", "Bortoleto": "BOR",
    "Colapinto": "COL", "Ocon": "OCO", "Ricciardo": "RIC", "Zhou": "ZHO",
    "Magnussen": "MAG", "Bottas": "BOT", "Sargeant": "SAR",
}

# Polymarket F1 race-winner coverage began at the 2024 British GP. These are the 11
# 2024 races that overlap our results data, mapped to (our circuit name, Jolpica
# round). Slugs are enumerated (Polymarket's 2024 slugs contain typos).
MARKETS_2024: list[dict] = [
    {"slug": "british-grand-prix-winner", "circuit": "British", "round": 12},
    {"slug": "dutch-grand-prix-winner", "circuit": "Dutch", "round": 15},
    {"slug": "italian-grand-prix-winner", "circuit": "Italian", "round": 16},
    {"slug": "azerbijan-grand-prix-winner", "circuit": "Azerbaijan", "round": 17},
    {"slug": "singapore-grand-prix-winner", "circuit": "Singapore", "round": 18},
    {"slug": "us-grand-prix-winner", "circuit": "United States", "round": 19},
    {"slug": "mexican-grand-prix-winner", "circuit": "Mexico City", "round": 20},
    {"slug": "brazlian-grand-prix-winner", "circuit": "São Paulo", "round": 21},
    {"slug": "las-vegas-grand-prix-winner", "circuit": "Las Vegas", "round": 22},
    {"slug": "qatar-grand-prix-winner", "circuit": "Qatar", "round": 23},
    {"slug": "abu-dhabi-grand-prix-winner", "circuit": "Abu Dhabi", "round": 24},
]


def _ts(iso: str) -> int:
    import datetime as dt

    return int(dt.datetime.fromisoformat(iso[:19] + "+00:00").timestamp())


def race_start_ts(year: int, rnd: int, timeout: float = 20.0) -> int | None:
    """Authoritative lights-out time (unix sec) from Jolpica."""
    try:
        r = httpx.get(f"{JOLPICA}/{year}/{rnd}/results.json", timeout=timeout)
        race = r.json()["MRData"]["RaceTable"]["Races"][0]
        return _ts(f"{race['date']}T{race.get('time', '13:00:00Z').rstrip('Z')}")
    except Exception:
        return None


def prerace_devig(
    slug: str, race_ts: int, timeout: float = 25.0
) -> dict[str, float]:
    """De-vigged per-driver win probabilities snapshotted just before lights-out.

    Returns {driver_code: clean_prob}. Uses the last price before ``race_ts`` for
    each driver's YES token, then normalises across drivers (strips the overround).
    """
    import json as _json

    try:
        with httpx.Client(timeout=timeout) as c:
            ev = c.get(f"{GAMMA}/events", params={"slug": slug}).json()
            ev = ev[0] if isinstance(ev, list) and ev else ev
            if not ev:
                return {}
            start = _ts(ev["startDate"])
            end = min(_ts(ev["endDate"]), start + 14 * 86400)
            raw: dict[str, float] = {}
            for m in ev.get("markets", []):
                label = (m.get("groupItemTitle") or "").strip()
                code = SURNAME_TO_CODE.get(label.split()[-1]) if label else None
                if not code:
                    continue
                toks = m.get("clobTokenIds")
                toks = _json.loads(toks) if isinstance(toks, str) else toks
                if not toks:
                    continue
                h = c.get(
                    f"{CLOB}/prices-history",
                    params={"market": toks[0], "startTs": start, "endTs": end, "fidelity": 10},
                ).json().get("history", [])
                pre = [p["p"] for p in h if p["t"] <= race_ts]
                if pre:
                    raw[code] = float(pre[-1])
    except Exception:
        return {}
    return devig(raw)


def devig(prices: dict[str, float]) -> dict[str, float]:
    """Remove the overround: normalise outcome mid-prices so they sum to 1.

    For a multi-outcome market the mids sum to > 1 (the book's vig). Dividing each
    by the total recovers a proper probability distribution.
    """
    total = sum(v for v in prices.values() if v and v > 0)
    if total <= 0:
        return {}
    return {k: (v / total if v and v > 0 else 0.0) for k, v in prices.items()}


def overround(prices: dict[str, float]) -> float:
    """The book's vig: sum of raw prices minus 1 (e.g. 0.06 = 6% overround)."""
    return sum(v for v in prices.values() if v and v > 0) - 1.0


def kelly_fraction(p_model: float, p_market: float, scale: float = 0.25) -> float:
    """Fractional-Kelly stake (display only) for a binary outcome priced at p_market.

    For a binary contract that pays 1 if it resolves YES, buying at price b=p_market
    has net odds (1-b)/b. Kelly f* = (p*(1+odds) - 1)/odds; we scale it down.
    """
    b = min(max(p_market, 1e-4), 1 - 1e-4)
    odds = (1 - b) / b
    f = (p_model * (1 + odds) - 1) / odds
    return max(0.0, f) * scale


# Max bid/ask spread (absolute, on a 0-1 contract) for which a midpoint is trustworthy.
# On thin F1 books one side is often empty or the spread is huge, so a naive mid is
# meaningless -- past this we fall back to the last executed trade, then to Gamma.
MAX_SPREAD = 0.10


def _clob_books(token_ids: list[str], client) -> dict[str, dict]:
    """Batch-fetch CLOB order books -> {token_id (asset_id): book}. {} on any error."""
    out: dict[str, dict] = {}
    try:
        for i in range(0, len(token_ids), 50):
            chunk = token_ids[i : i + 50]
            r = client.post(f"{CLOB}/books", json=[{"token_id": t} for t in chunk])
            if r.status_code != 200:
                continue
            for b in r.json():
                if b.get("asset_id"):
                    out[b["asset_id"]] = b
    except Exception:
        pass
    return out


def _book_price(book: dict, gamma_price: float) -> tuple:
    """Robust outcome price from an order book: (price, bid, ask, spread, source).

    Only midpoints a TWO-SIDED book with a reasonable spread (the trustworthy case that
    matches what Polymarket shows). One-sided or wide-spread books fall back to the last
    executed trade, then to the Gamma last/mid -- never a meaningless mid across a gap."""
    def _flt(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    bids = book.get("bids") or []
    asks = book.get("asks") or []
    bb = max((f for f in (_flt(b.get("price")) for b in bids) if f is not None), default=None)
    ba = min((f for f in (_flt(a.get("price")) for a in asks) if f is not None), default=None)
    last = _flt(book.get("last_trade_price"))
    spread = round(ba - bb, 4) if (bb is not None and ba is not None) else None
    if bb is not None and ba is not None and 0 <= (ba - bb) <= MAX_SPREAD:
        return (bb + ba) / 2.0, bb, ba, spread, "book_mid"
    if last is not None and 0.0 < last < 1.0:
        return last, bb, ba, spread, "last_trade"
    return gamma_price, bb, ba, spread, "gamma"


def _event_to_market(ev: dict, client=None) -> dict | None:
    """Convert a Gamma event (multi-outcome) to the LiveMarket display shape.

    Prices come from the CLOB order book (best bid/ask -> midpoint) so they match what
    Polymarket shows, with safe fallbacks on thin books (see _book_price). Falls back to
    Gamma `outcomePrices` entirely if the book fetch is unavailable."""
    import json as _json

    rows: list[tuple[str, str, float]] = []  # (label, yes-token, gamma price)
    for m in ev.get("markets", []):
        label = (m.get("groupItemTitle") or "").strip()
        op = m.get("outcomePrices")
        op = _json.loads(op) if isinstance(op, str) else op
        toks = m.get("clobTokenIds")
        toks = _json.loads(toks) if isinstance(toks, str) else toks
        if label and op and toks:
            rows.append((label, toks[0], float(op[0])))
    if len(rows) < 2:
        return None

    books = _clob_books([t for _, t, _ in rows], client) if client is not None else {}
    prices: dict[str, float] = {}
    meta: dict[str, tuple] = {}
    for label, tok, gp in rows:
        price, bid, ask, spread, source = (
            _book_price(books[tok], gp) if tok in books else (gp, None, None, None, "gamma")
        )
        prices[label] = price
        meta[label] = (bid, ask, spread, source)
    clean = devig(prices)
    return {
        "question": ev.get("title", ""),
        "slug": ev.get("slug", ""),
        "overround": round(overround(prices), 4),
        "outcomes": [
            {
                "name": n,
                "price": round(p, 4),
                "implied": round(clean.get(n, 0.0), 4),
                "bid": round(meta[n][0], 4) if meta[n][0] is not None else None,
                "ask": round(meta[n][1], 4) if meta[n][1] is not None else None,
                "spread": meta[n][2],
                "source": meta[n][3],
            }
            for n, p in sorted(prices.items(), key=lambda x: -x[1])
        ],
    }


# Polymarket's race-name quirks vs FastF1 EventName (extend if a new race mismatches).
_SLUG_ALIASES = {"sao-paulo": "sao-paulo", "emilia-romagna": "emilia-romagna"}


def _event_slug_name(event_name: str) -> str:
    """EventName -> Polymarket slug stem (e.g. 'São Paulo Grand Prix' -> 'sao-paulo')."""
    name = event_name.replace(" Grand Prix", "").strip().lower()
    name = name.replace(" ", "-").replace("ã", "a").replace("í", "i")
    return _SLUG_ALIASES.get(name, name)


def _event_year(ev: dict) -> int | None:
    for k in ("endDate", "startDate"):
        v = ev.get(k)
        if isinstance(v, str) and len(v) >= 4 and v[:4].isdigit():
            return int(v[:4])
    return None


def resolve_winner_slug(name: str, year: int, race_date: str, client) -> str | None:
    """Find the real Polymarket winner-market slug for a race, robust to format drift.

    Polymarket used `<name>-grand-prix-winner` (no prefix/date) for 2024 and most of 2025,
    then switched to `f1-<name>-grand-prix-winner-<race-date>` late-2025 / 2026. We try the
    plausible candidates and VERIFY the resolved event's year matches -- so colliding bare
    slugs (e.g. `british-grand-prix-winner` is the 2024 market) are rejected for other years."""
    cands = [f"f1-{name}-grand-prix-winner-{race_date}"]
    if year <= 2025:
        cands.insert(0, f"{name}-grand-prix-winner")
    for slug in cands:
        try:
            ev = client.get(f"{GAMMA}/events", params={"slug": slug}).json()
            ev = ev[0] if isinstance(ev, list) and ev else ev
            if ev and _event_year(ev) == year:
                return slug
        except Exception:
            continue
    return None


def season_winner_markets(year: int, timeout: float = 20.0) -> list[dict]:
    """{slug, circuit, round, race_ts} for each COMPLETED race in `year` that has a (year-
    verified) Polymarket winner market. Race timestamp from the FastF1 schedule (offline/
    cached), avoiding flaky Jolpica. [] if the schedule is unreachable."""
    out: list[dict] = []
    try:
        import datetime as dt

        import fastf1

        from app.config import get_settings

        fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)
        now = dt.datetime.now(dt.timezone.utc)
        sched = fastf1.get_event_schedule(year, include_testing=False)
        with httpx.Client(timeout=timeout) as c:
            for _, row in sched.iterrows():
                rnd = int(row["RoundNumber"])
                if rnd == 0:
                    continue
                race = row.get("Session5DateUtc")
                if race is None:
                    continue
                if race.tzinfo is None:
                    race = race.tz_localize("UTC")
                if race > now:
                    continue  # not yet run
                name = _event_slug_name(str(row["EventName"]))
                slug = resolve_winner_slug(name, year, race.strftime("%Y-%m-%d"), c)
                if not slug:
                    continue
                out.append({
                    "slug": slug,
                    "circuit": str(row["EventName"]).replace(" Grand Prix", "").strip(),
                    "round": rnd,
                    "race_ts": int(race.timestamp()),
                })
    except Exception:
        pass
    return out


F1_TAG_ID = 435   # Polymarket's "Formula 1" tag — the ground-truth index of every F1 event.
_F1_EVENTS_CACHE: list[dict] | None = None


def classify_f1_market(slug: str) -> str:
    """Map a Polymarket F1 event slug to a canonical market TYPE.

    The single place that knows Polymarket's (inconsistent, drifting) F1 slug taxonomy, so the rest
    of the app can reason about market types instead of string-matching slugs. Used by the market
    catalog (companion-mode props), pole discovery, and the Benter market-finder. Returns "other"
    for anything unrecognised (championships, novelty markets, etc.)."""
    s = slug
    if "sprint-qualifying-pole" in s or "sprint-pole" in s:
        return "sprint_pole"
    if "sprint" in s and "winner" in s:
        return "sprint_winner"
    if ("driver-pole-position" in s or s.endswith("-pole-winner")) and "constructor" not in s:
        return "driver_pole"
    if "constructor-pole" in s:
        return "constructor_pole"
    if "driver-fastest-lap" in s or (s.endswith("-fastest-lap") and "practice" not in s and "constructor" not in s):
        return "driver_fastest_lap"
    if "constructor-fastest-lap" in s:
        return "constructor_fastest_lap"
    if "practice" in s and "fastest-lap" in s:
        return "practice_fastest_lap"
    if "safety-car" in s:
        return "safety_car"
    if "red-flag" in s:
        return "red_flag"
    if "podium" in s:
        return "driver_podium"
    if "h2h" in s or "head-to-head" in s or "matchup" in s or "finish-ahead" in s:
        return "head_to_head"
    if "champion" in s or "drivers-champion" in s or "constructors-champion" in s:
        return "championship"
    if "constructor" in s and ("scores" in s or "most-points" in s or "highest-score" in s):
        return "constructor_points"
    if any(p in s for p in ("2nd-place", "3rd-place", "4th-place", "5th-place")):
        return "finishing_position"
    if s.endswith("-winner") or "grand-prix-winner" in s or "-gp-winner" in s:
        return "race_winner"
    return "other"


def _f1_tag_events(timeout: float = 25.0) -> list[dict]:
    """Every event under Polymarket's Formula 1 tag (closed + open), each as
    {slug, title, closed, end_date (date|None), n_outcomes, type}. The reusable enumeration the
    whole app shares — companion-mode prop discovery, pole/championship market resolution, and the
    Benter market-finder all build on this instead of guessing slugs. Cached per process
    (one ~40-request sweep over the tag index)."""
    global _F1_EVENTS_CACHE
    if _F1_EVENTS_CACHE is not None:
        return _F1_EVENTS_CACHE
    import datetime as dt

    out: list[dict] = []
    try:
        with httpx.Client(timeout=timeout) as c:
            for closed in ("true", "false"):
                for off in range(0, 4000, 100):
                    r = c.get(f"{GAMMA}/events", params={
                        "tag_id": F1_TAG_ID, "limit": 100, "offset": off, "closed": closed}).json()
                    if not r:
                        break
                    for e in r:
                        s = e.get("slug", "")
                        if not s:
                            continue
                        end_raw = (e.get("endDate") or "")[:10]
                        try:
                            end = dt.date.fromisoformat(end_raw) if len(end_raw) == 10 else None
                        except ValueError:
                            end = None
                        out.append({
                            "slug": s,
                            "title": e.get("title", ""),
                            "closed": bool(e.get("closed")),
                            "end_date": end,
                            "n_outcomes": len(e.get("markets", [])),
                            "type": classify_f1_market(s),
                        })
                    if len(r) < 100:
                        break
    except Exception:
        pass
    # De-dup by slug (open/closed sweeps can overlap), keep first.
    seen: set[str] = set()
    uniq: list[dict] = []
    for e in out:
        if e["slug"] not in seen:
            seen.add(e["slug"])
            uniq.append(e)
    _F1_EVENTS_CACHE = uniq
    return _F1_EVENTS_CACHE


def discover_f1_markets(only_open: bool = False, market_type: str | None = None,
                        timeout: float = 25.0) -> list[dict]:
    """Catalog of Polymarket F1 markets for companion mode — every market, classified by type.

    Returns [{slug, title, type, closed, end_date (ISO|None), n_outcomes}], optionally filtered to
    still-open markets and/or a single `market_type` (see `classify_f1_market`). This is the
    foundation for surfacing live props (podium, head-to-head, fastest-lap, safety-car) and for the
    Benter blend to locate the matching live market. [] if Polymarket is unreachable."""
    evs = _f1_tag_events(timeout=timeout)
    out = []
    for e in evs:
        if only_open and e["closed"]:
            continue
        if market_type and e["type"] != market_type:
            continue
        out.append({**e, "end_date": e["end_date"].isoformat() if e["end_date"] else None})
    out.sort(key=lambda x: (x["end_date"] or "9999", x["type"]))
    return out


def _all_pole_events(timeout: float = 25.0) -> list[tuple]:
    """Driver-pole events as (slug, end_date), via the shared F1-tag enumeration — both naming
    conventions ('…-pole-winner' and '…-driver-pole-position-<date>'), constructor/sprint excluded."""
    return sorted({(e["slug"], e["end_date"]) for e in _f1_tag_events(timeout=timeout)
                   if e["type"] == "driver_pole" and e["end_date"] is not None})


def season_pole_markets(year: int, timeout: float = 20.0) -> list[dict]:
    """{slug, circuit, round, quali_ts} for each COMPLETED race in `year` that has a Polymarket
    MAIN-qualifying driver-pole market — matched by DATE, not by guessing slugs.

    We enumerate every pole event from the F1 tag (`_all_pole_events`), then attach each to the
    schedule race it resolves just after (race_date <= event end_date <= race_date + 12d, minimal
    gap). This is robust to Polymarket's two slug conventions AND their circuit-name quirks (Imola
    marketed as "italy", São Paulo as "brazilian", Mexico City as "mexican") because the join is
    purely temporal. `quali_ts` is the Q-session start = the leak-free cutoff (snapshot the market
    just BEFORE qualifying). NOTE: sprint-shootout pole markets exist too but are a DIFFERENT target
    (the sprint grid), not what `predict_quali` forecasts — excluded. [] if the schedule is
    unreachable."""
    out: list[dict] = []
    try:
        import datetime as dt

        import fastf1

        from app.config import get_settings

        fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)
        now = dt.datetime.now(dt.timezone.utc)
        events = _all_pole_events(timeout=timeout)
        sched = fastf1.get_event_schedule(year, include_testing=False)

        # The year's completed races as (race_date, round, circuit, quali_ts).
        races: list[tuple] = []
        for _, row in sched.iterrows():
            rnd = int(row["RoundNumber"])
            if rnd == 0:
                continue
            quali, race = row.get("Session4DateUtc"), row.get("Session5DateUtc")
            if quali is None or race is None:
                continue
            if quali.tzinfo is None:
                quali = quali.tz_localize("UTC")
            if race.tzinfo is None:
                race = race.tz_localize("UTC")
            if race > now:
                continue  # not yet run
            races.append((race.date(), rnd,
                          str(row["EventName"]).replace(" Grand Prix", "").strip(),
                          int(quali.timestamp())))

        # Match each pole EVENT to the race it resolves just after (nearest preceding race
        # within 12 days) -- event-centric so a market-less race can't steal a later race's event.
        by_round: dict[int, dict] = {}
        for slug, end in events:
            cand = [((end - rdt).days, (rdt, rn, ci, q)) for (rdt, rn, ci, q) in races
                    if 0 <= (end - rdt).days <= 12]
            if not cand:
                continue
            _, (_, rnd, circuit, quali_ts) = min(cand, key=lambda x: x[0])
            # Prefer the dated driver-pole-position slug if two events map to one race.
            prev = by_round.get(rnd)
            if prev is None or ("driver-pole-position" in slug and "driver-pole-position" not in prev["slug"]):
                by_round[rnd] = {"slug": slug, "circuit": circuit, "round": rnd, "quali_ts": quali_ts}
        out = sorted(by_round.values(), key=lambda d: d["round"])
    except Exception:
        pass
    return out


def next_race_event_slugs(timeout: float = 10.0) -> list[str]:
    """Derive the upcoming race's winner+pole event slugs from the FastF1 schedule.

    Deterministic (driven by data we control), so it survives Polymarket slug drift far
    better than scanning their API. Returns [] if the schedule isn't reachable.
    """
    try:
        import datetime as dt

        import fastf1

        from app.config import get_settings

        fastf1.Cache.enable_cache(get_settings().fastf1_cache_dir)
        now = dt.datetime.now(dt.timezone.utc)
        for year in (now.year, now.year + 1):
            sched = fastf1.get_event_schedule(year, include_testing=False)
            for _, row in sched.iterrows():
                race = row.get("Session5DateUtc")
                quali = row.get("Session4DateUtc")
                if race is None or race.tzinfo is None:
                    race = race.tz_localize("UTC") if race is not None else None
                if race is None or race < now - dt.timedelta(hours=6):
                    continue
                name = str(row["EventName"]).replace(" Grand Prix", "").strip().lower()
                name = name.replace(" ", "-").replace("ã", "a").replace("í", "i")
                name = _SLUG_ALIASES.get(name, name)
                rd = race.strftime("%Y-%m-%d")
                qd = (quali if quali is not None else race).strftime("%Y-%m-%d")
                return [
                    f"f1-{name}-grand-prix-winner-{rd}",
                    f"f1-{name}-grand-prix-driver-pole-position-{qd}",
                ]
    except Exception:
        pass
    return []


def championship_market(year: int, kind: str = "drivers", timeout: float = 20.0) -> dict[str, float]:
    """Best-effort de-vigged Polymarket title-outright odds for a season.

    Returns {driver_code (or team name): clean_prob} for the drivers'- (or constructors'-)
    championship market, or {} on any failure (off-season, slug drift, network down). Used only
    to surface a "what does the market think" column next to our season sim -- NOT a betting
    signal (the title market is efficient; we expect no edge). Maps Polymarket's per-driver YES
    markets (groupItemTitle = full name) to our 3-letter codes via SURNAME_TO_CODE; de-vigs the
    field so the probabilities sum to 1.
    """
    import json as _json
    import unicodedata

    base = "drivers" if kind == "drivers" else "constructors"
    # Polymarket slugs drift; the current (verified) forms are first, older forms after.
    cands = [
        f"{year}-f1-{base}-champion",
        f"f1-{base}-champion",                 # the open market often carries no year
        f"f1-{base}-champion-{year}",
        f"f1-{base}-championship-winner",
        f"f1-{year}-{base}-championship-winner",
    ]
    # Polymarket's constructor labels vs our roster team names.
    team_alias = {"Haas": "Haas F1 Team"}

    def _strip(s: str) -> str:
        return "".join(ch for ch in unicodedata.normalize("NFKD", s)
                       if not unicodedata.combining(ch))
    try:
        with httpx.Client(timeout=timeout) as c:
            ev = None
            for slug in cands:
                try:
                    r = c.get(f"{GAMMA}/events", params={"slug": slug}).json()
                    r = r[0] if isinstance(r, list) and r else r
                    if r and not r.get("closed") and _event_year(r) == year:
                        ev = r
                        break
                except Exception:
                    continue
            if not ev:
                return {}
            raw: dict[str, float] = {}
            for m in ev.get("markets", []):
                label = (m.get("groupItemTitle") or "").strip()
                op = m.get("outcomePrices")
                op = _json.loads(op) if isinstance(op, str) else op
                if not label or not op:
                    continue
                if label == "Other":
                    continue
                price = float(op[0])
                if kind == "drivers":
                    code = SURNAME_TO_CODE.get(_strip(label.split()[-1]))
                    if code:
                        raw[code] = price
                else:
                    raw[team_alias.get(label, label)] = price
            return devig(raw)
    except Exception:
        return {}


def live_market_tokens(timeout: float = 12.0) -> list[dict]:
    """The upcoming race's events with their YES-token ids + labels + Gamma fallback price:
    [{slug, question, tokens:[{token_id, label, gamma}]}]. Used to seed the live WS feed."""
    import json as _json

    slugs = next_race_event_slugs()
    out: list[dict] = []
    if not slugs:
        return out
    try:
        with httpx.Client(timeout=timeout) as c:
            for slug in slugs:
                ev = c.get(f"{GAMMA}/events", params={"slug": slug}).json()
                ev = ev[0] if isinstance(ev, list) and ev else ev
                if not ev or ev.get("closed"):
                    continue
                tokens = []
                for m in ev.get("markets", []):
                    label = (m.get("groupItemTitle") or "").strip()
                    op = m.get("outcomePrices")
                    op = _json.loads(op) if isinstance(op, str) else op
                    toks = m.get("clobTokenIds")
                    toks = _json.loads(toks) if isinstance(toks, str) else toks
                    if label and op and toks:
                        tokens.append({"token_id": toks[0], "label": label, "gamma": float(op[0])})
                if len(tokens) >= 2:
                    out.append({"slug": ev.get("slug", ""), "question": ev.get("title", ""),
                                "tokens": tokens})
    except Exception:
        pass
    return out


def market_from_books(question: str, slug: str, tokens: list[dict],
                      books: dict) -> dict | None:
    """Build a LiveMarket dict from a {token_id: book} cache (the WS path), reusing the same
    robust price selection + de-vig as the REST path."""
    prices: dict[str, float] = {}
    meta: dict[str, tuple] = {}
    for t in tokens:
        book = books.get(t["token_id"])
        price, bid, ask, spread, source = (
            _book_price(book, t["gamma"]) if book else (t["gamma"], None, None, None, "gamma")
        )
        prices[t["label"]] = price
        meta[t["label"]] = (bid, ask, spread, source)
    if len(prices) < 2:
        return None
    clean = devig(prices)
    return {
        "question": question,
        "slug": slug,
        "overround": round(overround(prices), 4),
        "outcomes": [
            {"name": n, "price": round(p, 4), "implied": round(clean.get(n, 0.0), 4),
             "bid": round(meta[n][0], 4) if meta[n][0] is not None else None,
             "ask": round(meta[n][1], 4) if meta[n][1] is not None else None,
             "spread": meta[n][2], "source": meta[n][3]}
            for n, p in sorted(prices.items(), key=lambda x: -x[1])
        ],
    }


def fetch_f1_markets_live(timeout: float = 12.0) -> list[dict]:
    """Best-effort live F1 markets for the upcoming race (winner + pole), de-vigged."""
    slugs = next_race_event_slugs()
    if not slugs:
        return []
    out: list[dict] = []
    try:
        with httpx.Client(timeout=timeout) as c:
            for slug in slugs:
                ev = c.get(f"{GAMMA}/events", params={"slug": slug}).json()
                ev = ev[0] if isinstance(ev, list) and ev else ev
                if ev and not ev.get("closed"):
                    m = _event_to_market(ev, client=c)
                    if m:
                        out.append(m)
    except Exception:
        return []
    return out


def load_markets_snapshot() -> dict | None:
    if MARKETS_SNAPSHOT.exists():
        try:
            return json.loads(MARKETS_SNAPSHOT.read_text())
        except Exception:
            return None
    return None


def refresh_markets_snapshot(markets: list[dict] | None = None) -> dict:
    """Cache the latest good live markets as the committed fallback (with a timestamp)."""
    import datetime as dt

    mk = markets if markets is not None else fetch_f1_markets_live()
    snap = {"as_of": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "markets": mk}
    if mk:  # only overwrite the snapshot with a *good* fetch, never with an empty one
        MARKETS_SNAPSHOT.write_text(json.dumps(snap, indent=2))
    return snap


def fetch_f1_markets(limit: int = 40, timeout: float = 8.0) -> list[dict]:
    """Best-effort: find active Polymarket F1 markets via the Gamma API.

    Returns a list of {question, slug, outcomes:[{name, price}], overround,
    clean:{name->prob}}; empty list if none are live or the network is unavailable.
    """
    try:
        with httpx.Client(timeout=timeout) as c:
            r = c.get(
                f"{GAMMA}/markets",
                params={"active": "true", "closed": "false", "limit": 200},
            )
            r.raise_for_status()
            markets = r.json()
    except Exception:
        return []

    out: list[dict] = []
    for m in markets:
        text = f"{m.get('question', '')} {m.get('slug', '')}".lower()
        if not any(k in text for k in ("formula 1", "f1 ", "grand prix", "verstappen")):
            continue
        outcomes = _market_outcomes(m)
        if len(outcomes) < 2:
            continue
        prices = {o["name"]: o["price"] for o in outcomes}
        clean = devig(prices)
        out.append(
            {
                "question": m.get("question", ""),
                "slug": m.get("slug", ""),
                "overround": round(overround(prices), 4),
                "outcomes": [
                    {
                        "name": o["name"],
                        "price": round(o["price"], 4),
                        "implied": round(clean.get(o["name"], 0.0), 4),
                    }
                    for o in sorted(outcomes, key=lambda x: -x["price"])
                ],
            }
        )
        if len(out) >= limit:
            break
    return out


def _market_outcomes(m: dict) -> list[dict]:
    """Extract {name, price} per outcome from a Gamma market record."""
    import json as _json

    try:
        names = m.get("outcomes")
        prices = m.get("outcomePrices")
        if isinstance(names, str):
            names = _json.loads(names)
        if isinstance(prices, str):
            prices = _json.loads(prices)
        if not names or not prices:
            return []
        return [
            {"name": str(n), "price": float(p)}
            for n, p in zip(names, prices)
            if p is not None
        ]
    except Exception:
        return []
