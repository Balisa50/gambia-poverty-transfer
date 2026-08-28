"""
The one Gambian evaluation. Pre-registered in docs/06-preregistration-h4.md.

This script is the specification. It is committed together with that document
before any Gambian wealth label is read, and its commit hash goes in the paper.
Changing it after that commit requires a dated amendment saying what changed and
why, exactly as with the gate band in docs/04.

It runs once.

What it tests
-------------
H4: out-of-country conformal coverage is unreliable for an individual country.
For The Gambia, a nominal 90% interval built and calibrated entirely on the
eleven training countries covers a fraction of Gambian clusters differing from
0.90 by more than sampling variation alone explains.

Confirmatory if coverage falls outside [0.865, 0.935], the two-sided 95%
binomial interval at n=280 under exactly nominal coverage. Disconfirmatory if
inside. No direction is predicted: unreliability is the claim, and a value
above the band confirms H4 exactly as one below does.

Power is 0.529 against a false positive rate of 0.050. A disconfirmatory result
is therefore weak evidence and must be reported as "not confirmed at 53% power",
never as evidence that coverage is reliable.

What it must not do
-------------------
The Gambia contributes nothing to fitting or calibration. `exclude=TARGET`
is passed to both conformal calibrators, which raise rather than proceed if a
target cluster reaches the calibration set. Calibrating on the target would
restore coverage by construction and destroy the experiment.

Run:  python src/evaluate_gambia.py --i-have-read-the-preregistration
"""

from __future__ import annotations

import argparse
import json
import subprocess
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score

from conformal import (ConformalizedQuantile, SplitConformal, coverage,
                       interval_score, mean_width)
from run_gate import FEATURES, TARGET_COUNTRY
from splits import assign_blocks, blocked_kfold

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
OUT = PROC / "gambia_evaluation.json"

# Frozen in docs/06. None of these may be tuned.
LEVELS = [0.50, 0.80, 0.90, 0.95]
HEADLINE = 0.90
BLOCK_KM = 110.0
N_FOLDS = 10
CAL_FOLDS = 3          # folds 0-2 calibrate, 3-9 fit
SEED = 42

# Two-sided 95% binomial intervals at n=280 under exactly nominal coverage.
# Computed before the label was read; n comes from the GPS file.
N_GAMBIA_EXPECTED = 280
THRESHOLDS = {0.80: (0.753, 0.847),
              0.90: (0.865, 0.935),
              0.95: (0.924, 0.976)}

POWER = 0.529
FALSE_POSITIVE = 0.050


def _gbm(**kw):
    return GradientBoostingRegressor(random_state=0, **kw)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--i-have-read-the-preregistration", action="store_true",
                    help="required; this evaluation is intended to run once")
    args = ap.parse_args()
    if not getattr(args, "i_have_read_the_preregistration"):
        raise SystemExit(
            "Refusing to run.\n\n"
            "This is the single pre-registered evaluation of the target "
            "country. Read docs/06-preregistration-h4.md first, then pass\n"
            "  --i-have-read-the-preregistration\n\n"
            "The threshold, the power and what counts as confirmation are all "
            "fixed in that document. Running this after deciding what you want "
            "it to show is the one thing the design cannot survive.")

    if OUT.exists():
        print(f"WARNING: {OUT.name} already exists. This evaluation was "
              "intended to run once. The previous result is below, and this "
              "re-run will be recorded.\n")
        print(json.dumps(json.loads(OUT.read_text())["primary"], indent=2))
        print()

    df = pd.read_csv(PROC / "modelling_table.csv")
    full = df.dropna(subset=FEATURES + ["wealth", "lon", "lat"])
    src = full[full["country"] != TARGET_COUNTRY].reset_index(drop=True)
    tgt = full[full["country"] == TARGET_COUNTRY].reset_index(drop=True)

    print(f"training: {len(src)} clusters, {src['country'].nunique()} countries")
    print(f"target:   {len(tgt)} Gambian clusters "
          f"(pre-registration assumed {N_GAMBIA_EXPECTED})")
    if len(tgt) != N_GAMBIA_EXPECTED:
        print(f"  NOTE: n differs from the pre-registered {N_GAMBIA_EXPECTED}. "
              "The thresholds were computed at that n and are NOT recomputed "
              "here; the discrepancy is reported instead.")

    Xs = src[FEATURES].to_numpy(float)
    ys = src["wealth"].to_numpy(float)
    Xt = tgt[FEATURES].to_numpy(float)
    yt = tgt["wealth"].to_numpy(float)
    cs = src["country"].to_numpy()

    folds = blocked_kfold(
        assign_blocks(src["lon"].to_numpy(), src["lat"].to_numpy(), BLOCK_KM),
        n_folds=N_FOLDS, seed=SEED)
    cal = folds < CAL_FOLDS
    fit = ~cal
    print(f"fit {int(fit.sum())} clusters, calibrate {int(cal.sum())}, "
          f"spatial blocks at {BLOCK_KM:.0f} km\n")

    sc = SplitConformal(_gbm()).fit(Xs[fit], ys[fit])
    sc.calibrate(Xs[cal], ys[cal], countries=cs[cal], exclude=TARGET_COUNTRY)

    cq = ConformalizedQuantile(_gbm(loss="quantile", alpha=0.05),
                               _gbm(loss="quantile", alpha=0.95))
    cq.fit(Xs[fit], ys[fit])
    cq.calibrate(Xs[cal], ys[cal], countries=cs[cal], exclude=TARGET_COUNTRY)

    r2 = float(r2_score(yt, sc.model.predict(Xt)))

    rows = []
    for name, cp in (("split", sc), ("cqr", cq)):
        for lvl in LEVELS:
            a = 1 - lvl
            lo, hi = cp.predict_interval(Xt, alpha=a)
            cov = coverage(yt, lo, hi)
            band = THRESHOLDS.get(lvl)
            rows.append({
                "method": name, "nominal": lvl, "coverage": round(cov, 4),
                "width": round(mean_width(lo, hi), 4),
                "interval_score": round(interval_score(yt, lo, hi, a), 4),
                "band_lo": band[0] if band else None,
                "band_hi": band[1] if band else None,
                "outside_band": (None if not band
                                 else bool(cov < band[0] or cov > band[1])),
            })
    res = pd.DataFrame(rows)

    print("=" * 70)
    print("GAMBIA, pre-registered evaluation")
    print("=" * 70)
    print(res.to_string(index=False))

    prim = res[(res["method"] == "split") & (res["nominal"] == HEADLINE)].iloc[0]
    cov = float(prim["coverage"])
    lo_b, hi_b = THRESHOLDS[HEADLINE]
    confirmed = bool(cov < lo_b or cov > hi_b)

    print("\n" + "=" * 70)
    print(f"PRIMARY TEST (H4): split conformal, nominal {HEADLINE:.0%}")
    print("=" * 70)
    print(f"  coverage                 {cov:.3f}")
    print(f"  pre-registered band      [{lo_b}, {hi_b}]")
    print(f"  r-squared on Gambia      {r2:.3f}  (context, not a test)")
    print(f"\n  H4 {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    if confirmed:
        print(f"  Coverage falls outside the band. Under exactly nominal "
              f"coverage this happens with probability {FALSE_POSITIVE:.3f}.")
    else:
        print(f"  Coverage falls inside the band. This test has power "
              f"{POWER:.3f}, so it misses a true effect roughly half the time. "
              "Report as 'not confirmed at 53% power', NOT as evidence that "
              "coverage is reliable.")

    # Descriptive only, fixed in docs/06 as not a test.
    hist = PROC / "h2_h3_results.csv"
    if hist.exists():
        h = pd.read_csv(hist)
        h = h[(~h["coral"]) & (h["method"] == "split") &
              (h["nominal"] == HEADLINE)]["cov_out"].values
        below = int((h < cov).sum())
        print(f"\n  Descriptive: Gambia sits at rank {below + 1} of "
              f"{len(h) + 1} against the eleven training countries "
              f"(range {h.min():.3f} to {h.max():.3f}).")

    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip()
    except Exception:
        commit = "unknown"

    OUT.write_text(json.dumps({
        "date": str(date.today()),
        "commit_at_run": commit,
        "n_gambia": int(len(tgt)),
        "n_gambia_preregistered": N_GAMBIA_EXPECTED,
        "primary": {"method": "split", "nominal": HEADLINE, "coverage": cov,
                    "band": [lo_b, hi_b], "h4_confirmed": confirmed,
                    "power": POWER, "false_positive": FALSE_POSITIVE},
        "r2_gambia": r2,
        "all": rows,
    }, indent=2))
    print(f"\nWrote {OUT.name}")


if __name__ == "__main__":
    main()
