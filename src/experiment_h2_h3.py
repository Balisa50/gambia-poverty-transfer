"""
H2 and H3: does stated uncertainty survive a border, and does adaptation fix it?

This is the paper. RQ1 is context and is largely answered already: point
accuracy transfers almost intact, 0.746 in-country against 0.723
leave-one-country-out, so H1 looks falsified. What no study in the benchmark
table reports is whether the intervals still mean what they claim.

The Gambia is not touched here
------------------------------
docs/03 section 2.3 allows the target exactly one look, after the full
specification is committed. Everything below runs on the eleven training
countries, using leave-one-country-out, which docs/03 section 2.2 already
designates as the honest estimate of cross-border performance. It gives eleven
independent country pairs instead of one, so the effect is estimated rather than
observed once.

The comparison, and why it is constructed this way
-------------------------------------------------
For each held-out country the same fitted model and the same calibration set
produce two coverage figures:

  in-country      calibrate on training countries, test on held-out spatial
                  blocks of those same training countries
  out-of-country  calibrate on training countries, test on the held-out country

Both use a calibration set drawn only from training countries, so the only thing
that changes between them is whether the test data comes from the same countries
as the calibration data. That isolates the exchangeability failure, which is the
one assumption conformal prediction needs.

Reading in-country coverage off a random split would inflate it, for the reason
the sanity gate exists: spatially adjacent clusters leak. In-country coverage is
therefore measured on held-out spatial blocks.

H3 and what counts as domain adaptation here
--------------------------------------------
CORAL, correlation alignment. It whitens the source features and recolours them
with the target covariance, matching first and second moments between domains.
It is deterministic, has no hyperparameters to tune on the target, and is a
standard baseline in this literature.

The protocol names MMD alignment and an adversarial variant. CORAL matches
second moments exactly and is the cheap deterministic member of that family;
the adversarial variant is deferred and its absence is recorded rather than
glossed. The prediction under test does not depend on which member is used:

    aligning feature distributions contains no mechanism that acts on interval
    width, so adaptation should improve the point estimate while leaving the
    uncertainty just as wrong.

If CORAL improves r-squared and leaves coverage where it was, that is the
predicted result. If it repairs coverage, H3 is wrong and that is the more
useful finding for practitioners.

Run:  python src/experiment_h2_h3.py
"""

from __future__ import annotations

import warnings
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

# Nominal levels, fixed in docs/03 section 5.
LEVELS = [0.50, 0.80, 0.90, 0.95]
HEADLINE = 0.90

CAL_FRACTION = 0.30   # share of training countries held out to calibrate
SEED = 42


def coral(Xs: np.ndarray, Xt: np.ndarray) -> np.ndarray:
    """Align source features to target second-order statistics.

    Whitens the source covariance and recolours it with the target's. Uses only
    the target's *features*, never its labels, which is what makes this
    unsupervised domain adaptation and legitimate here: at deployment the target
    country has imagery but no survey.
    """
    eps = 1e-6
    Cs = np.cov(Xs, rowvar=False) + eps * np.eye(Xs.shape[1])
    Ct = np.cov(Xt, rowvar=False) + eps * np.eye(Xt.shape[1])

    def root(M, inverse=False):
        w, V = np.linalg.eigh(M)
        w = np.clip(w, eps, None)
        p = -0.5 if inverse else 0.5
        return V @ np.diag(w ** p) @ V.T

    mu_s, mu_t = Xs.mean(0), Xt.mean(0)
    return (Xs - mu_s) @ root(Cs, inverse=True) @ root(Ct) + mu_t


def _gbm(**kw):
    return GradientBoostingRegressor(random_state=0, **kw)


def evaluate_country(df: pd.DataFrame, held_out: str, use_coral: bool
                     ) -> list[dict]:
    """One leave-one-country-out fold, in-country and out-of-country coverage."""
    rng = np.random.default_rng(SEED)

    src = df[df["country"] != held_out]
    tgt = df[df["country"] == held_out]

    Xs_all = src[FEATURES].to_numpy(float)
    ys_all = src["wealth"].to_numpy(float)
    Xt = tgt[FEATURES].to_numpy(float)
    yt = tgt["wealth"].to_numpy(float)

    if use_coral:
        # Target features only. No target labels are read anywhere in this call.
        Xs_all = coral(Xs_all, Xt)

    # Split the source countries into fit and calibration sets by spatial
    # block, not at random. Adjacent clusters share covariates, so a random
    # calibration split would make the calibration residuals optimistic and
    # the intervals too narrow before any border is crossed.
    blocks = assign_blocks(src["lon"].to_numpy(), src["lat"].to_numpy(), 110.0)
    folds = blocked_kfold(blocks, n_folds=10, seed=SEED)

    # Three disjoint sets of whole spatial blocks:
    #   folds 0-2  calibrate   (30%)
    #   folds 3-7  fit         (50%)
    #   folds 8-9  in-country test (20%)
    # The in-country test set is what out-of-country coverage is compared
    # against, so it must be untouched by both fitting and calibration.
    cal_mask = folds < 3
    fit_mask = (folds >= 3) & (folds < 8)
    in_mask = folds >= 8

    sc = SplitConformal(_gbm()).fit(Xs_all[fit_mask], ys_all[fit_mask])
    sc.calibrate(Xs_all[cal_mask], ys_all[cal_mask],
                 countries=src["country"].to_numpy()[cal_mask],
                 exclude=TARGET_COUNTRY)

    cq = ConformalizedQuantile(
        _gbm(loss="quantile", alpha=0.05), _gbm(loss="quantile", alpha=0.95)
    ).fit(Xs_all[fit_mask], ys_all[fit_mask])
    cq.calibrate(Xs_all[cal_mask], ys_all[cal_mask],
                 countries=src["country"].to_numpy()[cal_mask],
                 exclude=TARGET_COUNTRY)

    r2_in = r2_score(ys_all[in_mask], sc.model.predict(Xs_all[in_mask]))
    r2_out = r2_score(yt, sc.model.predict(Xt))

    rows = []
    for name, cp in (("split", sc), ("cqr", cq)):
        for lvl in LEVELS:
            a = 1 - lvl
            lo_i, hi_i = cp.predict_interval(Xs_all[in_mask], alpha=a)
            lo_o, hi_o = cp.predict_interval(Xt, alpha=a)
            rows.append({
                "held_out": held_out, "method": name, "coral": use_coral,
                "nominal": lvl,
                "cov_in": coverage(ys_all[in_mask], lo_i, hi_i),
                "cov_out": coverage(yt, lo_o, hi_o),
                "width_in": mean_width(lo_i, hi_i),
                "width_out": mean_width(lo_o, hi_o),
                "is_in": interval_score(ys_all[in_mask], lo_i, hi_i, a),
                "is_out": interval_score(yt, lo_o, hi_o, a),
                "r2_in": r2_in, "r2_out": r2_out, "n_out": len(yt),
            })
    return rows


def main() -> None:
    df = pd.read_csv(PROC / "modelling_table.csv")
    train = df[df["country"] != TARGET_COUNTRY].dropna(
        subset=FEATURES + ["wealth", "lon", "lat"]).reset_index(drop=True)
    countries = sorted(train["country"].unique())

    print(f"{len(train)} clusters, {len(countries)} training countries. "
          f"{TARGET_COUNTRY} excluded and never loaded here.\n")

    rows = []
    for use_coral in (False, True):
        tag = "CORAL" if use_coral else "baseline"
        for cc in countries:
            print(f"  {tag:<9} hold out {cc}", end="\r")
            rows.extend(evaluate_country(train, cc, use_coral))
    res = pd.DataFrame(rows)
    res.to_csv(PROC / "h2_h3_results.csv", index=False)
    print(" " * 40, end="\r")

    # ------------------------------------------------------------------ H2
    print("=" * 72)
    print("H2: does a nominal interval keep its coverage across a border?")
    print("=" * 72)
    base = res[~res["coral"]]
    for method in ("split", "cqr"):
        m = base[base["method"] == method]
        print(f"\n  {method}")
        print(f"    {'nominal':>8}{'cov in':>9}{'cov out':>9}{'shortfall':>11}"
              f"{'width in':>10}{'width out':>11}")
        for lvl in LEVELS:
            s = m[m["nominal"] == lvl]
            ci, co = s["cov_in"].mean(), s["cov_out"].mean()
            print(f"    {lvl:>8.2f}{ci:>9.3f}{co:>9.3f}{ci - co:>11.3f}"
                  f"{s['width_in'].mean():>10.3f}{s['width_out'].mean():>11.3f}")

    print(f"\n  Per country at nominal {HEADLINE:.0%}, split conformal:")
    h = base[(base["method"] == "split") & (base["nominal"] == HEADLINE)]
    print(h[["held_out", "n_out", "cov_in", "cov_out", "width_out", "r2_out"]]
          .round(3).to_string(index=False))

    # ------------------------------------------------------------------ H3
    print("\n" + "=" * 72)
    print("H3: does domain adaptation repair calibration, or only accuracy?")
    print("=" * 72)
    print(f"\n  {'method':<7}{'nominal':>8}{'cov out base':>14}"
          f"{'cov out CORAL':>15}{'r2 out base':>13}{'r2 out CORAL':>14}")
    for method in ("split", "cqr"):
        for lvl in LEVELS:
            b = res[(~res["coral"]) & (res["method"] == method) &
                    (res["nominal"] == lvl)]
            c = res[(res["coral"]) & (res["method"] == method) &
                    (res["nominal"] == lvl)]
            print(f"  {method:<7}{lvl:>8.2f}{b['cov_out'].mean():>14.3f}"
                  f"{c['cov_out'].mean():>15.3f}{b['r2_out'].mean():>13.3f}"
                  f"{c['r2_out'].mean():>14.3f}")

    print(f"\nWrote {PROC / 'h2_h3_results.csv'}")


if __name__ == "__main__":
    main()
