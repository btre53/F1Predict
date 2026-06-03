// PIT WALL — RACE COMPANION. The upcoming race's Polymarket props with OUR model beside the
// market, outcome by outcome. Honest framing: a companion, not a betting signal — the market is
// efficient (briefs 07/27/29), so where we diverge it's transparency, not alpha. Props we can
// price (winner, pole, podium, safety car) show model · market · edge; props we don't model
// (fastest lap, red flag, H2H, constructor points) are listed market-only. Wired to /companion/props.
import { useEffect, useState } from "react";
import { api, type Companion as Comp, type CompanionProp } from "../api";
import { pct } from "./charts/Charts";

function fmtPct(x: number | null): string {
  return x == null ? "—" : pct(x);
}

function EdgeChip({ edge }: { edge: number | null }) {
  if (edge == null) return <span className="label" style={{ color: "var(--ink-3)" }}>—</span>;
  const pp = Math.round(edge * 100);
  const c = pp >= 6 ? "var(--green)" : pp <= -6 ? "var(--red)" : "var(--ink-3)";
  return <span className="tnum" style={{ color: c, fontWeight: 600 }}>{pp > 0 ? "+" : ""}{pp}</span>;
}

// One model bar with a market tick overlaid (│), so the gap is visible at a glance.
function CompareBar({ model, market }: { model: number; market: number | null }) {
  return (
    <div className="pw-track" style={{ position: "relative" }}
      title={`model ${pct(model)}${market != null ? ` · market ${pct(market)}` : ""}`}>
      <div className="pw-fill" style={{ width: `${Math.max(1.5, model * 100)}%`, background: "var(--red)" }} />
      {market != null && (
        <span style={{
          position: "absolute", top: -2, bottom: -2, left: `${Math.min(99, market * 100)}%`,
          width: 2, background: "var(--ink-1)", opacity: 0.85,
        }} />
      )}
    </div>
  );
}

function PropCard({ p }: { p: CompanionProp }) {
  return (
    <div className="pw-panel">
      <div className="pw-phead">
        <h2>{p.title}</h2>
        <span className="label">model <span style={{ color: "var(--red)" }}>■</span> · market │</span>
      </div>
      <table className="pw-table">
        <thead><tr><th></th><th>Model vs market</th><th className="num">Model</th><th className="num">Market</th><th className="num">Edge</th></tr></thead>
        <tbody>
          {p.outcomes.map((o) => (
            <tr key={o.name}>
              <td><span className="pw-code">{o.name}</span></td>
              <td style={{ minWidth: 200 }}><CompareBar model={o.model_pct} market={o.market_pct} /></td>
              <td className="num tnum" style={{ color: "var(--red-bright)", fontWeight: 600 }}>{pct(o.model_pct)}</td>
              <td className="num tnum" style={{ color: "var(--ink-3)" }}>{fmtPct(o.market_pct)}</td>
              <td className="num"><EdgeChip edge={o.edge} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Companion() {
  const [data, setData] = useState<Comp | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.companion().then(setData).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="pw-panel" style={{ borderColor: "var(--red)", color: "var(--red-bright)" }}>{err}</div>;
  if (!data) return <div className="label">Loading the upcoming race…</div>;
  if (!data.available || !data.race) {
    return (
      <div className="pw-live"><div>
        <div className="big">▮ NO OPEN MARKETS</div>
        <h2>Race companion</h2>
        <p className="desc" style={{ maxWidth: "46ch", margin: "0 auto" }}>
          No upcoming race with open Polymarket prop markets right now. This view lights up in the
          days before a Grand Prix.
        </p>
      </div></div>
    );
  }

  const r = data.race;
  const modelled = (data.props ?? []).filter((p) => p.modelled);
  const marketOnly = (data.props ?? []).filter((p) => !p.modelled);
  const preQuali = r.quali_utc ? new Date(r.quali_utc).getTime() > Date.now() : true;

  return (
    <div className="pw-stack">
      <div className="pw-controls">
        <div className="pw-readouts">
          <div className="pw-readout"><div className="label">Next race</div><div className="v">{r.event_name?.replace(" Grand Prix", "") || r.circuit}</div></div>
          <div className="pw-readout"><div className="label">Round</div><div className="v tnum">{r.round ?? "—"}</div></div>
          <div className="pw-readout"><div className="label">Days away</div><div className="v tnum">{r.days_away ?? "—"}</div></div>
          <div className="pw-readout"><div className="label">Grid</div>
            <div className="v" style={{ color: preQuali ? "var(--amber)" : "var(--green)" }}>{preQuali ? "PRE-QUALI" : "POST-QUALI"}</div></div>
          <div className="pw-readout"><div className="label">Props priced</div><div className="v tnum">{modelled.length}</div></div>
        </div>
      </div>

      <div className="pw-panel" style={{ borderColor: "var(--amber)" }}>
        <p className="desc" style={{ margin: 0 }}>
          Our model's number next to the de-vigged Polymarket price for every prop we can honestly
          price. <b>This is a companion, not a tip</b> — the market is efficient (we've shown no edge
          on winner, pole or in-play; briefs 07 / 27 / 29). Where the bars diverge it's the model's
          read shown transparently{preQuali ? " — and it's PRE-qualifying, so pole/winner sharpen once the grid is set" : ""}.
        </p>
      </div>

      {!r.modelled && (
        <div className="pw-panel"><p className="label" style={{ margin: 0 }}>
          We don't have calibrated data for {r.circuit} yet, so model numbers are unavailable — the
          market props are listed below.</p></div>
      )}

      {modelled.map((p) => <PropCard key={p.type} p={p} />)}

      {marketOnly.length > 0 && (
        <div className="pw-panel">
          <div className="pw-phead"><h2>Market-only props</h2><span className="label">we don't model these</span></div>
          <p className="desc" style={{ marginTop: 0 }}>
            Polymarket prices these for {r.event_name?.replace(" Grand Prix", "")}, but we don't
            produce an honest number for them (yet) — so we show no edge rather than a fake one.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {marketOnly.map((p) => (
              <span key={p.type} className="pw-badge" style={{ fontSize: 11 }}>{p.title}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
