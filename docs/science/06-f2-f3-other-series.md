# 06 — Expanding to F2 / F3 (and other series)

Feasibility of extending the engine beyond F1. **The engine is series-agnostic** —
physics, tyre, strategy and Monte-Carlo layers don't care about the series. The only
gap is the **data path**. Verdict: F2/F3 are feasible on free, no-key sources for
**pace + lap-in-stint degradation**, but with hard limits (no tyre compound, no
telemetry, no library — all DIY).

## Bottom line

| | F2 | F3 | F1 (baseline) |
|---|---|---|---|
| Historical per-lap | ✅ FIA timing **PDFs** since 2017 (scrape) | ✅ same `_f3_` pattern | ✅ FastF1 |
| Live timing | ✅ unauth SignalR (fragile) | ✅ identical | ✅ OpenF1 paid / risky SignalR |
| **Tyre compound / stint** | ⚠️ **stints inferable, compound NOT available** | ⚠️ same | ✅ FastF1 has compound |
| Telemetry | ❌ none | ❌ none | ✅ FastF1 |
| Library | ❌ none (DIY) | ❌ none | ✅ FastF1 |
| Cost / auth | Free, no key | Free, no key | Free hist / €10 live |

**The decisive limitation:** no public source exposes **per-stint tyre compound** for
F2/F3. We can calibrate *pace* and *degradation-by-lap-in-stint*, but **not
compound-specific tyre curves** like we do for F1. Set expectations accordingly.

## Live timing — corrected, verified endpoints

⚠️ The originally-suggested endpoint (`wss://www.fiaformula2.com/livetiming/signalr/
connect ... clientProtocol=1.5`) was **wrong**. The verified mechanics (captured live):

- **Host:** `ltss.fiaformula2.com` (F3: `ltss.fiaformula3.com`) — not `www.*`.
- **Stack:** classic ASP.NET **SignalR 2.x**, `clientProtocol=2.1`, hub **`streaming`**, unauthenticated.
- **Handshake:** `negotiate` (returns `ConnectionToken`) → `connect` (WSS upgrade) → `start`.

```
GET https://ltss.fiaformula2.com/streaming/negotiate?clientProtocol=2.1&connectionData=[{"name":"streaming"}]
    -> { ConnectionToken, TryWebSockets:true, ProtocolVersion:"2.0", KeepAliveTimeout:20 }
WSS https://ltss.fiaformula2.com/streaming/connect?transport=webSockets&clientProtocol=2.1&connectionToken=<TOKEN>&connectionData=[{"name":"streaming"}]
GET https://ltss.fiaformula2.com/streaming/start?transport=webSockets&clientProtocol=2.1&connectionToken=<TOKEN>&connectionData=[{"name":"streaming"}]
# Hub "streaming"; invoke joinFeeds(series, ['data','weather','status','time','commentary','racedetails'])
# Callbacks: datafeed, statsfeed, sessionfeed, trackfeed, weatherfeed, timefeed, comment, racedetailsfeed
```

- **`datafeed` fields:** number, position, driver/TLA, status (in-pit/retired/stopped),
  sector times, last lap, lap count, **pit-stop count**, gap to leader, interval ahead.
- **No tyre/compound field** anywhere (searched `tyre|tire|compound|stint` → zero).
- **No Python library** consumes this yet — fork FastF1's `SignalRClient` or use
  `signalrcore`/`websocket-client`. This is the **risky direct-SignalR** tier (no
  OpenF1-equivalent paid safety net for F2/F3); needs reconnect/retry supervision and
  breaks when FIA changes the handshake.

## Historical — FIA timing PDFs

- Results HTML (`fiaformula2.com/Results?raceid=N`) is **classification-only** (no laps).
- **Per-lap data lives in FIA timing PDFs** (`fia.com/sites/default/files/<YYYY_MM_CCC>_f2_r<n>_timing_<doctype>_v01.pdf`):
  **Lap Analysis / History Chart** = per-lap, per-driver lap times + gaps;
  **Pit Stop Summary** = stop lap + duration (→ infer stints). Parse with
  tabula/camelot/pdfplumber — brittle (layouts shift), 2017→present, F3 uses `_f3_`.
- ESPN APIs return **HTTP 400** for F2/F3; Jolpica/Ergast are F1-only; **no maintained
  community dataset** — build your own scraper.
- **ToS:** FIA PDFs carry a no-redistribution notice. Scraping for internal model
  training is lower-risk than republishing raw timing. The live feed is undocumented/
  unsanctioned (same posture as direct-F1-SignalR).

## Other series (brief)
- **WEC:** Al Kamel (`fiawec.alkamelsystems.com`) — per-lap **CSV** (easier than PDFs),
  live too, **but** explicit data-ownership/no-redistribution stance (legally touchy).
- **MotoGP:** unofficial motogp.com API for history; live is paid (TimingPass) or
  commercial feeds. Harder; not paywall-free for live.

## If we pursue F2/F3 (engineering shape)
1. **Historical:** a `fia_pdf` ETL module — download timing PDFs, parse Lap Analysis +
   Pit Stop Summary → the same normalized lap schema we already use. Calibrate base lap,
   pace offsets, and **stint-relative** degradation (no compound split).
2. **Live:** a forked SignalR client targeting `ltss.fiaformula{2,3}.com`, behind a flag,
   best-effort with auto-reconnect.
3. **Model:** reuse the existing engine unchanged; just omit compound-specific tyre
   overrides for F2/F3 (fall back to a single generic degradation curve per session).

_Source: live-captured F2/F3 SignalR handshake + `timing.js`; FIA timing-PDF archive;
FastF1 docs (F1-only scope). Full endpoint list in the research transcript._
