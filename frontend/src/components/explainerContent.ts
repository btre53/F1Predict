// Static copy for the Explainer tab — terse, technical.
export const EXPLAINER = [
  { n: "01", title: "How a lap time is built", tag: "PHYSICS + ML + NOISE", body: "Physics for the knowns, a learned residual for the patterns, skewed noise for the rest." },
  { n: "02", title: "Fuel-corrected pace", tag: "~0.03 S/LAP PER KG", body: "Strip out the ~100 kg fuel burn-off and the true tyre picture shows up." },
  { n: "03", title: "Three-phase tyre degradation", tag: "WARM-UP · LINEAR · CLIFF", body: "Warm-in, a steady linear phase, then the cliff. Each compound's curve is learned from long runs." },
  { n: "04", title: "Why driver noise is skewed", tag: "YOU CAN ONLY LOSE TIME", body: "A lock-up costs a second; a perfect lap never gains one. Randomness is positively skewed." },
  { n: "05", title: "Monte Carlo race simulation", tag: "10,000 RACES, NOT ONE", body: "Ten thousand runs of tyre luck, mistakes and safety cars — counted into probabilities." },
  { n: "06", title: "Pit stops, undercut & overcut", tag: "THE ~20-SECOND COST", body: "Race time is every lap plus a ~20 s stop. Fresh rubber early buys the leapfrog." },
  { n: "07", title: "Stackelberg: cover vs extend", tag: "LEADER–FOLLOWER GAME", body: "Cover the chaser's stop, or extend for a tyre offset. Solved backwards from the flag." },
  { n: "08", title: "Safety-car modelling", tag: "~50% OF RACES", body: "Half of all races see one. Stopping under it is close to a free pit." },
];

export const SOURCES = [
  "Heilmeier et al. 2020 — Monte Carlo race simulation (Applied Sciences)",
  "TUM FTM/race-simulation — open-source code + calibrated parameter files",
  "State-Space Tyre Degradation (arXiv 2512.00640)",
  "Aguad & Thraves — Stackelberg pit-stop game (EJOR 2024)",
];
