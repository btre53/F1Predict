# Deployment

**This app is deployed to the shared edge VPS behind a Cloudflare Tunnel + a single shared
Caddy reverse proxy. Do NOT follow any other deploy instructions in this repo** (e.g.
`deploy/`, `*DEPLOY*.md`, `HETZNER_*`, certbot/nginx/`docker compose` with published ports).
Those are OUTDATED — they predate the tunnel migration and must not be used.

## Canonical deployment
Deployment is owned by the infrastructure repo **github.com/btre53/infra** (see its `DEPLOY.md`
and `ARCHITECTURE.md`) plus the global conventions in `~/.claude/CLAUDE.md`.

The model: public ports 80/443 on the box are CLOSED; the origin is hidden behind a Cloudflare
Tunnel. This app runs as a Docker container on its own `edge-<app>` network with **no published
ports** and **no own reverse proxy / certbot**; the single shared Caddy routes
`<app>.built-by-bobby.com` to it. Build from this repo's Dockerfile; the edge compose (network,
volume, env) is infra-owned and lives in the VPS deploy dir, not in this repo.

**This repo is code only.** Do not add port-publishing, nginx, or certbot deploy steps here.
