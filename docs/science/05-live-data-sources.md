# 05 — Live Data Sources (ingestion decision)

Evaluation of candidate feeds for **(A)** historical model training and **(B)** true
low-latency live in-race prediction that must run **unattended on a Hetzner VPS**.
Supersedes the live-ingestion notes in [03-data-and-2026.md](03-data-and-2026.md).

## Decision

| Goal | Use | Notes |
|---|---|---|
| **(A) Historical training** (tyre-deg, driver style, strategy) | **FastF1** (primary) + **TracingInsights** (cross-check) + **Jolpica** (results/standings) | We already do this in `app/etl/`. |
| **(B) Live in-race** (unattended VPS) | **OpenF1 paid (€9.90/mo) via MQTT/WSS** (primary) · **direct F1 SignalR** (fallback, eyes-open) | Only sanctioned headless-clean live path. |

## Source-by-source

### F1 official SignalR live timing — fast but risky
- **What:** the real feed behind F1's live timing. Topics include full timing
  (sectors/gaps/intervals), `CarData.z` (zlib telemetry: speed/RPM/throttle/brake/
  DRS/gear), `Position.z` (X/Y/Z), track status, race control, weather, lap count.
- **Access:** negotiate `https://livetiming.formula1.com/signalrcore/negotiate` →
  `wss://livetiming.formula1.com/signalrcore`. A `no_auth` path exists and delivers
  effectively equivalent data (no token needed).
- **Latency:** ~100–500 ms transport (ahead of the 30–60 s TV delay). But some
  derived state (`DriverList`) lags — live positions need `DriverList`+`TimingData`
  fusion done yourself.
- ⚠️ **FastF1's client is record-to-file, not real-time** ("not possible to do
  real-time processing"; disconnects ~2 h). Live use needs a **custom `signalrcore`
  client** with incremental parsing.
- ⚠️ **Unsanctioned. F1 actively IP-blocks scrapers** (hosted community instances
  taken down). Handshake breaks across seasons (`/signalr` → `/signalrcore`). Carry
  the legal + maintenance risk knowingly; don't make it the *only* path.

### MultiViewer local GraphQL — ruled out for production
- `http://localhost:10101/api/graphql`, TV-synced, sub-ms local, Python via `mvf1`.
- ❌ **Requires the GUI desktop app + a logged-in F1 TV Pro session actively
  playing.** Not runnable unattended on a headless VPS, and server-side automation of
  a personal F1 TV sub breaches its ToS. **Local dev / ground-truth only.**

### TracingInsights GitHub archives — convenience layer
- Repos confirmed live & current: `TracingInsights/2026`, `TracingInsights-Archive/2025`,
  …, seasons **2018–2026**. **Apache-2.0** (commercial-OK).
- **JSON, ~30 min post-session.** `tel.json` is **3.7 Hz resampled** (vs FastF1 ~10 Hz)
  with **computed** (synthetic) acceleration; also `laptimes/weather/rcm/corners`.
- Downstream of FastF1 → little extra *raw* signal. Use as a pre-cleaned baseline,
  corner-geometry helper, and cross-validation — **not** the primary training source.
- Read: `requests.get(raw_github_url).json()` → `pl.DataFrame(...)`.

### OpenF1 — free historical, paid live
- **Free:** historical only (2023+), no auth, 3 req/s — no live data at all.
- **Paid €9.90/mo:** live REST + **MQTT `mqtt.openf1.org:8883` / WSS
  `wss://mqtt.openf1.org:8084/mqtt`**, 6 req/s. OAuth2 `POST /token` (**3600 s**
  expiry; token = MQTT password). Data refreshes **~3 s** (intervals ~4 s) — so
  **subscribe (push), don't poll**. Topics mirror REST paths.

```python
# Primary live path: OpenF1 MQTT/WSS (sanctioned, headless-clean)
import paho.mqtt.client as mqtt, requests
tok = requests.post("https://api.openf1.org/token",
                    data={"username": U, "password": P}).json()["access_token"]
c = mqtt.Client(transport="websockets"); c.tls_set()
c.username_pw_set("any", tok)                       # refresh before 3600 s
c.on_message = lambda cl, u, m: handle(m.topic, m.payload)
c.connect("mqtt.openf1.org", 8084)
for t in ("v1/intervals", "v1/laps", "v1/position", "v1/race_control"):
    c.subscribe(t)
c.loop_forever()
```

## Implications for the build (Phase 6 — Live)
1. **Live = OpenF1 paid MQTT/WSS** with a `paho-mqtt` worker + token refresh; ~3 s
   latency is fine (strategy/prediction tolerances are seconds, not ms).
2. Keep a **direct-SignalR client behind a flag** for <1 s / richer raw telemetry,
   accepting ToS + handshake-maintenance risk. Not the default.
3. **Do not** build production on MultiViewer or on scraping SignalR as the only path.
4. Add **TracingInsights** as an optional ETL source for corner geometry + a quick
   cross-check of FastF1-derived tyre-deg.

_Sources: FastF1 livetiming docs & client.py; FastF1 #630 (latency), #753 (signalrcore
migration); TracingInsights/2026 & Archive/2025 repos; openf1.org/auth; mvf1 docs._
