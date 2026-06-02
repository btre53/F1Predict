"""Optional live CLOB WebSocket feed (live pricing v2, task #9).

Maintains the upcoming race's Polymarket order books in memory by streaming the CLOB market
channel, so `/markets/live` and the SSE stream serve always-fresh, top-of-book prices without
a per-request REST round-trip. **Gated by F1P_LIVE_WS_ENABLED (default OFF)** so the deployed
app stays low-maintenance — when off, `/markets/live` just does its on-demand book fetch.

Robustness: `book` snapshots are authoritative; `price_change` deltas are applied best-effort;
the connection is recycled every RECONNECT_S so books refresh even if a delta is missed; any
error reconnects with backoff. If the cache goes stale the API falls back to the REST path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from .polymarket import live_market_tokens, market_from_books

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
RECONNECT_S = 150.0   # recycle the socket to refresh book snapshots (bounds staleness)
STALE_S = 30.0        # cache older than this -> treat as not-fresh (REST fallback)
log = logging.getLogger("f1p.clobws")


class LiveBookManager:
    def __init__(self) -> None:
        self.books: dict[str, dict] = {}     # token_id -> {bids, asks, last_trade_price}
        self.meta: list[dict] = []           # [{slug, question, tokens:[...]}]
        self.updated = 0.0
        self._task: asyncio.Task | None = None
        self._stop = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop = False
            self._task = asyncio.create_task(self._run())
            log.info("clob ws manager started")

    async def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()

    def fresh(self) -> bool:
        return bool(self.books) and (time.time() - self.updated) < STALE_S

    def markets(self) -> list[dict] | None:
        if not self.meta:
            return None
        out = [
            m for e in self.meta
            if (m := market_from_books(e["question"], e["slug"], e["tokens"], self.books))
        ]
        return out or None

    async def _run(self) -> None:
        import websockets

        backoff = 1.0
        while not self._stop:
            try:
                self.meta = await asyncio.to_thread(live_market_tokens)
                tokens = [t["token_id"] for e in self.meta for t in e["tokens"]]
                if not tokens:
                    await asyncio.sleep(60)
                    continue
                async with websockets.connect(WS_URL, open_timeout=15, ping_interval=10) as ws:
                    await ws.send(json.dumps({"assets_ids": tokens, "type": "market"}))
                    backoff = 1.0
                    deadline = time.time() + RECONNECT_S
                    while not self._stop and time.time() < deadline:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=RECONNECT_S)
                        except asyncio.TimeoutError:
                            break
                        self._handle(msg)
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                log.warning("clob ws reconnect: %s", e)
                await asyncio.sleep(min(backoff, 30.0))
                backoff *= 2

    def _handle(self, msg: str) -> None:
        try:
            data = json.loads(msg)
        except Exception:
            return
        for e in data if isinstance(data, list) else [data]:
            aid = e.get("asset_id")
            if not aid:
                continue
            et = e.get("event_type")
            if et == "book":
                self.books[aid] = {
                    "bids": e.get("bids", []), "asks": e.get("asks", []),
                    "last_trade_price": self.books.get(aid, {}).get("last_trade_price"),
                }
                self.updated = time.time()
            elif et == "price_change":
                b = self.books.setdefault(aid, {"bids": [], "asks": [], "last_trade_price": None})
                for ch in e.get("changes", []) or e.get("price_changes", []):
                    self._apply(b, ch)
                self.updated = time.time()
            elif et in ("last_trade_price", "tick_size_change"):
                b = self.books.setdefault(aid, {"bids": [], "asks": [], "last_trade_price": None})
                if e.get("price") is not None:
                    b["last_trade_price"] = e.get("price")
                self.updated = time.time()

    @staticmethod
    def _apply(book: dict, ch: dict) -> None:
        side = "bids" if str(ch.get("side", "")).lower() in ("buy", "bid") else "asks"
        price, size = ch.get("price"), ch.get("size")
        if price is None:
            return
        arr = [x for x in book.get(side, []) if x.get("price") != price]
        try:
            if size is not None and float(size) > 0:
                arr.append({"price": price, "size": size})
        except (TypeError, ValueError):
            pass
        book[side] = arr


_manager: LiveBookManager | None = None


def get_manager() -> LiveBookManager:
    global _manager
    if _manager is None:
        _manager = LiveBookManager()
    return _manager


def ws_markets() -> list[dict] | None:
    """Fresh WS-sourced markets, or None when the feed is off/stale (caller falls back)."""
    m = _manager
    return m.markets() if (m and m.fresh()) else None
