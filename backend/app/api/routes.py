"""API routes. Strategy Lab endpoints (the first user-facing surface)."""

from __future__ import annotations

from fastapi import APIRouter

from fastapi import HTTPException

from app import __version__
from app.engine import calibration_store as store
from app.engine import replay as replay_engine
from app.engine import track_geometry
from app.engine import track_positions
from app.engine.params import CircuitParams
from app.models.predict_kalman import predict_race_kalman
from app.etl.backtest import load_backtest
from app.etl.forward_backtest import load_forward_backtest
from app.etl.market_backtest import load_market_backtest
from app.etl.polymarket import (
    fetch_f1_markets_live,
    load_markets_snapshot,
)
from app.engine.strategy import (
    Stint,
    Strategy,
    cover_or_extend,
    evaluate_strategy,
    evaluate_undercut,
    optimize_strategy,
    rain_crossover,
    safety_car_decision,
)

from .schemas import (
    ChampionshipRequest,
    CircuitIn,
    CircuitInfo,
    CoverExtendRequest,
    CoverExtendResultOut,
    DriverOutcomeOut,
    EvaluateRequest,
    OptimizeRequest,
    PredictRequest,
    RaceSimOut,
    RainCrossoverRequest,
    RainCrossoverResultOut,
    SafetyCarRequest,
    SafetyCarResultOut,
    StopForkOption,
    StopForkRequest,
    StopForkResultOut,
    StrategyResultOut,
    UndercutRequest,
    UndercutResultOut,
)

router = APIRouter()


def _circuit_from(c: CircuitIn) -> CircuitParams:
    return CircuitParams(
        name=c.name, base_lap_ms=c.base_lap_ms, total_laps=c.total_laps
    )


@router.get("/circuits", response_model=list[CircuitInfo])
def list_circuits() -> list[CircuitInfo]:
    """Calibrated circuits available from the ETL (empty until ingest is run)."""
    out: list[CircuitInfo] = []
    for name in store.available_circuits():
        cp = store.circuit_params_for(name)
        overrides = store.tyre_overrides_for(name)
        out.append(
            CircuitInfo(
                name=name,
                base_lap_ms=cp.base_lap_ms,
                total_laps=cp.total_laps,
                era=cp.era.value,
                calibrated=bool(overrides),
                compounds_calibrated=sorted(c.value for c in overrides),
            )
        )
    return out


@router.get("/circuits/overtaking")
def overtaking_index() -> list[dict]:
    """Per-circuit overtaking-difficulty index (mechanistic, brand-agnostic).

    One track-physics number per circuit -- how locked is track position -- from
    grid->finish rank lock, green on-track passing rate, and lap-1 churn (no team
    or driver identity). High = hard to pass, qualifying-locked (Monaco); low =
    pace overcomes grid (Spa). It scales the Predictor's per-circuit spread and is
    the brand-agnostic replacement for the rejected team x circuit affinity. The
    honest-research showcase: see docs/science/16. Higher value -> tighter field.
    """
    from app.models.overtaking import OvertakingIndex

    idx = OvertakingIndex()
    out = [
        {
            "circuit": c,
            "index": round(idx.index(c), 3),
            "spread_temperature": round(idx.spread(c, 0.5, gamma=0.2), 3),
        }
        for c in store.available_circuits()
    ]
    out.sort(key=lambda r: r["index"], reverse=True)
    return out


@router.get("/circuits/safety-car")
def safety_car_prior() -> list[dict]:
    """Per-circuit structural safety-car prior (mechanistic, brand-agnostic).

    P(any SC) from measurable track structure (street-ness via low passing rate +
    high lap-1 churn) + weather, not circuit identity. HONEST CAVEAT: forward-chained
    this does *not* beat the calendar base rate for race-level prediction (SC is a
    near-Poisson shock) -- the value is the cross-sectional ordering (street/walled
    circuits fire more cautions; per-circuit SC-rate ~ passing-rate r=-0.39) for sim
    realism + the Explainer, not a calibrated edge. See docs/science/18.
    """
    from app.models.sc_index import sc_probability

    out = [{"circuit": c, "sc_prior": round(sc_probability(c), 3)}
           for c in store.available_circuits()]
    out.sort(key=lambda r: r["sc_prior"], reverse=True)
    return out


@router.get("/circuits/weather")
def circuit_weather() -> list[dict]:
    """Per-race race-window precipitation (free, leak-free; Open-Meteo ERA5 archive).

    Weather is an exogenous race-day shock. HONEST FINDING (docs/science/21): it does NOT
    raise DNF and does NOT help win/podium (the wet favourite is already calibrated), but it
    DOES scramble who-scores in the midfield -- so the Predictor widens ONLY the points market
    in the wet. This surfaces the raw artifact (wet flag + race-window precip) for the Explainer.
    """
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "data" / "weather.parquet"
    if not p.exists():
        return []
    import polars as pl

    rows = (
        pl.read_parquet(p)
        .select(["year", "circuit", "wet", "precip_mm_window", "precip_mm_max", "temp_c"])
        .sort(["year", "circuit"])
        .to_dicts()
    )
    return rows


@router.get("/cars/dna")
def car_dna_summary() -> dict:
    """Car-DNA corner-band decomposition (task #22): per-circuit corner-band demand +
    per-car shape-normalized band factors (where each car is *relatively* fast).

    HONEST CAVEAT: interpretable (McLaren/VER strong in slow corners, Alpine/Sauber on
    straights -- correct for 2024) but NOT predictive over scalar pace (forward-chained
    corr with qualifying deviation ~0). An Explainer artifact, not an edge. See science/19.
    Returns {} if the telemetry cache (data/car_dna.parquet) is absent.
    """
    try:
        from app.models.car_dna import dna_summary

        return dna_summary()
    except Exception:
        return {}


def _to_out(result) -> StrategyResultOut:
    return StrategyResultOut(
        total_time_s=round(result.total_time_s, 3),
        delta_to_best_s=round(result.delta_to_best_s, 3),
        avg_lap_s=round(result.avg_lap_s, 3),
        pit_laps=result.pit_laps,
        n_stops=result.n_stops,
        valid=result.valid,
        notes=result.notes,
        compounds=[s.compound.value for s in result.strategy.stints],
        stint_lengths=[s.length for s in result.strategy.stints],
        lap_times_s=[round(t, 3) for t in result.lap_times_s],
    )


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "f1predict", "version": __version__}


@router.post("/strategy/evaluate", response_model=StrategyResultOut)
def strategy_evaluate(req: EvaluateRequest) -> StrategyResultOut:
    if req.circuit_name:
        circuit = store.circuit_params_for(req.circuit_name)
        tyre_overrides = store.tyre_overrides_for(req.circuit_name) or None
    else:
        circuit = _circuit_from(req.circuit)
        tyre_overrides = None
    strategy = Strategy(
        [Stint(s.compound, s.length, s.start_tyre_age) for s in req.strategy.stints]
    )
    result = evaluate_strategy(
        strategy,
        circuit,
        pace_offset_s=req.pace_offset_s,
        tyre_overrides=tyre_overrides,
        sc_laps=set(req.sc_laps),
    )
    return _to_out(result)


@router.post("/strategy/optimize", response_model=list[StrategyResultOut])
def strategy_optimize(req: OptimizeRequest) -> list[StrategyResultOut]:
    if req.circuit_name:
        circuit = store.circuit_params_for(req.circuit_name)
        tyre_overrides = store.tyre_overrides_for(req.circuit_name)
    else:
        circuit = _circuit_from(req.circuit)
        tyre_overrides = None
    results = optimize_strategy(
        circuit,
        compounds=req.compounds,
        max_stops=req.max_stops,
        pace_offset_s=req.pace_offset_s,
        tyre_overrides=tyre_overrides,
        top_k=req.top_k,
    )
    out = [_to_out(r) for r in results]
    # The bulk optimizer omits per-lap times for speed; evaluate the top strategy so the UI's
    # lap-time profile chart has data (instead of a blank captioned panel).
    if results:
        full = evaluate_strategy(results[0].strategy, circuit,
                                 pace_offset_s=req.pace_offset_s, tyre_overrides=tyre_overrides)
        out[0].lap_times_s = [round(t, 3) for t in full.lap_times_s]
    return out


@router.get("/replay/races")
def replay_races() -> list[dict]:
    """List historical races available for replay."""
    return replay_engine.available_races()


@router.get("/replay/race")
def replay_race(circuit: str, year: int) -> dict:
    data = replay_engine.load_replay(circuit, year)
    if data.total_laps == 0:
        raise HTTPException(404, f"No replay data for {circuit} {year}")
    return {
        "circuit": data.circuit,
        "year": data.year,
        "total_laps": data.total_laps,
        "drivers": data.drivers,
        "laps": data.laps,
    }


@router.get("/replay/track")
def replay_track(circuit: str, year: int) -> dict | None:
    """Survey-accurate SVG outline for a circuit (FastF1 fastest-lap telemetry).

    Optional overlay: returns null (200) when uncached so the UI quietly uses its stylised
    fallback — a 404 here just spams the browser console for an expected, handled absence."""
    return track_geometry.outline_for(circuit, year) or None


@router.get("/replay/positions")
def replay_positions(circuit: str, year: int) -> dict | None:
    """Per-frame normalized car positions for a race (multi-car replay).

    Optional overlay: returns null (200) when uncached (single-dot fallback in the UI),
    not a 404 — avoids console-error noise for an expected, handled absence."""
    return track_positions.positions_for(circuit, year) or None


@router.get("/replay/inplay")
def replay_inplay(circuit: str, year: int) -> dict:
    """Per-lap model vs de-vigged Polymarket win-prob overlay for the replay leaderboard.

    Empty {} for races with no ingested in-play curve (the Explorer hides the columns
    then). Calibrated model live win-prob, but it does NOT lead the market (brief 13) --
    a transparency companion, not a trading signal."""
    return replay_engine.inplay_overlay(circuit, year)


@router.get("/tyres/teams")
def tyres_teams() -> dict:
    """Per-team tyre-management multipliers (for the explainer overlays)."""
    return store.load_team_tyres()


@router.get("/tyres/degradation")
def tyres_degradation() -> dict:
    """Per-compound tyre-age degradation re-fit on 2022+ stint residuals (Heilmeier closed
    forms, AIC-selected). Finding: the LOG form (best on 2014-19) is NOT best for the
    ground-effect era -- SOFT/MEDIUM are linear, HARD quadratic. See docs/science/20.
    Returns {} until app.etl.tyre_degradation has been run."""
    import json
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "data" / "tyre_degradation.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


@router.get("/circuits/qss")
def circuits_qss() -> dict:
    """Quasi-steady-state corner/straight decomposition + speed-profile reconstruction per
    circuit (telemetry-derived line). HONEST CAVEAT: tracks the speed-trace SHAPE (corr
    ~0.85) but overestimates pace ~20-30% on free data -- a decomposition/Explainer tool,
    not a lap-time predictor (curvature from ~10 Hz X/Y under-resolves corners). science/20.
    Returns {} until app.engine.qss.build() has been run."""
    from app.engine import qss

    return qss._profiles()


@router.get("/markets/backtest")
def markets_backtest() -> dict:
    """Precomputed calibration backtest: model probabilities vs real outcomes."""
    d = load_backtest()
    if d is None:
        raise HTTPException(404, "Backtest not computed yet — run app.etl.backtest")
    return d


@router.get("/markets/forward-backtest")
def markets_forward_backtest() -> dict:
    """Strict forward-chaining (leak-free) backtest, for honest comparison."""
    d = load_forward_backtest()
    if d is None:
        raise HTTPException(404, "Run app.etl.forward_backtest")
    return d


@router.get("/markets/vs-market")
def markets_vs_market() -> dict:
    """Real model-vs-Polymarket backtest (2024 races with market coverage)."""
    d = load_market_backtest()
    if d is None:
        raise HTTPException(404, "Run app.etl.market_backtest (needs network)")
    return d


@router.get("/companion/props")
def companion_props(n_sims: int = 8000) -> dict:
    """Race-companion view: the upcoming race's Polymarket props with OUR model beside the market.

    For the next race we (a) find its open prop markets from the F1-tag catalog, (b) compute our
    model's number for the props we can honestly price — race winner + podium (from the Kalman
    predictor), pole (from the qualifying model), safety car (the structural SC prior) — and
    (c) de-vig the market and join them per outcome (model · market · edge). Props we don't model
    (fastest lap, red flag, H2H, constructor points) are listed as market-only, transparently.
    Honest framing: this is a companion, NOT a betting signal — the market is efficient (briefs
    07/27/29). Network best-effort; degrades to `available=False` off-season / when unreachable.
    """
    from app.etl.calendar import next_race
    from app.etl.polymarket import (
        _surname_to_code, discover_f1_markets, event_devig,
    )

    nr = next_race()
    if not nr:
        return {"available": False}
    circuit, event_name = nr["circuit"], nr.get("event_name", "")
    modelled_circuit = circuit in set(store.available_circuits())

    # The next race's prop markets: open catalog entries whose slug carries this race's name
    # (handle Polymarket's circuit-name quirks). Avoids grabbing the next-next race's markets.
    stem = event_name.replace(" Grand Prix", "").strip().lower().replace(" ", "-")
    cands = {stem, *{"sao-paulo": ["brazilian"], "emilia-romagna": ["italy"],
                     "mexico-city": ["mexican"], "united-states": ["united-states"]}.get(stem, [])}
    catalog = discover_f1_markets(only_open=True)
    race_markets = [m for m in catalog if any(c and c in m["slug"] for c in cands)]

    # Model side (compute once; reuse for winner + podium).
    win_p: dict[str, float] = {}
    pod_p: dict[str, float] = {}
    pole_p: dict[str, float] = {}
    sc_yes = None
    if modelled_circuit:
        try:
            sim = predict_race_kalman(circuit, n_sims=n_sims)
            win_p = {o.driver: o.win_pct for o in sim.outcomes}
            pod_p = {o.driver: o.podium_pct for o in sim.outcomes}
            sc_yes = round(float(sim.sc_probability), 3)
        except Exception:  # noqa: BLE001
            pass
        try:
            from app.models.predict_quali import predict_grid

            pole_p = {g["driver"]: g["pole_pct"] for g in predict_grid(circuit)["grid"]}
        except Exception:  # noqa: BLE001
            pass

    # type -> (human title, model dict, exclusive de-vig?)
    DRIVER_PROPS = {
        "race_winner": ("Race winner", win_p, True),
        "driver_pole": ("Pole position", pole_p, True),
        "driver_podium": ("Podium finish", pod_p, False),
    }
    TITLES = {"safety_car": "Safety car", "driver_fastest_lap": "Fastest lap",
              "red_flag": "Red flag", "head_to_head": "Head-to-head",
              "constructor_points": "Most constructor points", "constructor_pole": "Constructor pole",
              "constructor_fastest_lap": "Constructor fastest lap", "sprint_pole": "Sprint pole",
              "sprint_winner": "Sprint winner", "driver_podium": "Podium finish"}

    props: list[dict] = []
    seen_types: set[str] = set()
    for m in race_markets:
        t = m["type"]
        if t in seen_types:
            continue
        seen_types.add(t)
        if t in DRIVER_PROPS and DRIVER_PROPS[t][1]:
            title, model, exclusive = DRIVER_PROPS[t]
            market = event_devig(m["slug"], exclusive=exclusive)
            rows = []
            for label, mkt in market.items():
                code = _surname_to_code(label)
                if code and code in model:
                    rows.append({"name": code, "model_pct": round(model[code], 4),
                                 "market_pct": round(mkt, 4),
                                 "edge": round(model[code] - mkt, 4)})
            rows.sort(key=lambda r: -r["model_pct"])
            props.append({"type": t, "title": title, "modelled": True,
                          "slug": m["slug"], "outcomes": rows[:8]})
        elif t == "safety_car" and sc_yes is not None:
            market = event_devig(m["slug"], exclusive=False)
            myes = market.get("Yes")
            props.append({"type": t, "title": "Safety car", "modelled": True, "slug": m["slug"],
                          "outcomes": [{"name": "Yes", "model_pct": sc_yes,
                                        "market_pct": round(myes, 4) if myes is not None else None,
                                        "edge": round(sc_yes - myes, 4) if myes is not None else None}]})
        else:
            props.append({"type": t, "title": TITLES.get(t, t.replace("_", " ").title()),
                          "modelled": False, "slug": m["slug"], "outcomes": []})

    # Modelled props first, then market-only.
    props.sort(key=lambda p: (not p["modelled"], p["type"]))
    return {
        "available": bool(props),
        "race": {"circuit": circuit, "event_name": event_name, "round": nr.get("round"),
                 "race_utc": nr.get("race_utc"), "quali_utc": nr.get("quali_utc"),
                 "days_away": nr.get("days_away"), "is_upcoming": nr.get("is_upcoming"),
                 "modelled": modelled_circuit},
        "n_props": len(props),
        "props": props,
    }


@router.get("/models/replay")
def models_replay() -> dict:
    """Forward-chained predictions for the Model Replay sandbox (methodology page).

    For each recent race, what each model (grid+quali baseline, production Kalman, the position-
    resolution sim, and the sim + held-up asymmetry) would have predicted using ONLY strictly-prior
    races — leak-free, exactly as the validators score them — alongside the actual finishing order.
    Lets the methodology page show, interactively, what every model gets right and wrong on real
    races. Precomputed (app.models.replay_predict); 404 until built.
    """
    from app.models.replay_predict import load_replay

    d = load_replay()
    if d is None:
        raise HTTPException(404, "Run app.models.replay_predict to build data/model_replay.json")
    return d


@router.get("/markets/f1-catalog")
def markets_f1_catalog(only_open: bool = True, market_type: str | None = None) -> dict:
    """Catalog of Polymarket F1 markets, classified by type — the companion-mode prop index.

    Enumerates Polymarket's Formula 1 tag (the ground truth) and labels every market by canonical
    type (race_winner, driver_pole, driver_podium, head_to_head, driver_fastest_lap, safety_car,
    red_flag, constructor_points, championship, sprint_*, …). This is the foundation for surfacing
    live props and for locating the market a Benter blend should price against — robust to
    Polymarket's slug drift, since classification is centralised. Network best-effort: returns an
    empty catalog if Polymarket is unreachable.
    """
    from collections import Counter

    from app.etl.polymarket import discover_f1_markets

    markets = discover_f1_markets(only_open=only_open, market_type=market_type)
    return {
        "available": bool(markets),
        "only_open": only_open,
        "n": len(markets),
        "by_type": dict(Counter(m["type"] for m in markets)),
        "markets": markets,
    }


@router.get("/markets/quali-backtest")
def markets_quali_backtest() -> dict:
    """Pole model vs Polymarket pole price (task #28, see docs/science/27).

    Honest probe of the most deterministic session, over all 23 races Polymarket has priced pole
    on (2025 from Miami + 2026 to date; markets found by enumerating Polymarket's F1 tag, since they
    use two slug formats). Verdict: no edge — the market is better calibrated (pole Brier ~0.039 vs
    ~0.045) and out-top-picks us 30% vs 26%, the same finding as the winner + in-play tests.
    """
    from app.models.validate_quali_market import load_quali_market_backtest

    d = load_quali_market_backtest()
    if d is None:
        raise HTTPException(404, "Run app.models.validate_quali_market (needs network)")
    return d


@router.get("/markets/live")
def markets_live() -> dict:
    """Live Polymarket F1 markets (vig-removed, read-only), with a snapshot fallback.

    Sources, in order: the live CLOB WebSocket cache (if enabled + fresh — instant, no REST
    round-trip), an on-demand REST book fetch, then the committed snapshot (off-season / feed
    down) — labelled with its source so the UI can say "as of <date>". Always robust.
    """
    from app.etl.clob_ws import ws_markets

    wsm = ws_markets()
    if wsm:
        return {"available": True, "source": "ws", "as_of": None, "markets": wsm}
    live = fetch_f1_markets_live()
    if live:
        return {"available": True, "source": "live", "as_of": None, "markets": live}
    snap = load_markets_snapshot()
    if snap and snap.get("markets"):
        return {
            "available": True,
            "source": "snapshot",
            "as_of": snap.get("as_of"),
            "markets": snap["markets"],
        }
    return {"available": False, "source": "none", "as_of": None, "markets": []}


@router.get("/markets/stream")
async def markets_stream():
    """Server-sent events: push the live markets ~every 2s from the CLOB WebSocket cache.

    True push when the WS feed is enabled (sub-poll freshness); otherwise it emits a
    REST book fetch refreshed at most every 8s (no hammering), then the snapshot. The
    frontend uses this when present and falls back to polling /markets/live on error.
    """
    import asyncio
    import json as _json
    import time as _time

    from fastapi.responses import StreamingResponse

    from app.etl.clob_ws import ws_markets

    async def gen():
        last_rest, rest_cache = 0.0, None
        while True:
            wsm = ws_markets()
            if wsm:
                payload = {"available": True, "source": "ws", "as_of": None, "markets": wsm}
            else:
                if _time.time() - last_rest > 8.0:
                    rest_cache = await asyncio.to_thread(fetch_f1_markets_live)
                    last_rest = _time.time()
                if rest_cache:
                    payload = {"available": True, "source": "live", "as_of": None,
                               "markets": rest_cache}
                else:
                    snap = load_markets_snapshot()
                    payload = {"available": bool(snap and snap.get("markets")),
                               "source": "snapshot",
                               "as_of": snap.get("as_of") if snap else None,
                               "markets": snap.get("markets", []) if snap else []}
            yield f"data: {_json.dumps(payload)}\n\n"
            await asyncio.sleep(2.0)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/calendar/next")
def calendar_next() -> dict:
    """The upcoming race (from the FastF1 schedule) so the UI can auto-select it.

    Returns the next race's round/event/circuit/session times + whether that circuit is
    calibrated (predictable now). `calibrated` lets the frontend default the Predictor to
    the next race when we have data for it, or fall back gracefully otherwise.
    """
    from app.etl.calendar import next_race

    nr = next_race()
    if not nr:
        return {"available": False}
    nr["calibrated"] = nr["circuit"] in set(store.available_circuits())
    return {"available": True, **nr}


@router.get("/health/data")
def health_data() -> dict:
    """Data freshness heartbeat — surfaces silent staleness / failed cron updates.

    Reports the most recent race in the committed lap data and the market snapshot age,
    so a broken refresh shows up here (and in the UI footer) instead of going unnoticed.
    """
    import datetime as dt
    from pathlib import Path

    import polars as pl

    info: dict = {"now": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    laps = Path(__file__).resolve().parents[2] / "data" / "laps.parquet"
    try:
        df = pl.read_parquet(laps, columns=["year", "circuit", "session_name"]).filter(
            pl.col("session_name") == "R"
        )
        years = sorted(df["year"].unique().to_list())
        info["lap_data"] = {
            "n_races": df.select(["year", "circuit"]).unique().height,
            "seasons": years,
            "latest_season": years[-1] if years else None,
        }
    except Exception as e:  # noqa: BLE001
        info["lap_data"] = {"error": str(e)}
    snap = load_markets_snapshot()
    info["markets_snapshot"] = {
        "present": snap is not None,
        "as_of": snap.get("as_of") if snap else None,
        "n_markets": len(snap.get("markets", [])) if snap else 0,
    }
    return info


def _race_sim_out(res) -> RaceSimOut:
    """Serialize an engine RaceSimResult into the wire shape (shared by /predict/race
    and the committed default snapshot generator)."""
    return RaceSimOut(
        circuit=res.circuit,
        total_laps=res.total_laps,
        n_sims=res.n_sims,
        sc_probability=round(res.sc_probability, 4),
        post_quali=res.post_quali,
        rain_prob=round(res.rain_prob, 3),
        wet=res.wet,
        outcomes=[
            DriverOutcomeOut(
                driver=o.driver,
                number=o.number,
                team=o.team,
                colour=o.colour,
                grid_pos=o.grid_pos,
                win_pct=round(o.win_pct, 4),
                podium_pct=round(o.podium_pct, 4),
                points_pct=round(o.points_pct, 4),
                mean_finish=round(o.mean_finish, 2),
                p50_finish=o.p50_finish,
                p10_finish=o.p10_finish,
                p90_finish=o.p90_finish,
                dnf_pct=round(o.dnf_pct, 4),
                finish_distribution=[round(x, 4) for x in o.finish_distribution],
            )
            for o in res.outcomes
        ],
    )


@router.post("/predict/race", response_model=RaceSimOut)
def predict(req: PredictRequest) -> RaceSimOut:
    res = predict_race_kalman(
        req.circuit_name, n_sims=req.n_sims, grid_order=req.grid_order,
        use_quali=req.use_quali,
    )
    return _race_sim_out(res)


@router.get("/predict/default", response_model=RaceSimOut)
def predict_default() -> RaceSimOut:
    """Instant first-paint prediction.

    The full 10k-sim forecast can be a multi-second cold start (the Kalman forward-chains
    the season + fits the hazard/SC models on first use), which left the Predictor stuck on a
    spinner for a recruiter's first screenshot. This returns a *committed*, pre-computed
    snapshot read straight from disk (no simulation, no cold start) so the dashboard paints a
    real result in well under a second; the frontend then transparently re-runs the live sim
    for the actually-selected circuit and swaps the sharper result in.

    Falls back to a tiny live sim only if the snapshot file is somehow absent, so the endpoint
    is always correct even before the ETL has been run.
    """
    import json
    from pathlib import Path

    snap = Path(__file__).resolve().parents[2] / "data" / "predict_default.json"
    try:
        return RaceSimOut(**json.loads(snap.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 -- snapshot missing/corrupt: degrade to a small live sim
        name = next(iter(store.available_circuits()), "Bahrain")
        return _race_sim_out(predict_race_kalman(name, n_sims=1000))


def _championship_payload(year: int | None, n_sims: int, overrides: dict | None,
                          with_market: bool) -> dict:
    """Run the season sim and (best-effort) graft on the de-vigged Polymarket title column.

    The market join is honest portfolio framing, not a signal: the title market is efficient, so
    we expect no edge -- the column just shows where the model and the book agree/disagree. It's a
    network best-effort: if Polymarket is unreachable or the market hasn't opened, the column is
    simply absent (`market_available=False`) and the sim still returns.
    """
    from app.models.season_sim import simulate_season

    out = simulate_season(year, n_sims=n_sims, overrides=overrides or None)

    drv_mkt: dict[str, float] = {}
    con_mkt: dict[str, float] = {}
    if with_market:
        from app.etl.polymarket import championship_market
        try:
            drv_mkt = championship_market(out["year"], "drivers")
            con_mkt = championship_market(out["year"], "constructors")
        except Exception:  # noqa: BLE001 -- never let a flaky feed break the page
            drv_mkt, con_mkt = {}, {}
    for r in out["drivers"]:
        r["market_pct"] = round(drv_mkt[r["driver"]], 4) if r["driver"] in drv_mkt else None
    for r in out["constructors"]:
        r["market_pct"] = round(con_mkt[r["team"]], 4) if r["team"] in con_mkt else None
    out["market_available"] = bool(drv_mkt) or bool(con_mkt)
    return out


@router.get("/championship")
def championship(year: int | None = None, n_sims: int = 20_000,
                 with_market: bool = True) -> dict:
    """Season championship forecast: Monte-Carlo the remaining races into title odds.

    Takes the current standings (classified results so far) and, for every race left, samples a
    finishing order from the same pre-quali pace model + hazard DNF we validate per race, awards
    points, repeats thousands of times -> per-driver and per-constructor title probability,
    expected points and P(top-3). Low overfit: it only aggregates already-validated per-race
    predictions. Includes a best-effort de-vigged Polymarket title column (honest "efficient
    market / no edge" framing -- see docs/journey_notes). See POST /championship/simulate for the
    interactive what-if sandbox.
    """
    n_sims = max(2000, min(60_000, int(n_sims)))
    return _championship_payload(year, n_sims, None, with_market)


@router.post("/championship/simulate")
def championship_simulate(req: ChampionshipRequest) -> dict:
    """Interactive championship sandbox: re-run the season with per-driver what-if overrides.

    overrides = {driver_code: {pace_delta (z, +ve faster), dnf_prob (per-race), extra_dnfs (added
    retirements over the rest of the season)}}. Lets a user ask "if VER has 3 more DNFs / a rookie
    finds 0.3z" and watch the title race re-shake. Market column skipped (it wouldn't reflect the
    hypothetical) so the sandbox stays fast.
    """
    overrides = {k: v.model_dump(exclude_none=True) for k, v in req.overrides.items()}
    return _championship_payload(req.year, req.n_sims, overrides, with_market=False)


@router.post("/strategy/cover-or-extend", response_model=CoverExtendResultOut)
def strategy_cover_or_extend(req: CoverExtendRequest) -> CoverExtendResultOut:
    circuit = store.circuit_params_for(req.circuit_name)
    tyre_overrides = store.tyre_overrides_for(req.circuit_name)
    d = cover_or_extend(
        gap_to_follower_s=req.gap_to_follower_s,
        laps_remaining=req.laps_remaining,
        leader_tyre_age=req.leader_tyre_age,
        leader_compound=req.leader_compound,
        circuit=circuit,
        tyre_overrides=tyre_overrides or None,
    )
    return CoverExtendResultOut(
        recommendation=d.recommendation,
        cover_value_s=round(d.cover_value_s, 3),
        extend_value_s=round(d.extend_value_s, 3),
        rationale=d.rationale,
    )


@router.post("/scenario/safety-car", response_model=SafetyCarResultOut)
def scenario_safety_car(req: SafetyCarRequest) -> SafetyCarResultOut:
    circuit = store.circuit_params_for(req.circuit_name)
    tyre_overrides = store.tyre_overrides_for(req.circuit_name)
    d = safety_car_decision(
        current_lap=req.current_lap,
        total_laps=circuit.total_laps,
        current_compound=req.current_compound,
        current_tyre_age=req.current_tyre_age,
        fresh_compound=req.fresh_compound,
        circuit=circuit,
        tyre_overrides=tyre_overrides or None,
    )
    return SafetyCarResultOut(
        recommendation=d.recommendation,
        pit_now_cost_s=round(d.pit_now_cost_s, 2),
        stay_out_cost_s=round(d.stay_out_cost_s, 2),
        delta_s=round(d.delta_s, 2),
        sc_pit_saving_s=round(d.sc_pit_saving_s, 2),
        stay_plan=d.stay_plan,
        rationale=d.rationale,
    )


@router.post("/scenario/stop-fork", response_model=StopForkResultOut)
def scenario_stop_fork(req: StopForkRequest) -> StopForkResultOut:
    """Best 1-stop vs best 2-stop for the selected circuit (calibrated)."""
    circuit = store.circuit_params_for(req.circuit_name)
    tyre_overrides = store.tyre_overrides_for(req.circuit_name) or None
    one = optimize_strategy(
        circuit, max_stops=1, tyre_overrides=tyre_overrides, top_k=1
    )
    two = optimize_strategy(
        circuit, max_stops=2, tyre_overrides=tyre_overrides, top_k=8
    )
    best_one = one[0]
    best_two = next((r for r in two if r.n_stops == 2), two[0])

    def _opt(r) -> StopForkOption:
        return StopForkOption(
            n_stops=r.n_stops,
            compounds=[s.compound.value for s in r.strategy.stints],
            stint_lengths=[s.length for s in r.strategy.stints],
            pit_laps=r.pit_laps,
            avg_lap_s=round(r.avg_lap_s, 3),
            total_time_s=round(r.total_time_s, 3),
        )

    delta = best_two.total_time_s - best_one.total_time_s
    winner = "2-STOP" if delta < 0 else "1-STOP"
    if winner == "2-STOP":
        rationale = (
            f"the extra stop pays for itself: the best 2-stop is {abs(delta):.1f}s faster "
            "over the race — fresher rubber outweighs the second pit loss."
        )
    else:
        rationale = (
            f"track position wins: the best 1-stop is {abs(delta):.1f}s faster — the second "
            "pit loss costs more than the tyre-life it buys."
        )
    return StopForkResultOut(
        winner=winner,
        delta_s=round(abs(delta), 3),
        one_stop=_opt(best_one),
        two_stop=_opt(best_two),
        rationale=rationale,
    )


@router.post("/scenario/rain-crossover", response_model=RainCrossoverResultOut)
def scenario_rain_crossover(req: RainCrossoverRequest) -> RainCrossoverResultOut:
    """Slicks vs intermediates crossover (calibrated heuristic, circuit-independent)."""
    d = rain_crossover(wetness=req.wetness, laps_remaining=req.laps_remaining)
    return RainCrossoverResultOut(
        recommendation=d.recommendation,
        wetness=round(d.wetness, 3),
        crossover_wetness=round(d.crossover_wetness, 3),
        slick_penalty_s=round(d.slick_penalty_s, 2),
        inter_penalty_s=round(d.inter_penalty_s, 2),
        per_lap_delta_s=round(d.per_lap_delta_s, 2),
        swing_over_remaining_s=round(d.swing_over_remaining_s, 1),
        rationale=d.rationale,
    )


@router.post("/strategy/undercut", response_model=UndercutResultOut)
def strategy_undercut(req: UndercutRequest) -> UndercutResultOut:
    circuit = _circuit_from(req.circuit)
    r = evaluate_undercut(
        gap_s=req.gap_s,
        attacker_compound=req.attacker_compound,
        attacker_tyre_age=req.attacker_tyre_age,
        defender_compound=req.defender_compound,
        defender_tyre_age=req.defender_tyre_age,
        pit_lap=req.pit_lap,
        circuit=circuit,
        window_laps=req.window_laps,
    )
    return UndercutResultOut(
        gap_s=r.gap_s,
        pit_lap=r.pit_lap,
        projected_gap_after_s=round(r.projected_gap_after_s, 3),
        undercut_works=r.undercut_works,
        fresh_tyre_gain_s=round(r.fresh_tyre_gain_s, 3),
        notes=r.notes,
    )
