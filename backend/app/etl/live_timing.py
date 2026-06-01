"""Record the live F1 SignalR timing stream to file (free, via FastF1).

This is the FREE path to live race state -- it captures the same official timing feed
the f1.com live timing page uses, so we can replay a session and reconstruct live state
(positions, gaps, tyres, track status) for the companion / scenario runner WITHOUT paying
for OpenF1's live tier. Caveats: it only streams while a session is LIVE, so start it
~15 min before lights-out (or before quali); the SignalR connection can drop, so babysit
/ restart; and the raw file must be loaded back via fastf1.livetiming.LiveTimingApi.

Run, per session (start before the session goes green):
    uv run python -m app.etl.live_timing --out data/monaco_2026_race.txt
    uv run python -m app.etl.live_timing --out data/monaco_2026_quali.txt
Stop with Ctrl-C. Replay later:
    import fastf1
    session = fastf1.get_session(2026, 'Monaco', 'R')
    session.load(livedata=fastf1.livetiming.data.LiveTimingData('data/monaco_2026_race.txt'))
"""

from __future__ import annotations

import argparse
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def record(out: Path, *, timeout: int = 60, debug: bool = False) -> None:
    """Block and stream the live timing feed to `out` until the session ends or Ctrl-C."""
    from fastf1.livetiming.client import SignalRClient

    out.parent.mkdir(parents=True, exist_ok=True)
    # filemode 'a' so a dropped-and-restarted connection appends rather than truncates.
    client = SignalRClient(filename=str(out), filemode="a", timeout=timeout, debug=debug)
    print(f"recording live timing -> {out}\n"
          f"  (only streams while a session is LIVE; Ctrl-C to stop)")
    client.start()  # blocking


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(DATA_DIR / "live_timing.txt"))
    ap.add_argument("--timeout", type=int, default=60,
                    help="seconds of silence before the client gives up")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    try:
        record(Path(a.out), timeout=a.timeout, debug=a.debug)
    except KeyboardInterrupt:
        print("\nstopped; timing file is on disk.")


if __name__ == "__main__":
    main()
