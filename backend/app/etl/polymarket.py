"""Polymarket read-only client + vig removal (docs/science/03 section 5).

We never place orders. This reads public prices, strips the vig (overround) to get
clean implied probabilities, and computes model-vs-market edge + fractional-Kelly
sizing for *display only*. The live-execution path stays off by design.

Network calls are best-effort: there may be no live F1 markets at a given time, so
every function degrades gracefully and the API surfaces a clear status.
"""

from __future__ import annotations

import httpx

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
JOLPICA = "https://api.jolpi.ca/ergast/f1"

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
