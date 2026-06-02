// PIT WALL — app shell. Replaces the existing src/App.tsx.
// Make sure the design system stylesheet is imported once (here or in main.tsx):
import "./styles/pitwall.css";
import { useEffect, useState } from "react";
import { Predictor } from "./components/Predictor";
import { StrategyLab } from "./components/StrategyLab";
import { ScenarioRunner } from "./components/ScenarioRunner";
import { Explorer } from "./components/Explorer";
import { Markets } from "./components/Markets";
import { Explainer } from "./components/Explainer";
import { Methodology } from "./components/Methodology";

const TABS = [
  { id: "predictor", label: "PREDICTOR", C: Predictor },
  { id: "strategy", label: "STRATEGY LAB", C: StrategyLab },
  { id: "scenario", label: "SCENARIO", C: ScenarioRunner },
  { id: "explorer", label: "EXPLORER", C: Explorer },
  { id: "markets", label: "MARKETS", C: Markets },
  { id: "explainer", label: "EXPLAINER", C: Explainer },
  { id: "findings", label: "FINDINGS", C: Methodology },
  { id: "live", label: "LIVE", soon: true, C: Live },
] as const;

function Live() {
  return (
    <div className="pw-live">
      <div>
        <div className="big">▮ TELEMETRY OFFLINE</div>
        <h2>Live timing</h2>
        <p className="desc" style={{ maxWidth: "44ch", margin: "0 auto" }}>
          Real-time positions, gaps and tyre ages stream here during a session. No live Grand Prix in progress.
        </p>
        <div className="pw-badge" style={{ marginTop: 22 }}>
          <span className="live" style={{ background: "var(--amber)", boxShadow: "0 0 8px var(--amber)" }} />Awaiting next session
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState("predictor");
  const [theme, setTheme] = useState(() => localStorage.getItem("pw-theme") || "dark");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("pw-theme", theme);
  }, [theme]);

  const Active = TABS.find((t) => t.id === tab)?.C ?? Predictor;

  return (
    <div className="pw-app">
      <header className="pw-header">
        <div className="pw-wrap pw-header-in">
          <div className="pw-brand">
            <span className="bar" />
            <div>
              <h1>F1<b>Predict</b></h1>
              <div className="sub">Stochastic race simulation engine</div>
            </div>
          </div>
          <nav className="pw-nav">
            {TABS.map((t) => (
              <button key={t.id} className={tab === t.id ? "active" : ""}
                disabled={"soon" in t && t.soon} onClick={() => !("soon" in t && t.soon) && setTab(t.id)}>
                <span className="dot" />{t.label}{"soon" in t && t.soon && <span className="soon">SOON</span>}
              </button>
            ))}
          </nav>
          <div className="pw-toggle">
            <button className={theme === "dark" ? "on" : ""} onClick={() => setTheme("dark")} title="Carbon">◐</button>
            <button className={theme === "light" ? "on" : ""} onClick={() => setTheme("light")} title="Blueprint">○</button>
          </div>
        </div>
      </header>

      <main className="pw-wrap pw-section"><Active /></main>

      <footer className="pw-footer">
        MODELS DOCUMENTED IN docs/science/ · SEEDED FROM THE TUM HEILMEIER RACE SIMULATOR
      </footer>
    </div>
  );
}
