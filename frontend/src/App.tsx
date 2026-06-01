import { useState } from "react";
import { Explainer } from "./components/Explainer";
import { Explorer } from "./components/Explorer";
import { Markets } from "./components/Markets";
import { Predictor } from "./components/Predictor";
import { ScenarioRunner } from "./components/ScenarioRunner";
import { StrategyLab } from "./components/StrategyLab";

const TABS = [
  { id: "strategy", label: "Strategy Lab", ready: true },
  { id: "scenario", label: "Scenario Runner", ready: true },
  { id: "predictor", label: "Predictor", ready: true },
  { id: "explorer", label: "Explorer", ready: true },
  { id: "markets", label: "Markets", ready: true },
  { id: "live", label: "Live", ready: false },
  { id: "explainer", label: "Explainer", ready: true },
];

export default function App() {
  const [tab, setTab] = useState("strategy");

  return (
    <div className="mx-auto flex min-h-full max-w-6xl flex-col px-6">
      <header className="flex items-center justify-between border-b border-edge py-5">
        <div className="flex items-center gap-3">
          <div className="h-7 w-1.5 rounded-full bg-f1-red" />
          <div>
            <h1 className="text-lg font-bold tracking-tight">
              F1<span className="text-f1-red">Predict</span>
            </h1>
            <p className="text-[11px] uppercase tracking-[0.2em] text-zinc-600">
              Stochastic race simulation engine
            </p>
          </div>
        </div>
        <nav className="flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => t.ready && setTab(t.id)}
              disabled={!t.ready}
              className={`relative rounded-md px-3 py-1.5 text-sm transition ${
                tab === t.id
                  ? "bg-slate-panel text-white"
                  : t.ready
                    ? "text-zinc-400 hover:text-white"
                    : "cursor-not-allowed text-zinc-700"
              }`}
            >
              {t.label}
              {!t.ready && (
                <span className="ml-1 align-super text-[8px] text-zinc-700">soon</span>
              )}
            </button>
          ))}
        </nav>
      </header>

      <main className="flex-1 py-8">
        {tab === "strategy" && <StrategyLab />}
        {tab === "scenario" && <ScenarioRunner />}
        {tab === "predictor" && <Predictor />}
        {tab === "explorer" && <Explorer />}
        {tab === "markets" && <Markets />}
        {tab === "explainer" && <Explainer />}
      </main>

      <footer className="border-t border-edge py-4 text-center text-[11px] text-zinc-600">
        Models documented in <span className="text-zinc-500">docs/science/</span> ·
        seeded from the TUM Heilmeier race simulator
      </footer>
    </div>
  );
}
