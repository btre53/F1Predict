# 03 — Data Sources, 2026 Regulations & Markets

The practical data layer. **Golden rule:** all three data APIs are rate-limited and
slow — run them as an **offline batch ETL → cache (Parquet) → serving DB (Postgres)
→ the web app reads only the DB.** Never call FastF1/OpenF1/Jolpica from a request
handler.

---

## 1. FastF1 — historical ETL backbone

Open-source Python lib that scrapes the official F1 live-timing API + Jolpica and
caches aggressively. Returns **pandas** DataFrames (convert to Polars at the ETL
edge).

**Coverage:** telemetry & timing **2018 → present**; results/schedules back to 1950
via the bundled Ergast/Jolpica interface.

```python
import fastf1
fastf1.Cache.enable_cache('/var/cache/fastf1')      # call ONCE before loading

session = fastf1.get_session(2024, 'Monza', 'R')    # year, gp, FP1/Q/R/Sprint
session.load(laps=True, telemetry=True, weather=True, messages=True)

laps = session.laps          # per-lap DataFrame
weather = session.weather_data
results = session.results
```

**Key `session.laps` columns:** `LapTime, LapNumber, Stint, PitInTime, PitOutTime,
Sector1/2/3Time, SpeedI1/I2/FL/ST, Compound, TyreLife, FreshTyre, Team, Position,
TrackStatus, IsAccurate, Deleted`.
**`weather_data`:** `AirTemp, TrackTemp, Humidity, Pressure, Rainfall,
WindDirection, WindSpeed`.

**Rate limits (self-imposed on upstream):** ~4 req/s, **500 req/hour** (timing) /
**200 req/hour** (Ergast side). Cached requests don't count. Log rate-limit
warnings loudly (historically only at DEBUG level).

**Polars conversion:** `pl.from_pandas(session.laps)` — pandas `Timedelta`/`NaT`
time columns map to `Duration`/null; validate dtypes, or pre-convert Timedeltas to
float seconds.

**Derived state you must compute yourself (not in the data):**
- *Tyre age / compound / stint* → direct (`TyreLife`, `Compound`, `Stint`).
- *Fuel-corrected pace* → not provided; compute via the fuel model in
  [01-lap-time-model.md](01-lap-time-model.md).
- *Gaps/intervals* → derive from cumulative lap times, or pull from OpenF1
  `/intervals`.

Sources: [docs.fastf1.dev](https://docs.fastf1.dev/), [Fast-F1 GitHub](https://github.com/theOehrly/Fast-F1).

---

## 2. OpenF1 — REST (free) + streaming (paid)

**Base:** `https://api.openf1.org/v1` (JSON; `?csv=true` for CSV). Coverage from
**2023**.

| Endpoint | Returns |
|---|---|
| `/car_data` | speed, throttle, brake, drs, n_gear, rpm (~3.7 Hz) |
| `/intervals` | gap_to_leader, interval (race only, ~4 s) |
| `/laps` | lap_duration, sector durations, speeds, is_pit_out_lap |
| `/pit` | pit_duration, lane_duration, lap_number |
| `/stints` | compound, lap_start, lap_end, tyre_age_at_start |
| `/weather` | air/track temp, humidity, rainfall, wind |
| `/race_control` | category, flag, message, scope, sector |
| `/position`, `/location`, `/drivers`, `/sessions`, `/meetings` | ... |

Join on `session_key` + `driver_number`. Use `session_key=latest`.

⚠ **Correction:** **there is no free live websocket.** Real-time push is
**paywalled** (MQTT `mqtt.openf1.org:8883` / WSS `wss://…:8084/mqtt`, OAuth2 token,
~€9.90/mo personal tier). The free tier is **REST + historical only**. For "Live"
mode we either (a) pay the personal tier, (b) **poll free REST during sessions**
(higher latency; intervals only refresh ~4 s anyway), or (c) run **post-session
backfill** via FastF1 as source of truth.

Sources: [openf1.org/docs](https://openf1.org/docs/), [auth](https://openf1.org/auth.html).

---

## 3. Jolpica-F1 — Ergast replacement (results & schedules)

**Ergast is deprecated.** Drop-in successor: **`https://api.jolpi.ca/ergast/f1/`**
(backwards-compatible JSON). FastF1 already uses it under the hood.

- Endpoints: `/seasons`, `/circuits`, `/drivers`, `/constructors`, `/races`
  (schedule), `/results`, `/qualifying`, `/sprint`, `/laps`, `/pitstops`,
  `/driverstandings`, `/constructorstandings`, `/status`.
- Pagination: `limit` (max 100) + `offset`.
- **Rate limits:** 4 req/s burst, **500 req/hour** sustained (429 on exceed; limits
  will *decrease* as auth rolls out — cache hard).
- Use for canonical calendars, classifications, championship standings, history to
  1950.

Sources: [jolpica-f1](https://github.com/jolpica/jolpica-f1/blob/main/docs/README.md).

---

## 4. The 2026 regulations (confirmed vs speculative)

**Confirmed (FIA-ratified):**

| Area | 2026 |
|---|---|
| Engine | 1.6 L V6 turbo, **MGU-H deleted** |
| ICE output | ~400 kW (down from ~550) |
| MGU-K output | **350 kW** (up from 120) — ~3× |
| Power split | **~50/50 ICE/electric** |
| Fuel | 100% sustainable; max load drops to ~70 kg |
| Min weight | **768 kg** (−~30 kg) |
| Wheelbase | ≤ **3400 mm** (−200 mm) |
| Width | **1900 mm** (−100 mm) |
| Tyres | front −25 mm, rear −30 mm (18") |
| Overtaking | **DRS removed → "Manual Override" boost** |
| Aero | **Active aero: Z-mode (downforce) / X-mode (low-drag)** |

⚠ **Energy figures — resolving the doc's 4 MJ vs 9 MJ confusion (two different
quantities):**
- **~8.5–9 MJ** = per-lap **harvest/recovery throughput** (roughly doubled).
- **~4 MJ** = instantaneous **battery store cap** (max energy stored at any moment).

They are **not** the same number. Do not use 9 MJ as the battery size or 4 MJ as
the per-lap deploy budget. For load-bearing numbers cite the **FIA 2026 Power Unit
Technical Regulations PDF**, not press articles.

**Override mechanics:** leading car's deployment tapers from 290 km/h to zero by
~355 km/h; a follower within ~1 s gets full 350 kW up to ~337 km/h, +~0.5 MJ.

**Speculative:** the strategic *consequences* (will overtaking get easier? will
energy-saving dominate?) — label as projections in the UI.

Sources: [F1.com power units](https://www.formula1.com/en/latest/article/explained-2026-power-unit-regulations-fia.68izKQ2tn1voQPWvgLVMXN),
[F1.com aero Z/X-mode](https://www.formula1.com/en/latest/article/explained-2026-aerodynamic-regulations-fia-twitter-mode-z-mode-.26c1CtOzCmN3GfLMywrgb2),
[The Race 2026 car rules](https://www.the-race.com/formula-1/f1-2026-new-car-rules-explained/).

---

## 5. Polymarket — read-only market data (paper trading)

Two public, no-auth read APIs.

**Gamma (discovery):** `https://gamma-api.polymarket.com`
```
GET /markets?tag_id=<F1>&active=true&closed=false      # find F1 markets
GET /tags                                              # discover the F1 tag_id
```
Each market exposes `slug`, `outcomes`, `conditionId`, and **`clobTokenIds`** (the
per-outcome token IDs).

**CLOB (prices/order book):** `https://clob.polymarket.com` — all read methods need
no auth. `GET /book?token_id=`, `/price`, `/midpoint`, `/spread`,
`/last-trade-price` (+ batch `/books`, `/midpoints`). Python: `py-clob-client`,
instantiate without keys for read-only.

**Implied probability & vig removal:** a YES token price ≈ implied probability. Use
the **midpoint** as the fair estimate. For multi-outcome markets the mids sum to
**> 1** (overround) — normalize `p_i = mid_i / Σ mid_j` to strip the vig. Model
fills against `/book` depth for realistic paper-trading slippage.

⚠ **Legal/ToS:** Polymarket restricts **real-money trading** in several
jurisdictions (notably the US). **Read-only data and paper trading are fine** — we
stay strictly read/paper, place **no real orders**, and keep the live-execution
path key-gated and off by default.

Sources: [Polymarket CLOB](https://docs.polymarket.com/developers/CLOB/introduction),
[Gamma fetch-markets](https://docs.polymarket.com/developers/gamma-markets-api/fetch-markets-guide),
[py-clob-client](https://github.com/Polymarket/py-clob-client).

---

## 6. Architecture flags from the research

1. **No free OpenF1 websocket** — plan Live around polling/paid/backfill.
2. **2026 energy: 8.5–9 MJ harvest ≠ 4 MJ store** — don't conflate.
3. **"Sub-10 ms Postgres writes" is not a guarantee** on a small VPS with fsync on
   — **batch-insert** telemetry (COPY / multi-row transactions), buffer in memory;
   don't architect around per-row durability.
4. **Never call the data APIs from request handlers** — ETL → DB → web only.
5. **DRS is gone in 2026** — model Override + active aero, not DRS zones.
6. **pandas → Polars at the ETL boundary** — validate Timedelta/NaT columns.
