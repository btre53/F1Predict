// PIT WALL — Scenario Runner tab.
// Pick a live race situation + a triggering event; the calibrated engine gives the
// strategic call in the open (the "anti-AWS"). Each scenario composes Strategy Lab
// primitives. Wired to api.safetyCar / undercut / coverOrExtend / stopFork / rainCrossover.
import { useEffect, useState } from "react";
import {
  api,
  type Circuit,
  type CircuitInfo,
  type Compound,
  type CoverExtendResult,
  type RainCrossoverResult,
  type SafetyCarResult,
  type StopForkResult,
  type UndercutResult,
} from "../api";
import { COMPOUND_COLOR, DuelBar, Slider, StintBar } from "./charts/Charts";

const SCENARIOS = [
  { id: "sc", label: "Safety car" },
  { id: "undercut", label: "Undercut" },
  { id: "cover", label: "Cover vs extend" },
  { id: "fork", label: "1 vs 2 stop" },
  { id: "rain", label: "Rain crossover" },
] as const;

const DRY: Compound[] = ["SOFT", "MEDIUM", "HARD"];

function useDebounced<T>(value: T, ms = 110): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return v;
}

// Pit-wall compound picker, matching the pw-seg look.
function Compounds({
  label,
  value,
  onChange,
}: {
  label: string;
  value: Compound;
  onChange: (c: Compound) => void;
}) {
  return (
    <div className="pw-slider">
      <div className="top">
        <span className="label">{label}</span>
        <span className="v tnum">{value}</span>
      </div>
      <div className="pw-seg" style={{ gap: 6 }}>
        {DRY.map((c) => (
          <button
            key={c}
            className={value === c ? "on" : ""}
            style={{ width: "auto", flex: 1, fontSize: 11 }}
            onClick={() => onChange(c)}
          >
            {c}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ScenarioRunner() {
  const [circuits, setCircuits] = useState<CircuitInfo[]>([]);
  const [ci, setCi] = useState<CircuitInfo | null>(null);
  const [scenario, setScenario] = useState<(typeof SCENARIOS)[number]["id"]>("sc");

  useEffect(() => {
    api.circuits().then((cs) => {
      setCircuits(cs);
      setCi(cs[0] ?? null);
    });
  }, []);

  return (
    <div className="pw-stack">
      <div className="pw-intro">
        <h2>Scenario Runner</h2>
        <p>
          Put the car in a live situation and let the calibrated strategy engine make the
          call — the reasoning a race engineer would, shown in the open.
        </p>
      </div>

      <div className="pw-controls">
        <div className="pw-field">
          <span className="label">Circuit</span>
          <select
            className="pw-select"
            value={ci?.name ?? ""}
            onChange={(e) => setCi(circuits.find((c) => c.name === e.target.value) ?? null)}
          >
            {circuits.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} GP
              </option>
            ))}
          </select>
        </div>
        <div className="pw-field">
          <span className="label">Scenario</span>
          <div className="pw-seg" style={{ flexWrap: "wrap" }}>
            {SCENARIOS.map((s) => (
              <button
                key={s.id}
                className={scenario === s.id ? "on" : ""}
                style={{ width: "auto", padding: "0 12px" }}
                onClick={() => setScenario(s.id)}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        {ci && (
          <div className="pw-readouts">
            <div className="pw-readout">
              <div className="label">{ci.total_laps} laps</div>
              {ci.calibrated && (
                <div className="pw-badge" style={{ marginTop: 6 }}>
                  <span className="live" />Calibrated
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {!ci ? (
        <div className="label">Loading calibrated circuits…</div>
      ) : (
        <>
          {scenario === "sc" && <SafetyCarScenario circuit={ci} />}
          {scenario === "undercut" && <UndercutScenario circuit={ci} />}
          {scenario === "cover" && <CoverExtendScenario circuit={ci} />}
          {scenario === "fork" && <StopForkScenario circuit={ci} />}
          {scenario === "rain" && <RainCrossoverScenario circuit={ci} />}
        </>
      )}
    </div>
  );
}

// ---- Safety car: pit now (cheap stop) vs stay out -------------------------- //
function SafetyCarScenario({ circuit }: { circuit: CircuitInfo }) {
  const [lap, setLap] = useState(Math.round(circuit.total_laps * 0.45));
  const [compound, setCompound] = useState<Compound>("MEDIUM");
  const [age, setAge] = useState(20);
  const [fresh, setFresh] = useState<Compound>("HARD");
  const [res, setRes] = useState<SafetyCarResult | null>(null);

  useEffect(() => setLap(Math.round(circuit.total_laps * 0.45)), [circuit]);

  const dLap = useDebounced(lap);
  const dAge = useDebounced(age);
  useEffect(() => {
    api
      .safetyCar({
        circuit_name: circuit.name,
        current_lap: dLap,
        current_compound: compound,
        current_tyre_age: dAge,
        fresh_compound: fresh,
      })
      .then(setRes)
      .catch(() => {});
  }, [dLap, compound, dAge, fresh, circuit]);

  const pit = res?.recommendation === "PIT";

  return (
    <div className="pw-panel pw-toolpanel">
      <div className="pw-phead">
        <h2>Safety car — box, or stay out?</h2>
        <span className="desc">
          A safety car bunches the field, so a pit stop costs far less time than usual. Take the
          cheap stop for fresh tyres, or hold track position?
        </span>
      </div>
      <div className="pw-grid2">
        <div className="pw-stack" style={{ gap: 18 }}>
          <Slider
            label={`Current lap (${circuit.total_laps - lap} to go)`}
            min={1}
            max={circuit.total_laps - 1}
            value={lap}
            onChange={setLap}
          />
          <Compounds label="Tyre on the car now" value={compound} onChange={setCompound} />
          <Slider label="Tyre age" value={age} min={0} max={40} unit=" laps" onChange={setAge} />
          <Compounds label="Fresh set you'd fit" value={fresh} onChange={setFresh} />
        </div>
        <div className="pw-stack" style={{ gap: 16 }}>
          {res && (
            <DuelBar
              aLabel="Pit now"
              a={+res.pit_now_cost_s.toFixed(1)}
              bLabel="Stay out"
              b={+res.stay_out_cost_s.toFixed(1)}
            />
          )}
          {res && (
            <div
              className="pw-verdict"
              style={{ borderColor: pit ? "var(--red)" : "#3b8dff" }}
            >
              <h3 style={{ color: pit ? "var(--red-bright)" : "#3b8dff" }}>
                {pit ? "BOX NOW" : "STAY OUT"}
              </h3>
              <div className="pw-vrow">
                <span>{pit ? "Faster by" : "Better staying by"}</span>
                <span className="v">{Math.abs(res.delta_s).toFixed(1)}s</span>
              </div>
              <div className="pw-vrow">
                <span>SC stop discount vs green</span>
                <span className="v">−{res.sc_pit_saving_s.toFixed(1)}s</span>
              </div>
              {res.rationale && <div className="pw-vnote">{res.rationale}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- Undercut: does pitting now clear the car ahead? ----------------------- //
function UndercutScenario({ circuit }: { circuit: CircuitInfo }) {
  const [gap, setGap] = useState(1.5);
  const [atk, setAtk] = useState<Compound>("SOFT");
  const [def, setDef] = useState<Compound>("MEDIUM");
  const [defAge, setDefAge] = useState(18);
  const [res, setRes] = useState<UndercutResult | null>(null);

  const dGap = useDebounced(gap);
  const dDefAge = useDebounced(defAge);
  useEffect(() => {
    const c: Circuit = {
      name: circuit.name,
      base_lap_ms: circuit.base_lap_ms,
      total_laps: circuit.total_laps,
    };
    api
      .undercut({
        gap_s: dGap,
        attacker_compound: atk,
        attacker_tyre_age: 0,
        defender_compound: def,
        defender_tyre_age: dDefAge,
        pit_lap: Math.round(circuit.total_laps * 0.4),
        circuit: c,
      })
      .then(setRes)
      .catch(() => {});
  }, [dGap, atk, def, dDefAge, circuit]);

  const works = res?.undercut_works;

  return (
    <div className="pw-panel pw-toolpanel">
      <div className="pw-phead">
        <h2>Undercut — pit now to jump the car ahead?</h2>
        <span className="desc">
          You pit for fresh tyres while the car ahead stays out on worn rubber. Does the
          fresh-tyre pace make up the gap before they react?
        </span>
      </div>
      <div className="pw-grid2">
        <div className="pw-stack" style={{ gap: 18 }}>
          <Slider label="Gap to car ahead" value={gap} min={0} max={4} step={0.1} unit="s" onChange={setGap} />
          <Compounds label="Your fresh tyre" value={atk} onChange={setAtk} />
          <Compounds label="Their tyre" value={def} onChange={setDef} />
          <Slider label="Their tyre age" value={defAge} min={0} max={40} unit=" laps" onChange={setDefAge} />
        </div>
        <div className="pw-stack" style={{ gap: 16 }}>
          {res && (
            <DuelBar
              aLabel="Gap to clear"
              a={+gap.toFixed(1)}
              bLabel="Fresh-tyre gain"
              b={+res.fresh_tyre_gain_s.toFixed(2)}
            />
          )}
          {res && (
            <div
              className="pw-verdict"
              style={{ borderColor: works ? "var(--green)" : "var(--line)" }}
            >
              <h3 style={{ color: works ? "var(--green)" : "var(--ink-2)" }}>
                {works ? "UNDERCUT WORKS" : "GAP TOO BIG"}
              </h3>
              <div className="pw-vrow">
                <span>Fresh-tyre gain over window</span>
                <span className="v">+{res.fresh_tyre_gain_s.toFixed(2)}s</span>
              </div>
              <div className="pw-vrow">
                <span>Projected gap after cycle</span>
                <span className="v">
                  {res.projected_gap_after_s > 0 ? "+" : ""}
                  {res.projected_gap_after_s.toFixed(2)}s
                </span>
              </div>
              {res.notes[0] && <div className="pw-vnote">{res.notes[0]}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- Cover vs extend (Stackelberg leader decision) ------------------------- //
function CoverExtendScenario({ circuit }: { circuit: CircuitInfo }) {
  const [gap, setGap] = useState(1.2);
  const [lapsRem, setLapsRem] = useState(Math.max(5, Math.round(circuit.total_laps * 0.4)));
  const [age, setAge] = useState(18);
  const [res, setRes] = useState<CoverExtendResult | null>(null);

  useEffect(
    () => setLapsRem(Math.max(5, Math.round(circuit.total_laps * 0.4))),
    [circuit],
  );

  const dGap = useDebounced(gap);
  const dLaps = useDebounced(lapsRem);
  const dAge = useDebounced(age);
  useEffect(() => {
    api
      .coverOrExtend({
        circuit_name: circuit.name,
        gap_to_follower_s: dGap,
        laps_remaining: dLaps,
        leader_tyre_age: dAge,
        leader_compound: "MEDIUM",
      })
      .then(setRes)
      .catch(() => {});
  }, [dGap, dLaps, dAge, circuit]);

  const extend = res?.recommendation === "EXTEND";

  return (
    <div className="pw-panel pw-toolpanel">
      <div className="pw-phead">
        <h2>Cover vs extend</h2>
        <span className="desc">
          Leader's Stackelberg call: react to the follower's undercut now, or extend the stint
          to build a tyre-age offset for a fresher final stint.
        </span>
      </div>
      <div className="pw-grid2">
        <div className="pw-stack" style={{ gap: 18 }}>
          <Slider label="Gap to follower" value={gap} min={0} max={5} step={0.1} unit="s" onChange={setGap} />
          <Slider label="Laps remaining" value={lapsRem} min={3} max={circuit.total_laps} onChange={setLapsRem} />
          <Slider label="Leader tyre age" value={age} min={0} max={40} unit=" laps" onChange={setAge} />
        </div>
        <div className="pw-stack" style={{ gap: 16 }}>
          {res && (
            <DuelBar
              aLabel="Cover value"
              a={+res.cover_value_s.toFixed(2)}
              bLabel="Extend value"
              b={+res.extend_value_s.toFixed(2)}
            />
          )}
          {res && (
            <div
              className="pw-verdict"
              style={{ borderColor: extend ? "#3b8dff" : "var(--amber)" }}
            >
              <h3 style={{ color: extend ? "#3b8dff" : "var(--amber)" }}>{res.recommendation}</h3>
              <div className="pw-vrow">
                <span>Cover value</span>
                <span className="v">
                  {res.cover_value_s > 0 ? "+" : ""}
                  {res.cover_value_s.toFixed(2)}s
                </span>
              </div>
              <div className="pw-vrow">
                <span>Extend value</span>
                <span className="v">
                  {res.extend_value_s > 0 ? "+" : ""}
                  {res.extend_value_s.toFixed(2)}s
                </span>
              </div>
              {res.rationale && <div className="pw-vnote">{res.rationale}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- 1-stop vs 2-stop fork ------------------------------------------------- //
function ForkOption({ opt, win }: { opt: StopForkResult["one_stop"]; win: boolean }) {
  return (
    <div className={"pw-optrow" + (win ? " best" : "")}>
      <div className="pw-optnum">{opt.n_stops}</div>
      <div>
        <div className="pw-optmeta">
          <span>
            <b className="mono">{opt.n_stops}-stop</b>{" "}
            <span className="pw-team mono">
              {opt.pit_laps.length ? `pit ${opt.pit_laps.join(", ")}` : "no stop"}
            </span>
          </span>
          <span style={{ textAlign: "right" }}>
            <span className={"delta" + (win ? " best" : "")}>{win ? "FASTER" : ""}</span>
            <br />
            <span className="avg">avg {opt.avg_lap_s.toFixed(1)}s/lap</span>
          </span>
        </div>
        <StintBar compounds={opt.compounds} lengths={opt.stint_lengths} />
      </div>
    </div>
  );
}

function StopForkScenario({ circuit }: { circuit: CircuitInfo }) {
  const [res, setRes] = useState<StopForkResult | null>(null);

  useEffect(() => {
    setRes(null);
    api
      .stopFork({ circuit_name: circuit.name })
      .then(setRes)
      .catch(() => {});
  }, [circuit]);

  const oneWins = res?.winner === "1-STOP";

  return (
    <div className="pw-panel pw-toolpanel">
      <div className="pw-phead">
        <h2>1-stop vs 2-stop fork</h2>
        <span className="desc">
          For {circuit.name} GP the engine optimizes the best one-stop and the best two-stop, then
          compares total race time. Fewer pit losses vs fresher rubber — which wins here?
        </span>
      </div>
      {!res ? (
        <div className="label">Optimizing both strategies…</div>
      ) : (
        <div className="pw-stack" style={{ gap: 16 }}>
          <ForkOption opt={res.one_stop} win={oneWins} />
          <ForkOption opt={res.two_stop} win={!oneWins} />
          <div
            className="pw-verdict"
            style={{ borderColor: oneWins ? "#3b8dff" : "var(--red)" }}
          >
            <h3 style={{ color: oneWins ? "#3b8dff" : "var(--red-bright)" }}>
              {res.winner} WINS
            </h3>
            <div className="pw-vrow">
              <span>Margin over the race</span>
              <span className="v">{res.delta_s.toFixed(1)}s</span>
            </div>
            <div className="pw-vrow">
              <span>Best 1-stop · avg lap</span>
              <span className="v">{res.one_stop.avg_lap_s.toFixed(1)}s</span>
            </div>
            <div className="pw-vrow">
              <span>Best 2-stop · avg lap</span>
              <span className="v">{res.two_stop.avg_lap_s.toFixed(1)}s</span>
            </div>
            {res.rationale && <div className="pw-vnote">{res.rationale}</div>}
          </div>
        </div>
      )}
    </div>
  );
}

// ---- Rain crossover (slicks vs inters, calibrated heuristic) --------------- //
function RainCrossoverScenario({ circuit }: { circuit: CircuitInfo }) {
  const [wetness, setWetness] = useState(0.35);
  const [lapsRem, setLapsRem] = useState(Math.max(5, Math.round(circuit.total_laps * 0.5)));
  const [res, setRes] = useState<RainCrossoverResult | null>(null);

  useEffect(
    () => setLapsRem(Math.max(5, Math.round(circuit.total_laps * 0.5))),
    [circuit],
  );

  const dWet = useDebounced(wetness);
  const dLaps = useDebounced(lapsRem);
  useEffect(() => {
    api
      .rainCrossover({ wetness: dWet, laps_remaining: dLaps })
      .then(setRes)
      .catch(() => {});
  }, [dWet, dLaps]);

  const inters = res?.recommendation === "INTERS";

  return (
    <div className="pw-panel pw-toolpanel">
      <div className="pw-phead">
        <h2>Rain crossover — slicks vs intermediates</h2>
        <span className="desc">
          Calibrated heuristic (not a fitted model): slick pace falls apart fast as water appears,
          inters improve as the track wets. The crossover is the wetness where inters become faster.
        </span>
      </div>
      <div className="pw-grid2">
        <div className="pw-stack" style={{ gap: 18 }}>
          <Slider
            label="Track wetness"
            value={+(wetness * 100).toFixed(0)}
            min={0}
            max={100}
            unit="%"
            onChange={(v) => setWetness(v / 100)}
          />
          <Slider label="Laps remaining" value={lapsRem} min={3} max={circuit.total_laps} onChange={setLapsRem} />
        </div>
        <div className="pw-stack" style={{ gap: 16 }}>
          {res && (
            <DuelBar
              aLabel="Slick penalty/lap"
              a={+res.slick_penalty_s.toFixed(1)}
              bLabel="Inter penalty/lap"
              b={+res.inter_penalty_s.toFixed(1)}
              unit="s"
            />
          )}
          {res && (
            <div
              className="pw-verdict"
              style={{
                borderColor: inters
                  ? COMPOUND_COLOR.INTERMEDIATE
                  : COMPOUND_COLOR.SOFT,
              }}
            >
              <h3
                style={{
                  color: inters ? COMPOUND_COLOR.INTERMEDIATE : COMPOUND_COLOR.SOFT,
                }}
              >
                {inters ? "BOX FOR INTERS" : "STAY ON SLICKS"}
              </h3>
              <div className="pw-vrow">
                <span>Crossover wetness</span>
                <span className="v">{(res.crossover_wetness * 100).toFixed(0)}%</span>
              </div>
              <div className="pw-vrow">
                <span>Per-lap delta (slick − inter)</span>
                <span className="v">
                  {res.per_lap_delta_s > 0 ? "+" : ""}
                  {res.per_lap_delta_s.toFixed(1)}s
                </span>
              </div>
              <div className="pw-vrow">
                <span>Swing over {lapsRem} laps</span>
                <span className="v">
                  {res.swing_over_remaining_s > 0 ? "+" : ""}
                  {res.swing_over_remaining_s.toFixed(0)}s
                </span>
              </div>
              {res.rationale && <div className="pw-vnote">{res.rationale}</div>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
