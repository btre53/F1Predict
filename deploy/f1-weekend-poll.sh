#!/usr/bin/env bash
# Race-weekend poller, installed on the edge VPS at
#   /usr/local/bin/f1-weekend-poll
# and run by root cron every 20 min across a race weekend (Fri-Mon):
#   */20 * * * 5,6,0,1 /usr/local/bin/f1-weekend-poll   # Fri/Sat/Sun/Mon, every 20 min
#
# It runs app.etl.weekend_poll INSIDE the api container. The poller reacts to OpenF1's data
# (session officially classified + lap feed settled), NOT to the clock, so it ingests:
#   - the real post-quali grid the moment quali is classified (Sat), cached to the f1data volume
#     for the live predictor/companion -- no api restart needed (read fresh per request);
#   - the full race (laps + recalibration + overlays) the moment the race is complete (Sun eve),
#     the same job f1-weekend-refresh runs -- and THEN restarts the api to serve it.
# Idempotent and cheap when there's nothing new; no-ops entirely outside a race weekend.
# The Monday f1-weekend-refresh cron remains the backstop. See docs/CURRENT_STATE.md.
#
# This file is the source of truth; to update the VPS copy:
#   scp deploy/f1-weekend-poll.sh root@<vps>:/usr/local/bin/f1-weekend-poll
set -uo pipefail
LOG=/var/log/f1_poll.log
{
  echo "=== $(date -u +%FT%TZ) poll start ==="
  docker exec f1-api-1 uv run python -m app.etl.weekend_poll
  rc=$?
  echo "poll exit=$rc"
  # exit 10 = a new race was ingested -> restart the api to serve it (quali-only runs exit 0)
  if [ "$rc" -eq 10 ]; then
    docker compose -f /opt/deploy/f1/docker-compose.edge.yml restart api && echo "api restarted (new race)"
  fi
  echo "=== $(date -u +%FT%TZ) done ==="
} >> "$LOG" 2>&1
