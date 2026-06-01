"""Live Polymarket price capture for race-weekend dogfooding.

Polls the live Polymarket F1 markets every interval and appends a timestamped row per
outcome to a CSV (append-only = crash-safe across a multi-hour session). Captures the
real in-play winner-market curve plus pole / safety-car / constructor props, so we have
our own record to replay and to put alongside the live companion overlay.

NB the 2026 slug format is `f1-<race>-grand-prix-<market>-<date>` (the older
`<race>-grand-prix-winner` form is 2024/25 only -- this is why `fetch_f1_markets`'s
keyword scan missed the 2026 markets). LOCKBOX: 2026 is the held-out OOS set -- capture
for dogfooding/replay, do NOT train models on it.

Run:  uv run python -m app.etl.live_capture --gp monaco --date 2026-06-07 --interval 60
Stop with Ctrl-C; the CSV is complete at every row.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

import httpx

from app.etl.polymarket import CLOB, GAMMA

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

# Market types we try per GP. winner/pole/constructor are multi-outcome; safety-car is
# a Yes/No binary. Some may not exist for a given race -- missing ones are skipped.
MARKET_SUFFIXES = {
    "winner": "winner",
    "pole": "driver-pole-position",
    "safety_car": "safety-car",
    "constructor_first": "constructor-scores-1st",
    "fastest_lap": "fastest-lap",
}


def slugs_for(gp: str, date: str) -> dict[str, str]:
    """Build the 2026-format event slugs for a GP, e.g. gp='monaco', date='2026-06-07'.

    pole resolves the day before the race; we try both the race date and date-1."""
    gp = gp.lower().replace(" ", "-")
    out: dict[str, str] = {}
    for name, suf in MARKET_SUFFIXES.items():
        d = date
        if name == "pole":  # pole market is dated the quali day (race date - 1)
            y, m, dd = (int(x) for x in date.split("-"))
            import datetime as _dt
            d = (_dt.date(y, m, dd) - _dt.timedelta(days=1)).isoformat()
        out[name] = f"f1-{gp}-grand-prix-{suf}-{d}"
    return out


def _event(c: httpx.Client, slug: str) -> dict | None:
    try:
        r = c.get(f"{GAMMA}/events", params={"slug": slug}).json()
        ev = r[0] if isinstance(r, list) and r else r
        return ev or None
    except Exception:
        return None


def _midpoint(c: httpx.Client, token: str) -> float | None:
    """Fresh CLOB midpoint (best bid/ask mid) -- truer than Gamma's cached outcomePrice."""
    try:
        b = c.get(f"{CLOB}/book", params={"token_id": token}).json()
        bids = [float(x["price"]) for x in b.get("bids", [])]
        asks = [float(x["price"]) for x in b.get("asks", [])]
        if bids and asks:
            return (max(bids) + min(asks)) / 2.0
    except Exception:
        pass
    return None


def snapshot(c: httpx.Client, slugs: dict[str, str], now: int) -> list[dict]:
    """One row per (market, outcome): timestamp, last price, and fresh CLOB midpoint."""
    rows: list[dict] = []
    for market, slug in slugs.items():
        ev = _event(c, slug)
        if not ev or ev.get("closed"):
            continue
        for m in ev.get("markets", []):
            label = (m.get("groupItemTitle") or m.get("question") or "").strip()
            op = m.get("outcomePrices"); op = json.loads(op) if isinstance(op, str) else op
            outs = m.get("outcomes"); outs = json.loads(outs) if isinstance(outs, str) else outs
            toks = m.get("clobTokenIds"); toks = json.loads(toks) if isinstance(toks, str) else toks
            if not op or not toks:
                continue
            # For binaries (Yes/No) use the Yes leg; for multi, the single YES token.
            mid = _midpoint(c, toks[0])
            rows.append({
                "ts": now, "market": market, "slug": slug,
                "outcome": label or (outs[0] if outs else ""),
                "last_price": float(op[0]), "midpoint": mid if mid is not None else "",
            })
    return rows


def capture_loop(slugs: dict[str, str], out: Path, interval: int = 60,
                 until_ts: int | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    new_file = not out.exists()
    fields = ["ts", "market", "slug", "outcome", "last_price", "midpoint"]
    print(f"capturing {list(slugs.values())}\n -> {out} every {interval}s (Ctrl-C to stop)")
    with httpx.Client(timeout=20) as c, open(out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            w.writeheader()
        while True:
            now = int(time.time())
            rows = snapshot(c, slugs, now)
            for r in rows:
                w.writerow(r)
            f.flush()
            print(f"  {now}: wrote {len(rows)} rows")
            if until_ts and now >= until_ts:
                print("reached until-ts; done.")
                return
            time.sleep(interval)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gp", default="monaco")
    ap.add_argument("--date", default="2026-06-07", help="race date YYYY-MM-DD")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--out", default=None)
    ap.add_argument("--once", action="store_true", help="single snapshot then exit (smoke test)")
    a = ap.parse_args()
    slugs = slugs_for(a.gp, a.date)
    out = Path(a.out) if a.out else DATA_DIR / f"live_{a.gp}_{a.date}.csv"
    if a.once:
        with httpx.Client(timeout=20) as c:
            for r in snapshot(c, slugs, int(time.time())):
                print(f"  {r['market']:18s} {r['outcome']:18s} last={r['last_price']:.3f} mid={r['midpoint']}")
        return
    try:
        capture_loop(slugs, out, interval=a.interval)
    except KeyboardInterrupt:
        print("\nstopped; CSV is complete.")


if __name__ == "__main__":
    main()
