# 12 — Telemetry → Racecraft Validation (step 1 of the in-play plan)

**Question (TODO "Immediate next" #1):** is the car-netted **racecraft** signal
(`app/models/racecraft.py` — positions-gained-above-expectation, PGAE) actually
**visible in in-race process** we can measure, or is it only a finishing-position
*outcome*? This gates the whole in-play/live-telemetry thesis: *if racecraft is real
driver skill that shows up in measurable, real-time behaviour, then a live telemetry
feed could improve live predictions. If it doesn't, paying for a live feed (~€10/mo
OpenF1) to "see racecraft happen" is unjustified.* Learned for **free**, before any spend.

**Method.** Racecraft is **car-netted** (a driver vs their own car), so every test is
**teammate-paired**: compute a process signature per driver-race, subtract the team's
mean that race (car/track/fuel cancel), and ask whether the netted signature tracks the
netted outcome (PGAE). Two grains: per **driver-race** (n≈1.8k) and per **driver**
(career rating, n=31 with ≥15 races). Code: `app/models/racecraft_signatures.py`
(lap-level, free, no API) and `app/models/telemetry_signatures.py` (sub-lap car
telemetry, sampled). Data: `laps.parquet` (105 races, 2018–2025; green-flag, accurate,
non-pit, dry laps only).

---

## Result 1 — lap-level process signatures (free, decisive)

Teammate-netted signature vs teammate-netted PGAE. Sign in parens = "better racecraft":

| Signature | per-driver-race r | per-driver r | Verdict |
|---|---|---|---|
| **race pace** (% gap to race-best green lap) | **−0.275** (−) | **−0.507** (−) | **Only real signal.** Faster-than-teammate race pace ↔ gains positions. |
| tyre management (within-stint deg slope, s/lap) | −0.051 (−) | −0.118 (−) | ~nothing at lap resolution |
| consistency (detrended stint lap scatter, s) | +0.069 (–, wrong sign) | +0.089 (wrong) | ~nothing / conflated with racing hard |
| traffic penalty (dirty-air lap-time loss) | +0.069 (wrong) | −0.047 (−) | ~nothing (lap-resolution gap proxy is too crude) |
| on-track positions gained *(semi-outcome)* | +0.769 (+) | +0.580 (+) | circular — it *is* roughly PGAE; not evidence |

**Robustness — is "race pace" just one-lap pace, or genuine race-day skill?**
- teammate-netted **quali** pace vs PGAE: **r = +0.034** → one-lap pace does **not**
  predict positions gained (correct: grid already encodes quali, so PGAE is the
  residual). **Racecraft is a distinct skill, not "this driver is faster."**
- race-pace's correlation with PGAE **survives removing quali** (residual r = −0.284,
  if anything stronger); corr(quali_net, race_pace_net) = +0.13. So the race-pace
  advantage is a real **race-day** quantity, separable from qualifying.

**The caveat that matters:** race pace is **confounded with track position**. A driver
who gains places runs in **clean air** → faster median lap. So "fast race pace ↔ gains
positions" may be **effect, not cause**. We cannot cleanly separate the two from lap
medians alone (a clean-air pace correction is future work).

---

## Result 2 — sub-lap car-telemetry style (sampled, 8 races, n=152 driver-races)

Pulled FastF1 **car telemetry** (Speed/Throttle/Brake/gear/DRS, ~370 samples/lap) for 8
races chosen for strong within-team racecraft contrast (2024 Bahrain/Spain/Austria/Italy/
Mexico, 2023 Bahrain/Hungary/Brazil). Per driver-race we took the median over green
racing laps of full-throttle %, brake %, coast %, top/avg speed, and throttle smoothness
(`throttle_jerk` = mean |Δthrottle|), teammate-netted. Cached to `data/telemetry_sig.parquet`.

| Style metric | per-driver-race r (n=152) | per-driver r (n=20) |
|---|---|---|
| full_throttle_pct | −0.179 | −0.482 |
| throttle_jerk (lower=smoother) | +0.134 | +0.538 |
| brake_pct | +0.150 | +0.167 |
| avg_speed | −0.083 | +0.195 |
| top_speed | +0.086 | +0.206 |
| coast_pct | +0.094 | −0.183 |

(The per-driver column wobbles ±0.03 between runs — n=20 is fragile, which is the point.
The per-driver-race column is stable.)

**Read:** at the reliable grain (**per driver-race, n=152**) **nothing reaches |r|>0.18** —
sub-lap driving style does **not** separate racecraft from the car. The eye-catching
per-driver numbers (full-throttle −0.52, throttle-jerk +0.53) are **fragile (n=20) and
have the wrong sign for a skill story** — "better racecraft ⇒ *less* full throttle and a
*jerkier* pedal" is the fingerprint of a **good driver stuck in a slow car running in
traffic** (HAM, ALB here), i.e. **traffic exposure, not skill**. Same clean-air confound
as Result 1, inverted — which *reinforces* that telemetry style tracks **where** a driver
runs, not a hidden skill channel.

---

## Honest conclusion (amber, leaning negative on the paid-feed premise)

1. **Racecraft is real but thin, and embodied in race-pace/position, not in granular
   behaviour.** The car-netted skill signal is genuine (distinct from quali pace) but at
   lap resolution it shows up almost entirely as a **race-pace delta** (|r|≈0.3–0.5) —
   and that is partly a **clean-air artefact** of the position-gaining itself.
2. **Tyre management, consistency, and traffic-handling carry ~no teammate-netted signal**
   at lap resolution. The "racecraft = visible tyre-whispering / traffic-mastery" story
   is **not supported** by the lap data.
3. **Implication for the live-telemetry thesis:** a live feed would mostly re-derive
   **race pace and track position**, which we already get from **lap timing** (free,
   from FastF1/SignalR) — not a hidden granular skill channel. So the **marginal value of
   a paid telemetry feed for live racecraft prediction looks low.** The in-play edge, if
   any, is the **fast race-state reaction** thesis (SC/VSC/rain/DNF repricing vs a slow
   thin market — see brief 10 §1 WPA, brief 11), **not** "see racecraft in telemetry."

**Recommendation:** do **not** gate in-play work on telemetry. Re-point step 1's
conclusion at the **WPA-from-reconstructed-state** direction (brief 10) and the
**track-evolution / rain-transition** signal (brief 11), both backtestable for free on
lap + weather data we already have. Keep telemetry as an **interpretability/Explainer**
feature (car-DNA factors, brief 10 §4), not a live-prediction dependency.
