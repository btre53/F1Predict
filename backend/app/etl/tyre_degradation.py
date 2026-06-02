"""Re-fit per-compound tyre-age degradation with Heilmeier's closed forms (brief 20, part A).

Heilmeier 2020 / TUMFTM model tyre degradation as a per-COMPOUND closed-form function of
tyre age -- linear / quadratic / cubic / logarithmic loss vs a fresh tyre. They found the
LOG form best on 2014-2019; their coefficients were fit on a different era, so we re-fit on
CURRENT ground-effect-era (2022+) FastF1 stint residuals and let AIC pick the winning form
(open question 3 in docs/science/20).

Target = the stint-relative, fuel-corrected degradation residual (a lap's loss vs its own
stint's fastest fuel-corrected lap), pooled across circuits per compound -- exactly the
Heilmeier Delta_t_tyre(age) quantity. Fully free-data: lap/sector timing only, no tyre
temps / loads / slip.

Writes data/tyre_degradation.json (per-compound best form + coefficients + the loss curve),
a documented artifact for the Explainer and a candidate to sharpen the sim's tyre model.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
from scipy.optimize import curve_fit

from app.engine.params import RegulationEra
from app.etl.calibrate import _clean_race_laps, _fuel_correct, MIN_STINT_LAPS

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LAPS_PARQUET = DATA_DIR / "laps.parquet"
OUT_JSON = DATA_DIR / "tyre_degradation.json"

DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")
MODERN_ERAS = ("GE_DRS_2022_2025", "ACTIVE_AERO_2026")  # the current ground-effect era
MIN_LAPS = 60   # per compound, pooled across circuits, to fit up to 4 params robustly


def _compound_residuals(df: pl.DataFrame) -> pl.DataFrame:
    """Pooled per-(compound, tyre_life) stint-relative fuel-corrected residuals (2022+)."""
    frames: list[pl.DataFrame] = []
    for circuit in df["circuit"].unique().to_list():
        sub = df.filter(pl.col("circuit") == circuit)
        era = RegulationEra(sub["regulation_era"][0])
        total_laps = int(sub["lap_number"].max())
        clean = _fuel_correct(_clean_race_laps(sub), era, total_laps)
        if clean.height == 0:
            continue
        stint_min = clean.group_by(["driver", "stint"]).agg(
            pl.col("fuel_corrected_s").min().alias("base"),
            pl.len().alias("slen"),
        )
        clean = clean.join(stint_min, on=["driver", "stint"]).filter(
            pl.col("slen") >= MIN_STINT_LAPS
        )
        frames.append(
            clean.with_columns(
                (pl.col("fuel_corrected_s") - pl.col("base")).alias("deg_residual")
            ).select(["compound", "tyre_life", "deg_residual"])
        )
    if not frames:
        return pl.DataFrame()
    out = pl.concat(frames, how="vertical_relaxed")
    return out.filter(
        pl.col("tyre_life").is_not_null() & pl.col("deg_residual").is_finite()
    )


MIN_BIN_LAPS = 20   # laps needed at a tyre age for its median to be trustworthy
MAX_AGE = 40        # ignore very-long-age tails (sparse, mostly SC-extended stints)


def _bin_medians(age: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Robust degradation curve: median residual per integer tyre age (kills traffic
    outliers that swamp the per-lap signal), with the lap count per age for weighting."""
    a = np.round(age).astype(int)
    ages, meds, wts = [], [], []
    for k in range(1, MAX_AGE + 1):
        yk = y[a == k]
        if len(yk) >= MIN_BIN_LAPS:
            ages.append(float(k))
            meds.append(float(np.median(yk)))
            wts.append(float(len(yk)))
    return np.array(ages), np.array(meds), np.array(wts)


def _aic(n: int, rss: float, k: int) -> float:
    """Akaike information criterion for a Gaussian least-squares fit (lower = better)."""
    rss = max(rss, 1e-9)
    return n * np.log(rss / n) + 2 * k


def _log_model(age, k0, k1, k2):
    return k0 + k1 * np.log(k2 * age + 1.0)


def _fit_forms(age: np.ndarray, y: np.ndarray, w: np.ndarray) -> dict:
    """Fit the four Heilmeier closed forms to the per-age median curve (count-weighted).

    RMSE/AIC are on the binned curve, so they measure how well each form captures the
    degradation SHAPE -- not the per-lap traffic noise."""
    n = len(age)
    sw = np.sqrt(w)
    forms: dict[str, dict] = {}
    for name, deg in (("linear", 1), ("quadratic", 2), ("cubic", 3)):
        if n < deg + 2:
            continue
        coefs = np.polyfit(age, y, deg, w=sw)
        pred = np.polyval(coefs, age)
        rss = float(np.sum(w * (y - pred) ** 2) / w.mean())
        forms[name] = {
            "coefs": [round(float(c), 6) for c in coefs[::-1]],  # ascending k0, k1, ...
            "rmse": round(float(np.sqrt(np.average((y - pred) ** 2, weights=w))), 4),
            "aic": round(_aic(n, rss, deg + 1), 1),
        }
    try:
        popt, _ = curve_fit(_log_model, age, y, p0=[0.0, 0.5, 0.3], sigma=1.0 / sw,
                            bounds=([-5, 0, 1e-3], [5, 20, 50]), maxfev=10000)
        pred = _log_model(age, *popt)
        rss = float(np.sum(w * (y - pred) ** 2) / w.mean())
        forms["log"] = {
            "coefs": [round(float(c), 6) for c in popt],  # k0, k1, k2
            "rmse": round(float(np.sqrt(np.average((y - pred) ** 2, weights=w))), 4),
            "aic": round(_aic(n, rss, 3), 1),
        }
    except Exception:
        pass
    return forms


def _eval(form: str, coefs: list[float], a: np.ndarray) -> np.ndarray:
    if form == "log":
        return _log_model(a, *coefs)
    return np.polyval(list(coefs)[::-1], a)  # coefs stored ascending -> polyval wants desc


def _loss_curve(form: str, coefs: list[float], max_age: float,
                ages=(5, 10, 15, 20, 25, 30)) -> dict:
    """Degradation loss (s) at each tyre age, RELATIVE TO A FRESH (age-1) tyre -- so it
    reads as pure age degradation, not the scatter/traffic floor in the intercept. Only
    ages WITHIN the fitted data range are emitted (no extrapolation past the stints a
    compound is actually run to -- softs run short, so their high-age curve is censored)."""
    fresh = float(_eval(form, coefs, np.array([1.0]))[0])
    keep = [x for x in ages if x <= max_age]
    y = _eval(form, coefs, np.array(keep, dtype=float)) - fresh
    return {str(int(x)): round(float(v), 3) for x, v in zip(keep, y)}


def fit_all(df: pl.DataFrame | None = None) -> dict:
    df = df if df is not None else pl.read_parquet(LAPS_PARQUET)
    df = df.filter(pl.col("regulation_era").is_in(MODERN_ERAS))
    res = _compound_residuals(df)
    out: dict = {"era": "ground_effect_2022plus", "compounds": {}}
    if res.height == 0:
        return out
    for comp in DRY_COMPOUNDS:
        sub = res.filter(pl.col("compound") == comp)
        if sub.height < MIN_LAPS:
            continue
        age = sub["tyre_life"].to_numpy().astype(float)
        y = sub["deg_residual"].to_numpy().astype(float)
        ba, bm, bw = _bin_medians(age, y)
        if len(ba) < 5:
            continue
        forms = _fit_forms(ba, bm, bw)
        if not forms:
            continue
        best = min(forms, key=lambda f: forms[f]["aic"])
        out["compounds"][comp] = {
            "n_laps": int(sub.height),
            "n_age_bins": int(len(ba)),
            "max_age_fitted": int(ba.max()),
            "best_form": best,
            "loss_at_age_s": _loss_curve(best, forms[best]["coefs"], float(ba.max())),
            "forms": forms,
        }
    return out


def run() -> Path:
    out = fit_all()
    OUT_JSON.write_text(json.dumps(out, indent=2))
    print(f"Per-compound tyre degradation (era {out['era']}):\n")
    for comp, d in out["compounds"].items():
        lc = d["loss_at_age_s"]
        print(f"  {comp:7s} n={d['n_laps']:5d}  maxAge={d['max_age_fitted']:2d}  "
              f"best={d['best_form']:9s}  loss@10={lc.get('10', '—')}s @20={lc.get('20', '—')}s "
              f"@max={lc.get(str(d['max_age_fitted']), list(lc.values())[-1] if lc else '—')}s")
        for f, v in d["forms"].items():
            mark = " *" if f == d["best_form"] else "  "
            print(f"      {f:9s} rmse={v['rmse']:.4f} aic={v['aic']:.0f}{mark}")
    print(f"\n  -> wrote {OUT_JSON}")
    return OUT_JSON


if __name__ == "__main__":
    run()
