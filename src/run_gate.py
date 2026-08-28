"""
Run the pre-registered sanity gate on the training countries.

The Gambia is excluded here and everywhere before the final evaluation
(docs/03 section 2.3). Running the gate on the target would spend the one look
this design allows on a diagnostic.

Features are satellite-derived only
-----------------------------------
`urban`, `radius_m` and `buffer_km2` are excluded even though they sit in the
table. They come from the DHS GPS file, not from imagery, and the last two
encode the first exactly, since the buffer radius is chosen by urban or rural
status. A model given them is partly reading the survey's own classification of
the place rather than the satellite record of it, and the paper is about what
can be predicted from imagery where no survey exists.

Pixel counts (`*_count`) are excluded for the same reason in reverse: they are a
property of the buffer geometry, not of the place.

Run:  python src/run_gate.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score

from sanity_gate import HIGH_REQUIRES_DIAGNOSTICS, evaluate, report, run
from splits import assign_blocks, blocked_kfold, leave_one_country_out

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"

TARGET_COUNTRY = "GM"

FEATURES = [
    "nightlights_mean", "nightlights_stdDev",
    "nightlights_masked_mean",
    "population_mean", "population_stdDev",
    "builtup_mean", "builtup_nres_mean",
    "landcover_mode",
    "rainfall_mean",
    "water_fraction_mean",
    "elevation_mean", "elevation_stdDev",
]


# Thresholds for the three mandatory diagnostics, from the docs/04 amendment.
MAX_SENSITIVITY_DROP = 0.10   # across a four-fold or larger block-size range
MAX_LOCO_SHORTFALL = 0.10     # blocked r2 minus leave-one-country-out r2


def _blocked_r2(df, features, block_km, n_folds=5) -> float:
    X, y = df[features].to_numpy(float), df["wealth"].to_numpy(float)
    folds = blocked_kfold(
        assign_blocks(df["lon"].to_numpy(), df["lat"].to_numpy(), block_km),
        n_folds=n_folds)
    scores = []
    for f in range(n_folds):
        te, tr = folds == f, folds != f
        if te.sum() < 10 or tr.sum() < 50:
            continue
        m = GradientBoostingRegressor(random_state=0).fit(X[tr], y[tr])
        scores.append(r2_score(y[te], m.predict(X[te])))
    return float(np.mean(scores))


def leakage_diagnostics(df, features, block_km: float = 110.0) -> bool:
    """Run the three checks docs/04 requires for any result above 0.70.

    Returns whether all three pass. This is computed, never asserted: the gate
    takes the result of this function, so the high band cannot be cleared by
    setting a flag.
    """
    X, y = df[features].to_numpy(float), df["wealth"].to_numpy(float)

    print("\n--- mandatory leakage diagnostics (docs/04 amendment) ---")

    print("\n1. Block-size sensitivity. Leakage falls away as blocks grow.")
    sizes = [block_km, block_km * 2, block_km * 4, block_km * 6]
    r2s = []
    for bkm in sizes:
        r = _blocked_r2(df, features, bkm)
        r2s.append(r)
        n_blocks = len(np.unique(assign_blocks(df["lon"].to_numpy(),
                                               df["lat"].to_numpy(), bkm)))
        print(f"     {bkm:>6.0f} km  {n_blocks:>4} blocks   r2 = {r:.3f}")
    drop = max(r2s) - min(r2s)
    ok_sens = drop <= MAX_SENSITIVITY_DROP
    print(f"     range {min(sizes):.0f}-{max(sizes):.0f} km, drop {drop:.3f} "
          f"(limit {MAX_SENSITIVITY_DROP}) -> {'pass' if ok_sens else 'FAIL'}")

    print("\n2. Leave-one-country-out. No test cluster has any training "
          "neighbour.")
    loco = []
    for sp in leave_one_country_out(df["country"].to_numpy()):
        m = GradientBoostingRegressor(random_state=0).fit(X[sp.train], y[sp.train])
        v = r2_score(y[sp.test], m.predict(X[sp.test]))
        loco.append(v)
        print(f"     hold out {sp.name}: n={int(sp.test.sum()):<5} r2 = {v:.3f}")
    loco_mean = float(np.mean(loco))
    blocked = _blocked_r2(df, features, block_km)
    shortfall = blocked - loco_mean
    ok_loco = shortfall <= MAX_LOCO_SHORTFALL
    print(f"     mean LOCO r2 = {loco_mean:.3f} vs blocked {blocked:.3f}, "
          f"shortfall {shortfall:.3f} (limit {MAX_LOCO_SHORTFALL}) -> "
          f"{'pass' if ok_loco else 'FAIL'}")

    print("\n3. No block split across folds.")
    blocks = assign_blocks(df["lon"].to_numpy(), df["lat"].to_numpy(), block_km)
    folds = blocked_kfold(blocks, n_folds=5)
    split = sum(1 for b in np.unique(blocks)
                if len(np.unique(folds[blocks == b])) > 1)
    ok_split = split == 0
    print(f"     {split} of {len(np.unique(blocks))} blocks split -> "
          f"{'pass' if ok_split else 'FAIL'}")

    allok = ok_sens and ok_loco and ok_split
    print(f"\n   diagnostics: {'ALL PASS' if allok else 'NOT ALL PASSED'}")
    return allok


def main() -> None:
    df = pd.read_csv(PROC / "modelling_table.csv")
    missing = [c for c in FEATURES if c not in df.columns]
    if missing:
        raise SystemExit(f"modelling_table.csv is missing: {missing}")

    train = df[df["country"] != TARGET_COUNTRY].copy()
    print(f"{len(df)} clusters total, {len(train)} after excluding "
          f"{TARGET_COUNTRY} (the target, held for the final evaluation)\n")

    # Feature nulls have to be visible before any fit. A covariate null for one
    # country and not others is a distribution shift we introduced.
    nulls = train[FEATURES].isna().sum()
    if nulls.any():
        print("Nulls per feature:")
        print(nulls[nulls > 0].to_string(), "\n")
        by_country = (train.groupby("country")[FEATURES]
                      .apply(lambda g: g.isna().any(axis=1).mean()))
        print("Share of clusters with any null feature, by country:")
        print(by_country[by_country > 0].round(3).to_string(), "\n")

    fitted = train.dropna(subset=FEATURES + ["wealth", "lon", "lat"])
    print(f"{len(fitted)} clusters usable after dropping nulls "
          f"({len(train) - len(fitted)} lost)\n")

    print("=" * 66)
    print("POOLED across the 11 training countries")
    print("=" * 66)
    provisional = run(fitted, FEATURES, target_col="wealth")

    # Above 0.70 the band is not cleared by the number alone, so the
    # diagnostics are run and their actual result is fed back in.
    diag = False
    if provisional.r2_blocked > HIGH_REQUIRES_DIAGNOSTICS:
        diag = leakage_diagnostics(fitted, FEATURES)
        res = evaluate(provisional.r2_blocked, provisional.r2_naive,
                       provisional.n, diagnostics_passed=diag)
    else:
        res = provisional
    report(res)

    print("\n" + "=" * 66)
    print("PER COUNTRY")
    print("=" * 66)
    rows = []
    for cc, g in fitted.groupby("country"):
        if len(g) < 150:
            print(f"{cc}: {len(g)} clusters, too few for blocked folds, skipped")
            continue
        r = run(g, FEATURES, target_col="wealth")
        # Leave-one-country-out is undefined inside a single country, so the
        # diagnostics that clear the 0.70-0.85 band cannot be run per country.
        # A country above 0.70 is reported as HIGH rather than PASS or FAIL:
        # calling it FAIL would imply a leakage finding the per-country design
        # cannot support, and calling it PASS would claim a check that was not
        # done. The gate verdict is the pooled one.
        v = r.verdict
        if r.r2_blocked > HIGH_REQUIRES_DIAGNOSTICS:
            v = "HIGH*"
        rows.append({"cc": cc, "n": r.n, "r2_blocked": round(r.r2_blocked, 3),
                     "r2_naive": round(r.r2_naive, 3),
                     "leakage": round(r.leakage, 3), "verdict": v})
    out = pd.DataFrame(rows)
    print()
    print(out.to_string(index=False))
    print("\n  * above 0.70. Leave-one-country-out is undefined within one "
          "country, so the diagnostics that clear that band are pooled-only.")

    n_pass = int((out["verdict"] == "PASS").sum())
    n_high = int((out["verdict"] == "HIGH*").sum())
    print(f"\n{n_pass}/{len(out)} countries PASS outright, {n_high} above 0.70.")
    print(f"\nGATE VERDICT (pooled, the one that governs): {res.verdict}")
    if res.verdict == "PASS" and diag:
        print("  Cleared the 0.70-0.85 band by running the diagnostics, not by "
              "the number alone.")


if __name__ == "__main__":
    main()
