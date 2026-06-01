# Monaco GP 2026 — dogfooding runbook

Capture live data over the Monaco weekend so we can (a) replay it and (b) put our
calibrated model/companion alongside the real market. **LOCKBOX WARNING: 2026 is the
held-out out-of-sample set (`docs/science/09`). Capture for dogfooding/replay only —
do NOT train or tune models on 2026 data, or we burn the only clean OOS test.**

## Session times (UTC)
| Session | When (UTC) |
|---|---|
| FP1 | Fri 2026-06-05 11:30 |
| FP2 | Fri 2026-06-05 15:00 |
| FP3 | Sat 2026-06-06 10:30 |
| **Qualifying** | **Sat 2026-06-06 14:00** |
| **Race** | **Sun 2026-06-07 13:00** |

(Convert to local time wherever you are. The two that matter most: quali and race.)

## 1. Polymarket price capture (run it across the whole weekend)
Appends a timestamped row per outcome (winner / pole / safety-car / constructor) to a CSV
every 60s. Append-only, so it's safe to stop/restart; the CSV is complete at every row.

```
cd backend
uv run python -m app.etl.live_capture --gp monaco --date 2026-06-07 --interval 60
```
- Smoke test any time (single snapshot, no file): add `--once`.
- Output: `backend/data/live_monaco_2026-06-07.csv`.
- Start it now if you like — it captures the pre-race drift too. Leave it running through
  the race; stop with Ctrl-C.

## 2. FastF1 live-timing recorder (start ~15 min BEFORE quali and race)
Records the free SignalR timing stream so we can replay the session and reconstruct live
state (positions/gaps/tyres/track status). **It only streams while the session is LIVE** —
start it before the session goes green, one file per session.

```
# Saturday ~13:45 UTC, before Qualifying:
uv run python -m app.etl.live_timing --out data/monaco_2026_quali.txt

# Sunday ~12:45 UTC, before the Race:
uv run python -m app.etl.live_timing --out data/monaco_2026_race.txt
```
- Stop with Ctrl-C after the session. If the connection drops, just re-run the same
  command (filemode is append).
- Replay later:
  ```python
  import fastf1
  from fastf1.livetiming.data import LiveTimingData
  s = fastf1.get_session(2026, 'Monaco', 'R')
  s.load(livedata=LiveTimingData('data/monaco_2026_race.txt'))
  ```

## 3. Dogfood the app (live, free)
- Markets tab: the de-vig panel shows the live Polymarket winner/pole line. (Note:
  `fetch_f1_markets` discovery needs the 2026 slug fix — see TODO; the de-vig math is fine.)
- Pre-race: run the Predictor for Monaco 2026 and eyeball our win/podium/points vs the
  live de-vigged market. We expect to *match* calibration, not beat it (that's the honest
  story — `docs/science/13`).
- After the weekend: replay the timing file to reconstruct live state and (later) drive the
  companion / scenario overlay.

## Reality check on betting (so we don't fool ourselves)
- No outright / in-play / T-12h edge was found (briefs 07, 13; T-12h test this session).
- Market-making these props is negative-to-zero EV for retail (`docs/science/14`).
- So Monaco dogfooding is about **product + data**, not profit: validate the companion,
  collect a clean replay, and show calibrated, transparent strategy reasoning.
