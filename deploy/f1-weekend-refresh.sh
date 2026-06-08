#!/usr/bin/env bash
# Autonomous weekend F1 data refresh, installed on the edge VPS at
#   /usr/local/bin/f1-weekend-refresh
# and run by root cron:
#   23 8 * * 1 /usr/local/bin/f1-weekend-refresh   # Mondays 08:23 UTC, after Sunday races
#
# It runs app.etl.refresh INSIDE the api container -- which is FastF1-free now (laps from
# OpenF1, results/calendar from Jolpica, both reachable from the VPS unlike F1's livetiming
# CDN; see docs/CURRENT_STATE.md) -- so new races are written to the persistent f1data volume,
# then the api is restarted to serve them. Idempotent: no-ops when there's no new race and
# catches up any race it missed. Fully server-side: no GitHub, no residential machine, no proxy.
#
# This file is the source of truth; to update the VPS copy:
#   scp deploy/f1-weekend-refresh.sh root@<vps>:/usr/local/bin/f1-weekend-refresh
set -uo pipefail
LOG=/var/log/f1_refresh.log
{
  echo "=== $(date -u +%FT%TZ) refresh start ==="
  docker exec f1-api-1 uv run python -m app.etl.refresh
  rc=$?
  echo "refresh exit=$rc"
  if [ "$rc" -eq 0 ]; then
    docker compose -f /opt/deploy/f1/docker-compose.edge.yml restart api && echo "api restarted"
  fi
  echo "=== $(date -u +%FT%TZ) done ==="
} >> "$LOG" 2>&1
