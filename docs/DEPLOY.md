> ⚠️ SUPERSEDED — see DEPLOY.md at the repo root. These instructions predate the Cloudflare Tunnel / shared-edge migration and must NOT be followed.

# Deploying F1Predict

The whole stack runs from `docker compose`: **Caddy** (TLS + entrypoint) → **web** (nginx
serving the built SPA + proxying `/api`) → **api** (FastAPI/uvicorn) → **db** (Postgres, future
use — the engine itself runs on the committed Parquet artifacts). Target host: a small Hetzner
VPS, but any Docker host works.

## Prerequisites
- A Docker host with `docker` + `docker compose` (Hetzner CX22 is plenty).
- (For HTTPS) a domain's A/AAAA record pointing at the host.

## First deploy
```bash
git clone https://github.com/btre53/F1Predict.git && cd F1Predict
cp .env.example .env            # edit: set F1P_CORS_ORIGINS to your https origin
export DOMAIN=f1predict.example.com   # omit for local plain-HTTP on :80
docker compose up -d --build
```
- With `DOMAIN` set to a real host, Caddy obtains a Let's Encrypt cert automatically and serves
  HTTPS on 443. Unset → plain HTTP on `:80` (local/testing).
- The app is self-contained: the API ships with the committed `backend/data/*.parquet`
  artifacts (lap data, calibration, hazard, overtaking proxies, tyre degradation, market
  snapshot), so it predicts immediately with **no network or DB** needed.

## Verify
```bash
curl -s localhost/api/health           # API up (through Caddy+nginx)
curl -s localhost/api/health/data      # data freshness heartbeat (latest race, snapshot age)
# then open the site in a browser
```

## Keeping it current (optional)
Two independent paths, both off by default:
- **In-app scheduler:** set `F1P_REFRESH_ENABLED=true` in `.env`. After each race weekend
  (Mon 06:00 UTC) the API pulls new races and recalibrates (laps, hazard, overtaking proxies,
  tyre degradation, Polymarket snapshot).
- **GitHub Action (`.github/workflows/ingest.yml`):** the robust, self-healing path — refresh →
  test → commit only if green. Pull + `docker compose up -d --build` to redeploy the new data.
- Live Polymarket prices come from the CLOB order book live, degrading to the committed
  `markets_snapshot.json` when the feed is down/off-season.
- **Live WebSocket feed (optional):** set `F1P_LIVE_WS_ENABLED=true` for a background task that
  streams the upcoming race's order books and pushes them to the browser via SSE
  (`/markets/stream`) — sub-poll freshness with no per-request REST. Off by default (the REST
  book fetch is plenty for a market that moves in <8% of minutes); enable it for a live race.

## Updating the app
```bash
git pull && docker compose up -d --build
```

## Notes / gotchas
- The frontend talks to a **relative `/api`** (no build-time API URL) — nginx proxies it to the
  api container, so the same image works at any domain.
- CI (`.github/workflows/ci.yml`) runs pytest + the frontend build on every push.
- Postgres is wired in compose for future use; the current engine does not require it. Drop the
  `db` service if you don't want it.
- Resource use is modest (FastF1 cache is NOT shipped; it rebuilds lazily only if refresh runs).
